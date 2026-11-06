#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Extract windowed spectra from FEFF site directories and aggregate them.

Input: a *dataset manifest* describing structures, their frames and their sites, e.g.

  {
    "frames": 10,
    "energy_windows": {"C": [275.0, 0.2, 200], "N": [397.0, 0.2, 200], "O": [528.0, 0.2, 200]},
    "structures": [
      {"id": "s1", "elements": ["C","C","O","H"],
       "sites": [{"frame": 0, "atom": 0, "element": "C", "dir": "out/s1/f00_a000_C"}, ...]}
    ]
  }

Output:
  * <site>/spectrum.csv                          (energy_eV, mu) per absorbed atom
  * <out>.h5 :
        /energies/<El>          (npoints,)       absolute energy axis of that edge
        /structures/<id>/
            elements            (n_atoms,)
            atomic_numbers      (n_atoms,)
            spectra             (frames, n_atoms, npoints)  float32, NaN where absent/failed
            site_ok             (frames, n_atoms) bool      True iff a spectrum was obtained
            element_sum         (frames, n_edges, npoints)  sum over VALID sites of that element;
                                                            all-invalid frame -> 0
            element_counts      (n_edges,)                  atoms of that element in the record

Combination rules are physics, not preference: same element adds (independent absorbers, absolute
cross-sections stay on the same per-atom scale); different elements never add (different energy
ranges) — concatenate them instead. Failed sites are excluded through `site_ok`; a per-atom average
is `element_sum / site_ok.sum(axis=1)` computed downstream.
"""
import argparse
import json
from pathlib import Path

import h5py
import numpy as np

DEFAULT_WINDOWS = {"C": (275.0, 0.2, 200), "N": (397.0, 0.2, 200), "O": (528.0, 0.2, 200)}
Z = {"H": 1, "C": 6, "N": 7, "O": 8, "F": 9, "S": 16, "P": 15}


def read_xmu(site_dir, start, step, npts):
    """xmu.dat -> mu on the requested window. Returns None when the file is unusable.

    Column 4 is mu. Points below the first energy FEFF actually computed are marked NaN
    (not zero!) so that a model cannot learn a fake leading edge.
    """
    p = Path(site_dir) / "xmu.dat"
    try:
        t = np.loadtxt(p)
    except Exception:
        return None
    if t.ndim != 2 or t.shape[0] < 10 or t.shape[1] < 4:
        return None
    e = start + step * np.arange(npts)
    mu = np.interp(e, t[:, 0], t[:, 3], left=0.0)
    below = e < t[0, 0]
    if below.any():
        mu[below] = np.nan
    return None if not np.isfinite(mu).any() else mu


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="dataset manifest JSON")
    ap.add_argument("--out", required=True, help="output HDF5 path")
    args = ap.parse_args()

    spec = json.loads(Path(args.dataset).read_text())
    windows = {k: tuple(v) for k, v in spec.get("energy_windows", DEFAULT_WINDOWS).items()}
    edges = [e for e in ("C", "N", "O") if e in windows]
    nframes = int(spec.get("frames", 1))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(out_path, "w", libver="latest") as out:
        for e in edges:
            start, step, npts = windows[e]
            out.create_dataset(f"energies/{e}", data=start + step * np.arange(npts))
        G = out.create_group("structures")

        n_ok = n_bad_sites = 0
        for st in spec["structures"]:
            els = st["elements"]
            n_atoms = len(els)
            npts = {e: windows[e][2] for e in edges}
            spectra = {e: np.full((nframes, n_atoms, npts[e]), np.nan, dtype=np.float32) for e in edges}
            mask = np.zeros((nframes, n_atoms), dtype=bool)

            for s in st["sites"]:
                e, fr, ai = s["element"], int(s["frame"]), int(s["atom"])
                if e not in windows:
                    continue
                start, step, np_ = windows[e]
                mu = read_xmu(s["dir"], start, step, np_)
                if mu is None:
                    n_bad_sites += 1
                    continue
                spectra[e][fr, ai, :] = mu
                mask[fr, ai] = True
                n_ok += 1
                np.savetxt(Path(s["dir"]) / "spectrum.csv",
                           np.column_stack([start + step * np.arange(np_), mu]), delimiter=",",
                           header="energy_eV,mu", comments="", fmt=["%.1f", "%.6e"])

            g = G.create_group(st["id"])
            g.create_dataset("elements", data=np.array(els, dtype=h5py.string_dtype("utf-8")))
            g.create_dataset("atomic_numbers", data=np.array([Z.get(x, 0) for x in els], dtype="i4"))
            g.create_dataset("site_ok", data=mask)
            # store one spectra block per edge, stacked along a trailing "edge" axis for clarity
            npts_max = max(npts.values())
            block = np.full((nframes, n_atoms, len(edges), npts_max), np.nan, dtype=np.float32)
            for j, e in enumerate(edges):
                block[:, :, j, : npts[e]] = spectra[e]
            g.create_dataset("spectra_by_edge", data=block)
            g.create_dataset("edges", data=np.array(edges, dtype=h5py.string_dtype("utf-8")))

            es = np.full((nframes, len(edges), npts_max), np.nan, dtype=np.float32)
            counts = np.zeros(len(edges), dtype="i4")
            for j, e in enumerate(edges):
                idxs = [i for i, x in enumerate(els) if x == e]
                counts[j] = len(idxs)
                if not idxs:
                    continue
                # sum over VALID sites only; a frame with no valid site for this element becomes 0
                vals = np.where(mask[:, idxs][:, :, None], spectra[e][:, idxs, :].astype(np.float64), np.nan)
                es[:, j, : npts[e]] = np.nansum(vals, axis=1).astype(np.float32)
            g.create_dataset("element_sum", data=es)
            g.create_dataset("element_counts", data=counts)

        out.attrs["n_structures"] = len(spec["structures"])
        out.attrs["frames"] = nframes
        out.attrs["edges"] = json.dumps(edges)
        out.attrs["windows"] = json.dumps({e: windows[e] for e in edges})
        out.attrs["units"] = "mu = absolute cross-section (A^2 per absorbing atom) when the FEFF " \
                             "header normalisation factor is 1.0 (ABSOLUTE card)"
        out.attrs["sum_rule"] = "element_sum = sum over valid sites of that element; " \
                                "no valid site in a frame -> 0; never sum across edges"
    print(f"[i] structures={len(spec['structures'])} sites_ok={n_ok} sites_failed={n_bad_sites} -> {out_path}")


if __name__ == "__main__":
    main()
