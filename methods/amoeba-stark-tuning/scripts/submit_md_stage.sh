#!/usr/bin/env bash
# Batch driver: run one MD stage for every <solvent>/<replicate> of a study.
#
#   ./scripts/submit_md_stage.sh build_system
#   ./scripts/submit_md_stage.sh minimize
#   ./scripts/submit_md_stage.sh npt
#   ./scripts/submit_md_stage.sh nvt
#   ./scripts/submit_md_stage.sh production
#
# It detaches itself (setsid) so that the whole stage survives the shell, and writes
# one log per replicate plus a job_status.tsv under <STUDY_DIR>/run_logs/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="${SKILL_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
export SKILL_DIR
SYSTEM_CONFIG="${SYSTEM_CONFIG:-${SKILL_DIR}/config/system_config.sh}"
export SYSTEM_CONFIG
if [[ ! -f "$SYSTEM_CONFIG" ]]; then
  echo "ERROR: study config not found at ${SYSTEM_CONFIG}" >&2
  echo "Create one first:  cp ${SKILL_DIR}/config/system_config.example.sh ${SKILL_DIR}/config/system_config.sh" >&2
  exit 1
fi
# Export everything the config defines so the per-replicate step script inherits the
# same settings (it re-sources the config, whose assignments are all ${VAR:-default}).
set -a
# shellcheck source=/dev/null
source "$SYSTEM_CONFIG"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_defaults.sh"
set +a

: "${STUDY_DIR:?STUDY_DIR must be set in the study config}"
PARAMETERS_DIR="${PARAMETERS_DIR:-${STUDY_DIR}/parameters}"
SOLVENT_TABLE="${SOLVENT_TABLE:-${SKILL_DIR}/config/solvent_table.tsv}"
export STUDY_DIR PARAMETERS_DIR SOLVENT_TABLE
export PYTHON_CMD MINIMIZE_CMD DYNAMIC_CMD ANALYZE_CMD PACKMOL_CMD OMP_NUM_THREADS

MD_PARALLEL_JOBS="${MD_PARALLEL_JOBS:-4}"
OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
MD_OVERWRITE="${MD_OVERWRITE:-0}"
PACKMOL_TOLERANCE="${PACKMOL_TOLERANCE:-2.0}"
PACKMOL_DISCALE="${PACKMOL_DISCALE:-1.5}"
RANDOM_SEED_BASE="${RANDOM_SEED_BASE:-20260617}"
BOX_A="${BOX_A:-40.0}"
REPLICATE_COUNT="${REPLICATE_COUNT:-3}"
SOLVENT_NAMES="${SOLVENT_NAMES:-}"
TARGET_SOLVENTS="${TARGET_SOLVENTS:-}"
TARGET_REPLICATES="${TARGET_REPLICATES:-}"
MD_STEP_SCRIPT="${MD_STEP_SCRIPT:-run_md_step.sh}"
SOLUTE_NAME="${SOLUTE_NAME:?SOLUTE_NAME must be set in the study config}"
PROBE_ELEMENTS="${PROBE_ELEMENTS:-C O}"
PROBE_LABEL="${PROBE_LABEL:-probe}"
PROBE_ATOM_INDICES="${PROBE_ATOM_INDICES:-}"
PACKMOL_COUNTS_TSV="${PACKMOL_COUNTS_TSV:-${STUDY_DIR}/packmol_counts.tsv}"

usage() {
  cat <<'EOF'
Usage: submit_md_stage.sh <stage>

Stages:
  build_system  Packmol box per replicate, then the typed Tinker system.xyz + probe_atoms.json
  keys          write system.key / ref.key / stage key files
  minimize      minimize to the configured RMS gradient target
  npt           NPT density equilibration
  nvt           NVT equilibration
  production    production run (save-induced must stay enabled for the field extraction)

Environment controls:
  SYSTEM_CONFIG=/path/to/system_config.sh
  TARGET_SOLVENTS="hexane thf"       limit to solvents
  TARGET_REPLICATES="hexane/replicate_1"
  MD_PARALLEL_JOBS=4  OMP_NUM_THREADS=8
  MD_OVERWRITE=1                     rebuild existing build_system output
  PACKMOL_TOLERANCE=2.0 PACKMOL_DISCALE=1.5
  MD_FOREGROUND=1                    run synchronously instead of detaching
                                     (use under Slurm or any reaper of detached jobs)

Examples:
  ./scripts/submit_md_stage.sh build_system
  TARGET_SOLVENTS=toluene MD_PARALLEL_JOBS=3 ./scripts/submit_md_stage.sh minimize
  TARGET_REPLICATES="dmso/replicate_1" NPT_STEPS=2000 ./scripts/submit_md_stage.sh npt
EOF
}

stage="${1:-}"
case "$stage" in
  build_system|keys|minimize|npt|nvt|production) ;;
  -h|--help|"") usage; exit 0 ;;
  *) echo "Unknown stage: ${stage}" >&2; usage >&2; exit 2 ;;
esac

if [[ "${MD_BATCH_WORKER:-0}" != "1" ]]; then
  run_id="$(date +%Y%m%d_%H%M%S)"
  log_dir="${STUDY_DIR}/run_logs/md_${stage}_${run_id}"
  mkdir -p "$log_dir"

  if [[ "${MD_FOREGROUND:-0}" == "1" ]]; then
    # Run synchronously. Use this under a batch scheduler or any environment that
    # reaps detached processes (the MD still runs MD_PARALLEL_JOBS replicates at a time).
    export MD_BATCH_WORKER=1
    export MD_BATCH_STAGE="$stage"
    export MD_BATCH_RUN_ID="$run_id"
    export MD_BATCH_LOG_DIR="$log_dir"
    echo "Running stage ${stage} in the foreground"
    echo "Stage: ${stage}"
    echo "Study: ${STUDY_DIR}"
    echo "Job logs: ${log_dir}"
  else
    driver_log="${STUDY_DIR}/run_logs/submit_md_${stage}_driver_${run_id}.out"

    MD_BATCH_WORKER=1 \
    MD_BATCH_STAGE="$stage" \
    MD_BATCH_RUN_ID="$run_id" \
    MD_BATCH_LOG_DIR="$log_dir" \
    setsid bash "$0" "$stage" > "$driver_log" 2>&1 < /dev/null &

    driver_pid=$!
    echo "Detached MD batch driver PID: ${driver_pid}"
    echo "Stage: ${stage}"
    echo "Study: ${STUDY_DIR}"
    echo "Driver log: ${driver_log}"
    echo "Job logs: ${log_dir}"
    exit 0
  fi
fi

RUN_ID="${MD_BATCH_RUN_ID:?missing MD_BATCH_RUN_ID}"
STAGE="${MD_BATCH_STAGE:?missing MD_BATCH_STAGE}"
LOG_DIR="${MD_BATCH_LOG_DIR:?missing MD_BATCH_LOG_DIR}"
STATUS_FILE="${LOG_DIR}/job_status.tsv"

mkdir -p "$LOG_DIR"
: > "$STATUS_FILE"

replicate_list() {
  if [[ -n "$TARGET_REPLICATES" ]]; then
    printf '%s\n' $TARGET_REPLICATES
    return
  fi
  local solvent rep solvent_source
  solvent_source="${TARGET_SOLVENTS:-$SOLVENT_NAMES}"
  for solvent in $solvent_source; do
    for rep in $(seq 1 "$REPLICATE_COUNT"); do
      printf '%s/replicate_%s\n' "$solvent" "$rep"
    done
  done
}

replicate_to_solvent() { printf '%s\n' "${1%%/*}"; }
replicate_index() { printf '%s\n' "${1##*_}"; }
replicate_dir() { printf '%s/md/%s\n' "$STUDY_DIR" "$1"; }
stage_dir() { printf '%s/md/%s/%s\n' "$STUDY_DIR" "$1" "$2"; }
atom_count() { awk 'NR == 1 {print int($1); exit}' "$1"; }

# Deterministic seed: SEED_BASE + 100 * (solvent position in SOLVENT_NAMES) + replicate index.
# The published benzaldehyde case used exactly this, so the seeds stay reproducible.
solvent_seed_offset() {
  local solvent="$1" index=0 name
  for name in $SOLVENT_NAMES; do
    index=$((index + 1))
    if [[ "$name" == "$solvent" ]]; then
      echo $((100 * index))
      return 0
    fi
  done
  echo 900
}

packmol_seed_for() {
  echo $((RANDOM_SEED_BASE + $(solvent_seed_offset "$1") + $(replicate_index "$2")))
}

num_solvent_for() {
  local solvent="$1"
  if [[ -f "$PACKMOL_COUNTS_TSV" ]]; then
    awk -v solvent="$solvent" 'NR > 1 && $1 == solvent {print $2; found=1} END {exit found ? 0 : 1}' \
      "$PACKMOL_COUNTS_TSV" 2>/dev/null && return 0
  fi
  return 1
}

resolve_packmol_cmd() {
  if [[ -x "$PACKMOL_CMD" ]]; then printf '%s\n' "$PACKMOL_CMD"; return 0; fi
  if command -v packmol >/dev/null 2>&1; then command -v packmol; return 0; fi
  echo "Packmol command not found or not executable: ${PACKMOL_CMD}" >&2
  return 1
}

solute_xyz() { printf '%s/%s/%s.xyz\n' "$PARAMETERS_DIR" "$SOLUTE_NAME" "$SOLUTE_NAME"; }
solute_prm() { printf '%s/%s/%s.prm\n' "$PARAMETERS_DIR" "$SOLUTE_NAME" "$SOLUTE_NAME"; }
solvent_xyz() { printf '%s/%s/%s.xyz\n' "$PARAMETERS_DIR" "$1" "$1"; }
solvent_prm() { printf '%s/%s/%s.prm\n' "$PARAMETERS_DIR" "$1" "$1"; }

ensure_replicate_inputs() {
  local replicate="$1" solvent="$2" dir
  dir="$(replicate_dir "$replicate")"
  mkdir -p "$dir"
  if [[ ! -f "${dir}/${MD_STEP_SCRIPT}" ]]; then
    cp "${SCRIPT_DIR}/${MD_STEP_SCRIPT}" "${dir}/${MD_STEP_SCRIPT}"
    chmod +x "${dir}/${MD_STEP_SCRIPT}"
  fi
  if [[ ! -f "${dir}/system.key" || ! -f "${dir}/ref.key" || "$STAGE" == "keys" ]]; then
    "$PYTHON_CMD" "${SKILL_DIR}/tools/write_replicate_keys.py" \
      --out-dir "$dir" \
      --solute-prm "$(solute_prm)" \
      --solvent-prm "$(solvent_prm "$solvent")" \
      --box "$BOX_A"
  fi
}

require_upstream() {
  local dir="$1" stage="$2" artifact="$3" want="$4"
  if [[ ! -f "${dir}/${stage}/${artifact}" ]]; then
    echo "${want} needs ${dir}/${stage}/${artifact}, which does not exist; run the ${stage} stage first." >&2
    return 1
  fi
}

prepare_stage_dir() {
  local replicate="$1" stage="$2" dir stage_path step_script_name
  dir="$(replicate_dir "$replicate")"
  stage_path="${dir}/${stage}"
  step_script_name="$(basename "$MD_STEP_SCRIPT")"
  mkdir -p "$stage_path"

  cp -f "${SCRIPT_DIR}/${MD_STEP_SCRIPT}" "${stage_path}/${step_script_name}"
  chmod +x "${stage_path}/${step_script_name}"

  case "$stage" in
    build_system) ;;
    keys)
      cp -f "${dir}/system.key" "${stage_path}/system.key"
      cp -f "${dir}/ref.key" "${stage_path}/ref.key"
      ;;
    minimize)
      ln -sf ../build_system/system.xyz "${stage_path}/system.xyz"
      ln -sf ../system.key "${stage_path}/system.key"
      ;;
    npt)
      require_upstream "$dir" minimize md_start.xyz "npt"
      ln -sf ../minimize/md_start.xyz "${stage_path}/md_start.xyz"
      ln -sf ../system.key "${stage_path}/system.key"
      ;;
    nvt)
      require_upstream "$dir" npt md_start.xyz "nvt"
      ln -sf ../npt/md_start.xyz "${stage_path}/md_start.xyz"
      if [[ -f "${dir}/npt/md_start.dyn" ]]; then
        cp -f "${dir}/npt/md_start.dyn" "${stage_path}/md_start.dyn"
      else
        echo "WARNING: ${dir}/npt/md_start.dyn is absent; nvt will start with fresh velocities" >&2
      fi
      ln -sf ../system.key "${stage_path}/system.key"
      ;;
    production)
      require_upstream "$dir" nvt md_start.xyz "production"
      ln -sf ../nvt/md_start.xyz "${stage_path}/md_start.xyz"
      if [[ -f "${dir}/nvt/md_start.dyn" ]]; then
        cp -f "${dir}/nvt/md_start.dyn" "${stage_path}/md_start.dyn"
      else
        echo "WARNING: ${dir}/nvt/md_start.dyn is absent; production will start with fresh velocities" >&2
      fi
      ln -sf ../system.key "${stage_path}/system.key"
      ;;
  esac
  return 0
}

run_build_system() {
  local replicate="$1" solvent="$2" stage_path seed packmol_cmd num_solvent num_args expected_atoms actual_atoms
  stage_path="$(stage_dir "$replicate" "build_system")"
  seed="$(packmol_seed_for "$solvent" "$replicate")"
  packmol_cmd="$(resolve_packmol_cmd)"

  for required in "$(solute_xyz)" "$(solvent_xyz "$solvent")"; do
    [[ -f "$required" ]] || { echo "Missing $required" >&2; return 1; }
  done

  mkdir -p "$stage_path"
  if [[ "$MD_OVERWRITE" != "1" ]]; then
    for existing in packmol.xyz system.xyz probe_atoms.json carbonyl_atoms.json; do
      if [[ -f "${stage_path}/${existing}" ]]; then
        echo "${stage_path}/${existing} already exists; set MD_OVERWRITE=1 to rebuild." >&2
        return 1
      fi
    done
  else
    for existing in packmol.xyz system.xyz probe_atoms.json carbonyl_atoms.json; do
      if [[ -f "${stage_path}/${existing}" ]]; then
        mv "${stage_path}/${existing}" "${stage_path}/${existing}.previous_${RUN_ID}"
      fi
    done
  fi

  "$PYTHON_CMD" "${SKILL_DIR}/tools/build_tinker_system.py" components \
    --solute "$(solute_xyz)" \
    --solvent "$(solvent_xyz "$solvent")" \
    --out-dir "$stage_path" \
    --solute-name "$SOLUTE_NAME" \
    --solvent-name "$solvent"

  num_args=()
  if num_solvent="$(num_solvent_for "$solvent")"; then
    num_args=(--num-solvent "$num_solvent")
    echo "Using num_solvent=${num_solvent} from ${PACKMOL_COUNTS_TSV}"
  else
    num_solvent=""
    echo "No entry in ${PACKMOL_COUNTS_TSV}; estimating num_solvent from the solvent table density"
  fi

  "$PYTHON_CMD" "${SKILL_DIR}/tools/write_packmol_input.py" \
    --solvent "$solvent" \
    --solvent-table "$SOLVENT_TABLE" \
    --out-dir "$stage_path" \
    --box "$BOX_A" \
    --tolerance "$PACKMOL_TOLERANCE" \
    --discale "$PACKMOL_DISCALE" \
    --seed "$seed" \
    "${num_args[@]}"
  num_solvent="$(cat "${stage_path}/num_solvent.txt")"

  echo "Running Packmol for ${replicate}: seed=${seed}, tolerance=${PACKMOL_TOLERANCE}, discale=${PACKMOL_DISCALE}, num_solvent=${num_solvent}"
  ( cd "$stage_path" && "$packmol_cmd" < packmol_40A.inp )

  [[ -f "${stage_path}/packmol.xyz" ]] || { echo "Packmol did not create ${stage_path}/packmol.xyz" >&2; return 1; }

  expected_atoms=$(( $(atom_count "${stage_path}/solute_component.xyz") + $(atom_count "${stage_path}/solvent_component.xyz") * num_solvent ))
  actual_atoms="$(atom_count "${stage_path}/packmol.xyz")"
  if [[ "$actual_atoms" != "$expected_atoms" ]]; then
    echo "Packmol atom count mismatch for ${replicate}: ${actual_atoms}/${expected_atoms}" >&2
    return 1
  fi

  "$PYTHON_CMD" "${SKILL_DIR}/tools/build_tinker_system.py" system \
    --packmol "${stage_path}/packmol.xyz" \
    --solute "$(solute_xyz)" \
    --solvent "$(solvent_xyz "$solvent")" \
    --num-solvent "$num_solvent" \
    --out "${stage_path}/system.xyz" \
    --metadata "${stage_path}/probe_atoms.json" \
    --solute-name "$SOLUTE_NAME" \
    --solvent-name "$solvent" \
    --probe-elements "$PROBE_ELEMENTS" \
    --probe-label "$PROBE_LABEL" \
    --probe-atom-indices "$PROBE_ATOM_INDICES" \
    --box "$BOX_A"
}

run_one() {
  local replicate="$1" solvent dir stage_path log_file step_script_name random_seed
  solvent="$(replicate_to_solvent "$replicate")"
  dir="$(replicate_dir "$replicate")"
  stage_path="$(stage_dir "$replicate" "$STAGE")"
  log_file="${LOG_DIR}/${solvent}_${replicate##*/}.${STAGE}.log"
  step_script_name="$(basename "$MD_STEP_SCRIPT")"
  random_seed="$(packmol_seed_for "$solvent" "$replicate")"

  if [[ ! "$replicate" =~ ^[^/]+/replicate_[0-9]+$ ]]; then
    printf '%s\tFAIL\tbad replicate name\n' "$replicate" >> "$STATUS_FILE"
    echo "Bad replicate name: ${replicate}" >&2
    return 1
  fi

  printf '%s\tSTART\t%s\n' "$replicate" "$(date '+%F %T')" >> "$STATUS_FILE"

  local status=0
  {
    set -e
    echo "replicate=${replicate}"
    echo "stage=${STAGE}"
    echo "study=${STUDY_DIR}"
    echo "workdir=${stage_path}"
    echo "OMP_NUM_THREADS=${OMP_NUM_THREADS}"
    echo "MD_STEP_SCRIPT=${MD_STEP_SCRIPT}"
    echo "RANDOM_SEED=${random_seed}"
    ensure_replicate_inputs "$replicate" "$solvent"
    case "$STAGE" in
      build_system) run_build_system "$replicate" "$solvent" ;;
      keys|minimize|npt|nvt|production)
        prepare_stage_dir "$replicate" "$STAGE"
        (
          cd "$stage_path"
          STUDY_DIR="$STUDY_DIR" SYSTEM_CONFIG="$SYSTEM_CONFIG" OMP_NUM_THREADS="$OMP_NUM_THREADS" \
            RANDOM_SEED="$random_seed" "./${step_script_name}" "$STAGE"
        )
        ;;
    esac
  } > "$log_file" 2>&1 || status=$?

  if ((status != 0)); then
    printf '%s\tFAIL\t%s\n' "$replicate" "$(date '+%F %T')" >> "$STATUS_FILE"
  else
    printf '%s\tDONE\t%s\n' "$replicate" "$(date '+%F %T')" >> "$STATUS_FILE"
  fi
  return "$status"
}

echo "Run ID: ${RUN_ID}"
echo "Stage: ${STAGE}"
echo "Study: ${STUDY_DIR}"
echo "Config: ${SYSTEM_CONFIG}"
echo "Python: ${PYTHON_CMD}"
echo "Packmol: ${PACKMOL_CMD}"
echo "Solute: ${SOLUTE_NAME}  probe: ${PROBE_LABEL} (${PROBE_ELEMENTS})"
echo "Solvents: ${TARGET_SOLVENTS:-$SOLVENT_NAMES}"
echo "Replicates per solvent: ${REPLICATE_COUNT}"
echo "Parallel jobs: ${MD_PARALLEL_JOBS}  OMP threads: ${OMP_NUM_THREADS}"
echo "Status: ${STATUS_FILE}"

pids=()
while IFS= read -r replicate; do
  [[ -n "$replicate" ]] || continue
  while true; do
    active=0
    for pid in "${pids[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then active=$((active + 1)); fi
    done
    if ((active < MD_PARALLEL_JOBS)); then break; fi
    sleep 1
  done
  run_one "$replicate" &
  pids+=("$!")
done < <(replicate_list)

failures=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then failures=$((failures + 1)); fi
done

if ((failures > 0)); then
  echo "${failures} MD job(s) failed at stage ${STAGE}. See ${LOG_DIR}." >&2
  exit 1
fi

echo "All MD jobs completed successfully for stage ${STAGE}."
