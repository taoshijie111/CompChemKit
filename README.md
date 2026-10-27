# CompChemKit

A curated collection of **agent skills for computational chemistry** — quantum chemistry,
force-field molecular dynamics, spectra simulation, and the cluster plumbing around them.

Each skill is a self-contained folder with a `SKILL.md` (YAML frontmatter + instructions) plus the
scripts, job templates and reference data it needs. Skills are loaded by an agent that reads
`SKILL.md` files — the DeepSeek Harness, or any other SKILL.md-based agent — so the same skill
works in your terminal, in an IDE assistant, or on a cluster login node.

The goal is not a library of programs but a library of **reproducible ways to do a specific
calculation**, including the traps: what has to be checked by hand, what silently produces a wrong
number, and which step costs the disk.

## How the repository is organised

| Folder | Holds | Test |
|---|---|---|
| `methods/` | **How to compute something**: software usage, HPC connection and job submission, concrete calculation workflows end to end. | Following it means running commands / editing scripts / submitting jobs. |
| `knowledge/` | **Distilled knowledge and experience**: what was learned from the literature, from benchmarks, or from practice — which method for which property, common pitfalls, convergence tables, how to read a class of spectra. | Following it means *deciding* something, not running a workflow. |

A rule is "runnable" → `methods/`. A rule is "conclusions and evidence" → `knowledge/`. See
[`knowledge/README.md`](knowledge/README.md) for the knowledge-skill contract.

```
CompChemKit/
├── methods/
│   └── <skill-name>/        SKILL.md + scripts, templates, reference data
├── knowledge/
│   └── <skill-name>/        SKILL.md + notes/, references/, data/
├── install.sh               installer (Linux / macOS / WSL / Git Bash)
├── install.ps1              installer (Windows PowerShell)
├── LICENSE                  MIT
└── README.md
```

## Skills

| Skill | Folder | What it does | Requires |
|---|---|---|---|
| `hpc-cluster` | [`methods/hpc-cluster/`](methods/hpc-cluster/) | Connect to any SSH HPC cluster: passwordless SSH bootstrap, partition/QOS/core-count choice, Slurm submit/monitor/cancel, file transfer with MD5 verification, and a local watchdog that wakes the agent when a job of a long multi-stage batch ends. Cluster addresses, accounts, scheduler names and software paths are kept in a local config file (`~/.compchemkit/config.json`), and per-cluster gotchas live in `platforms/<name>.md`. | SSH access to a Slurm/PBS cluster, Python 3.9+ with `paramiko` (fallback transport), PowerShell 7 for the watchdog |
| `amoeba-stark-tuning` | [`methods/amoeba-stark-tuning/`](methods/amoeba-stark-tuning/) | Vibrational Stark tuning rate and local probe-bond field from Tinker/AMOEBA MD: field from the induced-dipole difference (production minus gas-phase reference), per-solvent extraction, regression against your measured frequencies, publication-style plot. Ships a validated benzaldehyde / 7-solvent case study. | Tinker CPU binaries (`minimize`, `dynamic`, `analyze`, v25/v26), Poltype2 + xTB, Packmol, Open Babel, Python (numpy, matplotlib), **your own experimental IR frequencies**, ~33 GB disk per production replicate |
| `xtb-ir-pipeline` | [`methods/xtb-ir-pipeline/`](methods/xtb-ir-pipeline/) | Batch IR spectra from a SMILES list: Open Babel conformers → GFN2-xTB `--ohess` opt+freq → imaginary-frequency cleanup → Voigt/Lorentzian broadening into an HDF5 database, plus re-broadening and de-duplication. Ships SLURM array-job scripts. | `xtb` with `--ohess`, Open Babel with Python bindings, Python ≥ 3.9 (numpy, h5py, tqdm; numba strongly recommended), Slurm |

The table grows as skills are added. You do not have to edit the installers to add one: any
`methods/<name>/` or `knowledge/<name>/` folder that contains a `SKILL.md` is picked up
automatically.

## Install

The installers copy (or link) every skill folder into your agent's skills directory,
`~/.dsh/skills` by default.

```bash
# Linux / macOS / WSL / Git Bash
./install.sh                              # copy into ~/.dsh/skills
./install.sh --dest ~/agent/skills        # other destination
./install.sh --link                       # symlink instead of copy (falls back to copy)
./install.sh --force                      # allow replacing existing skills (asks first)
./install.sh --help
```

```powershell
# Windows PowerShell
.\install.ps1                             # copy into %USERPROFILE%\.dsh\skills
.\install.ps1 -Dest D:\agent\skills       # other destination
.\install.ps1 -Link                       # junction instead of copy (falls back to copy)
.\install.ps1 -Force                      # allow replacing existing skills (asks first)
.\install.ps1 -?                          # help
```

| Option | Linux/macOS | Windows | Meaning |
|---|---|---|---|
| destination | `--dest DIR` | `-Dest DIR` | where skills are installed |
| link mode | `--link` | `-Link` | `ln -s` / directory junction; falls back to copy on failure |
| replace existing | `--force` | `-Force` | required before an existing skill folder may be deleted |

Both installers print a table of what was installed and where. An existing skill directory is
**never** deleted implicitly: without `--force` / `-Force` it is skipped with a warning, and with
it you are asked to confirm interactively — a non-interactive run never deletes anything.

To install by hand, copy a skill folder into `~/.dsh/skills/<skill-name>/` and make sure the
folder name matches the `name` in its `SKILL.md` frontmatter.

## Configuration and secrets

This repository contains **no credentials, no cluster addresses, no usernames**. Every place that
needs one uses a placeholder such as `hpc.example.edu`, `your_username`, `/path/to/project` or
`~/.ssh/id_ed25519`.

A skill asks you for those values on first use and stores them **locally**, outside version
control — for example a per-study `config/system_config.sh` (the skill ships a
`config/system_config.example.sh` and its own `.gitignore` already excludes the real one), or
`config.local.*` / `*.local.json` / `.env` covered by the repository `.gitignore`. Keep access
credentials in your SSH agent or keyring; never paste them into a skill folder, a job script or a
commit.

## Safety

- **Skills run real jobs.** They submit to your scheduler, write many gigabytes, and some delete
  intermediate files by design. Read a skill's scripts and its pitfalls/hazards section before
  running it on a shared cluster, and start with a small smoke test.
- **Check the numbers.** A skill tells you how to compute something and how to sanity-check it; it
  does not validate your system for you. Unit and convention traps are real (Debye vs Å vs MV cm⁻¹,
  cm⁻¹ vs Eh, per-frame vs per-window averages) — the skills list the ones that were hit in practice.
- **Respect third-party licenses and your site policy.** Tinker, xtb, Open Babel, Poltype2,
  Packmol, Slurm and the rest keep their own licenses and terms; nothing here grants you access to
  a cluster or overrides its usage rules.
- **No warranty.** The skills are shared as-is under the MIT license — verify before you publish.

## Contributing

A skill is a folder plus a `SKILL.md` whose frontmatter has `name` (equal to the folder name) and
`description` (starting with the trigger "Use when …"). Put runnable workflows in `methods/`,
distilled knowledge in `knowledge/`. Keep the text UTF-8 with LF line endings, use placeholders
for anything site-specific, and test what you ship.

## License

[MIT](LICENSE) © 2026 taoshijie111.
