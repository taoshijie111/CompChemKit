# Hazards of this workflow

Every item below either cost real time while this skill was built or would silently corrupt a
result. They are ordered roughly by how easy they are to miss.

## 1. This is not a real-space field decomposition

The observable here is

$$
\mathbf{F}_i = \frac{299.79}{\alpha_i}
\left(\vec{\mu}^{\,\mathrm{ind,periodic}}_i - \vec{\mu}^{\,\mathrm{ind,gas,frozen}}_i\right)
$$

i.e. a fully periodic MD induced dipole minus the induced dipole of the isolated probe at the same
frozen geometry. It is **not** the solvent-only field obtained by zeroing solvent charges, and not
the per-molecule real-space sum produced by an MDI/ELECTRIC-style decomposition (which also needs
re-imaged trajectories). The two are not interchangeable; do not mix numbers from the two routes.

## 2. `.uind` values are dipoles in Debye, not coordinates

Tinker writes induced dipoles with the same XYZ formatting it uses for coordinates, but the numbers
are `debye * uind`. Reading a `.uind` file as a trajectory, or mixing its columns with `.arc`
columns, produces fields wrong by orders of magnitude with no error message. The conversion
constant `299.79` (= 2.99792e8 V/cm) is what turns Debye/Å³ into MV/cm; keep α in Å³.

## 3. The gas-phase reference key must stay box-less and Ewald-less

`ref.key` contains only the solute parameters plus the polarization block. Adding a box line or
`ewald` changes every field by ~0.1 MV/cm (~0.05 cm⁻¹ on the fit) — small against the 9-38 MV/cm
solvent spread, but systematic and silent. Recompute the reference only with a key that has no
`a-axis`/`b-axis`/`c-axis` and no `ewald`.

`tools/analyze_uind` resolves the key by convention: `<stem>.key` first, then `system.key`, then
`tinker.key`. For `ref.arc` that is `ref.key`. Renaming the reference trajectory silently switches
the baseline to `system.key` (periodic, Ewald). Do not rename it.

## 4. `analyze_uind` is a wrapper, not a Tinker program

Tinker ships `analyze` but no `analyze_uind`. Induced dipoles are only written when the key
contains `SAVE-INDUCED`, which is easy to forget when calling `analyze` by hand. This skill ships
the wrapper as `tools/analyze_uind` (it appends `SAVE-INDUCED` and picks the key file, and honours
`ANALYZE_CMD`).

## 5. Ordering assumptions in the extractor

- The solute must occupy the **first `solute_atom_count` lines** of every frame. Reorder the
  composition and the "reference" silently becomes part of a solvent molecule.
- `ref.uind` must have exactly as many frames as were selected; the tool hard-fails otherwise. That
  is intentional: a mismatch would pair the wrong geometries.
- Probe indices are 1-based Tinker indices into the whole frame, not offsets within the solute.

## 6. Trajectory reading modes

`seek-prefix` computes byte offsets from the frame width measured on the **first 20 frames only**.
If any later frame has a different ASCII width (large coordinates, extra digits, wrapped values),
the rest of the trajectory is silently misread. `--read-mode auto` is **not** the conservative
choice: it picks `seek-prefix` whenever those first 20 frames look uniform and only falls back to
`stream` otherwise. `sequential-fixed` reads every frame in order but still assumes a constant
span; `stream` is the only mode that parses every frame and tolerates a varying width. Pass
`--read-mode stream` when in doubt.

Related: `--stride 10 --max-selected-frames 5000` encodes a 5000 ps window only when the save
interval is 0.1 ps. Set `--frame-interval-ps` (or `FRAME_INTERVAL_PS`) to the actual save interval
or all times and the reported window are wrong. A run that saved fewer frames simply yields fewer
samples, with no warning.

## 7. Silent n-reduction in the fit

Solvents present in the frequency table but without field data (or vice versa) are dropped from the
fit. `scripts/fit_stark_rate.py` warns and records them in `excluded_solvents`, but a fit with
fewer points than solvents still "succeeds". Always check `excluded_solvents` is empty and that
`n_points` equals your solvent count.

## 8. The frequency table is experimental input

It is the one part of the calibration the workflow does not compute: measured probe frequencies in
neat solvents. It is therefore also the part most likely to be mis-pasted or left stale. Keep the
exact CSV next to the fit output — `stark_fit_results.json` records its path in `ir_csv` — and
check that path before quoting a slope. Filling the table with calculated frequencies makes the
regression meaningless.

## 9. Do not rewrite the inputs of a finished run

Two traps worth avoiding when re-analysing:

- Never edit `ref.key` in place to run the gas-phase reference; copy it. A stage that "helpfully"
  normalises `ref.key` destroys the baseline of earlier runs.
- Never reuse an existing `ref.arc`/`ref.uind` without regenerating it. A reference left over from
  a shorter or different frame window poisons the next extraction. The extractor here always
  rewrites them.

## 10. Atom-type ranges and polarizabilities

Polarizability is looked up **by Tinker atom type** from the `polarize` records of the parameter
files listed in `system.key`; later files win on collision. Solute and solvent ranges must be
disjoint (the case study used 401-410 and 501+). A remap that accidentally collides two molecules
changes α and therefore every field, with no error.

## 11. Statistical honesty

Between-replicate SEM in the case study is 0.017-0.34 MV/cm, while the within-replicate per-frame
SEM is 0.05-0.23 MV/cm and the per-frame standard deviation is 3-16 MV/cm. Frames are heavily
correlated, the fit is unweighted, and three replicates are what actually carry the independent
information. `slope_se` is a lower bound; quote the replicate scatter and add block averaging if
the number matters.

## 12. Cost

Each production replicate writes `md_start.arc` **and** `md_start.uind`: 8-22 GB each for 5 ns at a
0.1 ps save interval with 500-4400 solvent atoms (16.7 GB average in the case study, ~33 GB per
replicate, 700 GB for 21 replicates). The extraction is I/O bound and single-threaded by default;
budget hours for a full study when the trajectories are cold, and raise `FIELD_WORKERS` only if
your storage handles parallel reads.
