#!/usr/bin/env python3
"""
Recompute broadened spectra in an HDF5 database from raw frequencies/intensities.

Supported methods:
    - lorentzian_convolution
    - broaden_spectrum

The common broadening parameter is named "width" for both methods.
For the Voigt-style method, "width" is interpreted as FWHM.
For the Lorentzian method, the code follows half_width = width / 2.

Examples:
    python3 rebroaden_spectra.py spectra.h5
    python3 rebroaden_spectra.py spectra.h5 -o spectra_lorentzian.h5 --method lorentzian_convolution --width 12
    python3 rebroaden_spectra.py spectra.h5 --processes 8 --chunksize 8
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
from datetime import datetime, timezone

import h5py
import numpy as np

try:
    from numba import njit, prange

    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False


DEFAULT_SPEC_LENGTH = 4000
DEFAULT_BATCH_SIZE = 1000
DEFAULT_CHUNKSIZE = 1
SPECTRUM_DECIMALS = 4
METHOD_ALIASES = {
    "lorentzian": "lorentzian_convolution",
    "lorentzian_convolution": "lorentzian_convolution",
    "voigt": "broaden_spectrum",
    "broaden_spectrum": "broaden_spectrum",
}


if HAS_NUMBA:
    @njit(cache=True, fastmath=True)
    def lorentzian_convolution(
        frequencies: np.ndarray,
        intensities: np.ndarray,
        spec_length: int = DEFAULT_SPEC_LENGTH,
        width: float = 20.0,
    ) -> np.ndarray:
        result = np.zeros(spec_length, dtype=np.float32)
        half_width = width / 2.0
        half_width_sq = half_width * half_width
        scale = 100.0 * half_width / np.pi
        n_modes = len(frequencies)

        for i in range(n_modes):
            freq = frequencies[i]
            intensity = intensities[i]
            if freq < 0.0:
                continue

            amp = intensity * scale
            for j in range(spec_length):
                x = j + 1.0
                dx = x - freq
                denom = dx * dx + half_width_sq
                result[j] += amp / denom

        return result


    @njit(cache=True, fastmath=True)
    def _voigt_kernel(x, pos, width, amp, shape):
        n = len(x)
        result = np.zeros(n, dtype=np.float32)
        sigma = width / 2.35482
        gamma = width / 2.0

        for i in prange(n):
            dx = x[i] - pos
            g = np.exp(-(dx * dx) / (2.0 * sigma * sigma))
            l = gamma * gamma / (dx * dx + gamma * gamma)
            result[i] = amp * ((1.0 - shape) * g + shape * l)

        return result


    @njit(cache=True, fastmath=True)
    def broaden_spectrum(
        freqs,
        intensities,
        spec_length: int = DEFAULT_SPEC_LENGTH,
        width: float = 20.0,
    ):
        y = np.zeros(spec_length, dtype=np.float32)
        x = np.arange(1, spec_length + 1, dtype=np.float32)
        n_modes = len(freqs)

        for i in range(n_modes):
            freq = freqs[i]
            intensity = intensities[i]
            if freq <= 0.0 or freq > spec_length or intensity <= 0.0:
                continue
            y += _voigt_kernel(x, freq, width, intensity, 0.5)

        return y
else:
    def lorentzian_convolution(
        frequencies: np.ndarray,
        intensities: np.ndarray,
        spec_length: int = DEFAULT_SPEC_LENGTH,
        width: float = 20.0,
    ) -> np.ndarray:
        output_range = np.arange(1, spec_length + 1, dtype=np.float32)
        result = np.zeros(spec_length, dtype=np.float64)
        half_width = width / 2.0
        scale = 100.0 * half_width / np.pi

        for freq, intensity in zip(frequencies, intensities):
            if freq < 0.0:
                continue
            denom = (output_range - freq) ** 2 + half_width**2
            result += intensity * scale / denom

        return result.astype(np.float32)


    def _voigt_kernel(x, pos, width, amp, shape):
        sigma = width / 2.35482
        gamma = width / 2.0
        dx = x - pos
        g = np.exp(-(dx * dx) / (2.0 * sigma * sigma))
        l = gamma * gamma / (dx * dx + gamma * gamma)
        return (amp * ((1.0 - shape) * g + shape * l)).astype(np.float32)


    def broaden_spectrum(
        freqs,
        intensities,
        spec_length: int = DEFAULT_SPEC_LENGTH,
        width: float = 20.0,
    ):
        y = np.zeros(spec_length, dtype=np.float32)
        x = np.arange(1, spec_length + 1, dtype=np.float32)
        n_modes = len(freqs)

        for i in range(n_modes):
            freq = freqs[i]
            intensity = intensities[i]
            if freq <= 0.0 or freq > spec_length or intensity <= 0.0:
                continue
            y += _voigt_kernel(x, freq, width, intensity, 0.5)

        return y


def parse_method(method_name: str) -> str:
    method_key = method_name.strip().lower()
    if method_key not in METHOD_ALIASES:
        valid = ", ".join(sorted(METHOD_ALIASES))
        raise ValueError(f"Unsupported method '{method_name}'. Valid values: {valid}")
    return METHOD_ALIASES[method_key]


def infer_spec_length(src_file: h5py.File, explicit_spec_length: int | None) -> int:
    if explicit_spec_length is not None:
        return explicit_spec_length
    if "spectrum" in src_file and len(src_file["spectrum"].shape) == 2:
        return int(src_file["spectrum"].shape[1])
    return DEFAULT_SPEC_LENGTH


def infer_output_path(input_path: str, method: str, width: float) -> str:
    stem, ext = os.path.splitext(input_path)
    width_label = f"{width:g}"
    return f"{stem}_{method}_w{width_label}{ext or '.h5'}"


def validate_input_file(src_file: h5py.File) -> int:
    required = ("smiles", "frequency", "intensity")
    missing = [name for name in required if name not in src_file]
    if missing:
        raise KeyError(f"Input HDF5 is missing required datasets: {', '.join(missing)}")

    total = int(src_file["smiles"].shape[0])
    for name in ("frequency", "intensity"):
        if int(src_file[name].shape[0]) != total:
            raise ValueError(f"Dataset '{name}' length does not match 'smiles'")
    return total


def copy_non_spectrum_datasets(src_file: h5py.File, dst_file: h5py.File) -> None:
    for key, value in src_file.attrs.items():
        dst_file.attrs[key] = value

    for dataset_name in src_file.keys():
        if dataset_name == "spectrum":
            continue
        src_file.copy(dataset_name, dst_file, name=dataset_name)


def create_output_spectrum_dataset(
    src_file: h5py.File,
    dst_file: h5py.File,
    total: int,
    spec_length: int,
    batch_size: int,
):
    compression = "lzf"
    compression_opts = None
    chunks = (min(batch_size, total), spec_length)

    if "spectrum" in src_file:
        src_spectrum = src_file["spectrum"]
        if src_spectrum.compression is not None:
            compression = src_spectrum.compression
            compression_opts = src_spectrum.compression_opts
        if src_spectrum.chunks is not None and len(src_spectrum.chunks) == 2:
            src_chunk_rows, src_chunk_cols = src_spectrum.chunks
            if src_chunk_cols == spec_length:
                chunks = (min(src_chunk_rows, total), spec_length)

    if chunks[0] <= 0:
        chunks = (1, spec_length)

    return dst_file.create_dataset(
        "spectrum",
        shape=(total, spec_length),
        dtype=np.float32,
        chunks=chunks,
        compression=compression,
        compression_opts=compression_opts,
        scaleoffset=SPECTRUM_DECIMALS,
    )


def compute_one_spectrum(
    method: str,
    freqs: np.ndarray,
    intensities: np.ndarray,
    spec_length: int,
    width: float,
) -> np.ndarray:
    freqs = np.asarray(freqs, dtype=np.float32)
    intensities = np.asarray(intensities, dtype=np.float32)

    if method == "lorentzian_convolution":
        return lorentzian_convolution(freqs, intensities, spec_length, width)
    return broaden_spectrum(freqs, intensities, spec_length, width)


def quantize_spectrum(spectrum: np.ndarray) -> np.ndarray:
    np.round(spectrum, decimals=SPECTRUM_DECIMALS, out=spectrum)
    return spectrum


def warm_up_numba(method: str, spec_length: int, width: float) -> None:
    if not HAS_NUMBA:
        return

    sample_freqs = np.asarray([10.0, 100.0, 250.0], dtype=np.float32)
    sample_intensities = np.asarray([0.1, 1.0, 0.5], dtype=np.float32)
    compute_one_spectrum(method, sample_freqs, sample_intensities, spec_length, width)


def compute_spectrum_task(task):
    row_index, method, freqs, intensities, spec_length, width = task
    spectrum = compute_one_spectrum(method, freqs, intensities, spec_length, width)
    return row_index, quantize_spectrum(spectrum)


def build_batch_tasks(
    method: str,
    batch_freqs: np.ndarray,
    batch_intensities: np.ndarray,
    spec_length: int,
    width: float,
):
    for row_index, (freqs, intensities) in enumerate(zip(batch_freqs, batch_intensities)):
        yield row_index, method, freqs, intensities, spec_length, width


def compute_batch_spectra_serial(
    method: str,
    batch_freqs: np.ndarray,
    batch_intensities: np.ndarray,
    spec_length: int,
    width: float,
) -> np.ndarray:
    batch_spectra = np.zeros((len(batch_freqs), spec_length), dtype=np.float32)
    for task in build_batch_tasks(method, batch_freqs, batch_intensities, spec_length, width):
        row_index, spectrum = compute_spectrum_task(task)
        batch_spectra[row_index] = spectrum
    return batch_spectra


def compute_batch_spectra_parallel(
    pool: multiprocessing.pool.Pool,
    method: str,
    batch_freqs: np.ndarray,
    batch_intensities: np.ndarray,
    spec_length: int,
    width: float,
    chunksize: int,
) -> np.ndarray:
    batch_spectra = np.zeros((len(batch_freqs), spec_length), dtype=np.float32)
    tasks = build_batch_tasks(method, batch_freqs, batch_intensities, spec_length, width)
    for row_index, spectrum in pool.imap(compute_spectrum_task, tasks, chunksize=chunksize):
        batch_spectra[row_index] = spectrum
    return batch_spectra


def recompute_database(
    input_path: str,
    output_path: str,
    method: str,
    width: float,
    spec_length: int,
    batch_size: int,
    processes: int,
    chunksize: int,
) -> None:
    pool = None
    if processes > 1:
        pool = multiprocessing.Pool(processes=processes)

    try:
        with h5py.File(input_path, "r") as src_file:
            total = validate_input_file(src_file)

            with h5py.File(output_path, "w") as dst_file:
                copy_non_spectrum_datasets(src_file, dst_file)
                spectrum_ds = create_output_spectrum_dataset(
                    src_file, dst_file, total, spec_length, batch_size
                )
                if "spectrum" in src_file:
                    for key, value in src_file["spectrum"].attrs.items():
                        spectrum_ds.attrs[key] = value

                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                dst_file.attrs["rebroaden_source_file"] = os.path.abspath(input_path)
                dst_file.attrs["rebroaden_method"] = method
                dst_file.attrs["rebroaden_width"] = float(width)
                dst_file.attrs["rebroaden_spec_length"] = int(spec_length)
                dst_file.attrs["rebroaden_created_at_utc"] = now

                spectrum_ds.attrs["broadening_method"] = method
                spectrum_ds.attrs["broadening_width"] = float(width)
                spectrum_ds.attrs["broadening_spec_length"] = int(spec_length)
                spectrum_ds.attrs["rebroaden_created_at_utc"] = now

                for start in range(0, total, batch_size):
                    end = min(start + batch_size, total)
                    batch_freqs = src_file["frequency"][start:end]
                    batch_intensities = src_file["intensity"][start:end]

                    if pool is None:
                        batch_spectra = compute_batch_spectra_serial(
                            method, batch_freqs, batch_intensities, spec_length, width
                        )
                    else:
                        batch_spectra = compute_batch_spectra_parallel(
                            pool,
                            method,
                            batch_freqs,
                            batch_intensities,
                            spec_length,
                            width,
                            chunksize,
                        )

                    spectrum_ds[start:end] = batch_spectra
                    print(f"[{end:>7d}/{total}] spectra recomputed")
    finally:
        if pool is not None:
            pool.close()
            pool.join()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recompute broadened spectra in an HDF5 database."
    )
    parser.add_argument("input_h5", help="Input HDF5 file path")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output HDF5 file path. Default: derived from input file name.",
    )
    parser.add_argument(
        "-m",
        "--method",
        default="broaden_spectrum",
        help=(
            "Broadening method. Supported values: "
            "lorentzian_convolution/lorentzian, broaden_spectrum/voigt"
        ),
    )
    parser.add_argument(
        "--width",
        type=float,
        default=20.0,
        help="Common broadening width parameter for both methods",
    )
    parser.add_argument(
        "--spec-length",
        type=int,
        default=None,
        help="Spectrum length. Default: reuse input spectrum length if present, else 4000.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Number of molecules processed per batch",
    )
    parser.add_argument(
        "--processes",
        type=int,
        default=1,
        help="Worker process count for spectrum recomputation. Use 0 for all CPUs.",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=DEFAULT_CHUNKSIZE,
        help="Task chunksize passed to multiprocessing Pool.imap",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output file if it already exists",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    method = parse_method(args.method)
    output_path = args.output or infer_output_path(args.input_h5, method, args.width)

    if args.width <= 0:
        raise ValueError("--width must be positive")
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")
    if args.processes < 0:
        raise ValueError("--processes must be non-negative")
    if args.chunksize <= 0:
        raise ValueError("--chunksize must be positive")
    if args.spec_length is not None and args.spec_length <= 0:
        raise ValueError("--spec-length must be positive")

    processes = os.cpu_count() if args.processes == 0 else args.processes
    if processes is None or processes < 1:
        processes = 1

    input_abs = os.path.abspath(args.input_h5)
    output_abs = os.path.abspath(output_path)
    if input_abs == output_abs:
        raise ValueError("Input and output paths must be different")

    if os.path.exists(output_path):
        if not args.overwrite:
            raise FileExistsError(
                f"Output file already exists: {output_path}. Use --overwrite to replace it."
            )
        os.remove(output_path)

    with h5py.File(args.input_h5, "r") as src_file:
        spec_length = infer_spec_length(src_file, args.spec_length)

    print(f"input      : {args.input_h5}")
    print(f"output     : {output_path}")
    print(f"method     : {method}")
    print(f"width      : {args.width}")
    print(f"spec_length: {spec_length}")
    print(f"batch_size : {args.batch_size}")
    print(f"processes  : {processes}")
    print(f"chunksize  : {args.chunksize}")
    print(f"numba      : {'yes' if HAS_NUMBA else 'no'}")

    warm_up_numba(method, spec_length, args.width)
    recompute_database(
        input_path=args.input_h5,
        output_path=output_path,
        method=method,
        width=args.width,
        spec_length=spec_length,
        batch_size=args.batch_size,
        processes=processes,
        chunksize=args.chunksize,
    )
    print("done")


if __name__ == "__main__":
    main()
