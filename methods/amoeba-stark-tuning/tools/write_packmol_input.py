#!/usr/bin/env python
"""Write a Packmol input that packs one solute plus N solvent molecules in a cubic box.

Solvent count is estimated from the pure-liquid density unless an explicit count
is given:

    N = round(rho * L^3 * 1e-24 * N_A / M)

Solvent properties come from a TSV table (``--solvent-table``) with a header row:

    name    sdf     density_g_ml    molar_mass_g_mol    [num_solvent]

Adding a new solvent therefore means adding one row (and running Poltype2 on its
SDF), never editing this script. The seven solvents of the published
benzaldehyde case study remain available as a built-in fallback when no table is
given.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

AVOGADRO = 6.02214076e23

SOLVENTS = {
    "hexane": {"density_g_ml": 0.6606, "molar_mass_g_mol": 86.178},
    "thf": {"density_g_ml": 0.8876, "molar_mass_g_mol": 72.107},
    "dichloromethane": {"density_g_ml": 1.3266, "molar_mass_g_mol": 84.933},
    "chloroform": {"density_g_ml": 1.489, "molar_mass_g_mol": 119.378},
    "toluene": {"density_g_ml": 0.8669, "molar_mass_g_mol": 92.141},
    "acetonitrile": {"density_g_ml": 0.786, "molar_mass_g_mol": 41.053},
    "dmso": {"density_g_ml": 1.095, "molar_mass_g_mol": 78.133},
}


def estimate_count(density_g_ml: float, molar_mass_g_mol: float, box_angstrom: float) -> int:
    if density_g_ml <= 0 or molar_mass_g_mol <= 0:
        raise ValueError("density and molar mass must be positive")
    volume_cm3 = (box_angstrom ** 3) * 1.0e-24
    return int(round(density_g_ml * volume_cm3 / molar_mass_g_mol * AVOGADRO))


def read_solvent_table(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = [name.strip().lower() for name in (reader.fieldnames or [])]
        for required in ("name", "density_g_ml", "molar_mass_g_mol"):
            if required not in fieldnames:
                raise ValueError(f"solvent table {path} is missing the '{required}' column")
        for raw in reader:
            row = {(key or "").strip().lower(): (value or "").strip() for key, value in raw.items()}
            name = row.get("name", "")
            if not name or name.startswith("#"):
                continue
            rows[name] = row
    if not rows:
        raise ValueError(f"solvent table {path} has no rows")
    return rows


def resolve_solvent(name: str, table: dict[str, dict[str, str]] | None) -> tuple[float, float, int | None]:
    if table is not None:
        if name not in table:
            raise KeyError(f"solvent {name!r} is not in the solvent table; known: {', '.join(sorted(table))}")
        row = table[name]
        count_text = row.get("num_solvent", "")
        count = int(count_text) if count_text not in {"", "-", "none", "None"} else None
        return float(row["density_g_ml"]), float(row["molar_mass_g_mol"]), count
    if name not in SOLVENTS:
        raise KeyError(f"solvent {name!r} is not built in; pass --solvent-table")
    props = SOLVENTS[name]
    return props["density_g_ml"], props["molar_mass_g_mol"], None


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a Packmol input for one solute in one solvent.")
    parser.add_argument("--solvent", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--solvent-table", default=None, help="TSV with name/sdf/density_g_ml/molar_mass_g_mol")
    parser.add_argument("--box", type=float, default=40.0)
    parser.add_argument("--tolerance", type=float, default=2.0)
    parser.add_argument("--discale", type=float, default=1.5)
    parser.add_argument("--num-solvent", type=int, help="Override the density estimate")
    parser.add_argument("--seed", type=int, default=20260610)
    parser.add_argument("--basename", default="packmol_40A", help="Output file stem")
    args = parser.parse_args()
    if args.tolerance <= 0:
        parser.error("--tolerance must be positive")
    if args.discale <= 0:
        parser.error("--discale must be positive")

    table = read_solvent_table(Path(args.solvent_table)) if args.solvent_table else None
    density, molar_mass, table_count = resolve_solvent(args.solvent, table)
    if args.num_solvent is not None:
        count = args.num_solvent
    elif table_count is not None:
        count = table_count
    else:
        count = estimate_count(density, molar_mass, args.box)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    packmol_inp = out_dir / f"{args.basename}.inp"
    packmol_inp.write_text(
        f"""tolerance {args.tolerance:.3f}
discale {args.discale:.3f}
filetype xyz
seed {args.seed}
pbc 0.0 0.0 0.0 {args.box:.3f} {args.box:.3f} {args.box:.3f}
output packmol.xyz

structure solute_component.xyz
  number 1
  fixed {args.box / 2:.3f} {args.box / 2:.3f} {args.box / 2:.3f} 0.0 0.0 0.0
end structure

structure solvent_component.xyz
  number {count}
  inside box 0.0 0.0 0.0 {args.box:.3f} {args.box:.3f} {args.box:.3f}
end structure
""",
        encoding="utf-8",
    )
    (out_dir / "num_solvent.txt").write_text(f"{count}\n", encoding="utf-8")
    print(f"Wrote {packmol_inp}")
    print(f"num_solvent={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
