# FEFF cards and recommended values

All statements below come from the FEFF10 users guide (`references/feff10_users_guide.pdf`).
**The numbers are recommendations for molecular C/N/O K-edge XANES. Confirm them with the user
before a production run; none of them is a property of FEFF.**

## Cards used by the recommended protocol

| card | recommended | meaning (manual) |
|---|---|---|
| `EDGE` | `K 1.0` | Selects the edge. The optional second number is the amplitude reduction factor **S0²** (not an energy shift); values < 0.1 make FEFF estimate it from atomic overlap integrals. |
| `CONTROL` | `1 1 1 1 1 1` | Turns on all modules. |
| `PRINT` | `1 0 0 0 0 0` | Minimal printing (higher values write extra files and slow the run). |
| `COREHOLE` | `RPA` | `RPA` = RPA-screened core hole, computed by the `screen` module (BSE-like); `FSR` (default when omitted) = final-state rule, unscreened; `none` = no core hole. The manual recommends RPA for k-space work and notes that RPA omits the exchange term of the particle-hole interaction. |
| `EXCHANGE` | `0 0.0 0.000000` | `ixc=0` → Hedin-Lundqvist; `vr0`, `vi0` = constant real/imaginary potential shifts (eV). Zeros = no shift. |
| `SCF` | `<rfms1> 1 30 0.2 1` | `SCF rfms1 [lfms1 nscmt ca nmix]`. `lfms1=1` centres the sphere on the absorbing atom and is the **molecular** setting (0 is for solids); `nscmt` = max iterations (default 30), `ca` = mixing (default 0.2), `nmix` = default 1. Omit the card entirely for non-self-consistent overlapped-atom potentials. |
| `ABSOLUTE` | present | Disables FEFF's normalisation of the spectrum at ~40–50 eV above threshold. The header then reports the normalisation factor as `1.0`, and column 4 of `xmu.dat` is the **absolute cross-section in Å² per absorbing atom** (1 Å² = 100 Mbarn). |
| `FMS` | `<rfms> 0` | `FMS rfms [lfms2 minv …]`; full multiple scattering inside a sphere centred on the absorber. `lfms2=0` = real space. A converged XANES usually needs 50–150 atoms in the cluster; for small molecules the whole molecule is the cluster. |
| `RPATH` | `0.1` | Maximum half path length. `0.1 Å` effectively disables the path expansion, which the manual recommends for FMS-based XANES ("better results are obtained without the MS contribution"). |
| `XANES` | `4.0 0.04 0.1` | `XANES [xkmax xkstep vixan]`: max k of the XANES mesh (Å⁻¹), k step far from the edge, and `vixan` (eV) imaginary potential. k = 4 Å⁻¹ ≈ 61 eV above the edge; the manual warns FMS is inaccurate beyond k ≈ 6. |
| `POTENTIALS` | absorber `0`, others by first appearance | Potential table; the absorbing atom must be potential 0. |
| `ATOMS` | absorber first, then the rest | Cartesian coordinates (Å) with an optional potential index and label. Coordinates are written with 4 decimals by convention. |

Not used here: `DEBYE`/`SIG2` (EXAFS Debye-Waller only), `CFAVERAGE` (configuration average over
absorbers — the manual calls it unreliable in general and specifically questionable for XANES),
`EXAFS` (path expansion), `HOLE`/`NOHOLE` (deprecated in favour of `EDGE`/`COREHOLE`).

## Cluster radius

Recommended rule: `r = 10 Å` when the farthest atom from the absorber is < 10 Å, otherwise
`r = 15 Å`, and **refuse** the site when the extent reaches 15 Å (a bigger cluster changes the
cost model and the convergence question). Same value for `SCF rfms1`, `FMS rfms` and the path
sphere. For small molecules this is simply "the whole molecule"; shrink it towards the first
coordination shell only when the user asks for that (results change).

## Energy window

Fixed windows make spectra comparable across structures. Recommended grids: 200 points, 0.2 eV:

| edge | window (eV) | note |
|---|---|---|
| C K | 275.0 – 314.8 | starts ~9 eV below the typical C K edge on FEFF's absolute scale |
| N K | 397.0 – 436.8 | **397.0, not 395.0**: FEFF's own N grid was observed to start at 395.8–396.5 eV, so a 395.0 start silently zero-fills the first ~1.4 eV |
| O K | 528.0 – 567.8 | starts ~2 eV below the O K edge in FEFF units |

Before accepting a window, check `xmu.dat`'s first energy column against the window start. If the
grid starts above the window, either move the window up or mark the uncovered points missing.

## Combination rules (physics, not preference)

- μ is a per-absorber cross-section; a molecule with N atoms of the same element absorbs N times
  as much, so **same-element spectra add**. Do not normalise individual sites before adding: that
  would destroy the per-atom scale.
- Per-atom average = sum / (number of valid sites); derive it downstream from the validity mask
  instead of storing another field.
- Different edges live on different absolute energy ranges; **do not add them**. Concatenate.
- Experimental spectra are usually normalised to an edge jump of 1 per absorbing atom. If the
  target is comparison with experiment, normalise after combining, per element.
