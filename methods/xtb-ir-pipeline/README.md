# xtb Batch IR Spectrum Calculation Pipeline

**English** | [中文](README_CN.md)

An automated **batch IR spectrum calculation workflow** built on [xtb](https://xtb-docs.readthedocs.io/). Starting from nothing but a SMILES file, it automatically performs 3D conformer generation → structure optimization & frequency calculation → imaginary-frequency cleanup → result archiving & cleanup → spectrum broadening, and finally produces a unified HDF5 spectral database.

## Pipeline Overview

```
SMILES file (.smi)
  │  ① generate_xyz_openbabel_single.py   Conformer search with Open Babel → 3D structures
  ▼
XYZ tree  batch_k/molecule_i/molecule_i.xyz
  │  ② run_xtb_ir.py                      xtb optimization + frequencies + imaginary-mode cleanup
  ▼
Batch archives  <task>_batch_results.pkl.gz  +  CONVERGED marker (intermediates deleted)
  │  ③ extract_spectrum.py                 Threaded I/O + multiprocess/Numba broadening
  ▼
Spectrum HDF5 database  spectra.h5
  │  ④ rebroaden_spectra.py (optional)     Recompute spectra with different method/width
  │  ⑤ dedup_h5_by_smiles.py (optional)    Deduplicate by SMILES
  ▼
Final dataset
```

## Repository Layout

```
.
├── data/                               # Example input: SMILES shards (one SMILES per line)
│   └── part_00.smi
├── xyz_out/                            # Example output: XYZ conformers + xtb results
│   └── batch_0/
│       ├── xtb_ir_batch_results.pkl.gz # Batch archive of xtb results (gzip pickle stream)
│       └── molecule_0/
│           ├── molecule_0.xyz          # 3D conformer (SMILES on line 2, used downstream)
│           └── xtb_ir/                 # xtb task dir (only the marker survives cleanup)
│               └── CONVERGED
├── generate_xyz_openbabel_single.py    # ① SMILES → XYZ 3D conformers (Open Babel search)
├── run_xtb_ir.py                       # ② xtb optimization + frequencies + imag. cleanup + archive
├── xtbgaussian_parser.py               # Parses xtb's Gaussian-format output (g98.out)
├── extract_spectrum.py                 # ③ Archives → broadened spectra → HDF5 database
├── rebroaden_spectra.py                # ④ Re-broaden from stored frequency/intensity
├── dedup_h5_by_smiles.py               # ⑤ Deduplicate HDF5 by SMILES
├── submit_generate_xyz_openbabel.sh    # SLURM submission script (step ①, array job)
├── submit_run_xtb_ir.sh                # SLURM submission script (step ②, array job)
├── spectrum_extract.sh                 # SLURM submission script (step ③)
└── spectra_lorentzian_fwhm8.h5         # Example artifact: broadened spectrum database
```

## Dependencies

- Python ≥ 3.9 (developed on 3.11)
- `numpy`, `h5py`, `tqdm`
- `openbabel` (incl. `pybel`), `periodictable`
- `numba` (optional but strongly recommended: accelerates the broadening kernels tens of times; the pure-Python fallback is very slow)
- `rdkit` (optional: infers charge/spin multiplicity from SMILES; falls back to a regex parser when missing)
- `xtb` executable (requires `--ohess` support; emits Gaussian-format `g98.out`)

## Usage

### Step 1: SMILES → 3D conformers (XYZ)

```bash
python generate_xyz_openbabel_single.py \
    --input-smi data/part_00.smi \
    --output-root xyz_out \
    --processes 16 \
    --force-field mmff94 \
    --timeout 600
```

- Input `.smi` file: one SMILES per line; lines starting with `#` are skipped; the first whitespace-separated token of each line is taken as the SMILES.
- Open Babel adds hydrogens, builds an initial structure with `OBBuilder`, then runs a force-field conformer search (`WeightedRotorSearch` + `ConjugateGradients` + `SteepestDescent`; force field: `uff`/`mmff94`/`mmff94s`).
- Output layout: `<output-root>/batch_{i//batch_size}/molecule_{i}/molecule_{i}.xyz`, default 1000 molecules per batch folder.
- Multiprocessing pool; with `--timeout`, each molecule runs in a dedicated subprocess so hung molecules are hard-killed.
- Failures are recorded in `<output-root>/error.log` (`index\tsmiles\treason`); use `--overwrite` to regenerate existing molecules.

### Step 2: xtb optimization + frequencies + imaginary-mode cleanup

```bash
python run_xtb_ir.py \
    --root-dir xyz_out \
    --task-name xtb_ir \
    --max-workers 16 \
    --cores-per-task 4 \
    --max-iterations 10 \
    --disp-scale 1 \
    --imag-threshold 0 \
    --skip-completed
```

- For each `molecule_*.xyz`, runs in `<root>/batch_k/molecule_i/<task-name>/`:

  ```
  xtb molecule_i.xyz --ohess extreme -P <cores> --chrg <charge> --uhf <uhf> [--ptb] [--raman]
  ```

- **Imaginary-frequency cleanup**: parses `g98.out` for frequencies and normal-mode displacements; if the lowest frequency is below `--imag-threshold` (e.g. 0), the geometry is perturbed along that mode (`coords + disp_scale × displacement`) and xtb re-runs, up to `--max-iterations` times. Molecules still showing imaginary modes are reported as failed.
- **Archive & cleanup**: on success, results are appended to the batch archive `batch_k/<task-name>_batch_results.pkl.gz`, a `CONVERGED` marker is written, and all intermediate files (logs, hessian, ...) in the task dir are deleted — disk usage stays very low.
- **Resume support**: `--skip-completed` skips already-finished molecules; the legacy per-molecule `result.pkl.gz` format is auto-detected and migrated.
- Concurrency: a thread pool schedules molecules; worker count is `--max-workers`, defaulting to `CPU count // cores_per_task`.

### Step 3: Extract results and broaden → HDF5

```bash
python extract_spectrum.py --xyz-dir xyz_out -o spectra.h5 --fwhm 20
# Lorentzian broadening instead:
python extract_spectrum.py --xyz-dir xyz_out -o spectra_lorentzian.h5 --method lorentzian --fwhm 8
```

- Recursively discovers data sources: new-style batch archives `*_batch_results.pkl.gz` plus legacy per-molecule `result.pkl.gz`.
- I/O and compute are decoupled: 8 threads handle disk reads (tuned for spinning disks), a multiprocessing pool with optional Numba does decompression and broadening; batches are streamed into HDF5 with append support.
- Spectrum grid is fixed at 1–4000 cm⁻¹ (`--spec-length`); default broadening is Voigt-style (50% Gaussian + 50% Lorentzian) with `--fwhm` default 20.
- Output fields can be trimmed with `--no-frequency` / `--no-intensity` / `--no-spectrum`.

### Step 4 (optional): Re-broaden

```bash
python rebroaden_spectra.py spectra.h5 -m lorentzian_convolution --width 8
```

Relies only on the `frequency`/`intensity` datasets already stored in the HDF5 — no raw archives needed. Output is named `<original>_<method>_w<width>.h5`, with provenance attributes recording the source file, method, width, and spec length.

### Step 5 (optional): Deduplicate by SMILES

```bash
python dedup_h5_by_smiles.py spectra.h5               # writes <name>.dedup.h5
python dedup_h5_by_smiles.py spectra.h5 --replace     # replace in place, original backed up to .bak
```

Keeps the first occurrence of each SMILES.

### SLURM examples

- `submit_generate_xyz_openbabel.sh`: array job over `part_XX.smi` shards (64 processes, mmff94, 600 s timeout).
- `submit_run_xtb_ir.sh`: matching array job (64 workers, 10 cleanup iterations, `disp_scale=1`, `imag_threshold=0`).
- `spectrum_extract.sh`: submission script for step ③.

## Data Formats

### XYZ file

```
42
C1CCC=CCCCCCCCCCC1=O
C  -1.709744  -6.176910  -0.224917
...
```

Line 1: atom count. Line 2: SMILES (both `run_xtb_ir.py` and `extract_spectrum.py` depend on this line). Following lines: `Element X Y Z`.

### Batch archive (gzip-compressed pickle stream)

`gzip.open(path, "ab")` appends one pickle record per molecule (records are terminated by EOF). Each record is a dict:

| Field | Shape | dtype | Description |
| --- | --- | --- | --- |
| `molecule` | — | str | e.g. `molecule_0` (index within the batch) |
| `smiles` | — | str | original SMILES |
| `atomnos` | (N,) | int16 | atomic numbers |
| `atomcoords` | (N, 3) | float32 | optimized coordinates (Å) |
| `vibfreqs` | (3N-6,) | float32 | vibrational frequencies (cm⁻¹) |
| `vibirs` | (3N-6,) | float32 | IR intensities (km/mol) |

### HDF5 database structure (`extract_spectrum.py` output)

| Dataset | Shape | dtype | Description |
| --- | --- | --- | --- |
| `smiles` | (N,) | utf-8 str | one row per molecule |
| `coords` | (N,) | vlen float32 | flattened N_atom×3 coordinates per molecule |
| `atom_counts` | (N,) | int32 | number of atoms per molecule |
| `atomnos` | (N,) | vlen int32 | atomic numbers per molecule |
| `frequency` | (N,) | vlen float32 | filtered, sorted frequencies (optional) |
| `intensity` | (N,) | vlen float32 | matching IR intensities (optional) |
| `spectrum` | (N, 4000) | float32, lzf | broadened spectrum per molecule |

## Implementation Details

- **Charge & multiplicity inference**: RDKit is used first (sum of formal charges; `uhf = number of unpaired electrons`, multiplicity = uhf+1); when RDKit is unavailable it falls back to regex-parsing `[...]` charge fragments in the SMILES (with `uhf=0`).
- **Imaginary-mode cleanup**: frequencies and displacement vectors (shape 3N-6 × N × 3) are parsed from `g98.out`; the perturbation is applied to xtb's optimized coordinates (`parser.atomcoords`); the `hessian` file is deleted before each rerun to avoid stale caches.
- **Thread-safe archiving**: batch archives are appended under a per-file lock; results are stored as float32/int16 to keep size down.
- **Resume logic**: CONVERGED marker validation (format, archive name, molecule name) → legacy `result.pkl.gz` migration → retro-cleanup when the log tail contains `normal termination of xtb` and `g98.out` shows no imaginary modes.
- **Broadening**: only modes with `freq > 0` and `intensity ≥ 0` are kept and sorted by ascending frequency; the Lorentzian kernel is area-normalized as `amp = intensity × 100 × (fwhm/2) / π`; the Voigt kernel is 50% Gaussian + 50% Lorentzian (FWHM definition).
- **`xtbgaussian_parser.py`**: parses xtb's Gaussian-format output, exposing `atomnos` / `atomcoords` / `vibfreqs` / `vibirs` / `vibramans` / `vibrmasses` / `vibdisps` (M×N×3).
