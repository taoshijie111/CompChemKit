---
name: amoeba-stark-tuning
description: Use when computing a vibrational Stark tuning rate (linear VSE) or the local electrostatic field on a probe bond (C=O, C#N, C-D, ...) from Tinker/AMOEBA molecular dynamics, when re-analysing AMOEBA .uind induced-dipole trajectories, or when adapting the benzaldehyde 7-solvent Stark workflow to a new solute/solvent set.
---

# AMOEBA Stark Tuning Rate from Tinker Induced Dipoles

## Overview

Solvatochromic calibration of the vibrational Stark effect measures the probe frequency
in a series of solvents, computes the solvent electric field on the probe bond from MD,
and fits the two:

$$
\bar{\nu}_{\mathrm{obs}} = \bar{\nu}_0 + b\,F_{\mathrm{probe}},
\qquad
b = |\Delta\vec{\mu}|
$$

$\bar{\nu}_{\mathrm{obs}}$ is the measured probe frequency in cm⁻¹, $\bar{\nu}_0$ the zero-field
frequency, and $F_{\mathrm{probe}}$ the solvent field projected on the probe bond in MV cm⁻¹.
The fitted $b$ — `slope` in the output JSON — is the Stark tuning rate in cm⁻¹/(MV cm⁻¹).

This skill implements one specific, validated way of getting $F_{\mathrm{probe}}$ with a
**polarizable AMOEBA** force field in **Tinker**: the field is reconstructed from the *induced
dipoles* that Tinker already converges every step, by differencing the production trajectory
against a **gas-phase re-evaluation of the frozen solute geometry**:

$$
\mathbf{F}_i = \frac{299.79}{\alpha_i}
\left(\vec{\mu}^{\,\mathrm{ind,prod}}_i - \vec{\mu}^{\,\mathrm{ind,gas}}_i\right),
\qquad
F_{\mathrm{bond}} = \tfrac{1}{2}\left(\mathbf{F}_1 + \mathbf{F}_2\right)\cdot\hat{u},
\qquad
\hat{u} = \frac{\mathbf{r}_2 - \mathbf{r}_1}{\left|\mathbf{r}_2 - \mathbf{r}_1\right|}
$$

$\mathbf{F}_i$ is in MV cm⁻¹ for each probe atom $i \in \{1,2\}$,
$\vec{\mu}^{\,\mathrm{ind}}$ are Tinker's induced dipoles in Debye, $\alpha_i$ is the atomic
polarizability in Å³ (read from the `polarize` records), and $\hat{u}$ points from atom1 to
atom2 (carbonyl C $\to$ O, nitrile C $\to$ N, ...).

Core principle: **no MDI, no ELECTRIC, no trajectory re-imaging, no charge-zeroing.**
The solute self-field and the finite-gas-phase normal-mode dipole are removed exactly by the
difference, at the exact saved coordinates, because `save-induced` gives you
$\vec{\mu}^{\,\mathrm{ind}}$ for the full periodic system and `ref.key` gives you
$\vec{\mu}^{\,\mathrm{ind}}$ for the isolated probe.

Reference implementation: `reference/benzaldehyde_7solvents/` reproduces the published
benzaldehyde C=O result **0.4483 cm⁻¹/(MV cm⁻¹), $R^2 = 0.9725$**
(7 solvents, 3 replicates, 5 ns each). It reproduces the original per-solvent fields to the last
digit and the original fit to double-precision round-off; see
`reference/benzaldehyde_7solvents/CASE_STUDY.md`.

## When to Use

- Calibrating (or applying) a vibrational Stark tuning rate for a bond probe in solution.
- Extracting a solvent-induced field on a specific bond from an existing AMOEBA trajectory.
- Reusing the benzaldehyde workflow for another solute, probe bond, or solvent list.

**When not to use:**

- Fixed-charge force fields (GAFF/AMBER + TIP3P) — there is no induced dipole; use the
  charge-division route instead. It yields a systematically different (typically smaller) field
  and hence a different apparent Stark tuning rate.
- A one-off gas-phase estimate — use DFT with an applied field (`Field=Z+n`) instead.
- Protic/H-bonding environments where a blue shift contaminates the frequency: a linear VSE
  fit alone cannot separate the H-bond shift from the Stark shift.
- Needing the strict PME total field or a per-molecule real-space decomposition — this
  method yields the periodic-MD induced dipole minus the vacuum reference.

## Prerequisites

| Requirement | Notes |
|---|---|
| Tinker CPU binaries | `minimize`, `dynamic`, `analyze` (v25/v26; validated on v26.1) |
| `tools/analyze_uind` | **Required.** Tinker has no `analyze_uind` program; this skill ships the wrapper that appends `SAVE-INDUCED` and picks the key file |
| Poltype2 + xTB | AMOEBA parameterisation of every molecule |
| Packmol | Box construction |
| Open Babel | Optional, only to build SDFs from SMILES |
| Python | numpy + matplotlib (fit and plotting only) |
| Experimental IR frequencies | **Required input, not computed here.** The measured probe frequency in each neat solvent, one row per solvent; without it there is no Stark tuning rate. Template: `config/ir_shifts.example.csv` |
| Disk | ~33 GB **per production replicate** measured (`.arc` and `.uind` are 8-22 GB each for 5 ns at 0.1 ps save; 700 GB for the 21-replicate case study) |

## Quick Reference

| # | Stage | Command | Main output |
|---|---|---|---|
| 0 | Tool check (after stage 2) | `./scripts/00_check_tools.sh` | go / no-go |
| 1 | Molecules | `./scripts/01_generate_molecules.sh` | `$STUDY_DIR/molecules/*.sdf` |
| 2 | Parameters | `./scripts/02_parameterize.sh <name> <sdf> <type-base>` | `parameters/<name>/<name>.{xyz,key,prm}` |
| 3 | Boxes + system | `./scripts/submit_md_stage.sh build_system` | `build_system/system.xyz`, `probe_atoms.json` |
| 4 | Optional | `./scripts/submit_md_stage.sh keys` | `min/npt/nvt/production.key` (inspect before running) |
| 5 | Equilibration | `./scripts/submit_md_stage.sh minimize` → `npt` → `nvt` | `minimize/md_start.xyz`, `npt/md_start.dyn`, `nvt/md_start.dyn` |
| 6 | Production | `./scripts/submit_md_stage.sh production` | `production/md_start.{arc,uind,dyn}` |
| 7 | Field extraction | `./scripts/extract_fields.sh` | `analysis/*/partial_field_summary.csv` + per-replicate `fields/` |
| 8 | Fit (needs **your experimental** CSV) | `./scripts/fit_stark_rate.py --root-dir <analysis> --ir-csv <csv>` | `stark_fit_results.json`, `stark_fit.png` |

Add `MD_FOREGROUND=1` to run a stage synchronously instead of detaching it — use that under a
batch scheduler or any environment that reaps detached processes.

Stages 3-6 run all `<solvent>/replicate_N` combinations in parallel and detach; watch
`$STUDY_DIR/run_logs/md_<stage>_<runid>/job_status.tsv` (each replicate gets a `DONE` or `FAIL`
line; the driver exits non-zero if any failed). The table assumes Setup below has been done, i.e.
a `config/system_config.sh` and the molecule parameters exist.

## Setup

```bash
cp config/system_config.example.sh config/system_config.sh
$EDITOR config/system_config.sh                          # STUDY_DIR, SOLUTE_NAME, PROBE_ELEMENTS, solvents
cp config/solvent_table.tsv "$STUDY_DIR"/solvent_table.tsv
$EDITOR "$STUDY_DIR"/solvent_table.tsv                   # per-study solvent library, one row per solvent
cp config/ir_shifts.example.csv "$STUDY_DIR"/ir_shifts.csv
$EDITOR "$STUDY_DIR"/ir_shifts.csv                       # REQUIRED: your own measured frequencies
./scripts/01_generate_molecules.sh                       # only the solvents listed in SOLVENT_NAMES
./scripts/02_parameterize.sh <name> <structure.sdf> <type-base>   # per molecule
./scripts/00_check_tools.sh                              # pre-flight gate; fails until every parameter exists
```

Edit the **per-study** copy of the solvent table, not the one in `config/`: every study defaults to
`$STUDY_DIR/solvent_table.tsv`, and editing the shared template would leak one study's solvents
into the next.

Every script reads the same config; `SYSTEM_CONFIG=/path/other_config.sh` switches studies,
which is how the reference case is re-run without touching this skill's defaults.

### Config fields that decide the physics

| Field | Meaning | Benzaldehyde case |
|---|---|---|
| `SOLUTE_NAME` | probe molecule id, also the `parameters/<name>/` directory | `benzaldehyde` |
| `PROBE_ELEMENTS` | two elements, **atom1 -> atom2 is the projection axis and its sign** | `C O` (C -> O) |
| `PROBE_ATOM_INDICES` | optional explicit 1-based Tinker indices, needed when several matching bonds exist | `2 1` |
| `PROBE_LABEL` | cosmetic label for plots/metadata | `C=O` |
| `SOLUTE_TYPE_BASE` / `SOLVENT_TYPE_BASE` | remapped AMOEBA atom-type ranges; **must not overlap** | `401` / `501` |
| `BOX_A`, `REPLICATE_COUNT` | cubic box edge, independent replicates | `40.0`, `3` |
| `FRAME_INTERVAL_PS` | **must equal** the production save interval, or all times are mislabeled | `0.1` |
| `PRODUCTION_SAVE_INDUCED` | **must stay 1**, otherwise there is no `.uind` to analyse | `1` |

## Workflow Details

### 1-2. Molecules and parameters (Poltype2 + type remap)

```bash
mkdir -p $STUDY_DIR/molecules
./scripts/01_generate_molecules.sh benzaldehyde "O=Cc1ccccc1"     # or supply your own SDF
./scripts/01_generate_molecules.sh                                # every solvent in SOLVENT_NAMES
./scripts/02_parameterize.sh benzaldehyde $STUDY_DIR/molecules/benzaldehyde.sdf 401
for s in hexane thf dichloromethane chloroform toluene acetonitrile dmso; do
  ./scripts/02_parameterize.sh "$s" "$STUDY_DIR/molecules/$s.sdf" 501
done
```

`02_parameterize.sh` runs Poltype2 then **always** remaps into the requested type range with
`tools/remap_poltype_outputs.py`. Never trust Poltype2's own numbering to be unique or
in-range: two molecules in one system are combined by simply listing both `.prm` files, so
overlapping types silently merge different atoms.

Sanity-check the parameters before any dynamics: each `.prm` must contain
`multipole` and `polarize <type> <alpha> ...` records — the extraction reads `alpha` from
there and cannot proceed without it.

### 3. Build the boxes

`submit_md_stage.sh build_system` per replicate: `build_tinker_system.py components`
(centroid-centred components) -> `write_packmol_input.py` -> `packmol` -> `build_tinker_system.py system`
(typed Tinker XYZ with connectivity + `probe_atoms.json`).

The solvent count is taken from, in order of precedence: a `num_solvent` column in the solvent
table, a study-level `packmol_counts.tsv` (`solvent<TAB>num_solvent`, read by the driver), or the
pure-liquid density estimate $N = \mathrm{round}(\rho L^3 N_A / M)$.

`probe_atoms.json` is the single most important file to check by hand:

```json
{"solute":"benzaldehyde","solvent":"hexane","solute_atom_count":14,"solvent_atom_count":20,
 "num_solvent":295,"probe_elements":["C","O"],"probe_label":"C=O",
 "atom1_index":2,"atom2_index":1,"projection_axis":"C_to_O","box_angstrom":40.0}
```

Verify against `build_system/system.xyz` that `atom1_index`/`atom2_index` really are the two
atoms of the intended bond and that `atom1` is the atom the field should be projected *from*
(C -> O, C -> N). If the molecule has several matching bonds, set `PROBE_ATOM_INDICES`.

The writer also produces two key files per replicate:

- `system.key` — solute + solvent, cubic box, `ewald`, `ewald-cutoff 7.0`,
  `neighbor-list`, `vdw-cutoff 12.0`, `vdw-correction`, mutual polarization.
- `ref.key` — **solute only, no box, no Ewald, no cutoffs.** This is the gas-phase
  reference. Adding a box or `ewald` to it changes every field by ~0.1 MV/cm with no error.

### 4-6. Minimise, equilibrate, produce

```bash
./scripts/submit_md_stage.sh minimize
./scripts/submit_md_stage.sh npt
./scripts/submit_md_stage.sh nvt
./scripts/submit_md_stage.sh production      # save-induced is on
tail $STUDY_DIR/run_logs/md_production_*/job_status.tsv
```

Underlying commands (the settings that produced the published result):

```
minimize  system.xyz  -k min.key 0.5
dynamic   md_start.xyz -k ref_npt.key 50000 1.0 0.1 4 300.0 1.0        # 50 ps NPT, Berendsen
dynamic   md_start.xyz -k ref_nvt.key 200000 1.0 0.1 2 300.0           # 200 ps NVT, keeps .dyn
dynamic   md_start.xyz -k ref_production_npt_mc.key 5000000 1.0 0.1 4 300.0 1.0
```

`integrator beeman` + `thermostat andersen`/`collision 0.1`; Tinker switches Beeman to
velocity Verlet when an Andersen thermostat is present, which is expected. Production uses
the Monte Carlo barostat (`volume-scale molecular`, `volume-trial 25`, `volume-move 100.0`)
and `save-induced`. The `.dyn` restart carries box + velocities across stages; `nvt` copies
it from `npt` and `production` from `nvt`, and `.dyn` in the stage directory takes precedence
over the box in the key.

Use `TARGET_SOLVENTS`, `TARGET_REPLICATES`, `NPT_STEPS=2000`, `PRODUCTION_STEPS=10000` and
similar environment overrides for smoke tests before launching 5 ns runs.

### 7. Extract the probe field

```bash
./scripts/extract_fields.sh
# TARGET_SOLVENTS="hexane thf" ANALYSIS_DIR=/path/out FIELD_WORKERS=8 ./scripts/extract_fields.sh
# one replicate: either "solvent/replicate_N" or a bare "replicate_N" (then all solvents,
# unless TARGET_SOLVENTS narrows it)
# TARGET_REPLICATES="thf/replicate_2" ./scripts/extract_fields.sh
# TARGET_SOLVENTS=thf TARGET_REPLICATES=replicate_3 ./scripts/extract_fields.sh
```

Per replicate and per selected frame the extractor:

1. reads frame `k` from `production/md_start.arc` (coordinates) and `md_start.uind` (induced
   dipoles, **already in Debye** — they are Tinker-XYZ formatted but are *not* coordinates);
2. writes the solute lines only (`solute_atom_count` first lines of the frame) to `ref.arc`,
   box line and solvent stripped;
3. runs `analyze_uind ref.arc U` with `ref.key` (resolved as `<stem>.key` = `ref.key`), giving
   `ref.uind` for the isolated probe at the same geometry;
4. differences the dipoles, divides by the atom polarizability read from the `polarize`
   records of `system.key`'s parameter files, projects on the bond unit vector and averages
   the two atoms.

Outputs per replicate in `<analysis>/md/<solvent>/<replicate>/fields/`:

| File | Content |
|---|---|
| `fields.csv` | `frame, source_frame, estimated_time_ps, field_atom1_MV_cm, field_atom2_MV_cm, field_mean_MV_cm, field_drop_MV_cm, probe_length_A` |
| `field_stats.json` | mean/std/SEM of `field_mean_MV_cm`, probe length, atom indices/types, polarizabilities, read mode, window |
| `ref.arc`, `ref.uind`, `ref_analyze_uind.log` | the gas-phase reference and its log |
| `system.key`, `ref.key`, `probe_atoms.json` | verbatim copies of the inputs used |

plus `<analysis>/partial_field_summary.csv` (one row per replicate), `partial_field_errors.json`
and `partial_field_run.json`. The extractor copies **no** IR table into the analysis root; supply
the experimental CSV explicitly at the fit step.

Defaults: `--stride 10 --max-selected-frames 5000` at a 0.1 ps save interval = the 1-5000 ps
window, `--read-mode auto`. Reading modes:

| mode | behaviour | when to use |
|---|---|---|
| `auto` | probes the first 20 frames; if they all have identical byte width and atom count it uses `seek-prefix`, otherwise it falls back to `stream` | normal AMOEBA ASCII output (fixed composition ⇒ fixed width) |
| `seek-prefix` | jumps to frame `k` by byte offset | fast; **only** valid if *every* frame has the same width, which is only checked on the first 20 |
| `sequential-fixed` | reads every frame in order using the measured byte span | same assumption as `seek-prefix`, without the seeking |
| `stream` | text-parses every frame, no byte arithmetic | the defensive choice; slower, and the only mode that tolerates a varying width |

Note that `auto` is not the conservative choice: for fixed-width trajectories it silently picks
`seek-prefix`. If a run could produce width changes (huge coordinates, extra digits, a different
atom count per frame), pass `--read-mode stream` explicitly.

### 8. Fit against experimental frequencies

**The experimental data is your input, not something this workflow produces.** The calibration is
a regression of measured frequencies on computed fields,

$$
\bar{\nu}^{\,\mathrm{exp}}_{\mathrm{obs}} = \bar{\nu}_0 + b\,F^{\,\mathrm{MD}}_{\mathrm{probe}}
$$

so you must supply a measured probe frequency for **every solvent in the study** — one row per
solvent, in that neat solvent, from your own FTIR/Raman measurement (or from the literature).
Without that table there is no fit and no Stark tuning rate; a missing or wrong table is the most
common way to get a meaningless slope. Start from `config/ir_shifts.example.csv` (its numbers are
the benzaldehyde case values, not defaults) and replace them.

```bash
cp config/ir_shifts.example.csv "$STUDY_DIR"/ir_shifts.csv   # then edit it
./scripts/fit_stark_rate.py --root-dir <analysis-dir> --ir-csv "$STUDY_DIR"/ir_shifts.csv \
    --labels-json reference/benzaldehyde_7solvents/plot_labels.json
```

The CSV needs a name column (`name`/`nanme`/`solvent`/`molecule`) and a wavenumber column
(`IR_wavenumber`, `wavenumber`, `frequency`, ...); values may be `1711.62 cm-1`. Solvent names
are matched to directory names case-insensitively, ignoring punctuation, with a synonym table
(`tetrahydrofuran`->`thf`, `dimethyl sulfoxide`->`dmso`, `methylene chloride`->`dichloromethane`,
...). A solvent present in one table but not the other is dropped from the fit with a warning and
recorded in `excluded_solvents`. `--labels-json` optionally supplies per-solvent plot
labels/offsets. **Keep the exact CSV with the results** — the fitted slope is only meaningful
together with the frequency table it was fitted against.

`stark_fit_results.json` reports the slope (= Stark tuning rate), intercept, R^2, n_points,
slope_se, rmse.

## Adapting to a New System

1. **Probe bond.** Set `PROBE_ELEMENTS` to your bond in `atom1 -> atom2` order (`C O` for a
   carbonyl, `C N` for a nitrile) and/or pin `PROBE_ATOM_INDICES`. Re-run `build_system` and
   confirm `probe_atoms.json`.
2. **Solute.** `SOLUTE_NAME` + Poltype2 with `SOLUTE_TYPE_BASE` (e.g. 401).
3. **Solvents.** Add rows to the per-study `$STUDY_DIR/solvent_table.tsv`
   (name, SDF, SMILES, density, molar mass), list them in `SOLVENT_NAMES`, parameterise each at
   `SOLVENT_TYPE_BASE` (e.g. 501; solvents may share a range because each system contains only
   one solvent).
4. **Box / sampling.** `BOX_A` (40 A is the validated choice), `REPLICATE_COUNT` >= 3,
   production >= 5 ns.
5. **Experimental IR data (required).** One row per solvent: the probe frequency you measured
   in that neat solvent. Copy `config/ir_shifts.example.csv`, replace the numbers, and keep the
   solvent names recognisable (they are matched to `md/<solvent>/` directory names). No
   experimental table means the workflow can produce fields but no Stark tuning rate.
6. **Re-validate.** Run the checks below on one replicate before the full study.

If the probe is a different vibration (C-D, N-H, S=O, ...), the *method* is unchanged, but
$\bar{\nu}_0$ and the fitted $b$ must be recalibrated for that mode — and with a probe that can hydrogen bond,
expect the linear VSE to break down in protic solvents.

## Verification and Sanity Checks

Cheap checks, in order of how often they catch a real problem:

| Check | Expected |
|---|---|
| `probe_atoms.json` indices vs `system.xyz` elements/connectivity | the intended bonded pair, correct direction |
| `field_stats.json` -> `polarizability_atom1/2` | finite, matching the `polarize` lines; **0 or missing ⇒ wrong key file** |
| `probe_length_mean_A` | the physical bond length (~1.23 A for C=O, ~1.16 A for C#N) |
| `ref.uind` frame count vs `frames` | equal (the extractor hard-fails otherwise) |
| `read_mode` | `seek-prefix` when `auto` found fixed-width frames, `stream` otherwise; the archived run used `seek-prefix` |
| `partial_field_errors.json` | `[]` |
| Field ordering across solvents | tracks solvent polarity / the experimental order |
| `stark_fit_input.csv` `n_replicates` | `REPLICATE_COUNT` for every solvent |
| `stark_fit_results.json` -> `excluded_solvents` | `[]` — a non-empty list means a silent n-reduction |
| R^2 | a good probe in a good solvent series gives R^2 > 0.9 |

Expected magnitudes for a benzaldehyde-like C=O probe in a solvent series of this polarity range
are in `reference/benzaldehyde_7solvents/CASE_STUDY.md` (fields -9 to -38 MV/cm, slope
≈ 0.45 cm⁻¹/(MV cm⁻¹), $R^2$ ≈ 0.97). A new system should be checked the same way: probe length
equal to the physical bond length, `.uind` frame count equal to `frames`, empty
`partial_field_errors.json`, `excluded_solvents` empty, and $R^2$ above ~0.9 for a probe whose
frequency really follows the field.

Always pass `--ir-csv` explicitly and check the `ir_csv` field of `stark_fit_results.json`
afterwards: an IR table sitting next to the results is not necessarily the one that was fitted.

## Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `save-induced` disabled for production | no `md_start.uind`; extraction cannot run | keep `PRODUCTION_SAVE_INDUCED=1` |
| `ref.key` given a box line or `ewald` | gas-phase baseline wrong, every field shifted ~0.1 MV/cm, silently | never add box/EWALD to `ref.key`; check the file |
| Reading `.uind` as coordinates | fields wrong by 10^2-10^3 | induced dipoles are Debye, not positions |
| `FRAME_INTERVAL_PS` != production save interval | all times/windows mislabeled | set it equal to `PRODUCTION_SAVE_PS` |
| Wrong solvent count or box size | densities off, so fields are not comparable with the case study | keep a `packmol_counts.tsv`-style table for the counts you actually used; otherwise the density estimate is used |
| Overlapping `SOLUTE_TYPE_BASE`/`SOLVENT_TYPE_BASE` | two different molecules share atom types and multipoles | keep the ranges disjoint |
| Several candidate probe bonds | the shortest matching bond is picked automatically | set `PROBE_ATOM_INDICES` |
| `seek-prefix` (what `auto` picks for fixed-width files) on a trajectory whose frame width varies | later frames silently misread | pass `--read-mode stream` |
| No experimental IR table, or frequencies filled in from the calculation itself | the slope is meaningless (the fit degenerates into fitting the probe against itself); the workflow cannot supply these values | measure the probe frequency in each neat solvent first; see `config/ir_shifts.example.csv` |
| Fit matched the wrong IR table | MeCN 1701.81 vs 1699.943 changes the slope 0.4224 -> 0.4483 and R^2 0.916 -> 0.972 | pass `--ir-csv` explicitly; check `ir_csv` in `stark_fit_results.json` |
| An IR table left next to the results is assumed to be the one that was fitted | wrong frequencies, wrong slope | pass `--ir-csv` explicitly and check `ir_csv` in `stark_fit_results.json`; this skill never copies an IR table into the analysis directory |
| Quoting `slope_se` as the real uncertainty | it is a lower bound: between-replicate SEM only, on an unweighted 7-point fit; frames are strongly correlated | report replicate scatter and, ideally, block averaging |
| Launching 21 production runs at once | 700 GB of ASCII measured for the case study | check disk; set `MD_PARALLEL_JOBS` |

## Approaches Not Taken

The workflow described here is the end of a longer search. Three variants were tried and rejected;
knowing them prevents wasted effort:

- **Real-space decomposition instead of the induced-dipole difference.** An MDI/ELECTRIC-style
  run that decomposes the field per molecule in the absence of Ewald (and therefore needs
  re-imaged, non-periodic frames) measures a related but different quantity. It gave fields
  1-20x smaller and a fit that was not usable. Pick one observable and stay with it.
- **Segmented NVT heating + NVT production + a 0.5 fs timestep.** Stable, but it samples
  differently from the NPT/Monte Carlo production with 1 fs steps used here, and it changes the
  density trajectory. The settings in this skill are the validated ones.
- **Reading whole trajectories into memory.** Fine for a smoke test, fatal for a 20 GB `.arc` per
  replicate, and dangerous if the code reuses an existing `ref.arc` instead of rebuilding it.

The induced-dipole difference and the real-space decomposition are not the same quantity; results
from the two are not interchangeable.

## Files in This Skill

```
SKILL.md                     this file
README.md / README_ch.md     English and Chinese project overviews
config/system_config.example.sh   copy to config/system_config.sh
config/solvent_table.tsv     solvent library template (name/sdf/smiles/density/molar mass)
config/ir_shifts.example.csv experimental probe-frequency template (required input for the fit)
scripts/_defaults.sh         shared toolchain/resource defaults (no machine-specific paths)
scripts/00_check_tools.sh    toolchain + parameter presence check
scripts/01_generate_molecules.sh   SMILES -> 3D SDF via Open Babel
scripts/02_parameterize.sh   Poltype2 + atom-type remap for one molecule
scripts/submit_md_stage.sh   batch driver: build_system|keys|minimize|npt|nvt|production
scripts/run_md_step.sh       per-replicate stage runner (invoked by the driver)
scripts/extract_fields.sh    whole-study probe-field extraction
scripts/fit_stark_rate.py    Stark fit + publication-style plot
tools/build_tinker_system.py       Packmol xyz -> typed Tinker xyz + probe_atoms.json
tools/write_packmol_input.py       Packmol input from the solvent table
tools/write_replicate_keys.py      system.key (periodic/Ewald) + ref.key (gas phase)
tools/remap_poltype_outputs.py     Poltype2 output -> private atom-type range
tools/extract_probe_field.py       induced-dipole probe-field extraction
tools/analyze_uind                 wrapper: run Tinker analyze and write a .uind file
reference/benzaldehyde_7solvents/  validated case study: settings, frequencies, result, figure
reference/HAZARDS.md               pitfalls that cost real time or silently corrupt results
```
