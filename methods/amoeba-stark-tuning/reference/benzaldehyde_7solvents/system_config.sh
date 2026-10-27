# Settings of the benzaldehyde case study (the numbers in CASE_STUDY.md).
#
# Only the science is listed: toolchain paths come from scripts/_defaults.sh, and the
# 5 ns trajectories are not shipped with this skill (they are tens of GB). Use this file
# as a template for the settings, not as a runnable archive:
#
#   SYSTEM_CONFIG=reference/benzaldehyde_7solvents/system_config.sh \
#     ./scripts/00_check_tools.sh
#
# expects $STUDY_DIR to contain molecules/ and parameters/ for benzaldehyde + the 7 solvents.

STUDY_DIR="${STUDY_DIR:-${SKILL_DIR}/runs/benzaldehyde_7solvents}"
PARAMETERS_DIR="${PARAMETERS_DIR:-${STUDY_DIR}/parameters}"

# --- Probe: benzaldehyde carbonyl, C(index 2) -> O(index 1) -------------------
SOLUTE_NAME="${SOLUTE_NAME:-benzaldehyde}"
SOLUTE_TYPE_BASE="${SOLUTE_TYPE_BASE:-401}"
PROBE_ELEMENTS="${PROBE_ELEMENTS:-C O}"
PROBE_LABEL="${PROBE_LABEL:-C=O}"
PROBE_ATOM_INDICES="${PROBE_ATOM_INDICES:-2 1}"

# --- Solvents -----------------------------------------------------------------
SOLVENT_TABLE="${SOLVENT_TABLE:-${SKILL_DIR}/reference/benzaldehyde_7solvents/solvent_table.tsv}"
SOLVENT_NAMES="${SOLVENT_NAMES:-hexane thf dichloromethane chloroform toluene acetonitrile dmso}"
SOLVENT_TYPE_BASE="${SOLVENT_TYPE_BASE:-501}"

# --- Box and sampling ---------------------------------------------------------
BOX_A="${BOX_A:-40.0}"
REPLICATE_COUNT="${REPLICATE_COUNT:-3}"
PACKMOL_TOLERANCE="${PACKMOL_TOLERANCE:-2.0}"
PACKMOL_DISCALE="${PACKMOL_DISCALE:-1.5}"
RANDOM_SEED_BASE="${RANDOM_SEED_BASE:-20260617}"
TEMPERATURE_K="${TEMPERATURE_K:-300.0}"
PRESSURE_ATM="${PRESSURE_ATM:-1.0}"

# --- MD stages ----------------------------------------------------------------
MIN_GRADIENT="${MIN_GRADIENT:-0.5}"
NPT_STEPS="${NPT_STEPS:-50000}"
NPT_TIMESTEP_FS="${NPT_TIMESTEP_FS:-1.0}"
NPT_SAVE_PS="${NPT_SAVE_PS:-0.1}"
NVT_STEPS="${NVT_STEPS:-200000}"
NVT_TIMESTEP_FS="${NVT_TIMESTEP_FS:-1.0}"
NVT_SAVE_PS="${NVT_SAVE_PS:-0.1}"
PRODUCTION_ENSEMBLE="${PRODUCTION_ENSEMBLE:-npt}"
PRODUCTION_STEPS="${PRODUCTION_STEPS:-5000000}"
PRODUCTION_TIMESTEP_FS="${PRODUCTION_TIMESTEP_FS:-1.0}"
PRODUCTION_SAVE_PS="${PRODUCTION_SAVE_PS:-0.1}"
PRODUCTION_POLAR_EPS="${PRODUCTION_POLAR_EPS:-1.0e-5}"
PRODUCTION_SAVE_INDUCED="${PRODUCTION_SAVE_INDUCED:-1}"

# --- Field extraction: 5000 frames x 0.1 ps, stride 10 = the 1-5000 ps window --
FRAME_INTERVAL_PS="${FRAME_INTERVAL_PS:-0.1}"
FIELD_STRIDE="${FIELD_STRIDE:-10}"
FIELD_MAX_FRAMES="${FIELD_MAX_FRAMES:-5000}"
FIELD_READ_MODE="${FIELD_READ_MODE:-seek-prefix}"
FIELD_WORKERS="${FIELD_WORKERS:-1}"

# --- Resources ----------------------------------------------------------------
OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
MD_PARALLEL_JOBS="${MD_PARALLEL_JOBS:-4}"
