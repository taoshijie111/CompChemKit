#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path


TYPE_FIELD_RULES = {
    "atom": ("map", 1, 2),
    "vdw": ("map", 1),
    "vdw14": ("map", 1),
    "bond": ("signed", 1, 2),
    "angle": ("signed", 1, 2, 3),
    "anglep": ("signed", 1, 2, 3),
    "strbnd": ("signed", 1, 2, 3),
    "ureybrad": ("signed", 1, 2, 3),
    "angang": ("signed", 1, 2, 3, 4),
    "opbend": ("signed", 1, 2, 3, 4),
    "opdist": ("signed", 1, 2, 3, 4),
    "imptors": ("signed", 1, 2, 3, 4),
    "improp": ("signed", 1, 2, 3, 4),
    "torsion": ("signed", 1, 2, 3, 4),
    "pitors": ("signed", 1, 2),
    "chgpen": ("map", 1),
    "dispersion": ("map", 1),
    "repulsion": ("map", 1),
    "solute": ("map", 1),
    "soluate": ("map", 1),
}


def is_int(text: str) -> bool:
    try:
        int(text)
        return True
    except ValueError:
        return False


def is_float(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def split_comment(line: str) -> tuple[str, str]:
    stripped = line.rstrip("\n")
    if "#" not in stripped:
        return stripped, ""
    body, comment = stripped.split("#", 1)
    return body.rstrip(), "#" + comment


def read_atom_types_from_tinker_xyz(path: Path) -> list[int]:
    atom_types: list[int] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 6 and is_int(parts[5]):
            atom_type = int(parts[5])
            if atom_type not in atom_types:
                atom_types.append(atom_type)
    if not atom_types:
        raise ValueError(f"No Tinker atom types found in {path}")
    return sorted(atom_types)


def map_signed(token: str, mapping: dict[int, int]) -> str:
    value = int(token)
    sign = -1 if value < 0 else 1
    return str(sign * mapping.get(abs(value), abs(value)))


def remap_xyz_text(text: str, mapping: dict[int, int]) -> str:
    out: list[str] = []
    for lineno, line in enumerate(text.splitlines()):
        if lineno == 0 or not line.strip():
            out.append(line)
            continue
        parts = line.split()
        if len(parts) < 6 or not is_int(parts[5]):
            out.append(line)
            continue
        atom_index = int(parts[0])
        symbol = parts[1]
        x, y, z = (float(parts[2]), float(parts[3]), float(parts[4]))
        atom_type = mapping.get(int(parts[5]), int(parts[5]))
        bonds = [int(item) for item in parts[6:] if is_int(item)]
        out.append(
            f"{atom_index:6d} {symbol:<3s}"
            f"{x:13.6f}{y:13.6f}{z:13.6f}"
            f"{atom_type:6d}"
            + "".join(f"{bond:6d}" for bond in bonds)
        )
    return "\n".join(out) + "\n"


def remap_key_line(line: str, mapping: dict[int, int]) -> str:
    body, comment = split_comment(line)
    if not body.strip():
        return line.rstrip("\n")

    parts = body.split()
    keyword = parts[0].lower()

    if keyword == "multipole":
        for i in range(1, len(parts)):
            token = parts[i]
            if not is_int(token):
                break
            parts[i] = map_signed(token, mapping)
    elif keyword == "polarize":
        if len(parts) > 1 and is_int(parts[1]):
            parts[1] = str(mapping.get(int(parts[1]), int(parts[1])))
        for i in range(4, len(parts)):
            if is_int(parts[i]):
                parts[i] = str(mapping.get(int(parts[i]), int(parts[i])))
    elif keyword in TYPE_FIELD_RULES:
        rule = TYPE_FIELD_RULES[keyword]
        mode = rule[0]
        for i in rule[1:]:
            if i < len(parts) and is_int(parts[i]):
                if mode == "signed":
                    parts[i] = map_signed(parts[i], mapping)
                else:
                    parts[i] = str(mapping.get(int(parts[i]), int(parts[i])))
    else:
        return line.rstrip("\n")

    remapped = " ".join(parts)
    return f"{remapped}  {comment}" if comment else remapped


def remap_key_text(text: str, mapping: dict[int, int]) -> str:
    return "\n".join(remap_key_line(line, mapping) for line in text.splitlines()) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Remap Poltype2 final.xyz/final.key into a unique atom-type range.")
    parser.add_argument("--input-dir", required=True, help="Directory containing final.xyz and final.key")
    parser.add_argument("--prefix", required=True, help="Output prefix, for example tpan or thf")
    parser.add_argument("--base-type", type=int, required=True, help="First atom type/class number in the new range")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    final_xyz = input_dir / "final.xyz"
    final_key = input_dir / "final.key"
    if not final_xyz.is_file():
        raise FileNotFoundError(final_xyz)
    if not final_key.is_file():
        raise FileNotFoundError(final_key)

    old_types = read_atom_types_from_tinker_xyz(final_xyz)
    mapping = {old_type: args.base_type + i for i, old_type in enumerate(old_types)}

    xyz_text = remap_xyz_text(final_xyz.read_text(encoding="utf-8", errors="replace"), mapping)
    key_text = remap_key_text(final_key.read_text(encoding="utf-8", errors="replace"), mapping)

    out_xyz = input_dir / f"{args.prefix}.xyz"
    out_key = input_dir / f"{args.prefix}.key"
    out_prm = input_dir / f"{args.prefix}.prm"
    out_map = input_dir / f"{args.prefix}_type_map.json"

    out_xyz.write_text(xyz_text, encoding="utf-8")
    out_key.write_text(key_text, encoding="utf-8")
    out_prm.write_text(key_text, encoding="utf-8")
    out_map.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Wrote {out_xyz}")
    print(f"Wrote {out_prm}")
    print("Type map:", ", ".join(f"{old}->{new}" for old, new in mapping.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
