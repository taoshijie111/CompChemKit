# Shared defaults for every script in this skill.
#
# Sourced AFTER the study config, so anything set there (or exported in the
# environment) wins. Keeping the toolchain defaults here means a study config only
# has to describe the science, and the package stays free of machine-specific paths.
#
# Overriding examples:
#   AMOEBA_ENV_BIN=/opt/tinker/bin ./scripts/00_check_tools.sh
#   PYTHON_CMD=/usr/bin/python3 ./scripts/extract_fields.sh

# --- Tinker / Packmol / Python ------------------------------------------------
# A conda env that provides Tinker (minimize, dynamic, analyze) and Packmol.
AMOEBA_ENV_BIN="${AMOEBA_ENV_BIN:-${HOME:-}/miniconda3/envs/amoeba/bin}"
PYTHON_CMD="${PYTHON_CMD:-${AMOEBA_ENV_BIN}/python}"
MINIMIZE_CMD="${MINIMIZE_CMD:-${AMOEBA_ENV_BIN}/minimize}"
DYNAMIC_CMD="${DYNAMIC_CMD:-${AMOEBA_ENV_BIN}/dynamic}"
ANALYZE_CMD="${ANALYZE_CMD:-${AMOEBA_ENV_BIN}/analyze}"
PACKMOL_CMD="${PACKMOL_CMD:-${AMOEBA_ENV_BIN}/packmol}"
OBABEL_CMD="${OBABEL_CMD:-obabel}"

# --- Poltype2 (AMOEBA parameterisation) --------------------------------------
POLTYPE2_CMD="${POLTYPE2_CMD:-poltype2}"
POLTYPE_NUMPROC="${POLTYPE_NUMPROC:-8}"
POLTYPE_MAXMEM="${POLTYPE_MAXMEM:-16GB}"
# Poltype2 expects an xTB binary at this exact path; point it at your install.
POLTYPE_XTB_BIN="${POLTYPE_XTB_BIN:-${HOME:-}/miniconda3/envs/xtbenv/bin/xtb}"
# Starting atom type handed to Poltype2; the remap step is what really fixes numbering.
POLTYPE_ATMIDX="${POLTYPE_ATMIDX:-401}"

# --- Resources ---------------------------------------------------------------
OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
MD_PARALLEL_JOBS="${MD_PARALLEL_JOBS:-4}"
MD_OVERWRITE="${MD_OVERWRITE:-0}"
