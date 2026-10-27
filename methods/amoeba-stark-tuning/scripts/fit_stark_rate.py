#!/usr/bin/env python
"""Fit the vibrational Stark tuning rate from AMOEBA probe fields and EXPERIMENTAL frequencies.

Model (linear vibrational Stark effect):

    nu_obs = nu_0 + slope * F_probe          slope == Stark tuning rate [cm^-1 / (MV/cm)]

``F_probe`` per solvent is computed by this workflow: the mean over replicates of the
per-replicate mean field written by tools/extract_probe_field.py (``field_stats.json``).

``nu_obs`` is NOT computed here: it is your own measured probe frequency in each neat
solvent (FTIR/Raman, or literature values). One row per solvent. Without that table the
fit cannot be run, and filling it with calculated frequencies would make the result
meaningless. Start from config/ir_shifts.example.csv.

    ./scripts/fit_stark_rate.py --root-dir <analysis-dir> --ir-csv <your frequencies>.csv

Outputs stark_fit_input.csv, stark_fit_results.json and stark_fit.png in --out-dir.
Keep the input CSV next to those outputs: the slope is only meaningful together with the
frequency table it was fitted against.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

# Common spelling differences between an experimental IR table and directory names.
SYNONYMS = {
    "tetrahydrofuran": "thf",
    "dimethyl sulfoxide": "dmso",
    "dimethylsulfoxide": "dmso",
    "dimethylsulphoxide": "dmso",
    "methylene chloride": "dichloromethane",
    "dichloromethane": "dichloromethane",
    "methyl cyanide": "acetonitrile",
    "acetonitrile": "acetonitrile",
    "n-hexane": "hexane",
    "nhexane": "hexane",
    "trichloromethane": "chloroform",
    "methylbenzene": "toluene",
}


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.strip().lower())


def parse_wavenumber(text: str) -> float:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if match is None:
        raise ValueError(f"Could not parse a wavenumber from {text!r}")
    return float(match.group(0))


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def sample_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def build_solvent_resolver(
    known_solvents: list[str], extra_synonyms: dict[str, str] | None = None
) -> "callable":
    """Map a free-text solvent name from the IR table onto a directory name."""
    exact = {name.lower(): name for name in known_solvents}
    normalized = {normalize(name): name for name in known_solvents}
    synonyms = dict(SYNONYMS)
    for key, value in (extra_synonyms or {}).items():
        synonyms[normalize(key)] = value

    def resolve(display_name: str) -> str | None:
        key = display_name.strip().lower()
        if key in exact:
            return exact[key]
        if normalize(display_name) in normalized:
            return normalized[normalize(display_name)]
        target = synonyms.get(normalize(display_name))
        if target is not None:
            if target in exact:
                return exact[target]
            if normalize(target) in normalized:
                return normalized[normalize(target)]
        return None

    return resolve


def read_ir_csv(path: Path, name_column: str | None, value_column: str | None) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = [name.strip() for name in (reader.fieldnames or [])]
        lowered = {name.lower(): name for name in fieldnames}

        resolved_name = name_column or next(
            (lowered[key] for key in ("name", "nanme", "solvent", "molecule") if key in lowered), None
        )
        if resolved_name is None:
            raise ValueError(f"{path} needs a name column (tried name/nanme/solvent/molecule); found {fieldnames}")
        resolved_value = value_column or next(
            (
                lowered[key]
                for key in ("ir_wavenumber", "wavenumber", "frequency", "nu_obs", "ir_wavenumber_cm1")
                if key in lowered
            ),
            None,
        )
        if resolved_value is None:
            raise ValueError(f"{path} needs a wavenumber column; found {fieldnames}")

        records = []
        for row in reader:
            display_name = (row.get(resolved_name) or "").strip()
            if not display_name or display_name.startswith("#"):
                continue
            records.append(
                {
                    "display_name": display_name,
                    "ir_wavenumber_cm1": parse_wavenumber(row[resolved_value]),
                }
            )
    if not records:
        raise ValueError(f"{path} contains no usable rows")
    return records


def read_field_stats(md_dir: Path, metadata_name: str) -> dict[str, list[dict[str, object]]]:
    by_solvent: dict[str, list[dict[str, object]]] = defaultdict(list)
    for path in sorted(md_dir.glob(f"*/replicate_*/fields/{metadata_name}")):
        solvent = path.parts[-4]
        replicate = path.parts[-3]
        data = json.loads(path.read_text(encoding="utf-8"))
        by_solvent[solvent].append(
            {
                "replicate": replicate,
                "field_mean_MV_cm": float(data["field_mean_MV_cm"]),
                "field_sem_MV_cm": float(data.get("field_sem_MV_cm", 0.0)),
                "frames": int(data.get("frames", 0)),
                "path": str(path),
            }
        )
    return by_solvent


def fit_line(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    x_mean = float(np.mean(x))
    slope, intercept = np.polyfit(x, y, deg=1)
    y_hat = intercept + slope * x
    resid = y - y_hat
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
    dof = len(x) - 2
    sxx = float(np.sum((x - x_mean) ** 2))
    sigma2 = ss_res / dof if dof > 0 else float("nan")
    return {
        "slope_cm1_per_MV_cm": float(slope),
        "intercept_cm1": float(intercept),
        "r2": 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
        "n_points": int(len(x)),
        "slope_se": math.sqrt(sigma2 / sxx) if dof > 0 and sxx > 0 else float("nan"),
        "intercept_se": math.sqrt(sigma2 * (1.0 / len(x) + x_mean**2 / sxx))
        if dof > 0 and sxx > 0
        else float("nan"),
        "rmse_cm1": math.sqrt(ss_res / len(x)),
    }


def apply_publication_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "font.size": 7,
            "axes.labelsize": 7,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "axes.spines.right": True,
            "axes.spines.top": True,
            "axes.linewidth": 0.8,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.major.size": 3,
            "ytick.major.size": 3,
            "xtick.major.width": 0.8,
            "ytick.major.width": 0.8,
            "legend.frameon": False,
            "figure.dpi": 180,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.03,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fit a vibrational Stark tuning rate from AMOEBA probe fields.")
    parser.add_argument("--root-dir", required=True, help="Analysis root containing md/ (field_stats.json)")
    parser.add_argument(
        "--ir-csv",
        default="ir_shifts.csv",
        help="CSV of EXPERIMENTAL probe frequencies (one row per solvent), relative to --root-dir "
        "unless absolute; template: config/ir_shifts.example.csv",
    )
    parser.add_argument("--out-dir", default=None, help="Output directory (default: <root-dir>/stark_fit)")
    parser.add_argument("--ir-name-column", default=None, help="Name column of the IR CSV (auto-detected)")
    parser.add_argument("--ir-value-column", default=None, help="Wavenumber column of the IR CSV (auto-detected)")
    parser.add_argument("--metadata-name", default="field_stats.json", help="Per-replicate field metadata filename")
    parser.add_argument("--labels-json", default=None, help="Optional {solvent: {label, offset, ha}} plot styling")
    parser.add_argument("--xlabel", default="AMOEBA probe field (MV cm$^{-1}$)")
    parser.add_argument("--ylabel", default="probe frequency (cm$^{-1}$)")
    args = parser.parse_args()

    root = Path(args.root_dir).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else root / "stark_fit"
    out_dir.mkdir(parents=True, exist_ok=True)

    ir_path = root / args.ir_csv
    if not ir_path.is_file():
        raise FileNotFoundError(
            f"Experimental frequency table not found: {ir_path}\n"
            "This file is your input, not something the workflow produces: one row per solvent with the\n"
            "probe frequency you measured in that neat solvent. Start from config/ir_shifts.example.csv, e.g.\n"
            f"  cp config/ir_shifts.example.csv {ir_path}\n"
            "and replace the numbers, or pass an absolute path with --ir-csv."
        )

    field_stats = read_field_stats(root / "md", args.metadata_name)
    if not field_stats:
        raise ValueError(f"No {args.metadata_name} found under {root / 'md'}; run scripts/extract_fields.sh first")

    labels_config: dict[str, dict[str, object]] = {}
    if args.labels_json:
        labels_config = json.loads(Path(args.labels_json).read_text(encoding="utf-8"))
    resolve = build_solvent_resolver(sorted(field_stats), labels_config.get("synonyms"))  # type: ignore[arg-type]

    ir_records = read_ir_csv(ir_path, args.ir_name_column, args.ir_value_column)

    rows: list[dict[str, object]] = []
    unmatched: list[str] = []
    for ir in ir_records:
        display_name = str(ir["display_name"])
        solvent = resolve(display_name)
        if solvent is None:
            unmatched.append(display_name)
            rows.append(
                {
                    "solvent": None,
                    "display_name": display_name,
                    "ir_wavenumber_cm1": ir["ir_wavenumber_cm1"],
                    "n_replicates": 0,
                    "field_mean_MV_cm": float("nan"),
                    "field_std_between_replicates_MV_cm": float("nan"),
                    "field_sem_between_replicates_MV_cm": float("nan"),
                    "replicates": "",
                    "included_in_fit": False,
                }
            )
            continue
        reps = field_stats.get(solvent, [])
        fields = [float(rep["field_mean_MV_cm"]) for rep in reps]
        field_mean = mean(fields) if fields else float("nan")
        field_std = sample_std(fields) if fields else float("nan")
        field_sem = field_std / math.sqrt(len(fields)) if len(fields) > 1 else 0.0
        rows.append(
            {
                "solvent": solvent,
                "display_name": display_name,
                "ir_wavenumber_cm1": ir["ir_wavenumber_cm1"],
                "n_replicates": len(reps),
                "field_mean_MV_cm": field_mean,
                "field_std_between_replicates_MV_cm": field_std,
                "field_sem_between_replicates_MV_cm": field_sem,
                "replicates": ";".join(str(rep["replicate"]) for rep in reps),
                "included_in_fit": bool(reps),
            }
        )

    for solvent, reps in sorted(field_stats.items()):
        if not any(row.get("solvent") == solvent for row in rows):
            print(f"WARNING: field data exists for {solvent!r} but no IR row matched it; it is not in the fit")

    if unmatched:
        print(f"WARNING: no field data matched these IR rows: {', '.join(unmatched)}")
        print(f"         available solvent directories: {', '.join(sorted(field_stats))}")

    fit_rows = [row for row in rows if row["included_in_fit"]]
    if len(fit_rows) < 2:
        raise ValueError(f"Need at least 2 solvents with both IR and field data, got {len(fit_rows)}")

    x = np.array([float(row["field_mean_MV_cm"]) for row in fit_rows], dtype=float)
    y = np.array([float(row["ir_wavenumber_cm1"]) for row in fit_rows], dtype=float)
    fit = fit_line(x, y)

    with (out_dir / "stark_fit_input.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    result = {
        "fit_model": "IR_wavenumber_cm1 = intercept_cm1 + slope_cm1_per_MV_cm * field_mean_MV_cm",
        "stark_tuning_rate_cm1_per_MV_cm": fit["slope_cm1_per_MV_cm"],
        "stark_tuning_rate_abs_cm1_per_MV_cm": abs(fit["slope_cm1_per_MV_cm"]),
        "fit": fit,
        "ir_csv": str(ir_path),
        "field_stats_root": str((root / "md").resolve()),
        "included_solvents": [str(row["solvent"]) for row in fit_rows],
        "excluded_solvents": [str(row["solvent"]) for row in rows if not row["included_in_fit"]],
    }
    (out_dir / "stark_fit_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    apply_publication_style()
    fig, ax = plt.subplots(figsize=(3.54, 2.55))
    xerr = np.array([float(row["field_sem_between_replicates_MV_cm"]) for row in fit_rows], dtype=float)
    ax.errorbar(
        x,
        y,
        xerr=xerr,
        fmt="o",
        markersize=3.6,
        markerfacecolor="#2b2b2b",
        markeredgecolor="white",
        markeredgewidth=0.45,
        color="#2b2b2b",
        ecolor="#9aa0a6",
        elinewidth=0.8,
        capsize=2.2,
        capthick=0.8,
        zorder=3,
    )
    for row in fit_rows:
        solvent = str(row["solvent"])
        style = labels_config.get(solvent, {})
        offset = tuple(style.get("offset", (4, 4)))  # type: ignore[arg-type]
        ax.annotate(
            str(style.get("label", row["display_name"])),
            (float(row["field_mean_MV_cm"]), float(row["ir_wavenumber_cm1"])),
            xytext=offset,
            textcoords="offset points",
            fontsize=6.5,
            color="#2b2b2b",
            ha=str(style.get("ha", "left")),
        )

    x_pad = 1.2
    y_pad = 1.35
    x_line = np.linspace(float(np.min(x)) - x_pad, float(np.max(x)) + x_pad, 100)
    y_line = fit["intercept_cm1"] + fit["slope_cm1_per_MV_cm"] * x_line
    ax.plot(x_line, y_line, color="#b33b2e", linewidth=1.1, zorder=2)
    ax.set_xlim(float(np.min(x)) - x_pad, float(np.max(x)) + x_pad)
    ax.set_ylim(float(np.min(y)) - y_pad, float(np.max(y)) + y_pad)
    ax.set_xlabel(args.xlabel)
    ax.set_ylabel(args.ylabel)
    ax.tick_params(axis="both", which="both", direction="in", top=False, right=False)
    ax.text(
        0.03,
        0.96,
        f"$\\nu = {fit['slope_cm1_per_MV_cm']:.3f}F + {fit['intercept_cm1']:.2f}$\n"
        f"$R^2$ = {fit['r2']:.3f}",
        transform=ax.transAxes,
        fontsize=6.5,
        va="top",
        ha="left",
        color="#2b2b2b",
    )
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(out_dir / "stark_fit.png")
    plt.close(fig)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
