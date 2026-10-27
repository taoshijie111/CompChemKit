#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Atom:
    index: int
    symbol: str
    x: float
    y: float
    z: float
    atom_type: int | None
    bonds: tuple[int, ...]

    def with_coords(self, coords: tuple[float, float, float]) -> "Atom":
        return replace(self, x=coords[0], y=coords[1], z=coords[2])

    def shifted(self, atom_offset: int) -> "Atom":
        return replace(
            self,
            index=self.index + atom_offset,
            bonds=tuple(bond + atom_offset for bond in self.bonds),
        )


def is_int(text: str) -> bool:
    try:
        int(text)
        return True
    except ValueError:
        return False


def read_tinker_xyz(path: Path) -> list[Atom]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        raise ValueError(f"Empty file: {path}")
    atom_count = int(lines[0].split()[0])
    atoms: list[Atom] = []
    for line in lines[1 : 1 + atom_count]:
        parts = line.split()
        if len(parts) < 6:
            raise ValueError(f"Malformed Tinker xyz line in {path}: {line}")
        atom_type = int(parts[5]) if is_int(parts[5]) else None
        bonds = tuple(int(item) for item in parts[6:] if is_int(item))
        atoms.append(
            Atom(
                index=int(parts[0]),
                symbol=parts[1],
                x=float(parts[2]),
                y=float(parts[3]),
                z=float(parts[4]),
                atom_type=atom_type,
                bonds=bonds,
            )
        )
    if len(atoms) != atom_count:
        raise ValueError(f"Expected {atom_count} atoms in {path}, read {len(atoms)}")
    return atoms


def centroid(atoms: list[Atom]) -> tuple[float, float, float]:
    n = len(atoms)
    return (
        sum(atom.x for atom in atoms) / n,
        sum(atom.y for atom in atoms) / n,
        sum(atom.z for atom in atoms) / n,
    )


def write_simple_xyz(path: Path, atoms: list[Atom], title: str, center_at_origin: bool = False) -> None:
    cx, cy, cz = centroid(atoms) if center_at_origin else (0.0, 0.0, 0.0)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(f"{len(atoms)}\n")
        handle.write(f"{title}\n")
        for atom in atoms:
            handle.write(f"{atom.symbol:<3s} {atom.x - cx: .8f} {atom.y - cy: .8f} {atom.z - cz: .8f}\n")


def read_simple_xyz(path: Path) -> tuple[list[str], list[tuple[float, float, float]]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    atom_count = int(lines[0].split()[0])
    names: list[str] = []
    coords: list[tuple[float, float, float]] = []
    for line in lines[2 : 2 + atom_count]:
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"Malformed xyz line in {path}: {line}")
        names.append(parts[0])
        coords.append((float(parts[1]), float(parts[2]), float(parts[3])))
    if len(coords) != atom_count:
        raise ValueError(f"Expected {atom_count} atoms in {path}, read {len(coords)}")
    return names, coords


def write_tinker_xyz(path: Path, atoms: list[Atom], title: str) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(f"{len(atoms):6d}  {title}\n")
        for atom in atoms:
            atom_type = "" if atom.atom_type is None else f"{atom.atom_type:6d}"
            bonds = "".join(f"{bond:6d}" for bond in atom.bonds)
            handle.write(
                f"{atom.index:6d} {atom.symbol:<3s}"
                f"{atom.x:13.6f}{atom.y:13.6f}{atom.z:13.6f}"
                f"{atom_type}{bonds}\n"
            )


def atoms_with_new_coords(template: list[Atom], coords: list[tuple[float, float, float]], offset: int) -> list[Atom]:
    if len(template) != len(coords):
        raise ValueError("Template atom count and coordinate count differ")
    return [atom.with_coords(coord).shifted(offset) for atom, coord in zip(template, coords)]


def distance(a: Atom, b: Atom) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def find_atom(atoms: list[Atom], index: int) -> Atom:
    for atom in atoms:
        if atom.index == index:
            return atom
    raise KeyError(index)


def find_probe_pair(
    solute: list[Atom],
    probe_elements: tuple[str, str],
    probe_atom_indices: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Locate the probe bond inside the solute.

    The projection axis and its sign are always atom1 -> atom2, so atom1 must be
    the element the field is projected "from": carbonyl C -> O, nitrile C -> N,
    and so on. With no explicit indices the shortest bonded pair whose elements
    match probe_elements in that order is selected, which reproduces the original
    benzaldehyde C=O behaviour exactly.
    """
    if probe_atom_indices is not None:
        atom1 = find_atom(solute, probe_atom_indices[0])
        atom2 = find_atom(solute, probe_atom_indices[1])
        if atom2.index not in atom1.bonds and atom1.index not in atom2.bonds:
            raise ValueError(
                f"Atoms {atom1.index} and {atom2.index} are not bonded in the solute; "
                "the probe pair must be a bonded pair"
            )
        return atom1.index, atom2.index

    element1, element2 = (element.strip().upper() for element in probe_elements)
    candidates: list[tuple[float, int, int]] = []
    for atom in solute:
        if atom.symbol.upper() != element1:
            continue
        for bonded_index in atom.bonds:
            other = find_atom(solute, bonded_index)
            if other.symbol.upper() == element2:
                candidates.append((distance(atom, other), atom.index, other.index))
    if not candidates:
        raise ValueError(f"Could not find a bonded {element1}-{element2} probe pair in the solute")
    _, atom1_index, atom2_index = min(candidates)
    return atom1_index, atom2_index


def command_components(args: argparse.Namespace) -> int:
    solute = read_tinker_xyz(Path(args.solute))
    solvent = read_tinker_xyz(Path(args.solvent))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_simple_xyz(out_dir / "solute_component.xyz", solute, args.solute_name, center_at_origin=True)
    write_simple_xyz(out_dir / "solvent_component.xyz", solvent, args.solvent_name, center_at_origin=True)
    print(f"Wrote {out_dir / 'solute_component.xyz'}")
    print(f"Wrote {out_dir / 'solvent_component.xyz'}")
    return 0


def command_system(args: argparse.Namespace) -> int:
    solute_template = read_tinker_xyz(Path(args.solute))
    solvent_template = read_tinker_xyz(Path(args.solvent))
    _, coords = read_simple_xyz(Path(args.packmol))

    solute_n = len(solute_template)
    solvent_n = len(solvent_template)
    expected_n = solute_n + args.num_solvent * solvent_n
    if len(coords) != expected_n:
        raise ValueError(f"Packmol atom count is {len(coords)}, expected {expected_n}")

    atoms: list[Atom] = []
    atoms.extend(atoms_with_new_coords(solute_template, coords[:solute_n], 0))

    cursor = solute_n
    for i in range(args.num_solvent):
        block = coords[cursor : cursor + solvent_n]
        offset = solute_n + i * solvent_n
        atoms.extend(atoms_with_new_coords(solvent_template, block, offset))
        cursor += solvent_n

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_tinker_xyz(out_path, atoms, f"{args.solute_name} in {args.solvent_name}, {args.num_solvent} solvent molecules")

    probe_elements = tuple(part.strip() for part in args.probe_elements.split() if part.strip())
    if len(probe_elements) != 2:
        raise ValueError(f"--probe-elements needs exactly two element symbols, got {args.probe_elements!r}")
    probe_indices = None
    if args.probe_atom_indices:
        parts = [part for part in args.probe_atom_indices.replace(",", " ").split() if part]
        if len(parts) != 2 or not all(is_int(part) for part in parts):
            raise ValueError(f"--probe-atom-indices needs two integer indices, got {args.probe_atom_indices!r}")
        probe_indices = (int(parts[0]), int(parts[1]))

    atom1_index, atom2_index = find_probe_pair(atoms[:solute_n], probe_elements, probe_indices)
    metadata = {
        "solute": args.solute_name,
        "solvent": args.solvent_name,
        "solute_atom_count": solute_n,
        "solvent_atom_count": solvent_n,
        "num_solvent": args.num_solvent,
        "probe_elements": [probe_elements[0], probe_elements[1]],
        "probe_label": args.probe_label,
        "atom1_name": f"probe_{probe_elements[0].lower()}",
        "atom2_name": f"probe_{probe_elements[1].lower()}",
        "atom1_index": atom1_index,
        "atom2_index": atom2_index,
        "projection_axis": f"{probe_elements[0]}_to_{probe_elements[1]}",
        "box_angstrom": args.box,
    }
    meta_path = Path(args.metadata)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"Wrote {meta_path}")
    print(f"Probe atom indices ({probe_elements[0]} -> {probe_elements[1]}): {atom1_index}, {atom2_index}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a Tinker xyz system from Poltype2 molecule templates and Packmol coordinates, "
        "and record the probe-pair metadata used by the field extraction."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_components = sub.add_parser("components", help="Write Packmol component xyz files")
    p_components.add_argument("--solute", required=True)
    p_components.add_argument("--solvent", required=True)
    p_components.add_argument("--out-dir", required=True)
    p_components.add_argument("--solute-name", default="solute")
    p_components.add_argument("--solvent-name", required=True)
    p_components.set_defaults(func=command_components)

    p_system = sub.add_parser("system", help="Convert Packmol output into a typed Tinker xyz system")
    p_system.add_argument("--packmol", required=True)
    p_system.add_argument("--solute", required=True)
    p_system.add_argument("--solvent", required=True)
    p_system.add_argument("--num-solvent", type=int, required=True)
    p_system.add_argument("--out", required=True)
    p_system.add_argument("--metadata", required=True)
    p_system.add_argument("--solute-name", default="solute")
    p_system.add_argument(
        "--probe-elements",
        default="C O",
        help='Two element symbols defining the probe bond in atom1->atom2 order (default "C O")',
    )
    p_system.add_argument(
        "--probe-atom-indices",
        default="",
        help="Optional explicit 1-based Tinker atom indices of the probe pair, e.g. '2 1'; overrides element search",
    )
    p_system.add_argument("--probe-label", default="probe", help='Human-readable probe label, e.g. "C=O"')
    p_system.add_argument("--solvent-name", required=True)
    p_system.add_argument("--box", type=float, default=40.0)
    p_system.set_defaults(func=command_system)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
