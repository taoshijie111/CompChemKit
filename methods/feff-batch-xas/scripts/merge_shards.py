#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Merge per-shard HDF5 outputs produced by collect_spectra.py into one file.

Shards may overlap (a resumed or re-submitted batch can contain the same structure twice).
When a structure id appears in several shards, the copy with the most valid sites
(`site_ok.sum()`) wins, so a rerun never degrades earlier results.

Usage:
  python merge_shards.py --shards 'parts/*.h5' --out dataset.h5 [--drop-shards]
"""
import argparse
import glob
import json
from pathlib import Path

import h5py


def score(group):
    try:
        return int(group["site_ok"][()].sum())
    except Exception:
        return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", required=True, help="glob for shard files, e.g. 'parts/*.h5'")
    ap.add_argument("--out", required=True)
    ap.add_argument("--drop-shards", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(args.shards))
    if not files:
        raise SystemExit(f"no shards matched {args.shards}")
    print(f"[i] {len(files)} shards")

    # pick the best copy of every structure
    best = {}
    for fp in files:
        with h5py.File(fp, "r") as f:
            if "structures" not in f:
                continue
            for sid in f["structures"]:
                s = score(f["structures"][sid])
                if sid not in best or s > best[sid][0]:
                    best[sid] = (s, fp)
    print(f"[i] {len(best)} unique structures")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(out_path, "w", libver="latest") as dst:
        with h5py.File(files[0], "r") as f0:            # energy axes come from any shard
            if "energies" in f0:
                for k in f0["energies"]:
                    dst.create_dataset(f"energies/{k}", data=f0[f"energies/{k}"][()])
            for k, v in f0.attrs.items():
                dst.attrs[k] = v
        G = dst.create_group("structures")
        for sid, (_, fp) in sorted(best.items()):
            with h5py.File(fp, "r") as f:
                f.copy(f["structures"][sid], G, name=sid)
        dst.attrs["n_structures"] = len(best)
        dst.attrs["merged_from"] = len(files)
        dst.attrs["shards"] = json.dumps([Path(x).name for x in files])
    print(f"[i] -> {out_path} ({out_path.stat().st_size/1e6:.1f} MB)")

    if args.drop_shards:
        for fp in files:
            Path(fp).unlink()
        print(f"[i] removed {len(files)} shards")


if __name__ == "__main__":
    main()
