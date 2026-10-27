# Tinker/AMOEBA Stark tuning rates

[English](README.md) | [简体中文](README_ch.md)

These are the scripts I use to get the vibrational Stark tuning rate of a bond probe out of
Tinker/AMOEBA molecular dynamics. The field on the probe is reconstructed from the induced
dipoles Tinker already converges each step, so there is no extra MDI or ELECTRIC job to run and
nothing to re-image:

$$
\mathbf{F}_i = \frac{299.79}{\alpha_i}
\left(\vec{\mu}^{\,\mathrm{ind,prod}}_i - \vec{\mu}^{\,\mathrm{ind,gas}}_i\right),
\qquad
F_{\mathrm{bond}} = \tfrac{1}{2}\left(\mathbf{F}_1 + \mathbf{F}_2\right)\cdot\hat{u}
$$

The $\vec{\mu}^{\,\mathrm{ind}}$ are the induced dipoles in Debye, $\alpha_i$ the atomic
polarizabilities in Å³, and $\hat{u}$ runs from the first probe atom to the second (C→O for a
carbonyl, C→N for a nitrile). Subtract what the isolated molecule would do on its own, project on
the bond, and what is left is the solvent.

I used this to calibrate benzaldehyde's C=O stretch in seven solvents, three independent boxes per
solvent, 5 ns per box in a 40 Å cube. The regression of the measured frequencies on those fields
comes out at $b = 0.448302$ cm⁻¹/(MV cm⁻¹), $\bar{\nu}_0 = 1715.361$ cm⁻¹, $R^2 = 0.9725$. The
scripts here reproduce the seven fields and that fit from the same trajectories; the settings and
the numbers are written up in
[`reference/benzaldehyde_7solvents/CASE_STUDY.md`](reference/benzaldehyde_7solvents/CASE_STUDY.md).

## You have to bring the frequencies

The fit is one point per solvent: frequency measured, field computed. The field comes from the MD,
the frequency does not. For every solvent in the study you need a measured probe frequency in that
neat solvent, from your own FTIR or Raman run or from the literature. One row per solvent, solvent
name plus wavenumber; `config/ir_shifts.example.csv` shows the shape of it. The table used for the
benzaldehyde case is [`reference/benzaldehyde_7solvents/ir_shifts.csv`](reference/benzaldehyde_7solvents/ir_shifts.csv).

## What is in here

```
SKILL.md                          the full workflow: stages, settings, pitfalls, how to adapt it
README.md / README_ch.md          this file and its Chinese version
config/system_config.example.sh   copy to config/system_config.sh and edit
config/solvent_table.tsv          solvent library template
config/ir_shifts.example.csv      frequency table template
scripts/                          tool check, molecules, parameters, MD stages, extraction, fit
tools/                            Packmol/Tinker builders, field extractor, analyze_uind wrapper
reference/benzaldehyde_7solvents/ the worked case: settings, frequency table, result, figure
reference/HAZARDS.md              the mistakes that cost me time
```

## Running it

```bash
cp config/system_config.example.sh config/system_config.sh   # STUDY_DIR, solute, probe, solvents
cp config/solvent_table.tsv "$STUDY_DIR"/solvent_table.tsv
cp config/ir_shifts.example.csv "$STUDY_DIR"/ir_shifts.csv   # replace with your own numbers
./scripts/00_check_tools.sh
./scripts/01_generate_molecules.sh
./scripts/02_parameterize.sh <solute>  $STUDY_DIR/molecules/<solute>.sdf  401
./scripts/02_parameterize.sh <solvent> $STUDY_DIR/molecules/<solvent>.sdf 501   # each solvent
./scripts/submit_md_stage.sh build_system
./scripts/submit_md_stage.sh minimize
./scripts/submit_md_stage.sh npt
./scripts/submit_md_stage.sh nvt
./scripts/submit_md_stage.sh production      # keep save-induced on
./scripts/extract_fields.sh
./scripts/fit_stark_rate.py --root-dir <analysis-dir> --ir-csv "$STUDY_DIR"/ir_shifts.csv
```

The MD stages detach and run all solvent/replicate combinations in parallel; add
`TARGET_SOLVENTS=` or `TARGET_REPLICATES=` to run a subset, and `MD_FOREGROUND=1` if you are
inside a job script and would rather have it run in the foreground.

## What it needs

Tinker built with `minimize`, `dynamic` and `analyze` (I have used v25 and v26), Poltype2 together
with xTB, Packmol, and numpy plus matplotlib for the fit. The scripts expect the Tinker and Packmol
binaries under `${HOME}/miniconda3/envs/amoeba/bin`; point `AMOEBA_ENV_BIN` or the individual
`*_CMD` variables somewhere else if yours live elsewhere. Everything defaults to something
sensible in `scripts/_defaults.sh`, and `00_check_tools.sh` prints the paths it ended up using.

Leave room on disk. A 5 ns production run writes `md_start.arc` and `md_start.uind`, 8–22 GB each once you
have a few hundred to a few thousand solvent molecules, so roughly 33 GB per replicate. The
seven-solvent case with three replicates is 700 GB.

## Things that bite

- `save-induced` has to be on for production. Without it there is no `.uind` and the extraction
  simply has nothing to read; nothing complains along the way.
- `ref.key` must not contain a box or `ewald`. That file is the gas-phase reference; adding a box
  shifts every field by about 0.1 MV/cm and no one tells you.
- `.uind` holds induced dipoles in Debye, but it is formatted exactly like a coordinate file.
  Reading it as coordinates gives fields that are wrong by orders of magnitude.
- `slope_se` is a lower bound. Neighbouring frames are strongly correlated, so the three
  replicates are what actually carry the independent information.

The rest of what bit me is in [`reference/HAZARDS.md`](reference/HAZARDS.md), and the workflow
itself, including how to move it to another probe or solvent, is in [`SKILL.md`](SKILL.md).
