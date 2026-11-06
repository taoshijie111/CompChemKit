# FEFF failure modes (and how to defend against them)

Everything here was observed with a serial FEFF10 build on molecular C/N/O K-edge XANES. None of
it depends on a particular machine, scheduler or directory layout.

## 1. `screen` (RPA core hole) crashes or hangs on some geometries

Symptom: with `COREHOLE RPA`, the `screen` module exits with `rc=2` and a null-pointer traceback in
`screen.err`, or it simply never returns. Different frames of the *same* molecule can behave
differently, and raising `xkmax` does not help — it is geometry-dependent, not a card problem.

Defence:
- Give **every module** a hard timeout. Normal modules finish in well under 10 s on a small
  molecule; 120 s is already 12× margin and keeps one bad site from owning a worker for hours.
- On failure, retry the site once with a different core-hole model (`COREHOLE FSR`, which skips
  `screen` entirely) and record that the spectrum came from the fallback. Keep the fallback flag
  next to the data: mixing core-hole models silently is a physics error.
- If both fail, record the site as failed and move on. Do not abort the batch.

## 2. `ff2x` fails inside `polint` and still exits 0

Symptom: `ff2x.err` ends with `STOP failure in polint`, `ff2x` returns 0, and `xmu.dat` contains
only the ~701-byte header — no data rows.

Defence: validate what you parsed. Require a 2-D array with a plausible number of rows and finite
values before using it. A bare exit-code check passes this case and then crashes later in the
aggregation with an obscure indexing error.

## 3. Resuming on half-written spectra

If a batch is restarted, previously extracted `spectrum.csv` files are skipped. A file left
half-written by an interrupted process (0 bytes, or header only) will be read back as an empty
array and crash the worker.

Defence: on resume, validate shape and finiteness of the stored spectrum; on failure delete that
site's output and recompute it. Never trust the mere existence of the file.

## 4. Fixed windows vs FEFF's own grid

FEFF decides its own energy mesh from `EDGE`/`XANES`; the analysis window is imposed afterwards.
The two do not have to agree. Observed: the N K-edge grid started at 395.8–396.5 eV, so a window
beginning at 395.0 eV was filled with zeros for the first ~7 points (1.4 eV) of 99.8% of spectra.

Defence: compare the window start with `xmu.dat`'s first energy; move the window, or mark the
uncovered points as missing. Zero-filling creates a fake leading edge that a model will happily
learn.

## 5. Cost and disk are dominated by the intermediate files

One site writes ~84 files / ~7 MB (`apot.bin` ~3 MB, `gg.bin` + `gg.dat` ~1.3 MB each,
`pot.bin` ~0.9 MB, plus small ones). Only `feff.inp`, `xmu.dat` and the extracted spectrum are
worth keeping (~20 KB).

Defence: run each site in a scratch directory, copy out the three keepers, delete the rest
immediately. A cheap pruning step turns a multi-TB intermediate footprint into tens of GB.

## 6. One reaction/frame is not the unit of parallelism

Sites are independent; a structure with many sites is not. If the batch is parallelised over
"structures", a structure with 10 frames × 6 sites occupies one worker for 60 sequential site
runs, and one slow site stalls all of them. Parallelise over sites (or over (structure, frame)
groups small enough to keep workers fed), and checkpoint at the site level so restarts are cheap.

## 7. Do not sum across edges

C, N and O K-edge windows sit at completely different absolute energies. Adding them produces a
meaningless curve. Combine only within one edge; for a full multi-edge picture, concatenate the
per-element spectra on their own energy axes.

## 8. Launcher scripts that source site profiles

If a wrapper script sources a site-specific login profile or module system before running FEFF,
`set -u` can abort it on the first undefined variable inside that profile, often with no visible
error. Use `set -e` (and `set -o pipefail` where available) without `-u` in such wrappers.
