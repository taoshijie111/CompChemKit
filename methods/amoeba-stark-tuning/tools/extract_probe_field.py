#!/usr/bin/env python
"""Extract the solvent-induced electric field along a probe bond from AMOEBA MD output.

Method (this is the step that defines the whole workflow):

1. ``md_start.uind`` (written because production ran with ``save-induced``) holds the
   converged induced dipole of every atom in every saved frame, i.e. the probe
   molecule polarised by the solvent *and* by itself.
2. The solute atoms of each selected frame are written to a solute-only ``ref.arc``
   (no solvent, no box line). Re-evaluating that file with the gas-phase ``ref.key``
   via ``analyze_uind`` gives ``ref.uind``: the probe polarised only by itself.
3. Subtract, convert the induced dipole to a field with the atom polarizability and
   project on the probe bond unit vector:

       F_i = DIPOLE_TO_FIELD * (mu_ind,i - mu_ind,i^ref) / alpha_i
       F   = ( F_atom1 . u_hat  +  F_atom2 . u_hat ) / 2 ,   u_hat = (r_atom2 - r_atom1)/|...|

   DIPOLE_TO_FIELD = 299.79 converts Debye / Angstrom^3 to MV/cm.
   The sign convention is atom1 -> atom2 (for benzaldehyde: carbonyl C -> O).

The induced-dipole route needs no MDI/ELECTRIC and no trajectory re-imaging: the
subtraction removes the solute self-field implicitly, at the exact saved coordinates.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path


DIPOLE_TO_FIELD = 299.79
FLOAT_RE = re.compile(r"[-+]?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[EeDd][-+]?\d+)?")


@dataclass(frozen=True)
class Atom:
    index: int
    symbol: str
    x: float
    y: float
    z: float
    atom_type: int | None
    bonds: tuple[int, ...]

    @property
    def coords(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass(frozen=True)
class Frame:
    atom_count: int
    title: str
    box_line: str | None
    atom_lines: list[str]


@dataclass(frozen=True)
class FixedFrameLayout:
    atom_count: int
    frame_span: int
    prefix_span: int


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


def is_box_line(text: str) -> bool:
    fields = text.split()
    return len(fields) >= 6 and not is_int(fields[0]) and all(is_float(item) for item in fields[:6])


def parse_tinker_atom_line(atom_line: str, path: Path) -> Atom:
    head = re.match(r"^\s*(\d+)\s+(\S+)\s+(.*)$", atom_line)
    if head is None:
        raise ValueError(f"Malformed atom/vector line in {path}: {atom_line.rstrip()}")

    atom_index = int(head.group(1))
    symbol = head.group(2)
    rest = head.group(3)
    coord_matches = list(FLOAT_RE.finditer(rest))
    if len(coord_matches) < 3:
        raise ValueError(f"Could not parse coordinates in {path}: {atom_line.rstrip()}")

    coords = [float(match.group(0).replace("D", "E").replace("d", "e")) for match in coord_matches[:3]]
    tail = rest[coord_matches[2].end() :].split()
    atom_type = int(tail[0]) if tail and is_int(tail[0]) else None
    bonds = tuple(int(item) for item in tail[1:] if is_int(item))
    return Atom(atom_index, symbol, coords[0], coords[1], coords[2], atom_type, bonds)


def read_tinker_frame(handle, path: Path, keep_atom_lines: bool = True) -> Frame | None:
    while True:
        header = handle.readline()
        if header == "":
            return None
        if header.strip():
            break

    parts = header.split()
    if not parts or not is_int(parts[0]):
        raise ValueError(f"Malformed frame header in {path}: {header.rstrip()}")
    atom_count = int(parts[0])

    next_line = handle.readline()
    if next_line == "":
        return None
    box_line = next_line if is_box_line(next_line) else None
    atom_lines: list[str] = []
    if box_line is None:
        if keep_atom_lines:
            atom_lines.append(next_line)
        else:
            atom_lines_seen = 1
            while atom_lines_seen < atom_count:
                line = handle.readline()
                if line == "":
                    return None
                atom_lines_seen += 1
            return Frame(atom_count=atom_count, title=header.rstrip("\n"), box_line=box_line, atom_lines=atom_lines)

    if not keep_atom_lines:
        for _ in range(atom_count):
            line = handle.readline()
            if line == "":
                return None
        return Frame(atom_count=atom_count, title=header.rstrip("\n"), box_line=box_line, atom_lines=atom_lines)

    while len(atom_lines) < atom_count:
        line = handle.readline()
        if line == "":
            return None
        atom_lines.append(line)

    return Frame(atom_count=atom_count, title=header.rstrip("\n"), box_line=box_line, atom_lines=atom_lines)


def read_binary_frame_layout(handle, solute_atom_count: int) -> tuple[int, int, int, int] | None:
    start = handle.tell()
    header = handle.readline()
    if header == b"":
        return None
    parts = header.split()
    if not parts or not is_int(parts[0].decode("ascii", errors="ignore")):
        return None
    atom_count = int(parts[0])

    next_line = handle.readline()
    if next_line == b"":
        return None
    try:
        next_text = next_line.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        next_text = ""
    atom_lines_seen = 0
    prefix_end = None
    if not is_box_line(next_text):
        atom_lines_seen = 1
        if atom_lines_seen == solute_atom_count:
            prefix_end = handle.tell()

    while atom_lines_seen < atom_count:
        line = handle.readline()
        if line == b"":
            return None
        atom_lines_seen += 1
        if atom_lines_seen == solute_atom_count:
            prefix_end = handle.tell()

    end = handle.tell()
    if prefix_end is None:
        return None
    return start, end, atom_count, prefix_end - start


def probe_fixed_frame_layout(path: Path, solute_atom_count: int, sample_frames: int = 20) -> FixedFrameLayout | None:
    spans: list[int] = []
    prefix_spans: list[int] = []
    atom_counts: list[int] = []
    with path.open("rb") as handle:
        for _ in range(sample_frames):
            layout = read_binary_frame_layout(handle, solute_atom_count)
            if layout is None:
                break
            start, end, atom_count, prefix_span = layout
            spans.append(end - start)
            prefix_spans.append(prefix_span)
            atom_counts.append(atom_count)
    if not spans:
        return None
    if len(set(spans)) != 1 or len(set(prefix_spans)) != 1 or len(set(atom_counts)) != 1:
        return None
    return FixedFrameLayout(atom_count=atom_counts[0], frame_span=spans[0], prefix_span=prefix_spans[0])


def read_tinker_frame_prefix(handle, path: Path, frame_number: int, layout: FixedFrameLayout) -> Frame | None:
    offset = (frame_number - 1) * layout.frame_span
    handle.seek(offset)
    data = handle.read(layout.prefix_span)
    if len(data) < layout.prefix_span:
        return None
    lines = data.decode("utf-8", errors="replace").splitlines(keepends=True)
    if not lines:
        return None
    header = lines[0]
    parts = header.split()
    if not parts or not is_int(parts[0]):
        return None
    atom_count = int(parts[0])
    line_index = 1
    box_line = None
    if line_index < len(lines) and is_box_line(lines[line_index]):
        box_line = lines[line_index]
        line_index += 1
    atom_lines = lines[line_index:]
    if not atom_lines:
        return None
    return Frame(atom_count=atom_count, title=header.rstrip("\n"), box_line=box_line, atom_lines=atom_lines)


def frame_from_prefix_bytes(data: bytes) -> Frame | None:
    lines = data.decode("utf-8", errors="replace").splitlines(keepends=True)
    if not lines:
        return None
    header = lines[0]
    parts = header.split()
    if not parts or not is_int(parts[0]):
        return None
    atom_count = int(parts[0])
    line_index = 1
    box_line = None
    if line_index < len(lines) and is_box_line(lines[line_index]):
        box_line = lines[line_index]
        line_index += 1
    atom_lines = lines[line_index:]
    if not atom_lines:
        return None
    return Frame(atom_count=atom_count, title=header.rstrip("\n"), box_line=box_line, atom_lines=atom_lines)


def atom_by_index(atoms: list[Atom], atom_index: int) -> Atom:
    for atom in atoms:
        if atom.index == atom_index:
            return atom
    raise KeyError(f"Atom index {atom_index} not found")


def vector_sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vector_dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vector_scale(a: tuple[float, float, float], scale: float) -> tuple[float, float, float]:
    return (a[0] * scale, a[1] * scale, a[2] * scale)


def vector_norm(a: tuple[float, float, float]) -> float:
    return math.sqrt(vector_dot(a, a))


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def parse_parameter_paths(key_path: Path) -> list[Path]:
    paths: list[Path] = []
    for line in key_path.read_text(encoding="utf-8", errors="replace").splitlines():
        body = line.split("#", 1)[0].strip()
        if not body:
            continue
        parts = body.split(maxsplit=1)
        if len(parts) == 2 and parts[0].lower() == "parameters":
            candidate = Path(parts[1].strip().strip('"').strip("'"))
            if not candidate.is_absolute():
                candidate = key_path.parent / candidate
            paths.append(candidate.resolve())
    return paths


def parse_polarizabilities(parameter_paths: list[Path]) -> dict[int, float]:
    polar: dict[int, float] = {}
    for path in parameter_paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            body = line.split("#", 1)[0].strip()
            if not body:
                continue
            parts = body.split()
            if len(parts) >= 3 and parts[0].lower() == "polarize" and is_int(parts[1]):
                try:
                    polar[int(parts[1])] = float(parts[2])
                except ValueError:
                    pass
    return polar


def write_ref_frame(handle, frame_index: int, solute_atoms: list[Atom], frame_title: str = "probe") -> None:
    kept = {atom.index for atom in solute_atoms}
    handle.write(f"{len(solute_atoms):6d}  {frame_title} reference frame {frame_index}\n")
    for atom in solute_atoms:
        clean = replace(atom, bonds=tuple(bond for bond in atom.bonds if bond in kept))
        atom_type = "" if clean.atom_type is None else f"{clean.atom_type:6d}"
        bonds = "".join(f"{bond:6d}" for bond in clean.bonds)
        handle.write(
            f"{clean.index:6d} {clean.symbol:<3s}"
            f"{clean.x:13.6f}{clean.y:13.6f}{clean.z:13.6f}"
            f"{atom_type}{bonds}\n"
        )


def run_analyze_uind(fields_dir: Path, analyze_cmd: str) -> None:
    cmd_path = shutil.which(analyze_cmd) or analyze_cmd
    env = os.environ.copy()
    cmd_parent = str(Path(cmd_path).resolve().parent)
    env["PATH"] = f"{cmd_parent}{os.pathsep}{env.get('PATH', '')}"
    for stale in ("ref.uind", "ref_analyze_uind.log"):
        stale_path = fields_dir / stale
        if stale_path.exists():
            stale_path.unlink()
    proc = subprocess.run(
        [cmd_path, "ref.arc", "U"],
        cwd=fields_dir,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    (fields_dir / "ref_analyze_uind.log").write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"analyze_uind failed in {fields_dir}; inspect ref_analyze_uind.log")
    if not (fields_dir / "ref.uind").is_file():
        raise FileNotFoundError(fields_dir / "ref.uind")


def extract_selected_frames(
    replicate_dir: Path,
    fields_dir: Path,
    metadata: dict[str, object],
    stride: int,
    max_selected_frames: int,
    read_mode: str,
) -> tuple[list[dict[str, object]], int, int, tuple[int, int], str]:
    frame_title = str(metadata.get("solute") or metadata.get("probe_label") or "probe")
    atom1_index = int(metadata["atom1_index"])
    atom2_index = int(metadata["atom2_index"])
    solute_atom_count = int(metadata["solute_atom_count"])
    arc_path = replicate_dir / "production" / "md_start.arc"
    uind_path = replicate_dir / "production" / "md_start.uind"
    if not arc_path.is_file():
        raise FileNotFoundError(arc_path)
    if not uind_path.is_file():
        raise FileNotFoundError(uind_path)

    arc_layout = probe_fixed_frame_layout(arc_path, solute_atom_count)
    uind_layout = probe_fixed_frame_layout(uind_path, solute_atom_count)
    if (
        read_mode in {"auto", "sequential-fixed"}
        and arc_layout is not None
        and uind_layout is not None
        and arc_layout.atom_count == uind_layout.atom_count
    ):
        if read_mode == "sequential-fixed":
            return extract_selected_frames_sequential_fixed(
                frame_title=frame_title,
                arc_path=arc_path,
                uind_path=uind_path,
                fields_dir=fields_dir,
                atom1_index=atom1_index,
                atom2_index=atom2_index,
                solute_atom_count=solute_atom_count,
                stride=stride,
                max_selected_frames=max_selected_frames,
                arc_layout=arc_layout,
                uind_layout=uind_layout,
            )
    if (
        read_mode in {"auto", "seek-prefix"}
        and arc_layout is not None
        and uind_layout is not None
        and arc_layout.atom_count == uind_layout.atom_count
    ):
        return extract_selected_frames_by_seek(
            frame_title=frame_title,
            arc_path=arc_path,
            uind_path=uind_path,
            fields_dir=fields_dir,
            atom1_index=atom1_index,
            atom2_index=atom2_index,
            solute_atom_count=solute_atom_count,
            stride=stride,
            max_selected_frames=max_selected_frames,
            arc_layout=arc_layout,
            uind_layout=uind_layout,
        )
    if read_mode not in {"auto", "stream"}:
        raise ValueError(f"Requested read mode {read_mode!r} is unavailable for {replicate_dir}")

    selected: list[dict[str, object]] = []
    raw_frames_read = 0
    first_atom_types: tuple[int, int] | None = None
    ref_arc_path = fields_dir / "ref.arc"

    with arc_path.open("r", encoding="utf-8", errors="replace") as arc_handle, uind_path.open(
        "r", encoding="utf-8", errors="replace"
    ) as uind_handle, ref_arc_path.open("w", encoding="utf-8") as ref_handle:
        while len(selected) < max_selected_frames:
            next_frame = raw_frames_read + 1
            keep_frame = next_frame % stride == 0
            coord_frame = read_tinker_frame(arc_handle, arc_path, keep_atom_lines=keep_frame)
            uind_frame = read_tinker_frame(uind_handle, uind_path, keep_atom_lines=keep_frame)
            if coord_frame is None or uind_frame is None:
                break
            raw_frames_read += 1
            if coord_frame.atom_count != uind_frame.atom_count:
                raise ValueError(
                    f"Frame atom count mismatch in {replicate_dir}: "
                    f"arc={coord_frame.atom_count}, uind={uind_frame.atom_count}"
                )
            if not keep_frame:
                continue

            solute_atoms = [
                parse_tinker_atom_line(line, arc_path) for line in coord_frame.atom_lines[:solute_atom_count]
            ]
            solute_uind = [
                parse_tinker_atom_line(line, uind_path) for line in uind_frame.atom_lines[:solute_atom_count]
            ]
            atom1 = atom_by_index(solute_atoms, atom1_index)
            atom2 = atom_by_index(solute_atoms, atom2_index)
            uatom1 = atom_by_index(solute_uind, atom1_index)
            uatom2 = atom_by_index(solute_uind, atom2_index)
            if atom1.atom_type is None or atom2.atom_type is None:
                raise ValueError(f"Missing atom type for target atoms in {replicate_dir}")
            if first_atom_types is None:
                first_atom_types = (atom1.atom_type, atom2.atom_type)

            write_ref_frame(ref_handle, len(selected) + 1, solute_atoms, frame_title)
            selected.append(
                {
                    "selected_frame": len(selected) + 1,
                    "source_frame": raw_frames_read,
                    "atom1_coords": atom1.coords,
                    "atom2_coords": atom2.coords,
                    "atom1_uind": uatom1.coords,
                    "atom2_uind": uatom2.coords,
                }
            )

    if first_atom_types is None:
        raise ValueError(f"No selected frames from {replicate_dir}")
    return selected, raw_frames_read, len(selected), first_atom_types, "stream"


def extract_selected_frames_sequential_fixed(
    frame_title: str,
    arc_path: Path,
    uind_path: Path,
    fields_dir: Path,
    atom1_index: int,
    atom2_index: int,
    solute_atom_count: int,
    stride: int,
    max_selected_frames: int,
    arc_layout: FixedFrameLayout,
    uind_layout: FixedFrameLayout,
) -> tuple[list[dict[str, object]], int, int, tuple[int, int], str]:
    selected: list[dict[str, object]] = []
    raw_frames_read = 0
    first_atom_types: tuple[int, int] | None = None
    ref_arc_path = fields_dir / "ref.arc"
    last_source_frame = stride * max_selected_frames

    with arc_path.open("rb") as arc_handle, uind_path.open("rb") as uind_handle, ref_arc_path.open(
        "w", encoding="utf-8"
    ) as ref_handle:
        for source_frame in range(1, last_source_frame + 1):
            arc_chunk = arc_handle.read(arc_layout.frame_span)
            uind_chunk = uind_handle.read(uind_layout.frame_span)
            if len(arc_chunk) < arc_layout.frame_span or len(uind_chunk) < uind_layout.frame_span:
                break
            raw_frames_read = source_frame
            if source_frame % stride != 0:
                continue

            coord_frame = frame_from_prefix_bytes(arc_chunk[: arc_layout.prefix_span])
            uind_frame = frame_from_prefix_bytes(uind_chunk[: uind_layout.prefix_span])
            if coord_frame is None or uind_frame is None:
                break
            if coord_frame.atom_count != uind_frame.atom_count:
                raise ValueError(
                    f"Frame atom count mismatch: arc={coord_frame.atom_count}, uind={uind_frame.atom_count}"
                )

            solute_atoms = [
                parse_tinker_atom_line(line, arc_path) for line in coord_frame.atom_lines[:solute_atom_count]
            ]
            solute_uind = [
                parse_tinker_atom_line(line, uind_path) for line in uind_frame.atom_lines[:solute_atom_count]
            ]
            atom1 = atom_by_index(solute_atoms, atom1_index)
            atom2 = atom_by_index(solute_atoms, atom2_index)
            uatom1 = atom_by_index(solute_uind, atom1_index)
            uatom2 = atom_by_index(solute_uind, atom2_index)
            if atom1.atom_type is None or atom2.atom_type is None:
                raise ValueError(f"Missing atom type for target atoms in {arc_path}")
            if first_atom_types is None:
                first_atom_types = (atom1.atom_type, atom2.atom_type)

            write_ref_frame(ref_handle, len(selected) + 1, solute_atoms, frame_title)
            selected.append(
                {
                    "selected_frame": len(selected) + 1,
                    "source_frame": source_frame,
                    "atom1_coords": atom1.coords,
                    "atom2_coords": atom2.coords,
                    "atom1_uind": uatom1.coords,
                    "atom2_uind": uatom2.coords,
                }
            )
            if len(selected) >= max_selected_frames:
                break

    if first_atom_types is None:
        raise ValueError(f"No selected frames from {arc_path.parent.parent}")
    return selected, raw_frames_read, len(selected), first_atom_types, "sequential-fixed"


def extract_selected_frames_by_seek(
    frame_title: str,
    arc_path: Path,
    uind_path: Path,
    fields_dir: Path,
    atom1_index: int,
    atom2_index: int,
    solute_atom_count: int,
    stride: int,
    max_selected_frames: int,
    arc_layout: FixedFrameLayout,
    uind_layout: FixedFrameLayout,
) -> tuple[list[dict[str, object]], int, int, tuple[int, int], str]:
    selected: list[dict[str, object]] = []
    raw_frames_read = 0
    first_atom_types: tuple[int, int] | None = None
    ref_arc_path = fields_dir / "ref.arc"

    with arc_path.open("rb") as arc_handle, uind_path.open("rb") as uind_handle, ref_arc_path.open(
        "w", encoding="utf-8"
    ) as ref_handle:
        for source_frame in range(stride, stride * max_selected_frames + 1, stride):
            coord_frame = read_tinker_frame_prefix(arc_handle, arc_path, source_frame, arc_layout)
            uind_frame = read_tinker_frame_prefix(uind_handle, uind_path, source_frame, uind_layout)
            if coord_frame is None or uind_frame is None:
                break
            raw_frames_read = source_frame
            if coord_frame.atom_count != uind_frame.atom_count:
                raise ValueError(
                    f"Frame atom count mismatch: arc={coord_frame.atom_count}, uind={uind_frame.atom_count}"
                )

            solute_atoms = [
                parse_tinker_atom_line(line, arc_path) for line in coord_frame.atom_lines[:solute_atom_count]
            ]
            solute_uind = [
                parse_tinker_atom_line(line, uind_path) for line in uind_frame.atom_lines[:solute_atom_count]
            ]
            atom1 = atom_by_index(solute_atoms, atom1_index)
            atom2 = atom_by_index(solute_atoms, atom2_index)
            uatom1 = atom_by_index(solute_uind, atom1_index)
            uatom2 = atom_by_index(solute_uind, atom2_index)
            if atom1.atom_type is None or atom2.atom_type is None:
                raise ValueError(f"Missing atom type for target atoms in {arc_path}")
            if first_atom_types is None:
                first_atom_types = (atom1.atom_type, atom2.atom_type)

            write_ref_frame(ref_handle, len(selected) + 1, solute_atoms, frame_title)
            selected.append(
                {
                    "selected_frame": len(selected) + 1,
                    "source_frame": source_frame,
                    "atom1_coords": atom1.coords,
                    "atom2_coords": atom2.coords,
                    "atom1_uind": uatom1.coords,
                    "atom2_uind": uatom2.coords,
                }
            )

    if first_atom_types is None:
        raise ValueError(f"No selected frames from {arc_path.parent.parent}")
    return selected, raw_frames_read, len(selected), first_atom_types, "seek-prefix"


def read_ref_uind(fields_dir: Path, atom1_index: int, atom2_index: int, expected_frames: int) -> list[dict[str, object]]:
    ref_path = fields_dir / "ref.uind"
    refs: list[dict[str, object]] = []
    with ref_path.open("r", encoding="utf-8", errors="replace") as handle:
        while len(refs) < expected_frames:
            frame = read_tinker_frame(handle, ref_path)
            if frame is None:
                break
            atoms = [parse_tinker_atom_line(line, ref_path) for line in frame.atom_lines]
            refs.append(
                {
                    "atom1_ref_uind": atom_by_index(atoms, atom1_index).coords,
                    "atom2_ref_uind": atom_by_index(atoms, atom2_index).coords,
                }
            )
    if len(refs) != expected_frames:
        raise ValueError(f"ref.uind frame mismatch in {fields_dir}: expected {expected_frames}, got {len(refs)}")
    return refs


def compute_rows(
    selected: list[dict[str, object]],
    refs: list[dict[str, object]],
    polar1: float,
    polar2: float,
    frame_interval_ps: float,
) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for data, ref in zip(selected, refs):
        atom1_coords = data["atom1_coords"]
        atom2_coords = data["atom2_coords"]
        atom1_uind = data["atom1_uind"]
        atom2_uind = data["atom2_uind"]
        atom1_ref = ref["atom1_ref_uind"]
        atom2_ref = ref["atom2_ref_uind"]

        co_vec = vector_sub(atom2_coords, atom1_coords)
        co_len = vector_norm(co_vec)
        if co_len <= 0:
            raise ValueError(f"Zero C=O length at selected frame {data['selected_frame']}")
        co_unit = vector_scale(co_vec, 1.0 / co_len)

        field1_vec = vector_scale(vector_sub(atom1_uind, atom1_ref), DIPOLE_TO_FIELD / polar1)
        field2_vec = vector_scale(vector_sub(atom2_uind, atom2_ref), DIPOLE_TO_FIELD / polar2)
        field1 = vector_dot(field1_vec, co_unit)
        field2 = vector_dot(field2_vec, co_unit)
        source_frame = int(data["source_frame"])
        rows.append(
            {
                "frame": float(data["selected_frame"]),
                "source_frame": float(source_frame),
                "estimated_time_ps": source_frame * frame_interval_ps,
                "field_atom1_MV_cm": field1,
                "field_atom2_MV_cm": field2,
                "field_mean_MV_cm": 0.5 * (field1 + field2),
                "field_drop_MV_cm": field2 - field1,
                "probe_length_A": co_len,
            }
        )
    return rows


METADATA_CANDIDATES = ("probe_atoms.json", "carbonyl_atoms.json")
METADATA_SEARCH_DIRS = ("build_system", ".")


def resolve_metadata_path(replicate_dir: Path) -> Path:
    """Find the probe-pair metadata written by build_tinker_system.py."""
    for directory in METADATA_SEARCH_DIRS:
        for name in METADATA_CANDIDATES:
            candidate = replicate_dir / directory / name
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(
        f"No probe metadata found under {replicate_dir}; looked for "
        + ", ".join(f"{d}/{n}" for d in METADATA_SEARCH_DIRS for n in METADATA_CANDIDATES)
    )


def copy_small_inputs(replicate_dir: Path, fields_dir: Path, metadata_path: Path) -> None:
    for source, dest_name in (
        (replicate_dir / "system.key", "system.key"),
        (replicate_dir / "ref.key", "ref.key"),
        (metadata_path, "probe_atoms.json"),
    ):
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, fields_dir / dest_name)


def process_replicate(
    root: Path,
    out_root: Path,
    replicate_dir: Path,
    stride: int,
    max_selected_frames: int,
    frame_interval_ps: float,
    analyze_cmd: str,
    read_mode: str,
) -> dict[str, object]:
    solvent = replicate_dir.parent.name
    replicate = replicate_dir.name
    fields_dir = out_root / "md" / solvent / replicate / "fields"
    fields_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = resolve_metadata_path(replicate_dir)
    copy_small_inputs(replicate_dir, fields_dir, metadata_path)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    selected, raw_frames_read, selected_count, atom_types, read_mode = extract_selected_frames(
        replicate_dir=replicate_dir,
        fields_dir=fields_dir,
        metadata=metadata,
        stride=stride,
        max_selected_frames=max_selected_frames,
        read_mode=read_mode,
    )
    run_analyze_uind(fields_dir, analyze_cmd)
    refs = read_ref_uind(fields_dir, int(metadata["atom1_index"]), int(metadata["atom2_index"]), selected_count)

    polar = parse_polarizabilities(parse_parameter_paths(replicate_dir / "system.key"))
    atom1_type, atom2_type = atom_types
    if atom1_type not in polar or atom2_type not in polar:
        raise ValueError(f"Could not resolve polarizabilities for atom types {atom1_type}, {atom2_type}")

    rows = compute_rows(selected, refs, polar[atom1_type], polar[atom2_type], frame_interval_ps)
    field_values = [row["field_mean_MV_cm"] for row in rows]
    lengths = [row["probe_length_A"] for row in rows]
    stats = {
        "analysis": "partial_streaming_probe_field",
        "source_root": str(root),
        "source_replicate_dir": str(replicate_dir),
        "source_production_arc": str(replicate_dir / "production" / "md_start.arc"),
        "source_production_uind": str(replicate_dir / "production" / "md_start.uind"),
        "solvent": solvent,
        "replicate": replicate,
        "frames": len(rows),
        "raw_frames_read": raw_frames_read,
        "read_mode": read_mode,
        "stride": stride,
        "frame_interval_ps": frame_interval_ps,
        "estimated_window_ps": [rows[0]["estimated_time_ps"], rows[-1]["estimated_time_ps"]],
        "atom1_index": int(metadata["atom1_index"]),
        "atom2_index": int(metadata["atom2_index"]),
        "atom1_type": atom1_type,
        "atom2_type": atom2_type,
        "probe_elements": metadata.get("probe_elements"),
        "probe_label": metadata.get("probe_label"),
        "projection_axis": metadata.get("projection_axis"),
        "polarizability_atom1": polar[atom1_type],
        "polarizability_atom2": polar[atom2_type],
        "field_mean_MV_cm": mean(field_values),
        "field_std_MV_cm": stdev(field_values),
        "field_sem_MV_cm": stdev(field_values) / math.sqrt(len(field_values)),
        "probe_length_mean_A": mean(lengths),
        "probe_length_std_A": stdev(lengths),
    }

    with (fields_dir / "fields.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (fields_dir / "field_stats.json").write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stream AMOEBA production trajectories and compute the solvent-induced probe-bond field "
            "from the difference between the production and gas-phase induced dipoles."
        )
    )
    parser.add_argument("--root-dir", default=".")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--stride", type=int, default=10)
    parser.add_argument("--max-selected-frames", type=int, default=5000)
    parser.add_argument("--frame-interval-ps", type=float, default=0.1)
    parser.add_argument("--analyze-uind-cmd", default="analyze_uind")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--read-mode",
        choices=("auto", "seek-prefix", "sequential-fixed", "stream"),
        default="auto",
        help="Trajectory reading strategy. Use sequential-fixed for long windows on shared storage.",
    )
    parser.add_argument("--solvent", action="append", help="Limit to one or more solvent directory names.")
    parser.add_argument("--replicate", action="append", help="Limit to one or more replicate directory names.")
    args = parser.parse_args()

    root = Path(args.root_dir).resolve()
    out_root = Path(args.out_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    solvent_filter = set(args.solvent or [])
    replicate_filter = set(args.replicate or [])
    replicate_dirs = []
    for prod_dir in sorted((root / "md").glob("*/replicate_*/production")):
        replicate_dir = prod_dir.parent
        if solvent_filter and replicate_dir.parent.name not in solvent_filter:
            continue
        if replicate_filter and replicate_dir.name not in replicate_filter:
            continue
        replicate_dirs.append(replicate_dir)

    if not replicate_dirs:
        raise ValueError("No production directories matched the requested filters")

    def stats_to_summary(stats: dict[str, object]) -> dict[str, object]:
        return (
            {
                "solvent": stats["solvent"],
                "replicate": stats["replicate"],
                "frames": stats["frames"],
                "raw_frames_read": stats["raw_frames_read"],
                "read_mode": stats["read_mode"],
                "estimated_window_ps": f"{stats['estimated_window_ps'][0]:.3f}-{stats['estimated_window_ps'][1]:.3f}",
                "field_mean_MV_cm": stats["field_mean_MV_cm"],
                "field_std_MV_cm": stats["field_std_MV_cm"],
                "field_sem_MV_cm": stats["field_sem_MV_cm"],
                "probe_length_mean_A": stats["probe_length_mean_A"],
            }
        )

    summary_rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    workers = max(1, int(args.workers))
    if workers == 1:
        for index, replicate_dir in enumerate(replicate_dirs, start=1):
            label = f"{replicate_dir.parent.name}/{replicate_dir.name}"
            print(f"[{index}/{len(replicate_dirs)}] extracting {label}", flush=True)
            try:
                stats = process_replicate(
                    root=root,
                    out_root=out_root,
                    replicate_dir=replicate_dir,
                    stride=args.stride,
                    max_selected_frames=args.max_selected_frames,
                    frame_interval_ps=args.frame_interval_ps,
                    analyze_cmd=args.analyze_uind_cmd,
                    read_mode=args.read_mode,
                )
            except Exception as exc:
                errors.append({"replicate": label, "error": repr(exc)})
                print(f"  ERROR {label}: {exc}", flush=True)
                continue
            summary_rows.append(stats_to_summary(stats))
            print(
                f"  mean field {stats['field_mean_MV_cm']:.4f} MV/cm "
                f"from {stats['frames']} frames",
                flush=True,
            )
    else:
        print(f"Processing {len(replicate_dirs)} replicate(s) with {workers} worker(s)", flush=True)
        future_to_label: dict[concurrent.futures.Future[dict[str, object]], str] = {}
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            for replicate_dir in replicate_dirs:
                label = f"{replicate_dir.parent.name}/{replicate_dir.name}"
                future = executor.submit(
                    process_replicate,
                    root,
                    out_root,
                    replicate_dir,
                    args.stride,
                    args.max_selected_frames,
                    args.frame_interval_ps,
                    args.analyze_uind_cmd,
                    args.read_mode,
                )
                future_to_label[future] = label
                print(f"  submitted {label}", flush=True)
            completed = 0
            for future in concurrent.futures.as_completed(future_to_label):
                label = future_to_label[future]
                completed += 1
                try:
                    stats = future.result()
                except Exception as exc:
                    errors.append({"replicate": label, "error": repr(exc)})
                    print(f"[{completed}/{len(replicate_dirs)}] ERROR {label}: {exc}", flush=True)
                    continue
                summary_rows.append(stats_to_summary(stats))
                print(
                    f"[{completed}/{len(replicate_dirs)}] {label}: "
                    f"{stats['field_mean_MV_cm']:.4f} MV/cm from {stats['frames']} frames",
                    flush=True,
                )

    if summary_rows:
        with (out_root / "partial_field_summary.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0].keys()))
            writer.writeheader()
            writer.writerows(summary_rows)
    (out_root / "partial_field_errors.json").write_text(
        json.dumps(errors, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    metadata = {
        "root_dir": str(root),
        "out_dir": str(out_root),
        "stride": args.stride,
        "max_selected_frames": args.max_selected_frames,
        "frame_interval_ps": args.frame_interval_ps,
        "replicates_requested": len(replicate_dirs),
        "replicates_completed": len(summary_rows),
        "replicates_failed": len(errors),
    }
    (out_root / "partial_field_run.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
