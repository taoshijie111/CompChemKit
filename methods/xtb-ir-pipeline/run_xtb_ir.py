import argparse
import gzip 
import os
import re
import shutil
import pickle
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict, Set, Any

import numpy as np

try:
    from xtbgaussian_parser import XTBGaussianParser
except ImportError:
    class XTBGaussianParser:
        def __init__(self, path): pass
        vibfreqs = np.array([])
        vibdisps = np.array([])
        vibirs = np.array([])
        atomcoords = np.array([])
        atomnos = np.array([])

MOLECULE_DIR_RE = re.compile(r"^molecule_\d+$")
MOLECULE_FILE_RE = re.compile(r"^molecule_\d+\.xyz$")
CHARGE_RE = re.compile(r"\[([^\[\]]*?)([+-])(\d*)\]")
DEFAULT_CLEANUP_PATTERNS = [] 
BATCH_ARCHIVE_FORMAT = "xtb_batch_pickle_stream_v1"

_BATCH_ARCHIVE_LOCKS: Dict[Path, threading.Lock] = {}
_BATCH_ARCHIVE_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class JobConfig:
    task_name: str
    cores_per_task: int
    max_iterations: int
    disp_scale: float
    imag_threshold: float
    xtb_path: str
    log_name: str
    skip_completed: bool
    use_ptb: bool
    use_raman: bool
    cleanup_whitelist: List[str]


def iter_molecule_xyz(root_dir: Path) -> Iterable[Path]:
    for path in root_dir.rglob("molecule_*.xyz"):
        if not path.is_file():
            continue
        if not MOLECULE_FILE_RE.match(path.name):
            continue
        if not MOLECULE_DIR_RE.match(path.parent.name):
            continue
        if path.stem != path.parent.name:
            continue
        yield path


def read_xyz(path: Path) -> Tuple[str, List[str], np.ndarray]:
    with path.open("r") as handle:
        lines = [line.rstrip("\n") for line in handle]
    if len(lines) < 3:
        raise ValueError(f"invalid xyz file: {path}")
    try:
        atom_count = int(lines[0].strip())
    except ValueError:
        raise ValueError(f"invalid atom count in {path}")
    smiles = lines[1].strip()
    atoms: List[str] = []
    coords: List[List[float]] = []
    for line in lines[2:2 + atom_count]:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"invalid xyz line in {path}: {line}")
        atoms.append(parts[0])
        coords.append([float(parts[1]), float(parts[2]), float(parts[3])])
    if len(atoms) != atom_count:
        raise ValueError(f"atom count mismatch in {path}")
    return smiles, atoms, np.array(coords, dtype=float)


def tail_contains(path: Path, needle: str, max_bytes: int = 65536) -> bool:
    if not path.exists():
        return False
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            data = handle.read()
        return needle in data.decode("utf-8", errors="ignore")
    except OSError:
        return False


def read_smiles_header(xyz_path: Path) -> str:
    with xyz_path.open("r") as handle:
        handle.readline()
        smiles = handle.readline().strip()
    if not smiles:
        raise ValueError(f"missing smiles header in {xyz_path}")
    return smiles


def extract_result_data(parser: Any) -> Dict[str, Any]:
    try:
        _atomnos = parser.atomnos if hasattr(parser, "atomnos") else np.array([])
        _atomcoords = parser.atomcoords if hasattr(parser, "atomcoords") else np.array([])
        _vibfreqs = parser.vibfreqs if hasattr(parser, "vibfreqs") else np.array([])
        _vibirs = parser.vibirs if hasattr(parser, "vibirs") else np.array([])

        return {
            "atomnos": _atomnos.astype(np.int16) if _atomnos.size > 0 else _atomnos,
            "atomcoords": _atomcoords.astype(np.float32) if _atomcoords.size > 0 else _atomcoords,
            "vibfreqs": _vibfreqs.astype(np.float32) if _vibfreqs.size > 0 else _vibfreqs,
            "vibirs": _vibirs.astype(np.float32) if _vibirs.size > 0 else _vibirs,
        }
    except Exception as e:
        raise ValueError(f"Failed to extract/convert parser data: {e}") from e


def get_batch_archive_path(task_dir: Path, task_name: str) -> Path:
    return task_dir.parent.parent / f"{task_name}_batch_results.pkl.gz"


def read_converged_metadata(marker_path: Path) -> Dict[str, str]:
    if not marker_path.exists():
        return {}
    try:
        text = marker_path.read_text().strip()
    except OSError:
        return {}

    metadata: Dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def get_batch_archive_lock(archive_path: Path) -> threading.Lock:
    with _BATCH_ARCHIVE_LOCKS_GUARD:
        lock = _BATCH_ARCHIVE_LOCKS.get(archive_path)
        if lock is None:
            lock = threading.Lock()
            _BATCH_ARCHIVE_LOCKS[archive_path] = lock
        return lock


def write_converged_marker(task_dir: Path, archive_path: Path) -> None:
    marker_path = task_dir / "CONVERGED"
    marker_path.write_text(
        f"format={BATCH_ARCHIVE_FORMAT}\n"
        f"archive={archive_path.name}\n"
        f"molecule={task_dir.parent.name}\n"
    )


def cleanup_task_dir(task_dir: Path, whitelist: Set[str]) -> None:
    for item in task_dir.iterdir():
        if item.name not in whitelist:
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except OSError:
                pass


def append_batch_record(task_dir: Path, task_name: str, smiles: str, data: Dict[str, Any]) -> Path:
    archive_path = get_batch_archive_path(task_dir, task_name)
    record = {
        "molecule": task_dir.parent.name,
        "smiles": smiles,
        **data,
    }
    lock = get_batch_archive_lock(archive_path)
    with lock:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(archive_path, "ab") as handle:
            pickle.dump(record, handle, protocol=pickle.HIGHEST_PROTOCOL)
        write_converged_marker(task_dir, archive_path)
    return archive_path


def finalize_task(task_dir: Path, task_name: str, smiles: str, data: Dict[str, Any]) -> bool:
    try:
        archive_path = append_batch_record(task_dir, task_name, smiles, data)
    except Exception as e:
        print(f"Error saving batch archive for {task_dir}: {e}")
        return False

    cleanup_task_dir(task_dir, whitelist={"CONVERGED"})
    return archive_path.exists()


def finalize_task_from_parser(task_dir: Path, task_name: str, smiles: str, parser: Any) -> bool:
    try:
        data = extract_result_data(parser)
    except Exception as e:
        print(f"Warning: Failed to extract/convert data in {task_dir}: {e}")
        return False
    return finalize_task(task_dir, task_name, smiles, data)


def migrate_legacy_result(task_dir: Path, xyz_path: Path, task_name: str) -> Tuple[bool, str]:
    result_path = task_dir / "result.pkl.gz"
    if not result_path.exists():
        return False, "missing_legacy_result"

    try:
        with gzip.open(result_path, "rb") as handle:
            data = pickle.load(handle)
        smiles = read_smiles_header(xyz_path)
    except Exception as exc:
        return False, f"legacy_migration_failed({exc})"

    if not finalize_task(task_dir, task_name, smiles, data):
        return False, "legacy_archive_failed"
    return True, "skipped(migrated_legacy_result)"


def is_completed_run(
    xyz_path: Path,
    task_dir: Path,
    task_name: str,
    log_name: str,
    imag_threshold: float,
) -> Tuple[bool, str]:
    converged_marker = task_dir / "CONVERGED"
    archive_path = get_batch_archive_path(task_dir, task_name)
    if converged_marker.exists():
        metadata = read_converged_metadata(converged_marker)
        if (
            metadata.get("format") == BATCH_ARCHIVE_FORMAT
            and metadata.get("archive") == archive_path.name
            and metadata.get("molecule") == task_dir.parent.name
        ):
            return True, "skipped(converged)"
        migrated, status = migrate_legacy_result(task_dir, xyz_path, task_name)
        if migrated:
            return True, status

    log_path = task_dir / log_name
    if not log_path.exists():
        return False, "not_started"

    if not tail_contains(log_path, "normal termination of xtb"):
        return False, "incomplete_log"

    g98_path = task_dir / "g98.out"
    if not g98_path.exists():
        return False, "missing_g98"

    try:
        parser = XTBGaussianParser(str(g98_path))
    except Exception:
        return False, "parse_error"

    freqs = parser.vibfreqs
    if freqs.size == 0:
        return False, "no_freqs"

    if select_imaginary_mode(freqs, imag_threshold) is None:
        try:
            smiles = read_smiles_header(xyz_path)
        except Exception as exc:
            return False, f"smiles_read_failed({exc})"
        if finalize_task_from_parser(task_dir, task_name, smiles, parser):
            return True, "skipped(retro_cleaned)"
        return False, "archive_failed"
    
    return False, "imaginary_exists"


def write_xyz(path: Path, smiles: str, atoms: List[str], coords: np.ndarray) -> None:
    if coords.shape[0] != len(atoms):
        raise ValueError(f"coordinate size mismatch for {path}")
    lines = [str(len(atoms)), smiles]
    for atom, (x, y, z) in zip(atoms, coords):
        lines.append(f"{atom}  {x: .6f}  {y: .6f}  {z: .6f}")
    path.write_text("\n".join(lines) + "\n")


def infer_charge_uhf(smiles: str) -> Tuple[int, int]:
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            charge = sum(atom.GetFormalCharge() for atom in mol.GetAtoms())
            num_radicals = sum(atom.GetNumRadicalElectrons() for atom in mol.GetAtoms())
            mult = int(num_radicals + 1)
            return int(charge), max(0, mult - 1)
    except Exception:
        pass
    
    charge = 0
    for match in CHARGE_RE.finditer(smiles):
        sign = match.group(2)
        magnitude = match.group(3)
        delta = int(magnitude) if magnitude else 1
        if sign == "-":
            delta *= -1
        charge += delta
    return charge, 0


def run_xtb(
    xyz_path: Path,
    smiles: str,
    atoms: List[str],
    coords: np.ndarray,
    config: JobConfig,
) -> Tuple[int, Path]:
    task_dir = xyz_path.parent / config.task_name
    task_dir.mkdir(parents=True, exist_ok=True)
    input_xyz = task_dir / xyz_path.name
    write_xyz(input_xyz, smiles, atoms, coords)
    
    charge, uhf = infer_charge_uhf(smiles)
    log_path = task_dir / config.log_name
    
    cmd = [
        config.xtb_path,
        input_xyz.name,
        "--ohess",
        "extreme",
        "-P",
        str(config.cores_per_task),
        "--chrg",
        str(charge),
        "--uhf",
        str(uhf),
    ]
    if config.use_ptb:
        cmd.append("--ptb")
    if config.use_raman:
        cmd.append("--raman")
    
    with log_path.open("w") as handle:
        proc = subprocess.run(
            cmd,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
            cwd=task_dir,
        )
    return proc.returncode, log_path


def select_imaginary_mode(freqs: np.ndarray, threshold: float) -> Optional[int]:
    if freqs.size == 0:
        return None
    idx = int(np.argmin(freqs))
    if freqs[idx] < threshold:
        return idx
    return None


def perturb_geometry(
    coords: np.ndarray,
    disps: np.ndarray,
    mode_index: int,
    scale: float,
) -> np.ndarray:
    disp = disps[mode_index]
    return coords + scale * disp


def process_molecule(xyz_path: Path, config: JobConfig) -> Tuple[Path, str]:
    task_dir = xyz_path.parent / config.task_name
    
    if config.skip_completed:
        is_done, status_msg = is_completed_run(
            xyz_path,
            task_dir,
            config.task_name,
            config.log_name,
            config.imag_threshold,
        )
        if is_done:
            return xyz_path, status_msg

    for attempt in range(1, config.max_iterations + 1):
        try:
            smiles, atoms, coords = read_xyz(xyz_path)
        except Exception as e:
             return xyz_path, f"read_error({e})"

        returncode, log_path = run_xtb(xyz_path, smiles, atoms, coords, config)
        
        if returncode != 0:
            for p in task_dir.glob("*"):
                if p.name not in [config.log_name, xyz_path.name]:
                    try: p.unlink() 
                    except: pass
            return xyz_path, f"xtb_failed(returncode={returncode})"

        try:
            g98_path = log_path.parent / "g98.out"
            if not g98_path.exists():
                return xyz_path, "missing_g98_out"
            parser = XTBGaussianParser(str(g98_path))
        except Exception as exc:
            return xyz_path, f"parse_failed({exc})"

        freqs = parser.vibfreqs
        disps = parser.vibdisps
        if freqs.size == 0 or disps.size == 0:
            return xyz_path, "no_frequencies"

        mode_index = select_imaginary_mode(freqs, config.imag_threshold)
        
        if mode_index is None:
            if finalize_task_from_parser(task_dir, config.task_name, smiles, parser):
                return xyz_path, f"ok(iterations={attempt})"
            return xyz_path, "archive_failed"

        base_coords = parser.atomcoords
        if base_coords.size == 0:
            base_coords = coords
        if base_coords.shape != disps[mode_index].shape:
            return xyz_path, "shape_mismatch"

        new_coords = perturb_geometry(base_coords, disps, mode_index, config.disp_scale)
        write_xyz(xyz_path, smiles, atoms, new_coords)
        
        for p in task_dir.glob("hessian"):
             try: p.unlink() 
             except: pass

    return xyz_path, f"imaginary_remaining(iterations={config.max_iterations})"


def resolve_workers(max_workers: Optional[int], cores_per_task: int) -> int:
    if max_workers is not None and max_workers > 0:
        return max_workers
    cpu_count = os.cpu_count() or 1
    if cores_per_task <= 0:
        return 1
    return max(1, cpu_count // cores_per_task)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run xtb IR with aggressive cleanup and compressed result extraction.")
    parser.add_argument("--root-dir", default="xyz", help="Root directory.")
    parser.add_argument("--task-name", default="xtb_ir", help="Task directory name.")
    parser.add_argument("--max-workers", type=int, default=None, help="Concurrent tasks.")
    parser.add_argument("--cores-per-task", type=int, default=4, help="Cores per task.")
    parser.add_argument("--max-iterations", type=int, default=5, help="Max cleanup iterations.")
    parser.add_argument("--disp-scale", type=float, default=0.3, help="Displacement scale.")
    parser.add_argument("--imag-threshold", type=float, default=-1.0, help="Imaginary threshold.")
    parser.add_argument("--xtb-path", default="xtb", help="xtb executable path.")
    parser.add_argument("--log-name", default="xtb.log", help="Log filename.")
    parser.add_argument("--skip-completed", action="store_true", help="Skip completed tasks.")
    parser.add_argument("--ptb", action="store_true", help="Use --ptb.")
    parser.add_argument("--raman", action="store_true", help="Use --raman.")
    parser.add_argument("--cleanup-whitelist", nargs="*", default=[], help="Patterns to keep (deprecated).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root_dir = Path(args.root_dir)
    if not root_dir.exists():
        raise SystemExit(f"root dir not found: {root_dir}")

    config = JobConfig(
        task_name=args.task_name,
        cores_per_task=args.cores_per_task,
        max_iterations=args.max_iterations,
        disp_scale=args.disp_scale,
        imag_threshold=args.imag_threshold,
        xtb_path=args.xtb_path,
        log_name=args.log_name,
        skip_completed=args.skip_completed,
        use_ptb=args.ptb,
        use_raman=args.raman,
        cleanup_whitelist=list(args.cleanup_whitelist),
    )

    max_workers = resolve_workers(args.max_workers, args.cores_per_task)
    max_queue_size = max_workers * 2
    
    print(f"Start processing {root_dir} with {max_workers} workers.")
    print("Mode: Extract results (float32/int16) -> Save GZIPPED Pickle -> Delete intermediate files.")

    pending_futures = {}
    completed_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for xyz_path in iter_molecule_xyz(root_dir):
            
            if len(pending_futures) >= max_queue_size:
                done, _ = wait(pending_futures.keys(), return_when=FIRST_COMPLETED)
                for fut in done:
                    path = pending_futures.pop(fut)
                    try:
                        _, status = fut.result()
                    except Exception as exc:
                        status = f"error({exc})"
                    
                    completed_count += 1
                    print(f"[{completed_count}] {path} -> {status}")

            future = executor.submit(process_molecule, xyz_path, config)
            pending_futures[future] = xyz_path

        print("Scanning finished. Waiting for pending tasks...")
        while pending_futures:
            done, _ = wait(pending_futures.keys(), return_when=FIRST_COMPLETED)
            for fut in done:
                path = pending_futures.pop(fut)
                try:
                    _, status = fut.result()
                except Exception as exc:
                    status = f"error({exc})"
                
                completed_count += 1
                print(f"[{completed_count}] {path} -> {status}")

    print(f"All done. Processed {completed_count} molecules.")


if __name__ == "__main__":
    main()
