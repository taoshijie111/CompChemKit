#!/usr/bin/env python
"""Build one feff.inp per absorbing atom from a plain structure spec.

Input (JSON, one object or a list of objects):
  {"id": "mol1", "elements": ["C","C","O","H"], "coordinates_angstrom": [[x,y,z], ...]}

Output: <out-root>/<id>/f<frame>_a<atom>_<El>/feff.inp  plus manifest.json describing every site.

All card values are *recommended defaults* (see references/parameters.md) and can be overridden.
Nothing here assumes a scheduler or a particular directory layout beyond --out-root.
"""
import argparse
import json
from pathlib import Path

Z = {"H": 1, "He": 2, "Li": 3, "Be": 4, "B": 5, "C": 6, "N": 7, "O": 8, "F": 9, "Ne": 10,
     "Na": 11, "Mg": 12, "Al": 13, "Si": 14, "P": 15, "S": 16, "Cl": 17, "Ar": 18}

EDGES = {"C": "K", "N": "K", "O": "K", "S": "K", "P": "K", "F": "K",
         "Fe": "K", "Mn": "K", "Cu": "K", "Zn": "K"}

# recommended windows: element -> (start_eV, step_eV, npoints)
WINDOWS = {"C": (275.0, 0.2, 200), "N": (397.0, 0.2, 200), "O": (528.0, 0.2, 200),
           "S": (2460.0, 0.5, 200), "P": (2140.0, 0.5, 200)}


def cluster_radius(xyz, idx, r_inner=10.0, r_outer=15.0):
    """Recommended rule: 10 A if the whole system fits, else 15 A, else refuse."""
    d = max(sum((a - b) ** 2 for a, b in zip(p, xyz[idx])) ** 0.5 for p in xyz)
    if d >= r_outer:
        raise ValueError(f"atom {idx}: extent {d:.2f} A >= {r_outer} A; choose a radius explicitly")
    return (r_inner if d < r_inner else r_outer), d


def render(elements, xyz, idx, radius=None, corehole="RPA", edge=None, s2=1.0,
           xanes=(4.0, 0.04, 0.1), rpath=0.1, scf=(1, 30, 0.2, 1)):
    el = elements[idx]
    edge = edge or EDGES.get(el, "K")
    if radius is None:
        r, extent = cluster_radius(xyz, idx)
    else:
        r, extent = float(radius), None

    order = [idx] + [i for i in range(len(elements)) if i != idx]
    others = list(dict.fromkeys(elements[i] for i in order[1:]))
    pot = {e: i + 1 for i, e in enumerate(others)}

    lines = [f"TITLE {el} {edge} edge, absorber atom {idx}",
             f"EDGE {edge} {s2}",
             "CONTROL 1 1 1 1 1 1",
             "PRINT 1 0 0 0 0 0"]
    if corehole and corehole.lower() != "fsr":
        lines.append(f"COREHOLE {corehole}")
    lines += ["EXCHANGE 0 0.0 0.000000",
              f"SCF {r:.1f} {scf[0]} {scf[1]} {scf[2]:.6f} {scf[3]}",
              "ABSOLUTE",
              f"FMS {r:.1f} 0",
              f"RPATH {rpath}",
              f"XANES {xanes[0]:.6f} {xanes[1]} {xanes[2]:.6f}",
              "POTENTIALS",
              f"0 {Z[el]} {el}"]
    for e, i in pot.items():
        lines.append(f"{i} {Z[e]} {e}")
    lines.append("ATOMS")
    for i in order:
        ip = 0 if i == idx else pot[elements[i]]
        lines.append(f"{xyz[i][0]:.4f} {xyz[i][1]:.4f} {xyz[i][2]:.4f} {ip} {elements[i]}_{i}")
    lines += ["END", ""]
    meta = dict(element=el, edge=edge, atom_index=int(idx), radius_A=r, extent_A=extent,
                corehole=(corehole or "FSR"), n_atoms=len(elements),
                potential_by_atom=[0 if i == idx else pot[elements[i]] for i in range(len(elements))])
    return "\n".join(lines), meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("structures", help="JSON file: one structure object or a list of them")
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--frame", type=int, default=0, help="frame index used in the site name")
    ap.add_argument("--elements-for-sites", default="", help="only these elements get sites (default: all with a known edge)")
    ap.add_argument("--corehole", default="RPA")
    ap.add_argument("--radius", default="auto", help="auto (10/15 A rule) or a number")
    ap.add_argument("--xanes", default="4.0 0.04 0.1")
    ap.add_argument("--s2", type=float, default=1.0)
    ap.add_argument("--rpath", type=float, default=0.1)
    args = ap.parse_args()

    spec = json.loads(Path(args.structures).read_text())
    if isinstance(spec, dict):
        spec = [spec]
    xk = [float(x) for x in args.xanes.split()]
    radius = None if args.radius == "auto" else float(args.radius)
    only = {e.strip() for e in args.elements_for_sites.split(",") if e.strip()}

    out_root = Path(args.out_root)
    manifest = []
    for st in spec:
        els, xyz, sid = st["elements"], st["coordinates_angstrom"], st["id"]
        if len(els) != len(xyz):
            raise SystemExit(f"{sid}: elements/coordinates length mismatch")
        for idx, el in enumerate(els):
            if el not in Z:
                continue
            if only and el not in only:
                continue
            if el not in EDGES and not only:
                continue
            try:
                text, meta = render(els, xyz, idx, radius=radius, corehole=args.corehole,
                                    s2=args.s2, xanes=tuple(xk), rpath=args.rpath)
            except ValueError as exc:
                print(f"[skip] {sid} atom {idx} ({el}): {exc}")
                continue
            d = out_root / sid / f"f{args.frame:02d}_a{idx:03d}_{el}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "feff.inp").write_text(text)
            manifest.append(dict(structure=sid, frame=args.frame, atom=idx, element=el,
                                 dir=str(d), **meta))
    (out_root / "manifest.json").write_text(json.dumps(dict(sites=manifest), indent=2))
    print(f"[i] {len(manifest)} sites written under {out_root}")
    for e in sorted({m["element"] for m in manifest}):
        print(f"    {e}: {sum(1 for m in manifest if m['element'] == e)}")


if __name__ == "__main__":
    main()
