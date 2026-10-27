# `knowledge/` — distilled knowledge, not runnable workflows

Everything in `methods/` answers *how to run a calculation*: which software, which flags, how to
get it onto a cluster. `knowledge/` answers the other half of the question: **what did we learn
that should change the calculation you are about to run?**

A knowledge skill collects literature-derived, benchmark-derived or hard-won practical experience
and states it as reusable conclusions. It is *not* a runnable workflow — if following your skill
means editing a script and submitting a job, it belongs in `methods/`, not here.

## What belongs here

- **Method/property guidance** — "which functional and basis set for which property", which
  solvation model for which observable, which reference level is good enough for a benchmark.
- **Pitfalls of a method** — failure modes, silent errors, convergence traps, unit/convention
  traps, "this looks converged but is not".
- **Benchmark and convergence tables** — MAE/MAD tables from the literature or from your own runs,
  convergence criteria per property or per code, basis-set-limit ladders.
- **Interpretation guides** — how to read a class of spectra, how to tell a real signal from an
  artifact, what a small imaginary frequency usually means.
- **Rules of thumb with provenance** — short, checkable statements plus the paper, benchmark or
  dataset they came from.

What does **not** belong here:

- Step-by-step runnable procedures → `methods/`.
- Large raw datasets or binaries (download links are fine, blobs are not).
- Unattributed personal opinion. State the evidence and the confidence; a "rule" without a source
  is a rumour.
- Anything site-specific (hostnames, accounts, cluster paths) — placeholders only.

## Required `SKILL.md` frontmatter

```yaml
---
name: short-kebab-case-name
description: Use when <trigger> — <what knowledge this gives and what it lets the agent decide>.
---
```

- **`name`** — kebab-case and identical to the folder name (*required*).
- **`description`** — the only text an agent sees before deciding to load the skill (*required*).
  Start with the trigger ("Use when …"), then say what the skill provides. If the knowledge is
  narrow, say where it does *not* apply; an over-broad description makes the skill fire on
  unrelated tasks.
- No other keys are required. Keep the body focused: front-load the conclusions, then the
  evidence and the references.

## Recommended layout

```
knowledge/<skill-name>/
├── SKILL.md          # frontmatter + the distilled conclusions (the "answer" goes first)
├── notes/            # derivations, per-paper notes, reasoning, worked examples
├── references/       # citation list / BibTeX / DOI list backing every claim
└── data/             # small CSV tables the notes refer to (no large binaries)
```

Only `SKILL.md` is mandatory; add `notes/`, `references/` and `data/` when they carry real
content. Keep tables in `data/` machine-readable (CSV/TSV) and cite the source of each one in
`references/`.

## Status

`knowledge/` is currently **empty**: this README is a placeholder and the only file here. No
knowledge skills have landed yet — the maintainer will add the first ones, following the contract
above. Until then, `install.sh` / `install.ps1` install nothing from this folder, because a skill
is only picked up when its folder contains a `SKILL.md`.

## How to contribute one

1. Create `knowledge/<skill-name>/` with the folder name equal to the skill `name`.
2. Write `SKILL.md`: frontmatter (`name`, `description`) plus a body whose first section is the
   conclusions, not the introduction.
3. One claim per bullet, each traceable to a source in `references/`; mark your own experience as
   such and say on how many systems it was observed.
4. Put numbers in tables under `data/` (CSV) and version-stamp them — "B3LYP/def2-TZVP, xtb 6.6.1" —
   so the table stays meaningful years later.
5. Check for personal or institutional identifiers: use `hpc.example.edu`, `your_username`,
   `/path/to/project` — never a real host, account or home path.
6. Keep all text UTF-8 with LF line endings.
7. Run `./install.sh` (or `.\install.ps1`) and confirm the new skill appears in the table.
