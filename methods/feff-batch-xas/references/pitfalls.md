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

## 9. A truncated cluster and a full `POTENTIALS` table do not mix

Symptom: `pot` stops with

```
FMS for a cluster of   29 atoms around atom type   0
 Cannot find all representative atoms
 Increase FMS radius and rerun.
 In subroutine FMS
```

then the next module fails with something unrelated — typically `screen` (or `xsph`) exiting `rc=2`
because `pot.bin` was never written:

```
At line 108 of file rdpot.f90 (unit = 3)
Fortran runtime error: Cannot open file 'pot.bin': No such file or directory
```

Cause: FEFF builds one potential per entry in `POTENTIALS`, and **every potential must have at least
one representative atom inside the FMS sphere**. If you crop the cluster to a radius but keep
listing every element of the whole molecule in `POTENTIALS`, any element that only exists outside
the sphere has no representative atom and FEFF refuses to continue.

This never shows up on small test molecules (the whole molecule fits inside the sphere, so every
element is present) and appears only once structures are larger than the cluster radius — the
normal case for a real dataset. In one 1.11 M-site batch it affected **16.6 % of all sites**.

Defence: crop first, then number the potentials from what survived.

```python
dist = np.linalg.norm(xyz - xyz[idx], axis=1)
kept = [i for i in range(len(elements)) if dist[i] <= r - 1e-6]
order = [idx] + [i for i in kept if i != idx]
others = list(dict.fromkeys(elements[i] for i in order[1:]))
pot = {e: i + 1 for i, e in enumerate(others)}
# ... and write only `order` to ATOMS
```

The absorber's own element still needs its own potential if it also appears among the other atoms
(potential 0 carries the core hole), which the `dict.fromkeys` over `order[1:]` gives you for free.
Atoms outside the sphere are unused by `SCF`/`FMS` anyway, so this is a no-op physically: on sites
whose sphere already contained every element, the spectrum is bit-identical before and after the
change (measured: max |Δμ| = 0 over the whole window).

## 10. A module can STOP and still exit 0

Fortran `STOP` under gfortran terminates the process with status 0. So a module that refuses to run
(pitfall 9, and probably other guard clauses) looks like success to any launcher that only checks
`returncode`. The failure then surfaces one or two modules later, in a module that has nothing to do
with the real problem.

Defence: check the content of each module's stderr as well as its return code.

```python
if rc != 0:
    return failure(f"{m}: rc={rc}")
err_text = (workdir / f"{m}.err").read_text(errors="replace")
if any(line.strip() == "STOP" for line in err_text.splitlines()):
    return failure(f"{m}: STOP in stderr (rc=0)")
```

A lone `STOP` line is specific enough not to collide with the harmless warnings FEFF writes
(`IEEE_DIVIDE_BY_ZERO`, muffin-tin notes, SCF iteration lines).

## 11. Validate a cross-section of the batch, not a single job

A one-site smoke test proves the launcher works; it does not prove the batch will produce data.
The expensive failures are silent: a run that "completes" every job in milliseconds while writing
all-NaN spectra, and an aggregation step that reports `n_molecules_ok = N` because it only counts
files that exist.

Minimum validation before submitting the full batch:

- pick the **smallest**, the **median** and the **largest** structure, and run *all* their sites;
- assert `site_ok.any()` per structure and that the stored μ is finite and non-zero;
- print, per shard, both `sites_ok` and `sites_fail`, and make the runner exit non-zero when
  `sites_ok == 0` — a shard that succeeded at nothing must not look like a finished shard;
- re-run one structure after any change to the input generator and require the spectrum to be
  unchanged where the change should be a no-op.

A cross-section run of 2 molecules and 20 sites (about five minutes) is what caught pitfall 9 in the
1.11 M-site batch; without it the batch would have produced a dataset missing one sixth of its sites,
with file names and logs that all looked successful.

## 12. Per-site artifacts do not scale to 10^6 sites

The three-piece set is ~20 KB per site, which sounds harmless until the site count is large:
10^6 sites is ~20 GB but **3 × 10^6 files**, and listing/backing up/synchronising a directory tree
that size on networked storage is impractical (a `find` over 35 k directories already took 16 min in
one case). Intermediates are worse — ~7 MB per site, delete them inside the worker.

Defence: aggregate. Store the per-site spectra in one array per structure (or per shard) and keep the
`feff.inp` / `xmu.dat` / `spectrum.csv` trio only for a deterministic sample (a few per mille of the
structures). `feff.inp` is a pure function of (geometry, cards), and the cards plus the generator's
version can be recorded alongside the data, so full reproducibility does not require keeping the
files.

## 13. An element table that stops at Kr kills every iodine/tellurium molecule

`make_input.py` writes the whole retained cluster into `ATOMS` and needs a Z for each species, but
the absorbing-element list is what usually gets checked. A table that ends at Kr returns
`KeyError: 'Z53'` for iodine at render time — the traceback lands in the worker's stderr, the site is
scored as a FEFF failure, retried to exhaustion, and then quietly aggregated as NaN. In a real
dataset this hit 376 structures and 10,198 sites (0.9%), and was only noticed because the last 1%
of the batch would not finish.

Defence: before submitting, take the union of all atomic numbers in the input and assert every one
of them is in the Z table. Better still, have the renderer fail with a message that names the
species and the file, not a bare `KeyError`.

## 14. "Valid only if every point is finite" throws away good spectra

Missing points below the FEFF grid start are part of the agreed output convention (pitfall 3), and
their count depends on the edge energy: at a 275–315 eV window on the C K edge a single missed
point disqualifies the spectrum, while O K at 528 eV rarely loses any. A collector that used
`np.isfinite(mu).all()` therefore kept only 21% of the C sites, 48% of N and 94% of O, and reported
79% of a million-site dataset as missing — with a per-element gradient as the only clue.

Defence: require a *minimum* number of finite points (a few percent of the grid is plenty), record
the per-spectrum finite count, and when summing sites across an element use the per-point mask so a
point that is NaN in every site stays NaN rather than collapsing to 0 through `nansum`.

## 15. A completion cache is not an authority on completeness

Self-regulating submitters keep a "which structures are finished" cache so they do not rescan a
million site directories each round. When a bug fix invalidates previously-failed sites, that cache
still marks their structures complete, the submitter reports "nothing left to submit" and exits, and
the run looks finished at 98.9%.

Defence: keep the cache as an optimisation only. Reconcile against a fresh, threaded `stat` pass over
the planned site list, print the exact gap, and make the final "is it done" decision from that scan
rather than from the cache or from a completed-file counter that can never reach the planned total
(failed sites have no output file, so `done == total` is the wrong test to begin with).
