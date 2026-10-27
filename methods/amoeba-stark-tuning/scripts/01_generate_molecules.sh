#!/usr/bin/env bash
# Build 3D SDF structures with Open Babel.
#
#   ./scripts/01_generate_molecules.sh                 # every solvent row of the table that has SMILES
#   ./scripts/01_generate_molecules.sh <name> <smiles> # one arbitrary molecule (e.g. the solute)
#
# Solvent SDFs land in ${STUDY_DIR}/molecules/<sdf> where <sdf> is the 'sdf' column
# of the solvent table (absolute paths are used as-is).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="${SKILL_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
export SKILL_DIR
SYSTEM_CONFIG="${SYSTEM_CONFIG:-${SKILL_DIR}/config/system_config.sh}"
if [[ ! -f "$SYSTEM_CONFIG" ]]; then
  echo "ERROR: study config not found at ${SYSTEM_CONFIG}" >&2
  echo "Create one first:  cp ${SKILL_DIR}/config/system_config.example.sh ${SKILL_DIR}/config/system_config.sh" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$SYSTEM_CONFIG"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_defaults.sh"

STUDY_DIR="${STUDY_DIR:?STUDY_DIR must be set in the study config}"
OBABEL_CMD="${OBABEL_CMD:-obabel}"

SOLVENT_TABLE="${SOLVENT_TABLE:-${STUDY_DIR}/solvent_table.tsv}"
MOLECULE_DIR="${STUDY_DIR}/molecules"
mkdir -p "$MOLECULE_DIR"

generate() {
  local name="$1" smiles="$2" sdf="$3"
  if [[ -f "$sdf" ]]; then
    echo "exists  $sdf"
    return 0
  fi
  echo "build   $name  <- $smiles"
  "$OBABEL_CMD" -:"$smiles" -O "$sdf" --gen3d >/dev/null
  [[ -s "$sdf" ]] || { echo "Open Babel failed for ${name}" >&2; return 1; }
}

if [[ $# -ge 2 ]]; then
  generate "$1" "$2" "${3:-${MOLECULE_DIR}/$1.sdf}"
  exit 0
fi

[[ -f "$SOLVENT_TABLE" ]] || { echo "Missing solvent table ${SOLVENT_TABLE}" >&2; exit 1; }

wanted="${TARGET_SOLVENTS:-$SOLVENT_NAMES}"
if [[ -z "$wanted" ]]; then
  echo "No solvents requested: set SOLVENT_NAMES in the config, or pass TARGET_SOLVENTS." >&2
  exit 1
fi

for name in $wanted; do
  row="$(awk -F'\t' -v want="$name" '
    NR==1 { for (i=1;i<=NF;i++) h[tolower($i)]=i; next }
    $h["name"] == want { print $h["sdf"] "\t" $h["smiles"]; exit }' "$SOLVENT_TABLE")"
  if [[ -z "$row" ]]; then
    echo "WARNING: ${name} is not a row of ${SOLVENT_TABLE}; skipping" >&2
    continue
  fi
  sdf="${row%%$'\t'*}"
  smiles="${row#*$'\t'}"
  if [[ -z "$smiles" || "$smiles" == "-" ]]; then
    echo "WARNING: no SMILES for ${name}; skipping" >&2
    continue
  fi
  if [[ "$sdf" != /* ]]; then
    sdf="${MOLECULE_DIR}/${sdf}"
  fi
  generate "$name" "$smiles" "$sdf"
done
