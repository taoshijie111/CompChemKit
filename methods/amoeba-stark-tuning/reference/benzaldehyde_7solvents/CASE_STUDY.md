# Case study: benzaldehyde C=O in seven solvents

The reference result this skill was distilled from. The MD trajectories themselves are not
shipped (tens of GB); what follows is the system definition, the settings, and the numbers you
should recover if you rebuild it.

## System

| item | value |
|---|---|
| probe | benzaldehyde, 14 atoms; bond axis carbonyl **C(index 2) -> O(index 1)** |
| solvents | hexane, thf, dichloromethane, chloroform, toluene, acetonitrile, dmso |
| replicates | 3 independent boxes per solvent (21 systems) |
| box | 40 x 40 x 40 Å, Packmol `tolerance 2.0`, `discale 1.5` |
| solvent counts | hexane 295, thf 474, CH₂Cl₂ 602, CHCl₃ 481, toluene 363, MeCN 738, DMSO 540 |
| force field | AMOEBA (Poltype2); solute types 401-410, each solvent 501+ |
| probe polarizabilities | C (type 402) α = 1.6000 Å³, O (type 401) α = 0.9140 Å³ |
| mean C=O length | 1.2302 Å (hexane, replicate 1) |

## MD settings (per replicate)

| stage | setting |
|---|---|
| minimize | Tinker `minimize`, RMS gradient target 0.5, `polar-eps 1.0e-5` |
| NPT | 50 ps, 1 fs, 300 K, 1 atm, Berendsen `tau-pressure 1.0`, `volume-scale molecular` |
| NVT | 200 ps, 1 fs, 300 K, continues from the NPT restart |
| production | 5 ns, 1 fs, 300 K, 1 atm, **Monte Carlo barostat**, `save-induced`, save every 0.1 ps |
| electrostatics | `ewald`, `ewald-cutoff 7.0`; `neighbor-list`, `vdw-cutoff 12.0`, `vdw-correction` |
| integrator / thermostat | `integrator beeman` + `thermostat andersen`, `collision 0.1` |
| field extraction | `stride 10`, 5000 frames per replicate, 1-5000 ps window, `seek-prefix` |

## Result

Per-solvent mean field (3 replicates, 5000 frames each):

| solvent | mean field (MV/cm) | between-replicate std | SEM |
|---|---:|---:|---:|
| hexane | -9.142349 | 0.029797 | 0.017204 |
| toluene | -20.780346 | 0.144086 | 0.083188 |
| thf | -25.395221 | 0.192936 | 0.111392 |
| dichloromethane | -32.260403 | 0.176151 | 0.101701 |
| chloroform | -33.519949 | 0.586012 | 0.338334 |
| acetonitrile | -36.968343 | 0.317739 | 0.183447 |
| dmso | -38.103113 | 0.453575 | 0.261872 |

Fitted against the measured frequencies in `ir_shifts.csv`:

$$
\bar{\nu}_{\mathrm{C=O}} = 0.448302\,F_{\mathrm{C=O}} + 1715.361
$$

| fit quantity | value |
|---|---|
| `slope` (Stark tuning rate, $|\Delta\vec{\mu}|$) | 0.4483024697160737 cm⁻¹/(MV cm⁻¹) |
| `intercept` (zero-field C=O frequency) | 1715.3609101662419 cm⁻¹ |
| $R^2$ | 0.9724957459099587 |
| `rmse` | 0.724 cm⁻¹ |
| `slope_se` | 0.0337 |
| $n$ | 7 |

Sign convention: $F$ is positive along C → O. All seven solvents give a negative field, and the
more negative the field the lower the C=O frequency, i.e. a positive slope on this axis.

`stark_fit.png` is the corresponding figure; `plot_labels.json` holds its per-solvent labels.

## Validation

- The extraction in this skill reproduces the original per-solvent fields **frame by frame**: on
  all 5000 frames of `hexane/replicate_1` the mean, standard deviation, SEM and mean probe length
  agree to every printed digit, and the regenerated gas-phase reference (`ref.arc`, `ref.uind`) is
  byte-identical.
- The fit in this skill reproduces the original slope/intercept/R² to ~$10^{-14}$ (double-precision
  round-off).
- The whole pipeline — build -> minimize -> NPT -> NVT -> production with `save-induced` ->
  extraction — was smoke-tested end to end on a fresh one-replicate system built from these
  parameters.

## Caveats

- The acetonitrile frequency used here (1699.943 cm⁻¹) is taken as measured; the source record did
  not document its provenance. It shifts the slope by ~6% relative to 1701.81 cm⁻¹, so treat the
  value as part of the input data, not as a fitted quantity.
- `slope_se` is a lower bound: it reflects between-replicate scatter only, the fit is unweighted,
  and consecutive frames are strongly correlated. Prefer quoting the replicate scatter, and add
  block averaging if the uncertainty matters.
