#!/usr/bin/env bash
# Whole-study probe-field extraction from the production trajectories.
#
#   ./scripts/extract_fields.sh                       # all replicates of the study
#   TARGET_SOLVENTS="hexane thf" ./scripts/extract_fields.sh
#   TARGET_REPLICATES="thf/replicate_2" ./scripts/extract_fields.sh
#   ANALYSIS_DIR=/path/out FIELD_WORKERS=8 FIELD_READ_MODE=stream ./scripts/extract_fields.sh
#
# Writes <ANALYSIS_DIR>/{partial_field_summary.csv,partial_field_run.json,
# partial_field_errors.json,md/<solvent>/<replicate>/fields/*}.
# Every fields/ directory keeps fields.csv (per frame), field_stats.json (per
# replicate), ref.arc, ref.uind, the copied keys and the probe metadata.
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

ANALYSIS_DIR="${ANALYSIS_DIR:-${STUDY_DIR}/analysis/probe_field_$(date +%Y%m%d_%H%M%S)}"
STRIDE="${FIELD_STRIDE:-10}"
MAX_FRAMES="${FIELD_MAX_FRAMES:-5000}"
FRAME_INTERVAL_PS="${FRAME_INTERVAL_PS:-0.1}"
READ_MODE="${FIELD_READ_MODE:-auto}"
WORKERS="${FIELD_WORKERS:-1}"
ANALYZE_UIND_CMD="${ANALYZE_UIND_CMD:-${SKILL_DIR}/tools/analyze_uind}"

# analyze_uind needs to find the Tinker 'analyze' binary.
export ANALYZE_CMD="${ANALYZE_CMD:-analyze}"

# TARGET_SOLVENTS: space-separated solvent directory names.
# TARGET_REPLICATES: "solvent/replicate_2" or just "replicate_2" (then all solvents
# whose directory holds that replicate are processed, unless TARGET_SOLVENTS narrows it).
solvent_args=()
for solvent in ${TARGET_SOLVENTS:-}; do
  solvent_args+=(--solvent "$solvent")
done
replicate_args=()
for replicate in ${TARGET_REPLICATES:-}; do
  replicate_args+=(--replicate "${replicate##*/}")
  if [[ "$replicate" == */* ]]; then
    solvent_args+=(--solvent "${replicate%%/*}")
  fi
done

mkdir -p "$ANALYSIS_DIR"
echo "study     ${STUDY_DIR}"
echo "analysis  ${ANALYSIS_DIR}"
echo "stride ${STRIDE}  max frames ${MAX_FRAMES}  frame interval ${FRAME_INTERVAL_PS} ps  read mode ${READ_MODE}  workers ${WORKERS}"
echo "solvent filter: ${TARGET_SOLVENTS:-<all>}   replicate filter: ${TARGET_REPLICATES:-<all>}"
echo "note: the extracted field is compared with an experimental IR table only at the fit step"

"$PYTHON_CMD" "${SKILL_DIR}/tools/extract_probe_field.py" \
  --root-dir "$STUDY_DIR" \
  --out-dir "$ANALYSIS_DIR" \
  --stride "$STRIDE" \
  --max-selected-frames "$MAX_FRAMES" \
  --frame-interval-ps "$FRAME_INTERVAL_PS" \
  --read-mode "$READ_MODE" \
  --workers "$WORKERS" \
  --analyze-uind-cmd "$ANALYZE_UIND_CMD" \
  "${solvent_args[@]}" \
  "${replicate_args[@]}"

echo "summary   ${ANALYSIS_DIR}/partial_field_summary.csv"
