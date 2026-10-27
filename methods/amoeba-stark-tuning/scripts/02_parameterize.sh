#!/usr/bin/env bash
# Parameterise one molecule with Poltype2 and remap it into a private AMOEBA type range.
#
#   ./scripts/02_parameterize.sh <name> <structure.sdf> <type-base>
#
#   name         molecule id, e.g. benzaldehyde or hexane (also the .prm/.xyz prefix)
#   structure    SDF (or any format Poltype2/Open Babel can read)
#   type-base    first atom type of the remapped range; the solute and each solvent
#                must use different ranges, because an MD system includes exactly one
#                solute plus one solvent. The published case used 401 for the solute
#                and 501 for every solvent.
#
# Output in ${STUDY_DIR}/parameters/<name>/:
#   <name>.xyz   typed Tinker structure (atom types + connectivity)
#   <name>.key   Tinker key describing the single molecule
#   <name>.prm   same content as <name>.key, used as the 'parameters' include
#   <name>_type_map.json          old -> new atom type mapping
#   <name>.key.before_type_remap  untouched Poltype2 output, kept for diagnosis
#   final.xyz / final.key         raw Poltype2 output
#
# The remap step is authoritative: never rely on Poltype2's own type numbering to be
# unique or to stay inside a range you control.
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
PARAMETERS_DIR="${PARAMETERS_DIR:-${STUDY_DIR}/parameters}"
POLTYPE2_CMD="${POLTYPE2_CMD:-poltype2}"
POLTYPE_NUMPROC="${POLTYPE_NUMPROC:-8}"
POLTYPE_MAXMEM="${POLTYPE_MAXMEM:-16GB}"
POLTYPE_XTB_BIN="${POLTYPE_XTB_BIN:-}"

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <name> <structure.sdf> <type-base>" >&2
  exit 2
fi
NAME="$1"
STRUCTURE="$2"
TYPE_BASE="$3"
POLTYPE_ATMIDX="${POLTYPE_ATMIDX:-401}"

[[ -f "$STRUCTURE" ]] || { echo "Missing structure file $STRUCTURE" >&2; exit 1; }
if [[ ! -x "$POLTYPE_XTB_BIN" ]]; then
  echo "Poltype2 expects xTB at ${POLTYPE_XTB_BIN} (create a symlink or set POLTYPE_XTB_BIN)." >&2
  exit 1
fi

WORKDIR="${PARAMETERS_DIR}/${NAME}"
mkdir -p "$WORKDIR"
cp -f "$STRUCTURE" "${WORKDIR}/${NAME}.sdf"
cat > "${WORKDIR}/poltype.ini" <<EOF
structure=${NAME}.sdf
atmidx=${POLTYPE_ATMIDX}
numproc=${POLTYPE_NUMPROC}
maxmem=${POLTYPE_MAXMEM}
EOF

echo "[poltype2] ${NAME} in ${WORKDIR} (atmidx=${POLTYPE_ATMIDX})"
( cd "$WORKDIR" && "$POLTYPE2_CMD" )

if [[ ! -f "${WORKDIR}/final.xyz" || ! -f "${WORKDIR}/final.key" ]]; then
  echo "Poltype2 finished without final.xyz/final.key; inspect ${WORKDIR}/poltype.log and the QM logs." >&2
  exit 1
fi

"$PYTHON_CMD" "${SKILL_DIR}/tools/remap_poltype_outputs.py" \
  --input-dir "$WORKDIR" \
  --prefix "$NAME" \
  --base-type "$TYPE_BASE"

for produced in "${WORKDIR}/${NAME}.xyz" "${WORKDIR}/${NAME}.key" "${WORKDIR}/${NAME}.prm"; do
  [[ -s "$produced" ]] || { echo "Missing ${produced} after remap" >&2; exit 1; }
done
echo "[done] ${WORKDIR}/${NAME}.{xyz,key,prm}  type range ${TYPE_BASE}+"
