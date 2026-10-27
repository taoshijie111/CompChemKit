#!/usr/bin/env python
"""Write the two Tinker key files every replicate needs.

system.key
    solute + one solvent, periodic cubic box, Ewald/PME electrostatics.
    Used by minimize / NPT / NVT / production.

ref.key
    solute only, NO box and NO Ewald settings.
    It describes the isolated probe molecule in the gas phase. The field
    extraction writes a solute-only trajectory (ref.arc) at the production
    coordinates and re-evaluates the induced dipoles with this key; the
    difference between the two induced-dipole sets is the solvent-induced
    contribution. See tools/extract_probe_field.py and tools/analyze_uind.

Both files expand the first-level ``parameters`` includes of the molecule .prm
files before listing the .prm files themselves, so the AMOEBA header
(amoebabio18_header.prm) is always resolved explicitly rather than by Tinker's
search path.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def parameter_lines(prm_paths: list[Path]) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()

    for prm_path in prm_paths:
        for raw_line in prm_path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = raw_line.split()
            if len(parts) != 2 or parts[0].lower() != "parameters":
                continue
            include_path = Path(parts[1])
            if not include_path.is_absolute():
                include_path = prm_path.parent / include_path
            line = f"parameters {include_path}"
            if line not in seen:
                lines.append(line)
                seen.add(line)

    for prm_path in prm_paths:
        line = f"parameters {prm_path}"
        if line not in seen:
            lines.append(line)
            seen.add(line)

    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write system.key (periodic, Ewald) and ref.key (gas-phase solute) for one replicate."
    )
    parser.add_argument("--out-dir", required=True, help="Replicate directory that receives the two key files")
    parser.add_argument("--solute-prm", required=True, help="Poltype2 .prm of the probe solute")
    parser.add_argument("--solvent-prm", required=True, help="Poltype2 .prm of the solvent")
    parser.add_argument("--box", type=float, default=40.0, help="Cubic box edge in Angstrom")
    parser.add_argument("--polar-eps", default="1.0e-5", help="AMOEBA mutual polarization convergence")
    parser.add_argument("--polar-iter", type=int, default=200)
    parser.add_argument("--ewald-cutoff", type=float, default=7.0)
    parser.add_argument("--vdw-cutoff", type=float, default=12.0)
    parser.add_argument("--printout", type=int, default=100)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    solute_prm = Path(args.solute_prm).resolve()
    solvent_prm = Path(args.solvent_prm).resolve()
    for required in (solute_prm, solvent_prm):
        if not required.is_file():
            raise FileNotFoundError(required)

    system_key = out_dir / "system.key"
    ref_key = out_dir / "ref.key"
    system_parameters = "\n".join(parameter_lines([solute_prm, solvent_prm]))
    ref_parameters = "\n".join(parameter_lines([solute_prm]))

    system_key.write_text(
        f"""{system_parameters}

polarization mutual
polar-eps {args.polar_eps}
polar-iter {args.polar_iter}
polar-predict
ewald
ewald-cutoff {args.ewald_cutoff}
neighbor-list
vdw-cutoff {args.vdw_cutoff}
vdw-correction
a-axis {args.box:.6f}
b-axis {args.box:.6f}
c-axis {args.box:.6f}
alpha 90.0
beta 90.0
gamma 90.0
digits 8
printout {args.printout}
""",
        encoding="utf-8",
    )

    ref_key.write_text(
        f"""{ref_parameters}

polarization mutual
polar-eps {args.polar_eps}
polar-iter {args.polar_iter}
polar-predict
digits 8
printout {args.printout}
""",
        encoding="utf-8",
    )

    print(f"Wrote {system_key}")
    print(f"Wrote {ref_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
