# =============================================================================
# Study configuration for a Tinker/AMOEBA probe-field Stark tuning calculation.
#
#   cp config/system_config.example.sh config/system_config.sh
#   $EDITOR config/system_config.sh
#
# Only the science belongs in a study config; toolchain paths have defaults in
# scripts/_defaults.sh (see section 6 to override them). Every value below honours
# an existing environment variable, so a single setting can be changed for one
# command:
#
#   NPT_STEPS=2000 TARGET_SOLVENTS=toluene ./scripts/submit_md_stage.sh npt
# =============================================================================

# -----------------------------------------------------------------------------
# 1. Study root: holds molecules/, parameters/, md/, run_logs/, analysis/
# -----------------------------------------------------------------------------
STUDY_DIR="${STUDY_DIR:-${SKILL_DIR}/runs/my_study}"
PARAMETERS_DIR="${PARAMETERS_DIR:-${STUDY_DIR}/parameters}"

# -----------------------------------------------------------------------------
# 2. Probe (solute) and probe bond
# -----------------------------------------------------------------------------
SOLUTE_NAME="${SOLUTE_NAME:-benzaldehyde}"
SOLUTE_TYPE_BASE="${SOLUTE_TYPE_BASE:-401}"
# atom1 -> atom2 defines the field projection axis AND its sign (C O, C N, ...)
PROBE_ELEMENTS="${PROBE_ELEMENTS:-C O}"
PROBE_LABEL="${PROBE_LABEL:-C=O}"
# Optional explicit 1-based Tinker indices, e.g. "2 1"; empty = shortest matching bond
PROBE_ATOM_INDICES="${PROBE_ATOM_INDICES:-}"

# -----------------------------------------------------------------------------
# 3. Solvent library
# -----------------------------------------------------------------------------
# Per-study copy, so studies never overwrite each other's solvent library:
#   cp config/solvent_table.tsv "$STUDY_DIR"/solvent_table.tsv
SOLVENT_TABLE="${SOLVENT_TABLE:-${STUDY_DIR}/solvent_table.tsv}"
SOLVENT_NAMES="${SOLVENT_NAMES:-hexane thf dichloromethane chloroform toluene acetonitrile dmso}"
# Solvents may share this range: one MD system contains exactly one solvent.
SOLVENT_TYPE_BASE="${SOLVENT_TYPE_BASE:-501}"

# -----------------------------------------------------------------------------
# 4. Box, replicates, sampling
# -----------------------------------------------------------------------------
BOX_A="${BOX_A:-40.0}"
REPLICATE_COUNT="${REPLICATE_COUNT:-3}"
TARGET_REPLICATES="${TARGET_REPLICATES:-}"
PACKMOL_TOLERANCE="${PACKMOL_TOLERANCE:-2.0}"
PACKMOL_DISCALE="${PACKMOL_DISCALE:-1.5}"
RANDOM_SEED_BASE="${RANDOM_SEED_BASE:-20260617}"
TEMPERATURE_K="${TEMPERATURE_K:-300.0}"
PRESSURE_ATM="${PRESSURE_ATM:-1.0}"

# Minimisation
MIN_GRADIENT="${MIN_GRADIENT:-0.5}"
MIN_POLAR_EPS="${MIN_POLAR_EPS:-1.0e-5}"

# NPT equilibration: 50 ps at 1 fs, save every 0.1 ps
NPT_STEPS="${NPT_STEPS:-50000}"
NPT_TIMESTEP_FS="${NPT_TIMESTEP_FS:-1.0}"
NPT_SAVE_PS="${NPT_SAVE_PS:-0.1}"
NPT_POLAR_EPS="${NPT_POLAR_EPS:-1.0e-5}"

# NVT equilibration: 200 ps at 1 fs
NVT_STEPS="${NVT_STEPS:-200000}"
NVT_TIMESTEP_FS="${NVT_TIMESTEP_FS:-1.0}"
NVT_SAVE_PS="${NVT_SAVE_PS:-0.1}"
NVT_POLAR_EPS="${NVT_POLAR_EPS:-1.0e-5}"

# Production: 5 ns at 1 fs, save every 0.1 ps
PRODUCTION_ENSEMBLE="${PRODUCTION_ENSEMBLE:-npt}"
PRODUCTION_STEPS="${PRODUCTION_STEPS:-5000000}"
PRODUCTION_TIMESTEP_FS="${PRODUCTION_TIMESTEP_FS:-1.0}"
PRODUCTION_SAVE_PS="${PRODUCTION_SAVE_PS:-0.1}"
PRODUCTION_POLAR_EPS="${PRODUCTION_POLAR_EPS:-1.0e-5}"
# REQUIRED: writes production/md_start.uind, without which no field can be extracted
PRODUCTION_SAVE_INDUCED="${PRODUCTION_SAVE_INDUCED:-1}"

# -----------------------------------------------------------------------------
# 5. Field extraction: keep every Nth saved frame, stop after N frames
# -----------------------------------------------------------------------------
# Must equal PRODUCTION_SAVE_PS, otherwise times and the reported window are wrong
FRAME_INTERVAL_PS="${FRAME_INTERVAL_PS:-0.1}"
FIELD_STRIDE="${FIELD_STRIDE:-10}"
FIELD_MAX_FRAMES="${FIELD_MAX_FRAMES:-5000}"
# auto = seek-prefix when the first 20 frames have identical width, else stream.
# Use stream when a trajectory might change frame width (only mode that parses every frame).
# auto | seek-prefix | sequential-fixed | stream
FIELD_READ_MODE="${FIELD_READ_MODE:-auto}"
FIELD_WORKERS="${FIELD_WORKERS:-1}"

# -----------------------------------------------------------------------------
# 6. Experimental input (no variable: the fit takes it with --ir-csv)
# -----------------------------------------------------------------------------
# The measured probe frequency in EACH neat solvent is required for the fit and cannot be
# computed by this workflow. Template: config/ir_shifts.example.csv
#   cp config/ir_shifts.example.csv "$STUDY_DIR"/ir_shifts.csv   # then edit it
#   ./scripts/fit_stark_rate.py --root-dir <analysis> --ir-csv "$STUDY_DIR"/ir_shifts.csv

# -----------------------------------------------------------------------------
# 7. Toolchain overrides (optional; defaults live in scripts/_defaults.sh)
# -----------------------------------------------------------------------------
# AMOEBA_ENV_BIN, PYTHON_CMD, MINIMIZE_CMD, DYNAMIC_CMD, ANALYZE_CMD, PACKMOL_CMD,
# OBABEL_CMD, POLTYPE2_CMD, POLTYPE_NUMPROC, POLTYPE_MAXMEM, POLTYPE_XTB_BIN
#
# AMOEBA_ENV_BIN="${HOME}/miniconda3/envs/amoeba/bin"
# POLTYPE_XTB_BIN="${HOME}/miniconda3/envs/xtbenv/bin/xtb"

# -----------------------------------------------------------------------------
# 8. Resources
# -----------------------------------------------------------------------------
OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
MD_PARALLEL_JOBS="${MD_PARALLEL_JOBS:-4}"
MD_OVERWRITE="${MD_OVERWRITE:-0}"
