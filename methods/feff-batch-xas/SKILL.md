---
name: feff-batch-xas
description: Use when batch-computing X-ray absorption spectra (XANES/EXAFS) with FEFF for many structures and many absorbing sites — build one feff.inp per absorbing atom, run the FEFF module chain, extract spectra onto a fixed energy window, and aggregate per-site / per-element results with an explicit validity mask. Structure-source agnostic (conformers, trajectories, reaction paths, any XYZ-like array). Covers FEFF-side pitfalls (core-hole screening crashes, empty output on interpolation failure, resumable batches) and lists recommended card settings that MUST be confirmed with the user before production.
---

# FEFF batch XAS

Compute X-ray absorption spectra for many structures with FEFF, one absorbing atom at a time,
and turn the per-site output into per-element spectra with a validity mask.

**Scope.** FEFF itself: input cards, module chain, core-hole treatment, output extraction,
per-site/per-element combination, and the failure modes of those steps.
**Non-goals.** No scheduler assumptions, no queue policy, no directory conventions, no dataset
schema. Paths, parallelism and job submission are the caller's business; this skill only requires
that each absorbing site gets its own directory with a `feff.inp`.

## Pipeline

1. **Prepare** — for every (structure, frame, absorbing atom) build a `feff.inp`:
   absorber written first in `ATOMS`, absorber assigned potential 0, other elements grouped by
   first appearance. See `scripts/make_input.py`.
2. **Run** — execute the module chain in order, one process per module, inside the site directory.
   Record per-module return codes and wall times. See `scripts/run_sites.py`.
3. **Extract** — read `xmu.dat` (column 4 = μ) and sample it onto the fixed energy window of that
   edge. Never fabricate points FEFF did not compute. See `scripts/collect_spectra.py`.
4. **Aggregate** — per-site matrix + validity mask + per-element sum. See the same script.
5. **Archive** (optional) — merge per-shard HDF5 files into one with de-duplication.
   See `scripts/merge_shards.py`.

Module chain (serial build):

```
rdinp → atomic → pot → [screen] → xsph → fms → mkgtr → path → genfmt → ff2x
```

`screen` is only needed when `COREHOLE RPA` is used (it computes the RPA-screened core hole).
Every module must exit 0; `xmu.dat` is written by `ff2x`.

## Recommended parameters — NOT mandatory

The values below are a physics-sound starting point for molecular C/N/O K-edge XANES. Treat them
as **recommendations to confirm**, not as fixed rules: the edge, the core-hole model, the cluster
radius and the energy window all depend on the system and on what the spectra will be used for.

```
EDGE K 1.0                     # edge + S0^2 (the second number IS S0^2, not an energy shift)
CONTROL 1 1 1 1 1 1
PRINT 1 0 0 0 0 0
COREHOLE RPA                   # omit → default final-state rule (FSR); 'none' = no core hole
EXCHANGE 0 0.0 0.000000        # Hedin-Lundqvist, no constant-potential shift
SCF <r> 1 30 0.2 1             # r = cluster radius; lfms1=1 is the molecular setting
ABSOLUTE                       # μ stays an absolute cross-section (Å² per absorbing atom)
FMS <r> 0                      # full multiple scattering, same radius
RPATH 0.1                      # effectively disables the path expansion for XANES
XANES 4.0 0.04 0.1             # xkmax (Å⁻¹), xkstep, vixan (eV)
```

Recommended energy windows (200 points, 0.2 eV step) — see `references/parameters.md` for why:

| edge | start (eV) | end (eV) |
|---|---|---|
| C K | 275.0 | 314.8 |
| N K | 397.0 | 436.8 |
| O K | 528.0 | 567.8 |

**Confirm with the user before a production run:** which edges; `COREHOLE` model (RPA vs FSR vs
none); cluster radius (whole molecule vs coordinated shell); energy window and step; whether
spectra should stay absolute (Å²) or be normalised to the edge jump; whether failed sites may be
left as missing data.

## Data conventions this skill assumes

- One directory per absorbing site; after the run keep `feff.inp` + `xmu.dat` (+ extracted
  `spectrum.csv`) and prune the ~7 MB per site of intermediates.
- `μ` from `xmu.dat` column 4 is the **absolute cross-section in Å² per absorbing atom** when the
  normalisation factor in the file header is `1.0` (`ABSOLUTE`). Under this convention:
  - **Same element, same frame:** different absorbing atoms are independent absorbers, so their
    cross-sections **add**. No normalisation before adding.
  - **All sites of an element in a frame failed:** the sum is `0` (an explicit "no valid
    contribution"), and the validity mask says why.
  - **Different elements:** energy ranges do not overlap; do **not** add them. Concatenate along
    the energy axis instead.
- Keep a boolean mask `site_ok[frame, atom]`. It is the single source of truth for "this site has a
  spectrum"; every count (how many sites contributed, per-atom average = sum / count) is derived
  from it, so do not store redundant count fields.

## Pitfalls

Read `references/pitfalls.md` before scaling up. The three that cost the most time:

1. `screen` (RPA core hole) can crash (`rc=2`, null-pointer trace) or hang on specific geometries.
   Give every module a timeout and fall back to another core-hole model for that site.
2. `ff2x` can fail inside its interpolation (`STOP failure in polint`) and still exit 0 with a
   **701-byte header-only** `xmu.dat`. Validate the parsed array, not the exit code alone.
3. Fixed energy windows can start below the first energy FEFF actually computed. Shift the window
   or mark those points missing — never zero-fill, or every spectrum gets a fake leading edge.

Two more that only appear once the clusters are truncated (i.e. when the molecule is bigger than the
cluster radius — routine for large molecules, and invisible on small test systems):

4. **Every potential must have a representative atom inside the FMS sphere.** If `ATOMS` is
   truncated to a radius but the whole molecule's element list is still written to `POTENTIALS`,
   `pot` prints `FMS ... Cannot find all representative atoms` and stops. Write only the retained
   atoms and number the potentials from the retained elements.
5. **Modules can stop and still exit 0** (Fortran `STOP` under gfortran). A `pot` failure this way
   surfaces one module later as a confusing `screen`/`xsph` crash. Treat a lone `STOP` line in a
   module's stderr as a failure.

## Scaling out

Sites are independent, so the batch shape matters more than any single-site tuning: one job per
site (or per structure) with a short wall time and a self-regulating submitter beats one large,
long job array by a wide margin. The general reasoning — why arrays do not equal concurrency, why
the concurrency cap is counted in jobs rather than cores, and why backfill only takes short jobs —
is in the sibling skill `methods/hpc-cluster` (§3.6). Two consequences specific to XAS batches:

- The natural independent unit is the **(structure, absorbing atom)** pair, not the structure: a
  molecule with 200 absorbers spread over one job turns it into a multi-hour unit that is expensive
  to lose and hard to backfill.
- At 10^6 sites the per-site three-piece set (`feff.inp`, `xmu.dat`, `spectrum.csv`) is millions of
  files. Keep the spectra in aggregate arrays keyed by structure and retain the three-piece set for
  a small sample only, so the inputs stay auditable without drowning networked storage.

## Files

```
SKILL.md                        this file
references/parameters.md        card-by-card meaning, recommended values, what to confirm
references/pitfalls.md          FEFF-specific failure modes and defences
references/feff10_users_guide.pdf   official FEFF10 manual (card semantics, module docs)
scripts/make_input.py           structure + absorbing index → feff.inp
scripts/run_sites.py            run the module chain for a manifest of site directories
scripts/collect_spectra.py      xmu.dat → windowed spectra → per-site / per-element HDF5
scripts/merge_shards.py         merge per-shard HDF5 outputs (de-duplicating)
```

## 中文速览

本 skill 只沉淀 **FEFF 批量计算 XAS 本身**的经验：怎么给每个吸收原子生成 `feff.inp`、怎么跑
模块链、怎么从 `xmu.dat` 抽谱、怎么按"同元素相加 / 跨元素不混"的物理规则汇总，以及 FEFF 自身
的坑（`screen` 崩溃、`ff2x` 空谱、窗口低端补零）。文中参数是**推荐值，正式计算前必须与用户确认**。
不包含任何超算/队列/目录约定的内容——路径、并行度和提交方式由使用者自己决定。
