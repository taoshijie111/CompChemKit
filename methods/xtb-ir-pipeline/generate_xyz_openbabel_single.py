import argparse
import multiprocessing
import multiprocessing.pool
import os
import signal
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Tuple

from openbabel import openbabel as ob
from openbabel import pybel
import periodictable as pt

OBMol = Any

_GENERATOR: Optional["ConformerGenerator"] = None
_WORKER_TIMEOUT: Optional[float] = None
_WORKER_SETTINGS: Optional[Tuple[str, int, int]] = None


class TimeoutException(Exception):
    pass


class NoDaemonPool(multiprocessing.pool.Pool):
    @staticmethod
    def _repopulate_pool_static(
        ctx: "multiprocessing.context.BaseContext",
        Process: Any,
        processes: int,
        pool: List[Any],
        inqueue: Any,
        outqueue: Any,
        initializer: Optional[Any],
        initargs: Tuple[Any, ...],
        maxtasksperchild: Optional[int],
        wrap_exception: bool,
    ) -> None:
        for _ in range(processes - len(pool)):
            w = Process(
                ctx,
                target=multiprocessing.pool.worker,
                args=(inqueue, outqueue, initializer, initargs, maxtasksperchild, wrap_exception),
            )
            w.name = w.name.replace("Process", "PoolWorker")
            w.start()
            pool.append(w)
            multiprocessing.pool.util.debug("added worker")


def _timeout_handler(signum: int, frame: Optional[Any]) -> None:
    raise TimeoutException("timeout")


@contextmanager
def time_limit(seconds: Optional[float]) -> Iterable[None]:
    if not seconds or seconds <= 0:
        yield
        return
    if not hasattr(signal, "SIGALRM"):
        yield
        return
    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, float(seconds))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def get_element_symbol(atomic_num: int) -> str:
    if atomic_num <= 0:
        return "X"
    try:
        entry = pt.elements[atomic_num]
    except Exception:
        return "X"
    symbol = getattr(entry, "symbol", None)
    if isinstance(symbol, str) and symbol:
        return symbol
    return "X"


class ConformerGenerator(object):
    """
    Generate 3D conformer with Open Babel, utilizing conformer search.
    """

    def __init__(self, force_field: str = "uff", steps: int = 500, num_search: int = 10) -> None:
        self.force_field = force_field.lower()
        self.steps = steps
        self.num_search = num_search

    def __call__(self, mol: OBMol) -> OBMol:
        return self.generate_conformers(mol)

    def generate_conformers(self, mol: OBMol) -> OBMol:
        src_obmol = mol.OBMol
        obmol = ob.OBMol(src_obmol)
        obmol.AddHydrogens()

        builder = ob.OBBuilder()
        builder.Build(obmol)

        try:
            ff = self._get_force_field()
            if ff.Setup(obmol):
                ff.WeightedRotorSearch(self.num_search, self.steps)
                ff.ConjugateGradients(self.steps)
                ff.SteepestDescent(self.steps)
                ff.GetCoordinates(obmol)
        except Exception:
            pass

        mol3d = pybel.Molecule(obmol)
        return mol3d

    def _get_force_field(self) -> "ob.OBForceField":
        name = self.force_field
        if name == "uff":
            ff_name = "uff"
        elif name.startswith("mmff94"):
            ff_name = "mmff94"
        else:
            ff_name = "uff"

        ff = ob.OBForceField.FindForceField(ff_name)
        return ff


@dataclass(frozen=True)
class JobConfig:
    output_root: str
    batch_size: int
    overwrite: bool
    force_field: str
    steps: int
    num_search: int
    log_interval: int
    chunksize: int
    processes: int
    timeout: Optional[float]


def init_worker(force_field: str, steps: int, num_search: int) -> None:
    global _GENERATOR
    global _WORKER_TIMEOUT
    global _WORKER_SETTINGS
    _GENERATOR = ConformerGenerator(force_field=force_field, steps=steps, num_search=num_search)
    _WORKER_TIMEOUT = None
    _WORKER_SETTINGS = (force_field, steps, num_search)


def init_worker_with_timeout(force_field: str, steps: int, num_search: int, timeout: Optional[float]) -> None:
    global _WORKER_TIMEOUT
    init_worker(force_field, steps, num_search)
    _WORKER_TIMEOUT = timeout


def iter_smiles(smiles_path: str) -> Iterable[Tuple[int, str]]:
    with open(smiles_path, "r") as handle:
        idx = 0
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            smiles = line.split()[0]
            yield idx, smiles
            idx += 1


def count_smiles(smiles_path: str) -> int:
    total = 0
    with open(smiles_path, "r") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            total += 1
    return total


def make_output_path(output_root: str, global_idx: int, batch_size: int) -> Tuple[str, str]:
    batch_idx = global_idx // batch_size
    rel_dir = os.path.join(
        f"batch_{batch_idx}",
        f"molecule_{global_idx}",
    )
    target_dir = os.path.join(output_root, rel_dir)
    target_path = os.path.join(target_dir, f"molecule_{global_idx}.xyz")
    return target_dir, target_path


def _process_single_molecule(
    task: Tuple[int, str, str, int, bool],
    generator: "ConformerGenerator",
    timeout: Optional[float],
) -> Tuple[str, Optional[Tuple[int, str, str]]]:
    global_idx, smiles, output_root, batch_size, overwrite = task
    target_dir, target_path = make_output_path(output_root, global_idx, batch_size)

    if not overwrite and os.path.exists(target_path):
        return ("EXIST", None)

    try:
        with time_limit(timeout):
            mol = pybel.readstring("smi", smiles)
            mol3d = generator(mol)
            num_atoms = mol3d.OBMol.NumAtoms()
            if num_atoms == 0:
                raise ValueError("empty molecule")

        os.makedirs(target_dir, exist_ok=True)
        with open(target_path, "w") as f_out:
            f_out.write(f"{num_atoms}\n")
            f_out.write(f"{smiles}\n")
            for atom in mol3d:
                symbol = get_element_symbol(atom.atomicnum)
                x, y, z = atom.coords
                f_out.write(f"{symbol}  {x:.6f}  {y:.6f}  {z:.6f}\n")

        return ("SUCCESS", None)

    except TimeoutException:
        return ("TIMEOUT", (global_idx, smiles, f"timeout>{timeout}s"))
    except Exception as exc:
        return ("FAIL", (global_idx, smiles, str(exc)))


def _subprocess_target(
    conn: "multiprocessing.connection.Connection",
    task: Tuple[int, str, str, int, bool],
    force_field: str,
    steps: int,
    num_search: int,
    timeout: Optional[float],
) -> None:
    try:
        generator = ConformerGenerator(force_field=force_field, steps=steps, num_search=num_search)
        result = _process_single_molecule(task, generator, timeout)
    except TimeoutException:
        global_idx, smiles, *_ = task
        result = ("TIMEOUT", (global_idx, smiles, f"timeout>{timeout}s"))
    except Exception as exc:
        global_idx, smiles, *_ = task
        result = ("FAIL", (global_idx, smiles, str(exc)))
    try:
        conn.send(result)
    finally:
        conn.close()


def _run_with_hard_timeout(
    task: Tuple[int, str, str, int, bool],
    timeout: float,
) -> Tuple[str, Optional[Tuple[int, str, str]]]:
    settings = _WORKER_SETTINGS or ("uff", 1000, 10)
    force_field, steps, num_search = settings
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_subprocess_target,
        args=(child_conn, task, force_field, steps, num_search, timeout),
    )
    proc.daemon = True
    proc.start()
    child_conn.close()

    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        parent_conn.close()
        global_idx, smiles, *_ = task
        return ("TIMEOUT", (global_idx, smiles, f"timeout>{timeout}s (killed)"))

    result: Optional[Tuple[str, Optional[Tuple[int, str, str]]]] = None
    if parent_conn.poll(1.0):
        try:
            result = parent_conn.recv()
        except EOFError:
            result = None
    parent_conn.close()
    if result is None:
        global_idx, smiles, *_ = task
        return ("FAIL", (global_idx, smiles, "no result from subprocess"))
    return result


def worker_task(task: Tuple[int, str, str, int, bool]) -> Tuple[str, Optional[Tuple[int, str, str]]]:
    if _WORKER_TIMEOUT:
        global_idx, smiles, output_root, batch_size, overwrite = task
        if not overwrite:
            _, target_path = make_output_path(output_root, global_idx, batch_size)
            if os.path.exists(target_path):
                return ("EXIST", None)
        return _run_with_hard_timeout(task, _WORKER_TIMEOUT)

    if _GENERATOR is None:
        generator = ConformerGenerator()
    else:
        generator = _GENERATOR
    return _process_single_molecule(task, generator, None)


def process_smiles_file(smiles_path: str, config: JobConfig) -> None:
    total = count_smiles(smiles_path)
    if total == 0:
        print(f"No SMILES found in {smiles_path}")
        return

    os.makedirs(config.output_root, exist_ok=True)

    stats = {"EXIST": 0, "SUCCESS": 0, "FAIL": 0, "TIMEOUT": 0}
    failures: List[Tuple[int, str, str]] = []
    label = os.path.basename(smiles_path)

    tasks = (
        (idx, smiles, config.output_root, config.batch_size, config.overwrite)
        for idx, smiles in iter_smiles(smiles_path)
    )

    pool_cls = NoDaemonPool if config.timeout else multiprocessing.Pool
    with pool_cls(
        processes=config.processes,
        initializer=init_worker_with_timeout,
        initargs=(config.force_field, config.steps, config.num_search, config.timeout),
    ) as pool:
        for status, info in pool.imap_unordered(worker_task, tasks, chunksize=config.chunksize):
            stats[status] += 1
            if status in {"FAIL", "TIMEOUT"} and info is not None:
                failures.append(info)
            total_processed = sum(stats.values())
            if config.log_interval > 0 and total_processed % config.log_interval == 0:
                print(
                    f"[{label}] "
                    f"{total_processed}/{total} "
                    f"success={stats['SUCCESS']} "
                    f"fail={stats['FAIL']} timeout={stats['TIMEOUT']} exist={stats['EXIST']}",
                    end="\n",
                )

    print(
        f"[{label}] Done. "
        f"success={stats['SUCCESS']} "
        f"fail={stats['FAIL']} timeout={stats['TIMEOUT']} exist={stats['EXIST']}"
    )

    if failures:
        error_log_path = os.path.join(config.output_root, "error.log")
        with open(error_log_path, "w") as f_err:
            f_err.write("index\tsmiles\treason\n")
            for idx, smiles, reason in failures:
                f_err.write(f"{idx}\t{smiles}\t{reason}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate XYZ coordinates from a SMILES file with Open Babel conformer search."
    )
    parser.add_argument("--input-smi", required=True, help="Path to a .smi file.")
    parser.add_argument("--output-root", default="xyz_output", help="Root output folder.")
    parser.add_argument("--batch-size", type=int, default=1000, help="Max molecules per batch folder.")
    parser.add_argument("--processes", type=int, default=multiprocessing.cpu_count(), help="Process count.")
    parser.add_argument("--force-field", default="uff", help="Force field (uff, mmff94, mmff94s).")
    parser.add_argument("--steps", type=int, default=1000, help="Optimization steps per conformer.")
    parser.add_argument("--num-search", type=int, default=10, help="Number of conformers to search.")
    parser.add_argument("--chunksize", type=int, default=10, help="Multiprocessing chunksize.")
    parser.add_argument("--log-interval", type=int, default=100, help="Progress logging interval.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=0,
        help="Per-molecule timeout in seconds (0 disables).",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing XYZ files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = JobConfig(
        output_root=args.output_root,
        batch_size=args.batch_size,
        overwrite=args.overwrite,
        force_field=args.force_field,
        steps=args.steps,
        num_search=args.num_search,
        log_interval=args.log_interval,
        chunksize=args.chunksize,
        processes=args.processes,
        timeout=args.timeout if args.timeout and args.timeout > 0 else None,
    )

    start = time.time()
    print(f"Processing {args.input_smi}")
    process_smiles_file(args.input_smi, config)
    elapsed = time.time() - start
    print(f"All done. Time elapsed: {elapsed:.2f}s")


if __name__ == "__main__":
    main()
