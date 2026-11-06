#!/usr/bin/env python
"""Run the FEFF module chain for a set of site directories that already contain feff.inp.

Scheduler-agnostic: this is a plain CLI. Run it directly, wrap it in a loop, or hand a subset of
sites to it from any batch system (shard the manifest you give it).

Features that matter in practice:
  * per-module timeout (a wedged module must not hold a worker for hours);
  * automatic one-shot fallback: if `COREHOLE RPA` fails, re-run the same site without the
    `COREHOLE` card (final-state rule, no `screen` module) in a sibling directory;
  * `run.json` per site with return codes, wall times and which core-hole model produced the data;
  * optional pruning of the ~7 MB of intermediates, keeping feff.inp + xmu.dat.

Usage:
  python run_sites.py --manifest out/manifest.json --feff-bin /path/to/feff/bin/Seq \
      --workers 4 --timeout 120 --fallback
"""
import argparse
import json
import os
import shutil
import subprocess
import time
from multiprocessing import Pool
from pathlib import Path

BASE_MODULES = ["rdinp", "atomic", "pot", "xsph", "fms", "mkgtr", "path", "genfmt", "ff2x"]
KEEP = {"feff.inp", "xmu.dat", "run.json"}


def corehole_of(text):
    for line in text.splitlines():
        s = line.strip()
        if s.upper().startswith("COREHOLE"):
            return s.split()[1].upper() if len(s.split()) > 1 else "FSR"
    return "FSR"


def modules_for(corehole):
    """Module order; `screen` is required only for the RPA-screened core hole."""
    mods = ["rdinp", "atomic", "pot"]
    if corehole == "RPA":
        mods.append("screen")
    return mods + ["xsph", "fms", "mkgtr", "path", "genfmt", "ff2x"]


def run_chain(site_dir, feff_bin, timeout):
    """Run every module in order inside site_dir; return a report dict."""
    text = (site_dir / "feff.inp").read_text()
    corehole = corehole_of(text)
    mods = ["rdinp", "atomic", "pot"] + (["screen"] if corehole == "RPA" else []) + \
           ["xsph", "fms", "mkgtr", "path", "genfmt", "ff2x"]
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    report = dict(dir=str(site_dir), corehole=corehole, modules=[], success=False, error=None)
    t_site = time.monotonic()
    for m in mods:
        exe = Path(feff_bin) / m
        if not exe.exists():
            report["error"] = f"missing executable: {exe}"
            break
        t0 = time.monotonic()
        try:
            with open(site_dir / f"{m}.out", "w") as o, open(site_dir / f"{m}.err", "w") as e:
                rc = subprocess.call([str(exe)], cwd=site_dir, stdout=o, stderr=e,
                                     env=env, timeout=timeout)
        except subprocess.TimeoutExpired:
            report["modules"].append(dict(module=m, rc=None, seconds=round(time.monotonic() - t0, 2),
                                          error="timeout"))
            report["error"] = f"{m}: timeout after {timeout}s"
            break
        report["modules"].append(dict(module=m, rc=rc, seconds=round(time.monotonic() - t0, 2)))
        if rc != 0:
            report["error"] = f"{m}: rc={rc}"
            break
    report["site_seconds"] = round(time.monotonic() - t_site, 2)
    if report["error"] is None:
        xmu = site_dir / "xmu.dat"
        if not xmu.exists():
            report["error"] = "no xmu.dat"
        else:
            lines = [ln for ln in xmu.read_text().splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#")]
            if len(lines) < 10:                      # header-only file (e.g. ff2x polint failure)
                report["error"] = f"xmu.dat has no data rows ({len(lines)} lines)"
            else:
                report["success"] = True
    return report


def fallback_copy(site_dir):
    """Sibling dir with the COREHOLE card removed (=> final-state rule, no screen module)."""
    alt = site_dir.with_name(site_dir.name + "_fsr")
    shutil.rmtree(alt, ignore_errors=True)
    alt.mkdir(parents=True)
    text = "\n".join(ln for ln in (site_dir / "feff.inp").read_text().splitlines()
                     if not ln.strip().upper().startswith("COREHOLE"))
    (alt / "feff.inp").write_text(text + "\n")
    return alt


def prune(site_dir):
    for p in site_dir.iterdir():
        if p.is_file() and p.name not in KEEP and not p.name.endswith(".err"):
            p.unlink()


def do_site(args):
    site_dir, feff_bin, timeout, fallback, do_prune = args
    site_dir = Path(site_dir)
    if (site_dir / "run.json").exists():                    # resumable
        rep = json.loads((site_dir / "run.json").read_text())
        if rep.get("success"):
            return rep
    rep = run_chain(site_dir, feff_bin, timeout)
    if not rep["success"] and fallback and rep["corehole"] == "RPA":
        alt = fallback_copy(site_dir)
        rep2 = run_chain(alt, feff_bin, timeout)
        rep2["fallback_from"] = "RPA"
        if rep2["success"]:
            rep = rep2
            rep["dir"] = str(alt)
        else:
            rep["fallback_error"] = rep2["error"]
    (Path(rep["dir"]) / "run.json").write_text(json.dumps(rep, indent=2))
    if rep["success"] and do_prune:
        prune(Path(rep["dir"]))
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="manifest.json produced by make_input.py")
    ap.add_argument("--feff-bin", required=True, help="directory holding rdinp, atomic, ... (e.g. .../bin/Seq)")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=120.0, help="seconds per module")
    ap.add_argument("--fallback", action="store_true", help="retry failed RPA sites with FSR")
    ap.add_argument("--prune", action="store_true", help="delete intermediates after success")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    sites = [s["dir"] for s in json.loads(Path(args.manifest).read_text())["sites"]]
    if args.limit:
        sites = sites[: args.limit]
    todo = [(s, args.feff_bin, args.timeout, args.fallback, args.prune) for s in sites]
    print(f"[i] {len(todo)} sites, workers={args.workers}, timeout={args.timeout}s")
    t0 = time.monotonic()
    if args.workers > 1:
        with Pool(args.workers) as p:
            reports = p.map(do_site, todo)
    else:
        reports = [do_site(t) for t in todo]
    ok = sum(1 for r in reports if r["success"])
    fb = sum(1 for r in reports if r.get("fallback_from"))
    print(f"[i] success {ok}/{len(reports)}  (FSR fallback {fb})  wall={time.monotonic()-t0:.0f}s")
    for r in reports:
        if not r["success"]:
            print(f"    FAIL {r['dir']}: {r['error']}")


if __name__ == "__main__":
    main()
