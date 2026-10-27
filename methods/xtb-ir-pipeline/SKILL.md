---
name: xtb-ir-pipeline
description: Use when batch-computing IR spectra with xtb starting from a SMILES list — conformer generation (Open Babel) → GFN2 opt+freq → imaginary-frequency cleanup → spectral broadening into an HDF5 database, on a Slurm cluster. Includes SLURM array-job submission scripts and re-broadening / de-duplication utilities.
---

# xtb Batch IR Spectrum Pipeline

Turn a plain SMILES list into an HDF5 database of broadened IR spectra with xtb. Every molecule
goes through 3D conformer generation (Open Babel force-field search), a GFN2-xTB `--ohess`
optimization + frequency job, an automatic imaginary-frequency cleanup loop that displaces the
geometry along the offending normal mode and re-runs xtb, and finally Voigt or Lorentzian
broadening onto a fixed 1–4000 cm⁻¹ grid. Intermediate xtb files are deleted as each molecule
finishes, so the intermediate disk footprint stays small and the run is resumable; the expensive
part is the cluster array job, while the broadening is cheap and can be repeated with any width or
line shape from the stored frequencies.

## Pipeline

1. **Conformers** — `generate_xyz_openbabel_single.py` reads `data/part_XX.smi` (one SMILES per
   line, `#` comments skipped), adds hydrogens, runs a force-field conformer search and writes
   `<root>/batch_k/molecule_i/molecule_i.xyz` with the SMILES kept on line 2. Failures go to
   `<root>/error.log`; hung molecules are hard-killed by a per-molecule timeout.
2. **Optimization + frequencies** — `run_xtb_ir.py` runs
   `xtb molecule_i.xyz --ohess extreme -P <cores>` per molecule; if the lowest frequency is below
   `--imag-threshold`, the geometry is displaced along that mode and xtb re-runs (up to
   `--max-iterations`). Each success is appended to `batch_k/<task>_batch_results.pkl.gz` with a
   `CONVERGED` marker and the task directory is cleaned; `--skip-completed` resumes an interrupted
   run.
3. **Extract and broaden** — `extract_spectrum.py` walks the batch archives, broadens with a
   multiprocessing + Numba kernel and appends to `spectra.h5` (grid 1–4000 cm⁻¹, default Voigt
   FWHM 20; `--method lorentzian` for a Lorentzian).
4. **Re-broaden (optional)** — `rebroaden_spectra.py` recomputes spectra from the stored
   `frequency`/`intensity` datasets only, with another method and width.
5. **De-duplicate (optional)** — `dedup_h5_by_smiles.py` keeps the first row per SMILES.

## Files

| File | Step | Role |
|---|---|---|
| `generate_xyz_openbabel_single.py` | 1 | SMILES → 3D XYZ conformers (Open Babel, `uff`/`mmff94`/`mmff94s`, per-molecule timeout) |
| `submit_generate_xyz_openbabel.sh` | 1 | SLURM array job over the SMILES shards |
| `run_xtb_ir.py` | 2 | xtb opt + freq, imaginary-mode cleanup, batch archiving, resume |
| `xtbgaussian_parser.py` | 2 | Parses xtb's Gaussian-format `g98.out` (frequencies, IR intensities, displacements) |
| `submit_run_xtb_ir.sh` | 2 | Matching SLURM array job for step 2 |
| `extract_spectrum.py` | 3 | Batch archives → broadened spectra → HDF5 database |
| `spectrum_extract.sh` | 3 | SLURM submission script for step 3 |
| `rebroaden_spectra.py` | 4 | Re-broaden an existing `spectra.h5` |
| `dedup_h5_by_smiles.py` | 5 | De-duplicate an HDF5 database by SMILES |

## How to use

```bash
# copy this skill folder to the cluster, then from inside it:
sbatch submit_generate_xyz_openbabel.sh    # step 1: SMILES -> XYZ conformers
sbatch submit_run_xtb_ir.sh                # step 2: xtb opt + freq + imag. cleanup
bash spectrum_extract.sh                   # step 3: broaden -> spectra.h5
```

Before the first run, edit the `#SBATCH` headers (`--partition=your_partition`, node/task counts,
`--array`) and the input/output directories in the three `.sh` files so they match your cluster
and your shard names. Steps 4 and 5 are plain `python` calls and need no scheduler.

## Requirements

- `xtb` with `--ohess` support, on `$PATH` of the compute nodes
- Open Babel with Python bindings (`openbabel`/`pybel`) and `periodictable`
- Python ≥ 3.9 with `numpy`, `h5py`, `tqdm`; `numba` is strongly recommended (the pure-Python
  broadening fallback is orders of magnitude slower); `rdkit` optional (charge/multiplicity
  inference, with a regex fallback)
- A Slurm cluster for the batch steps

## See also

- [`README.md`](README.md) — full reference: CLI flags for every script, the XYZ / archive /
  HDF5 data formats, broadening kernels and implementation notes.
- [`README_CN.md`](README_CN.md) — 中文说明。
