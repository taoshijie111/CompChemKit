---
name: compchem-knowledge
description: Use when making a computational-chemistry method or interpretation decision — choosing a DFT functional, basis set, dispersion correction, solvation model or force field; judging how accurate a method is for a property; simulating or reading IR/Raman, NMR, UV-Vis or X-ray spectra; setting up MD, free-energy or ML-potential work; or weighing a benchmark. Routes to a literature-grounded knowledge base with one note per source, indexed by topic — open README.md, then read the single note that matches the decision.
---

# Computational Chemistry Knowledge Base

This folder is a **knowledge base**, not a workflow. It distils papers, reviews, preprints, blog
posts, documentation pages and talks into short decision notes: which method to use, what accuracy
to expect, what silently goes wrong, and how to read the number that comes out. One source is
exactly one Markdown note, filed under a topic directory.

## Use it like this

1. Open [`README.md`](README.md) — the topic taxonomy and the generated index (title, source, type,
   confidence, one-line takeaway) of every note.
2. Pick the single note that matches the decision at hand. Notes are short by design.
3. Before quoting a number, read `confidence`, `scope` and *Limits and failure modes*. A note is a
   distillation; when the number matters for publication, open the primary source (linked in the
   note's frontmatter and in its *References*).
4. Cite the note path **and** the primary source in anything you produce.

## Do not use it for

- Running a calculation — that is `methods/` (`xtb-ir-pipeline`, `amoeba-stark-tuning`,
  `hpc-cluster`).
- Raw data or binaries. Notes link to sources and keep only small tables.
- A substitute for the primary literature. Every note names its source; verify it before you
  publish a claim that rests on it.

## Topics

| Topic | Covers |
| --- | --- |
| `electronic-structure/` | DFT functionals, basis sets, dispersion, wavefunction methods, excited states, multireference, method-accuracy studies. |
| `thermochemistry-and-kinetics/` | Optimisation, frequencies, thermochemical corrections, conformers, transition states, rate theories. |
| `solvation-and-environment/` | Continuum and explicit solvation, cluster models, QM/MM embedding, environment effects. |
| `spectroscopy/` | IR/Raman/VCD, NMR, UV-Vis/ECD, X-ray: simulation protocols and interpretation. |
| `dynamics-and-force-fields/` | Classical and polarisable force fields, MD sampling, enhanced sampling, free energy. |
| `ml-and-automation/` | Machine-learned potentials, Δ-learning, datasets, automated and agent workflows. |
| `analysis-and-benchmarks/` | Bonding/wavefunction analysis, benchmark design, error statistics, uncertainty. |

A note that spans two topics lives in its primary topic and cross-links the other; nothing is
duplicated.

## Adding a note

A new source means a new file: copy [`_template.md`](_template.md), follow the *Note contract* in
[`README.md`](README.md#note-contract), then refresh the index:

```bash
python tools/build_index.py --write   # validate notes + regenerate the README index block
python tools/build_index.py           # check-only mode, exit 1 when notes or the index are stale
```

Keep one note per source, conclusions first, and every number attached to its conditions and its
source. Do not edit the README index by hand — it is generated between the `BEGIN:INDEX` and
`END:INDEX` comments.
