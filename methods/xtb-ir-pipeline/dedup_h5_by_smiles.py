#!/usr/bin/env python3

import argparse
import os
import shutil
from pathlib import Path

import h5py
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deduplicate an HDF5 spectra file by smiles, keeping the first occurrence.")
    parser.add_argument("input", help="Input HDF5 file.")
    parser.add_argument("-o", "--output", help="Output HDF5 file. Defaults to <input>.dedup.h5")
    parser.add_argument("--replace", action="store_true", help="Replace the input file after writing a deduplicated copy.")
    parser.add_argument("--backup-suffix", default=".bak", help="Backup suffix used with --replace.")
    return parser.parse_args()


def decode_smiles(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def get_keep_indices(smiles_dataset) -> np.ndarray:
    seen = set()
    keep = []
    for idx, raw_value in enumerate(smiles_dataset):
        smiles = decode_smiles(raw_value)
        if smiles in seen:
            continue
        seen.add(smiles)
        keep.append(idx)
    return np.asarray(keep, dtype=np.int64)


def copy_attrs(src_obj, dst_obj) -> None:
    for key, value in src_obj.attrs.items():
        dst_obj.attrs[key] = value


def copy_selected_datasets(src_file: h5py.File, dst_file: h5py.File, keep_indices: np.ndarray) -> None:
    copy_attrs(src_file, dst_file)

    for name, src_ds in src_file.items():
        if not isinstance(src_ds, h5py.Dataset):
            continue

        data = src_ds[keep_indices]
        dst_ds = dst_file.create_dataset(name, data=data, dtype=src_ds.dtype)
        copy_attrs(src_ds, dst_ds)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"input file not found: {input_path}")

    output_path = Path(args.output) if args.output else input_path.with_suffix("").with_suffix(".dedup.h5")
    if output_path == input_path and not args.replace:
        raise SystemExit("output path would overwrite input; pass --replace to replace in place")

    with h5py.File(input_path, "r") as src_file:
        if "smiles" not in src_file:
            raise SystemExit("dataset 'smiles' not found")
        total_rows = len(src_file["smiles"])
        keep_indices = get_keep_indices(src_file["smiles"])
        kept_rows = len(keep_indices)
        duplicate_rows = total_rows - kept_rows

        with h5py.File(output_path, "w") as dst_file:
            copy_selected_datasets(src_file, dst_file, keep_indices)

    print(f"Input rows: {total_rows}")
    print(f"Kept rows: {kept_rows}")
    print(f"Removed duplicates: {duplicate_rows}")
    print(f"Output file: {output_path}")

    if args.replace:
        backup_path = input_path.with_name(input_path.name + args.backup_suffix)
        if backup_path.exists():
            raise SystemExit(f"backup path already exists: {backup_path}")
        shutil.move(str(input_path), str(backup_path))
        shutil.move(str(output_path), str(input_path))
        print(f"Replaced input file. Backup saved to: {backup_path}")


if __name__ == "__main__":
    main()
