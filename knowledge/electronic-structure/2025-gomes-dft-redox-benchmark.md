---
title: "Best DFT model chemistries for S0, S1 and T1 redox potentials of organic photoredox catalysts"
category: electronic-structure
type: paper
authors: "Gomes L. A.; Lopez S. A."
year: 2025
venue: "J. Phys. Chem. A"
doi: "10.1021/acs.jpca.5c02406"
url: "https://doi.org/10.1021/acs.jpca.5c02406"
added: 2026-10-28
read: deep
confidence: medium
summary: "147 DFT/TD-DFT model chemistries vs experiment on 9 organic photoredox catalysts: PBE0-D3BJ and N12-SX/6-311+G(d,p) for S1 redox (MAE 0.16/0.08 eV), ωB97X and BHandH/6-311+G(d,p) for T1 redox (0.10/0.24 eV)."
tags: [dft, td-dft, redox-potential, photoredox, benchmark, solvation, excited-states]
scope: "Organic photoredox catalysts (cyanoarenes, benzophenones, xanthenes, acridinium) in MeCN vs SCE; S0/S1/T1 reduction and oxidation potentials and S1/T1 E0-0; 21 functionals x 7 basis sets."
related: []
---

# Best DFT model chemistries for S0, S1 and T1 redox potentials of organic photoredox catalysts

> Paper: Gomes, L. A.; Lopez, S. A. *J. Phys. Chem. A* **2025**, *129*, 6144–6154.
> DOI: [10.1021/acs.jpca.5c02406](https://doi.org/10.1021/acs.jpca.5c02406) · SI included ·
> open data: [figshare 10.6084/m9.figshare.25234249](https://doi.org/10.6084/m9.figshare.25234249)
> (optimized structures, log files, computed properties).
> Read: full paper + SI (Tables S1–S6); read 2026-10-28.

This is the reference benchmark to grab when you need a ground- or excited-state reduction/oxidation
potential for an organic photoredox catalyst (OPC) and you want a DFT/TD-DFT level you can defend.
147 model chemistries (21 functionals × 7 basis sets) are scored against experimental S0, S1 and T1
potentials and S1/T1 E0–0 energies for nine OPCs in acetonitrile. The headline: no single model
chemistry wins everywhere — the best functional depends on the state (S0 vs S1 vs T1) and on
whether you want a reduction or an oxidation potential.

## Bottom line

- **S1 reduction → PBE0-D3BJ/6-311+G(d,p)**: MAE 0.16 eV, R² = 0.90, ~2 h ES frequency job.
  Next best overall: B3LYP-D3BJ/6-311+G(d,p) (0.19 eV, 3 h) and mPW1PW91/aug-cc-pVDZ (0.19 eV, 5 h).
  N12-SX/aug-cc-pVDZ had the single lowest MAE (0.15 eV) but did not make the paper's MAE+CPU top 3.
- **S1 oxidation → N12-SX/6-311+G(d,p)**: MAE 0.08 eV, R² = 0.82, ~10 h. B3LYP-D3BJ/6-311+G(d,p)
  is much more correlated across the series (R² = 0.99, MAE 0.13 eV, 6 h) — use it when *ranking*
  catalysts matters more than absolute MAE.
- **T1 reduction → ωB97X/6-311+G(d,p)**: MAE 0.10 eV, R² = 0.94, ~6 h. ωB97X-D/6-311+G(d,p) is the
  cheap option (0.12 eV, 4 h); M06-2X/aug-cc-pVDZ is the expensive one (0.11 eV, 6 h).
- **T1 oxidation → BHandH/6-311+G(d,p)**: MAE 0.24 eV, R² = 0.92, ~2 h. BHandH was the *only*
  functional with consistently low T1 oxidation error (0.24 eV with 6-311+G(d,p), 0.26 eV with
  aug-cc-pVDZ).
- **GS potentials**: for reduction use B3LYP-D3BJ, BB95, TPSSH or MPW1B95 **with diffuse functions**
  (MAE 0.05–0.07 eV); avoid BHandH, M11-L, M06-HF, SVWN and SVWN-5 (0.17–0.75 eV). For oxidation use
  TPSSH, B3LYP-D3BJ, BHandH or N12-SX with aug-cc-pVDZ or 6-311+G(d,p) (MAE 0.10–0.15 eV).
- **E0–0 energies**: S1 needs 20–25% exact exchange (B3LYP-D3BJ, mPW1PBE, mPW1PW91, PBE0-D3BJ) or
  N12-SX (MAE 0.20–0.25 eV); T1 needs high-EXX/range-separated hybrids (BMK-D3BJ, BHandH, M06-2X,
  MN12-SX, CAM-B3LYP-D3BJ, ωB97X, ωB97X-D; MAE 0.15–0.21 eV). The two states want different functionals.
- **Basis-set rule**: diffuse functions are non-negotiable for the radical anion (GS reduction);
  **6-311+G(d,p) is the cost/accuracy default**; aug-cc-pVDZ rarely pays off in MAE, and
  aug-cc-pVTZ almost never finishes inside a sane CPU budget.
- **Error budget**: expect ~0.1–0.2 eV MAE on OPC-like molecules, which is already comparable to the
  experimental reference uncertainty (my assessment). Do not report 0.01 V precision, and prefer
  *one* model chemistry for a whole congeneric series so systematic errors cancel when you compare
  catalysts.

## At a glance

| Target | Recommended model chemistry | MAE (eV) | R² | ES frequency CPU (h) |
| --- | --- | --- | --- | --- |
| S1 reduction | PBE0-D3BJ/6-311+G(d,p) | 0.16 | 0.90 | 2 |
| S1 oxidation | N12-SX/6-311+G(d,p) | 0.08 | 0.82 | 10 |
| T1 reduction | ωB97X/6-311+G(d,p) | 0.10 | 0.94 | 6 |
| T1 oxidation | BHandH/6-311+G(d,p) | 0.24 | 0.92 | 2 |

| Target | Best-performing choices (paper's analysis) | MAE range (eV) | Notes |
| --- | --- | --- | --- |
| S0 reduction | B3LYP-D3BJ, BB95, TPSSH, MPW1B95 | 0.05–0.07 | diffuse functions required; avoid BHandH, M11-L, M06-HF, SVWN, SVWN-5 |
| S0 oxidation | TPSSH, B3LYP-D3BJ, BHandH, N12-SX | 0.10–0.15 | aug-cc-pVDZ slightly better overall; no consistent diffuse trend |
| S1 E0–0 | 20–25% EXX: B3LYP-D3BJ, mPW1PBE, mPW1PW91, PBE0-D3BJ; or N12-SX | 0.20–0.25 | PBE0-D3BJ must use 6-311+G(d,p) (aug set under-converged) |
| T1 E0–0 | BMK-D3BJ, BHandH, M06-2X, MN12-SX, CAM-B3LYP-D3BJ, ωB97X, ωB97X-D | 0.15–0.21 | high-EXX/RSH; both 6-311+G(d,p) and aug-cc-pVDZ work |

The CPU column is the paper's reported time for a vibrational-frequency job on the excited-state
geometry of one representative molecule (XO/TXO/BP depending on the panel), not a total cost.

## Context

Photoredox catalysis relies on single-electron transfer (SET) between an organic photoredox catalyst
(OPC) and a substrate. The relevant quantity is not just the ground-state (GS) potential: after
excitation, the catalyst can be a much stronger reductant or oxidant, and the excited-state (ES)
potential is what decides whether SET is thermodynamically feasible. The paper restates the standard
relations (eqs 5 and 6): the ES reduction potential is the GS reduction potential plus the 0–0
excitation energy, and the ES oxidation potential is the GS oxidation potential minus the 0–0 energy.
Both the GS potential and E0–0 therefore have to be right; an accurate ES potential can otherwise be
the accidental sum of two errors.

Earlier work benchmarked pieces of this problem: Jacquemin and co-workers on TD-DFT 0–0 energies
(PBE0/M06 best, 0.22–0.23 eV; M06-2X/CAM-B3LYP R² = 0.95, MAE 0.25 eV), Pastore et al. on S0/S1
oxidation of triphenylamine dyes (MPW1K/CAM-B3LYP, 0.2–0.3 eV), McCarthy et al. on T1 reduction of
phenoxazines (M06/6-311+G(d,p)), Singh et al. on T1 potentials with B3LYP/6-311G(d), Choi and Kim on
spin-flip DFT (MSD −0.15 eV GS, 0.01 eV S1), and Feher et al. on DFT + neural-network corrections
(15 functionals, def2-TZVPP energies, MAE 0.2 V GS after a 0.2 V empirical shift correcting systematic
underestimation, and 0.3 eV S1). What was missing was a single
benchmark that covers ground and both excited states, many functionals and basis sets, and several
OPC families on the same experimental footing. This paper is that benchmark: 147 model chemistries,
9 molecules, 4 OPC families, >14,000 quantum-chemical calculations.

## Method essentials

### Potentials and E0–0

All potentials are referenced to SCE in acetonitrile. The GS potential comes from the IEFPCM(MeCN)
free energies of the reduced and oxidized forms (eq 1):

```
E1/2 = -(G_reduced - G_oxidized) / (n_e * F) - 4.429 V    (n_e = 1, F = Faraday constant; vs SCE, MeCN)
```

The −4.429 V term is the reference constant written into the paper's eq 1; the text states that the
results are vs SCE in MeCN, and eq 1 cites Isse & Gennaro (ref 56) for the absolute-potential scale,
but the paper does not decompose the constant into its components. Treat the constant and the
SCE/MeCN convention as one unit: if you port eq 1 to another solvent or electrode, do not copy the
number alone — a mismatched reference offset is easily as large as the method errors discussed here.

The 0–0 energy is the adiabatic energy difference between the ES and GS minima, corrected for the
ZPVE difference (eqs 2–4):

```
E_adia = E_ES(R_ES) - E_GS(R_GS)
ΔE_ZPVE = ZPVE_GS - ZPVE_ES
E0-0   = E_adia - ΔE_ZPVE
```

ES potentials then follow (eqs 5–6):

```
E*_red = E_red + E0-0
E*_ox  = E_ox  - E0-0
```

Worked example (DCB, S1): measured S0 reduction −1.46 V, S1 E0–0 = 4.01 eV → predicted S1 reduction
= −1.46 + 4.01 = 2.55 V, which is the measured S1 reduction potential. This arithmetic is the whole
game: the ES potential is only as good as the GS potential and the 0–0 energy that went into it.

### Workflow (what the numbers actually come from)

1. **Molecule generation** — RDKit builds 3D coordinates from SMILES.
2. **Conformer search** — Universal Force Field search, four low-lying conformers kept; PM7 and RM1-D
   optimizations plus a single-point energy with each model chemistry identify the lowest conformer.
   One conformer per molecule is carried forward (no Boltzmann averaging).
3. **Optimization and frequencies** — Gaussian 16 (RM1-D in GAMESS); S0 and radical cation optimized
   first in vacuo, then *all* species (S0, S1, T1, radical cation, radical anion) reoptimized with
   IEFPCM(MeCN). S0/T1/radical ions with DFT, S1 with TD-DFT (`td=(root=1)`). Ultrafine pruned
   (99,590) grid, SCF = Tight (EDIIS + CDIIS), analytic second derivatives, frequency check that all
   modes are real.
4. **Extraction** — free energies and ZPVE differences feed eqs 1–6.

### Benchmark set and reference data

Nine OPCs in four families: cyanoarenes (DCB, DCN, DCA), xanthene (RhB6G), benzophenones (BP, MK,
XO, TXO), acridinium (Mes-Acr-Me+). The ES that matters differs by family: cyanoarenes and RhB6G
react from S1, benzophenones undergo fast intersystem crossing and react from T1, Mes-Acr-Me+ is a
strong S1 oxidant. Experimental values are the paper's Table 2, reproduced from Romero and Nicewicz
(2016) and the original references cited there; all in eV, referenced to SCE/MeCN.

| Molecule | S1 E0–0 | T1 E0–0 | S0 E_red | S0 E_ox | S1 E_red | S1 E_ox | T1 E_red | T1 E_ox |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DCB | 4.01 | 3.04 | −1.46 | — | 2.55 | — | 1.58 | — |
| DCN | 3.57 | 2.41 | −1.27 | — | 2.30 | — | 1.14 | — |
| DCA | 2.90 | 1.81 | −0.91 | — | 1.99 | — | 0.90 | — |
| RhB6G | 2.32 | 2.09 | −1.14 | 1.23 | 1.18 | −1.09 | 0.95 | −0.86 |
| BP | 3.22 | 3.00 | −1.72 | 2.39 | 1.50 | −0.83 | 1.28 | −0.61 |
| MK | 2.98 | 2.70 | −2.20 | 0.86 | 0.76 | −2.12 | 0.48 | −1.84 |
| XO | 3.40 | 3.22 | −1.65 | 1.80 | 1.76 | −1.61 | 1.57 | −1.42 |
| TXO | 3.14 | 2.80 | −1.62 | 1.69 | 1.52 | −1.45 | 1.18 | −1.11 |
| Mes-Acr-Me+ | 2.68 | 2.37 | −0.49 | 1.88 | 2.19 | −0.80 | 1.88 | −0.49 |

`—` = not reported. Cyanoarenes have no GS oxidation data, which is why the GS-oxidation MAEs rest on
as few as three molecules.

The model-chemistry space is 21 functionals × 7 basis sets:

- **Basis sets**: Pople 6-31G(d), 6-31+G(d,p), 6-311+G(d,p); Dunning cc-pVDZ, aug-cc-pVDZ, cc-pVTZ,
  aug-cc-pVTZ.
- **Functionals** (EXX % / class): SVWN (0, LSDA), SVWN-5 (0, LSDA), M11-L (0, mGGA),
  BB95 (0, mGGA), TPSSh (10, hybrid-mGGA), B3LYP-D3BJ (20, hybrid-GGA), mPW1PW91 (25, hybrid-GGA),
  mPW1PBE (25, hybrid-GGA), PBE0-D3BJ (25, hybrid-GGA), M06 (27, hybrid-mGGA), MPW1B95 (31,
  hybrid-mGGA), BMK-D3BJ (42, hybrid-mGGA), MPW1K (43, hybrid-GGA), BHandH (50, hybrid-GGA),
  M06-2X (54, hybrid-mGGA), M06-HF (100, hybrid-mGGA), N12-SX (25, RSH-GGA), MN12-SX (25, RSH-mGGA),
  CAM-B3LYP-D3BJ (19–65, RSH-GGA), ωB97X (15.77–100, RSH-GGA), ωB97X-D (22.2–100, RSH-GGA).

Naming quirks before reproducing a number: the PDF prints `ωB97X` and `ωB97X-D` (Table 1, abstract,
conclusions), but plain-text extraction of the PDF drops the omega and yields `B97X`/`B97X-D` — if
your copy says B97X, it is ωB97X. The body also prints `B3LYP` where Table 1 and the SI say
`B3LYP-D3BJ`. Table 1 + SI are the authoritative record of what was actually run.

### How to read the metrics

- **MAE** — average magnitude of the error; the headline accuracy number.
- **MSE** — signed bias. Positive MSE means the computed potential is too positive (too easily
  reduced / too hard to oxidize); a small MAE with a large MSE means a systematic offset you could
  correct, a small MAE with MSE ≈ 0 means random scatter.
- **R²** — correlation across the catalysts that have data for that property (6 for the oxidation
  potentials, because the cyanoarenes lack oxidation data; 9 for the reductions and E0–0). It rewards
  getting the *ordering* right, which is what you need when ranking candidates, and it can be high
  even when the MAE is mediocre.
- **Standard deviation** — spread across molecules; a low MAE with a large spread means the method is
  lucky on average but unreliable for a new molecule.
- **Successful-convergence filter** — MAE is reported only for model chemistries that converged on at
  least 5 molecules (3 for GS oxidation); jobs were capped at 160 CPU-days per model chemistry.
  That cap silently truncates the expensive basis sets (see Limits). Per-combination MAE and standard
  deviation for every basis set are in SI Tables S3–S6 (GS reduction, GS oxidation, S1 E0–0, T1 E0–0).

## Key results

### Basis sets: diffuse functions for anions, 6-311+G(d,p) as the default

- **GS reduction.** Without diffuse functions the MAE across model chemistries spans 0.10–0.53 eV;
  with diffuse functions it narrows to 0.05–0.23 eV (the paper's summary excludes the LSDA
  functionals: SI Table S3 still gives SVWN 0.73–0.75 eV and SVWN-5 0.25–0.29 eV with diffuse bases).
  The radical anion is the reason: diffuse functions describe electron density far from the nuclei.
  Exceptions where diffuse functions did not help: SVWN, SVWN-5, M11-L, MPW1K. Double-ζ → triple-ζ
  adds little once diffuse functions are present.
- **GS oxidation.** No consistent basis-set trend: for the same functional the MAE varies 0.07–0.29 eV
  across basis sets. Pople double-ζ often beats triple-ζ (6-31+G(d,p) better than 6-311+G(d,p) by
  0.01–0.24 eV in most cases); among Dunning sets, triple-ζ with diffuse functions is generally better
  by 0.01–0.13 eV (exceptions TPSSH, CAM-B3LYP-D3BJ, M06-2X). Lowest individual entries include
  BMK-D3BJ/6-31G(d) (0.06 eV) and M06/aug-cc-pVTZ (0.09 eV), but they do not generalize.
- **S1 E0–0.** Basis-set effect is modest for a given functional (0.04–0.15 eV; MPW1K 0.20 eV) and has
  no consistent winner: N12-SX is best with aug-cc-pVDZ (0.20 eV), B3LYP-D3BJ with cc-pVDZ (0.22 eV).
  The practical problem is cost: **54% of S1 calculations with aug-cc-pVDZ or aug-cc-pVTZ failed** the
  160 CPU-day limit; with aug-cc-pVTZ only BMK-D3BJ converged for at least five molecules, and its
  frequency job cost 13–32× more than with 6-311+G(d,p).
- **T1 E0–0.** Basis-set effect is 0.02–0.14 eV and depends on EXX: functionals with 20–25% EXX barely
  move (0.02–0.04 eV), while hybrids with >42% EXX and RSH functionals move 0.05–0.14 eV and benefit
  from diffuse functions (lowest MAEs 0.08–0.20 eV). Exceptions with low MAE even without diffuse
  functions: N12-SX, MN12-SX (the paper also names MPW1K, but SI Table S6 gives 0.40–0.45 eV for it;
  see the paper-vs-SI bullet in Limits).

### Functional choice: EXX% is the main lever

- **GS reduction.** 67% of the tested functionals overestimate the potential (positive MSE,
  0.01–0.75 eV); only BB95, BMK-D3BJ and BHandH systematically underestimate. The best functionals
  reach MAE 0.05–0.07 eV with small spread (B3LYP-D3BJ, BB95, TPSSH, MPW1B95; std 0.02–0.05 eV).
  BHandH, M11-L, M06-HF, SVWN and SVWN-5 are poor (0.17–0.75 eV) — do not use them for GS reduction.
- **GS oxidation.** Almost every computed value is overestimated (MSE 0.02–0.82 eV); the only
  exception is TPSSH/aug-cc-pVDZ (MSE −0.10 eV). The recommended functionals (TPSSH, B3LYP-D3BJ,
  BHandH, N12-SX) give 0.10–0.15 eV with std 0.06–0.15 eV. aug-cc-pVDZ is the slightly better basis
  overall; BHandH is the exception where 6-311+G(d,p) is 0.01 eV better.
- **S1 E0–0.** Low-EXX functionals (0–43%) systematically underestimate (MSE −0.71 to −0.01 eV,
  except BMK-D3BJ); functionals with ≥50% EXX and RSH functionals overestimate (0.03–0.47 eV, except
  N12-SX/6-311+G(d,p) at −0.05 eV). The sweet spot is 20–25% EXX plus N12-SX: MAE 0.20–0.25 eV. PBE0
  is the exception to "aug-cc-pVDZ is fine" — fewer than five molecules converged with it, so pair
  PBE0-D3BJ with 6-311+G(d,p). Recommended: B3LYP-D3BJ, mPW1PBE, mPW1PW91, PBE0-D3BJ (with
  6-311+G(d,p)), or N12-SX; basis 6-311+G(d,p) or aug-cc-pVDZ.
- **S1 geometry warning (BP).** The S1 minimum of benzophenone is twisted: out-of-plane dihedrals
  near 180° and 91°, versus 150–166° in the GS. The low-error functionals reproduce this; BHandH,
  despite being excellent elsewhere, gives GS-like 150°/166° dihedrals and the largest S1 E0–0 error
  (0.67 eV). A high-EXX functional is not automatically a good excited-state geometry optimizer.
- **T1 E0–0.** Generally underestimated (MSE −0.44 to −0.01 eV); M06-2X/6-311+G(d,p) is essentially
  unbiased (0.00 eV) and M06-HF overestimates (+0.26/+0.28 eV). The best set — BMK-D3BJ, BHandH,
  M06-2X, MN12-SX, CAM-B3LYP-D3BJ, ωB97X, ωB97X-D — reaches 0.15–0.21 eV, with essentially the same
  MAE for 6-311+G(d,p) and aug-cc-pVDZ (absolute differences 0.01–0.03 eV).

### ES redox potentials: property-specific winners, and two cyanoarene traps

Model chemistries for ES potentials were pre-filtered to those that are accurate for *both* the GS
potential and the E0–0 — deliberately avoiding error cancellation. This is the methodological point
to copy: do not bolt a good E0–0 onto a mediocre GS potential and call the result accurate.

- **S1 reduction.** Candidates: B3LYP-D3BJ, mPW1PBE and N12-SX (both 6-311+G(d,p) and aug-cc-pVDZ),
  PBE0-D3BJ/6-311+G(d,p), mPW1PW91/aug-cc-pVDZ; MAE 0.15–0.23 eV, std 0.09–0.17 eV. N12-SX/aug-cc-pVDZ
  is the single lowest (0.15 eV). **Recommended: PBE0-D3BJ/6-311+G(d,p)** — MAE 0.16 eV, R² = 0.90,
  2 h, and the cheapest of the top group; the other top-3 by MAE + CPU are B3LYP-D3BJ/6-311+G(d,p)
  (0.19 eV, 3 h) and mPW1PW91/aug-cc-pVDZ (0.19 eV, 5 h).
- **S1 reduction traps — cyanoarenes.** DCA and DCB are the outliers: DCA absolute errors 0.26–0.44 eV,
  DCB 0.35–0.52 eV, against 0.01–0.41 eV for the other molecules. The causes are opposite. For DCA the
  S1 E0–0 is underestimated (−0.54 to −0.47 eV) while the GS reduction potential is overestimated
  (0.12–0.20 eV); because the ES reduction potential is their sum, the errors partially cancel. For
  DCB both are overestimated, so the error compounds. If your target is a cyanoarene, validate the GS
  potential and E0–0 separately before trusting the ES number.
- **S1 oxidation.** Only B3LYP-D3BJ and N12-SX were carried forward (both bases); MAE 0.08–0.17 eV.
  N12-SX/aug-cc-pVDZ is lowest (0.08 eV), but N12-SX/6-311+G(d,p) is the recommendation: MAE 0.08 eV,
  R² = 0.82, 10 h. B3LYP-D3BJ/6-311+G(d,p) gives MAE 0.13 eV with R² = 0.99 at 6 h — pick it if the
  relative ordering of a catalyst series is the deliverable, since its correlation is much better.
  Both aug-cc-pVDZ variants cost ~15 h.
- **T1 reduction.** Functionals that were simultaneously good for GS reduction and T1 E0–0: BMK-D3BJ,
  M06-2X, MN12-SX, CAM-B3LYP-D3BJ, ωB97X, ωB97X-D; MAE 0.10–0.18 eV, std 0.05–0.15 eV. **Recommended:
  ωB97X/6-311+G(d,p)** — MAE 0.10 eV, R² = 0.94, 6 h. The top-3 accuracy/cost set is M06-2X/aug-cc-pVDZ
  (0.11 eV, 6 h), ωB97X/6-311+G(d,p) (0.10 eV, 6 h), ωB97X-D/6-311+G(d,p) (0.12 eV, 4 h). For a given
  functional, aug-cc-pVDZ is 18–81% more expensive than 6-311+G(d,p) here (MN12-SX is the exception,
  where 6-311+G(d,p) is 15% more expensive).
- **T1 oxidation.** Only BHandH works: MAE 0.24 eV (6-311+G(d,p)) and 0.26 eV (aug-cc-pVDZ), R² = 0.92,
  ~2 h. **Recommended: BHandH/6-311+G(d,p).** The recommendation rests on a single functional, so it is
  the least cross-validated of the four ES numbers in this note.

### Cost summary

- The reported cost metric is the vibrational-frequency job on the excited-state geometry; total job
  time also includes the optimization. The reported times are ~2–15 h per molecule for the
  recommended methods on these small OPCs.
- Pople 6-311+G(d,p) is 31–68% cheaper than aug-cc-pVDZ for the S1 calculations of N12-SX, B3LYP-D3BJ
  and mPW1PBE.
- aug-cc-pVTZ is effectively out of budget: only BMK-D3BJ cleared the five-molecule threshold for
  S1 E0–0, and its frequency job was 13–32× the 6-311+G(d,p) cost.

## Limits and failure modes

- **Small, narrow benchmark.** Nine molecules, four families, one solvent (MeCN), one reference
  electrode (SCE), experimental values taken largely from one 2016 review. The MAE values (0.1–0.2 eV)
  are of the same order as the uncertainty of the experimental reference itself (my assessment); the
  paper does not propagate that uncertainty.
- **Implicit solvation only.** IEFPCM(MeCN) for every species; no explicit solvent, no counterions,
  no ionic-strength effects. Absolute potentials for charged species (acridinium, radical ions) are
  the most exposed to this.
- **One conformer per molecule.** The lowest-energy conformer from a UFF/PM7/RM1-D funnel is carried
  through; no Boltzmann weighting, no conformational averaging of E0–0 or potentials. Flexible OPCs
  can have conformational spread comparable to the method error.
- **TD-DFT limitations.** S1 is a single TD-DFT root from a closed-shell GS; no spin-flip, no
  multireference, no state-specific solvation, no double excitations. Charge-transfer or
  multireference character in a new OPC is outside what this benchmark validates.
- **Error cancellation is invisible in the final ES number.** The paper explicitly shows the DCA case
  where a bad E0–0 and a bad GS potential cancel. A good ES MAE does not mean the underlying pieces
  are good.
- **Truncated model-chemistry space.** The 160 CPU-day cap means the expensive basis sets are evaluated
  on fewer molecules (S1 with aug-cc-pVDZ/aug-cc-pVTZ: 54% failures; aug-cc-pVTZ mostly only BMK-D3BJ).
  GS-oxidation MAEs are based on 3–6 molecules because cyanoarene oxidation data do not exist.
- **`PBE0` + aug-cc-pVDZ is under-converged.** Fewer than five molecules converged for S1 E0–0, which
  is why the paper pairs PBE0-D3BJ with 6-311+G(d,p).
- **S1 geometry sensitivity.** The BP case shows that a functional can be accurate for potentials and
  wrong for the S1 geometry (or vice versa). If your observable depends on the excited-state geometry,
  this benchmark is not sufficient validation.
- **Spin contamination and SCF stability are not reported** for the radical ions; check ⟨S²⟩ and the
  stability of the wavefunction yourself.
- **No semiempirical or ML correction comparison.** Feher et al. report DFT + ML corrections
  (MAE 0.2 V GS after a 0.2 V empirical shift, 0.3 eV S1); if you only need a screening estimate,
  that route may be cheaper than these DFT recommendations.
- **Some headline ranges do not reproduce from the SI per-combination tables.** Examples: the
  diffuse-basis GS-reduction range 0.05–0.23 eV excludes SVWN/SVWN-5 (0.25–0.75 eV with diffuse
  bases); MPW1K is named as a T1 E0–0 no-diffuse exception but SI Table S6 gives 0.40–0.45 eV; M06-HF
  has a 0.09 eV GS-reduction entry at aug-cc-pVDZ despite sitting in the "0.17–0.75 eV" group; the S1
  E0–0 0.20–0.25 eV range refers to each functional's best basis (SI mPW1PBE/6-311+G(d,p) = 0.28 eV).
  Treat the headline ranges as the authors' generalizations and SI Tables S3–S6 as the per-combination
  data.
- **Transition-character detail in the SI is inconsistent (TXO only).** Table S1 and the SI sentence
  agree that S1 is π→π* for most molecules, nπ→π* for BP and n→π* for XO, but the sentence assigns TXO
  nπ→π* while Table S1 labels TXO π→π*. Treat the qualitative character as indicative only.

## Practical rules

1. **Pick the model chemistry by the property, not globally.**

   ```
   S0 reduction        → B3LYP-D3BJ/6-311+G(d,p)  (or TPSSH/6-311+G(d,p)); diffuse functions required
   S0 oxidation        → TPSSH/6-311+G(d,p) or B3LYP-D3BJ/aug-cc-pVDZ
   S1 E0-0             → B3LYP-D3BJ/6-311+G(d,p) or N12-SX/6-311+G(d,p)
   T1 E0-0             → ωB97X/6-311+G(d,p) or BMK-D3BJ/6-311+G(d,p)
   S1 reduction        → PBE0-D3BJ/6-311+G(d,p)
   S1 oxidation        → N12-SX/6-311+G(d,p)   (B3LYP-D3BJ/6-311+G(d,p) if ranking matters)
   T1 reduction        → ωB97X/6-311+G(d,p)
   T1 oxidation        → BHandH/6-311+G(d,p)
   ```

2. **If one functional has to cover a whole state**, B3LYP-D3BJ/6-311+G(d,p) appears in both the S1
   reduction and S1 oxidation candidate lists (0.19 and 0.13 eV), and it is also the GS-reduction
   workhorse — a defensible single-functional choice for an S1 study (my inference from the paper's
   candidate lists, not a paper recommendation). There is no equivalent single-functional compromise
   for T1 reduction and T1 oxidation.

3. **Do not mix levels within one property.** Compute the GS potential and E0–0 with the same model
   chemistry, then combine with eqs 5–6. The paper's selection strategy is designed around this; mixing
   a good E0–0 with a different functional's GS potential reintroduces the error-cancellation problem.

4. **Always report/convert consistently.** The paper's numbers are vs SCE in MeCN with the 4.429 V
   constant. If your experiments are vs Fc+/Fc or Ag/AgCl, convert both sides with one convention
   before comparing; a 0.1 V offset is larger than most of the method differences discussed here.

5. **Sanity-check the ingredients, not just the final potential.**
   - Compare the computed GS potential with experiment when the molecule is in Table 2 (expect ~0.1 V).
   - Compare E0–0 with the experimental 0–0 (Table 2); a 0.3–0.5 eV discrepancy is a red flag even if
     the final ES potential looks fine.
   - Check the S1 geometry: for benzophenone-like molecules the S1 minimum is strongly twisted
     (~180°/91° dihedrals); a GS-like geometry usually signals a bad E0–0.
   - Confirm no imaginary frequencies and check ⟨S²⟩ for radical ions.
   - For cyanoarenes, validate S0 reduction and E0–0 separately (the DCA/DCB traps).

6. **Use 6-311+G(d,p) by default; escalate to aug-cc-pVDZ only if you have evidence that diffuse
   functions on the excited state matter, and never plan a production run on aug-cc-pVTZ** — the
   convergence/cost penalty is not worth the marginal MAE.

7. **When screening a catalyst series, compute all candidates with one model chemistry.** Absolute
   MAEs of 0.1–0.2 eV are larger than the differences you are usually chasing; the correlation
   (R² = 0.90–0.99 for the recommended methods) and the cancellation of systematic errors across a
   congeneric series are what make the ranking meaningful.

8. **If the target is a new OPC family**, treat this benchmark as a prior, not a guarantee: re-run a
   handful of molecules against experiment (or against a higher-level reference) before trusting the
   recommended functional for the new scaffold, especially for charged or CT-prone systems.

## Connections

- Topic: `electronic-structure/` — this is the "which functional/basis set for which property"
  evidence base; it feeds any future `methods/` workflow for OPC redox-potential screening.
- Related `methods/` skills: none implements this workflow yet; `methods/hpc-cluster/` is the
  natural way to run the Gaussian frequency jobs at scale, and `methods/xtb-ir-pipeline/` is *not*
  relevant to potentials.
- Reusable data: the paper's figshare deposit (DOI in frontmatter) contains optimized structures,
  Gaussian log files and computed properties for all model chemistries — use it instead of
  recomputing if you need a specific number.
- No other `knowledge/` notes yet; when redox-potential notes accumulate, a joint note on
  "error cancellation between GS potentials and E0–0" would be the natural synthesis.

## References

1. Gomes, L. A.; Lopez, S. A. Benchmarking Density Functionals for Ground- and Excited-State
   Reduction and Oxidation Potentials of Organic Photoredox Catalysts. *J. Phys. Chem. A* **2025**,
   *129*, 6144–6154. DOI: [10.1021/acs.jpca.5c02406](https://doi.org/10.1021/acs.jpca.5c02406).
2. Romero, N. A.; Nicewicz, D. A. Organic Photoredox Catalysis. *Chem. Rev.* **2016**, *116*,
   10075–10166. (Source of the experimental potentials in Table 2.)
3. Jacquemin, D.; Planchat, A.; Adamo, C.; Mennucci, B. TD-DFT Assessment of Functionals for Optical
   0–0 Transitions in Solvated Dyes. *J. Chem. Theory Comput.* **2012**, *8*, 2359–2372.
4. Jacquemin, D.; Moore, B., 2nd; Planchat, A.; Adamo, C.; Autschbach, J. Performance of an Optimally
   Tuned Range-Separated Hybrid Functional for 0–0 Electronic Excitation Energies. *J. Chem. Theory
   Comput.* **2014**, *10*, 1677–1685.
5. Feher, P. P.; Madarasz, A.; Stirling, A. Prediction of Redox Power for Photocatalysts: Synergistic
   Combination of DFT and Machine Learning. *J. Chem. Theory Comput.* **2023**, *19*, 4125–4135.
6. Choi, J.; Kim, H. Spin-Flip Density Functional Theory for the Redox Properties of Organic
   Photoredox Catalysts in Excited States. *J. Chem. Theory Comput.* **2021**, *17*, 767–776.
7. Isse, A. A.; Gennaro, A. Absolute Potential of the Standard Hydrogen Electrode and the Problem of
   Interconversion of Potentials in Different Solvents. *J. Phys. Chem. B* **2010**, *114*, 7894–7899.
8. Optimized structures, log files and computed properties:
   [figshare 10.6084/m9.figshare.25234249](https://doi.org/10.6084/m9.figshare.25234249).

## Source notes

- Eq. 1 (p. 6146; signs checked against the PDF): `E1/2 = -(G_reduced - G_oxidized)/(n_e F) - 4.429`,
  with F the Faraday constant and n_e = 1; the text references the result to SCE in MeCN.
- Eqs. 5–6 (p. 6147): `E*_red = E_red + E0-0` and `E*_ox = E_ox - E0-0`.
- Conclusions (p. 6151): for S1 reduction, PBE0-D3BJ/6-311+G(d,p) (MAE 0.16 eV, R² = 0.90); for S1
  oxidation, N12-SX/6-311+G(d,p) (0.08 eV); for T1 reduction, ωB97X/6-311+G(d,p) (0.10 eV, R² = 0.94);
  for T1 oxidation, BHandH/6-311+G(d,p) (0.24 eV, R² = 0.92).
- Abstract: "…PBE0-D3BJ/6-311+G(d,p) and N12-SX/6-311+G(d,p) excelling for S1 states and
  ωB97X/6-311+G(d,p) and BHandH/6-311+G(d,p) perform best for T1 states." (Table 1 and the PDF print
  ωB97X; plain-text extraction drops the omega.)
- Caveat (p. 6150): for DCA the S1 E0–0 and GS reduction errors partially cancel; for DCB they compound
  — the paper's own warning against trusting an ES potential without checking its ingredients.
