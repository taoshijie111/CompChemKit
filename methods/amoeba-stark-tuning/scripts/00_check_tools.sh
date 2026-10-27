#!/usr/bin/env bash
# Verify the toolchain, the study config and the molecule inputs before launching anything.
#
# MD tools (minimize/dynamic/analyze/packmol/python) are always required.
# Parameterisation tools (poltype2/xTB/Open Babel) are only required when one of the
# <name>.xyz / <name>.prm files is still missing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="${SKILL_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
export SKILL_DIR
SYSTEM_CONFIG="${SYSTEM_CONFIG:-${SKILL_DIR}/config/system_config.sh}"
missing=0
missing_params=0

if [[ ! -f "$SYSTEM_CONFIG" ]]; then
  echo "MISSING  study config: ${SYSTEM_CONFIG}"
  echo "         cp ${SKILL_DIR}/config/system_config.example.sh ${SKILL_DIR}/config/system_config.sh"
  exit 1
fi
# shellcheck source=/dev/null
source "$SYSTEM_CONFIG"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_defaults.sh"

STUDY_DIR="${STUDY_DIR:?STUDY_DIR must be set in the study config}"
SOLUTE_NAME="${SOLUTE_NAME:?SOLUTE_NAME must be set in the study config}"
PARAMETERS_DIR="${PARAMETERS_DIR:-${STUDY_DIR}/parameters}"
SOLVENT_TABLE="${SOLVENT_TABLE:-${STUDY_DIR}/solvent_table.tsv}"
SOLVENT_NAMES="${SOLVENT_NAMES:-}"
PROBE_ELEMENTS="${PROBE_ELEMENTS:-C O}"
PROBE_LABEL="${PROBE_LABEL:-probe}"
PROBE_ATOM_INDICES="${PROBE_ATOM_INDICES:-}"
BOX_A="${BOX_A:-40.0}"
REPLICATE_COUNT="${REPLICATE_COUNT:-3}"
PRODUCTION_ENSEMBLE="${PRODUCTION_ENSEMBLE:-npt}"
OBABEL_CMD="${OBABEL_CMD:-obabel}"
POLTYPE2_CMD="${POLTYPE2_CMD:-poltype2}"
POLTYPE_XTB_BIN="${POLTYPE_XTB_BIN:-}"

echo "config   ${SYSTEM_CONFIG}"
echo "study    ${STUDY_DIR}"
echo

check_file() {
  local label="$1" path="$2"
  if [[ -f "$path" ]]; then printf '%-18s %s\n' "$label" "$path"
  else printf '%-18s MISSING: %s\n' "$label" "$path"; missing=1; fi
}
check_exec() {
  local label="$1" path="$2"
  if [[ -x "$path" ]]; then printf '%-18s %s\n' "$label" "$path"
  else printf '%-18s MISSING: %s\n' "$label" "$path"; missing=1; fi
}
check_cmd() {
  local label="$1" name="$2" resolved
  if resolved="$(command -v "$name" 2>/dev/null)"; then printf '%-18s %s\n' "$label" "$resolved"
  else printf '%-18s MISSING: %s\n' "$label" "$name"; missing=1; fi
}

echo "[MD tools]"
check_exec python "$PYTHON_CMD"
check_exec minimize "$MINIMIZE_CMD"
check_exec dynamic "$DYNAMIC_CMD"
check_exec analyze "$ANALYZE_CMD"
check_exec packmol "$PACKMOL_CMD"
check_exec analyze_uind-wrapper "${SKILL_DIR}/tools/analyze_uind"
check_file solvent_table "$SOLVENT_TABLE"

echo
echo "[molecule parameters]"
for solvent in $SOLVENT_NAMES; do
  for path in "${PARAMETERS_DIR}/${SOLUTE_NAME}/${SOLUTE_NAME}.xyz" "${PARAMETERS_DIR}/${SOLUTE_NAME}/${SOLUTE_NAME}.prm" \
              "${PARAMETERS_DIR}/${solvent}/${solvent}.xyz" "${PARAMETERS_DIR}/${solvent}/${solvent}.prm"; do
    if [[ ! -f "$path" ]]; then
      printf '%-18s MISSING: %s\n' "parameters" "$path"
      missing_params=1
    fi
  done
done
if ((missing_params == 0)); then
  echo "all present"
fi

echo
echo "[parameterisation tools]"
if ((missing_params == 0)); then
  echo "not required (all parameters present)"
elif [[ -n "$POLTYPE_XTB_BIN" && -x "$POLTYPE_XTB_BIN" ]]; then
  check_cmd poltype2 "$POLTYPE2_CMD"
  check_cmd obabel "$OBABEL_CMD"
  check_exec xtb "$POLTYPE_XTB_BIN"
else
  echo "REQUIRED (parameters are missing)"
  check_cmd poltype2 "$POLTYPE2_CMD"
  check_cmd obabel "$OBABEL_CMD"
  if [[ -n "$POLTYPE_XTB_BIN" ]]; then check_exec xtb "$POLTYPE_XTB_BIN"; else missing=1; echo "xtb                MISSING: POLTYPE_XTB_BIN is not set"; fi
fi

echo
echo "probe    ${SOLUTE_NAME}  ${PROBE_LABEL}  elements='${PROBE_ELEMENTS}'  indices='${PROBE_ATOM_INDICES:-auto}'"
echo "solvents ${SOLVENT_NAMES}"
echo "box      ${BOX_A} A   replicates ${REPLICATE_COUNT}   ensemble ${PRODUCTION_ENSEMBLE}"

if ((missing != 0)); then
  echo
  echo "One or more required tools or parameter files are missing." >&2
  exit 1
fi
if ((missing_params != 0)); then
  echo
  echo "Parameterise the missing molecules first:" >&2
  echo "  ./scripts/01_generate_molecules.sh [<name> <smiles>]" >&2
  echo "  ./scripts/02_parameterize.sh <name> <structure.sdf> <type-base>" >&2
  exit 1
fi

echo
echo "Tool and parameter check passed."
