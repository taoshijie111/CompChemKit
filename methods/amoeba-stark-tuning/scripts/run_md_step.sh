#!/usr/bin/env bash
# Per-replicate stage runner for Tinker/AMOEBA probe-field MD.
#
# Copied by submit_md_stage.sh into <STUDY_DIR>/md/<solvent>/<replicate>/<stage>/
# and executed there, so every path below is relative to that stage directory.
#
# Stages: keys | minimize | npt | nvt | production
# (field extraction is a whole-study step: scripts/extract_fields.sh)
set -euo pipefail

ROOT_DIR="${STUDY_DIR:-${ROOT_DIR:-}}"
if [[ -z "$ROOT_DIR" ]]; then
  echo "ERROR: STUDY_DIR/ROOT_DIR must be set by submit_md_stage.sh" >&2
  exit 1
fi
: "${SYSTEM_CONFIG:?SYSTEM_CONFIG must point to the study config file (exported by submit_md_stage.sh)}"
# This script lives in the skill's scripts/ directory but runs with cwd = the stage
# directory, so it is found through SKILL_DIR (set by submit_md_stage.sh).
SKILL_DIR="${SKILL_DIR:-$(cd "$(dirname "$SYSTEM_CONFIG")/.." 2>/dev/null && pwd || true)}"
: "${SKILL_DIR:?SKILL_DIR must be set by submit_md_stage.sh, or SYSTEM_CONFIG must be inside the skill}"
# shellcheck source=/dev/null
source "$SYSTEM_CONFIG"
# shellcheck source=/dev/null
source "${SKILL_DIR}/scripts/_defaults.sh"

# Stage settings may be overridden per invocation (smoke tests).
NPT_STEPS="${NPT_STEPS:-50000}"
NPT_TIMESTEP_FS="${NPT_TIMESTEP_FS:-1.0}"
NPT_SAVE_PS="${NPT_SAVE_PS:-0.1}"
NVT_STEPS="${NVT_STEPS:-200000}"
NVT_TIMESTEP_FS="${NVT_TIMESTEP_FS:-1.0}"
NVT_SAVE_PS="${NVT_SAVE_PS:-0.1}"
PRODUCTION_STEPS="${PRODUCTION_STEPS:-5000000}"
PRODUCTION_TIMESTEP_FS="${PRODUCTION_TIMESTEP_FS:-1.0}"
PRODUCTION_SAVE_PS="${PRODUCTION_SAVE_PS:-0.1}"
PRODUCTION_ENSEMBLE="${PRODUCTION_ENSEMBLE:-npt}"
PRODUCTION_POLAR_EPS="${PRODUCTION_POLAR_EPS:-1.0e-5}"
PRODUCTION_SAVE_INDUCED="${PRODUCTION_SAVE_INDUCED:-1}"
BOX_A="${BOX_A:-40.0}"
TEMPERATURE_K="${TEMPERATURE_K:-300.0}"
PRESSURE_ATM="${PRESSURE_ATM:-1.0}"
MIN_GRADIENT="${MIN_GRADIENT:-0.5}"
MIN_POLAR_EPS="${MIN_POLAR_EPS:-1.0e-5}"
NPT_POLAR_EPS="${NPT_POLAR_EPS:-1.0e-5}"
NVT_POLAR_EPS="${NVT_POLAR_EPS:-1.0e-5}"
RANDOM_SEED="${RANDOM_SEED:-20260617}"

usage() {
  cat <<'EOF'
Usage: run_md_step.sh <stage>

Stages (run from inside a <replicate>/<stage> directory):
  keys        write min/NPT/NVT/production key files
  minimize    Tinker minimize to the configured RMS gradient target, then write md_start.xyz
  npt         NPT density equilibration (Berendsen barostat, tau-pressure 1.0)
  nvt         NVT equilibration (keeps the .dyn restart, so the box is carried over)
  production  production run; default NPT with Monte Carlo barostat + save-induced

Stage parameters come from the study config and can be overridden in the environment:
  NPT_STEPS=2000 ./run_md_step.sh npt
  PRODUCTION_STEPS=10000 PRODUCTION_ENSEMBLE=nvt ./run_md_step.sh production
EOF
}

run_cmd() {
  local command_line="$1"
  shift
  local -a command
  read -r -a command <<< "$command_line"
  if [[ "${#command[@]}" -eq 0 ]]; then
    echo "Empty command line" >&2
    exit 1
  fi
  "${command[@]}" "$@"
}

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "Missing $1" >&2
    exit 1
  fi
}

# Re-emit the parameter lines of a key file, expanding first-level includes so the
# AMOEBA header is always resolved explicitly.
write_parameter_lines() {
  local source_key="$1"
  require_file "$source_key"
  while read -r prm_file; do
    if [[ -f "$prm_file" ]]; then
      awk 'tolower($1) == "parameters" {print}' "$prm_file"
    fi
    echo "parameters $prm_file"
  done < <(awk 'tolower($1) == "parameters" {print $2}' "$source_key") | awk '!seen[$0]++'
}

copy_system_key() {
  local out_key="$1"
  write_parameter_lines system.key > "$out_key"
}

append_periodic_common() {
  local key_file="$1"
  local polar_eps="$2"
  local printout="$3"
  cat >> "$key_file" <<EOF

polarization mutual
polar-eps ${polar_eps}
polar-iter 200
polar-predict
ewald
ewald-cutoff 7.0
neighbor-list
vdw-cutoff 12.0
vdw-correction
a-axis ${BOX_A}
b-axis ${BOX_A}
c-axis ${BOX_A}
alpha 90.0
beta 90.0
gamma 90.0
digits 8
printout ${printout}
EOF
}

# The reference procedure reports Beeman; this Tinker build switches Beeman to
# velocity Verlet when an Andersen thermostat is present.
append_reference_integrator() {
  local key_file="$1"
  cat >> "$key_file" <<EOF

integrator beeman
thermostat andersen
collision 0.1
randomseed ${RANDOM_SEED}
EOF
}

write_min_key() {
  copy_system_key min.key
  append_periodic_common min.key "$MIN_POLAR_EPS" 100
}

write_ref_npt_key() {
  copy_system_key ref_npt.key
  append_periodic_common ref_npt.key "$NPT_POLAR_EPS" 100
  append_reference_integrator ref_npt.key
  cat >> ref_npt.key <<'EOF'
barostat berendsen
pressure isotropic
tau-pressure 1.0
volume-scale molecular
EOF
}

write_ref_nvt_key() {
  copy_system_key ref_nvt.key
  append_periodic_common ref_nvt.key "$NVT_POLAR_EPS" 100
  append_reference_integrator ref_nvt.key
}

write_ref_production_key() {
  copy_system_key ref_production_npt_mc.key
  append_periodic_common ref_production_npt_mc.key "$PRODUCTION_POLAR_EPS" 1000
  append_reference_integrator ref_production_npt_mc.key
  cat >> ref_production_npt_mc.key <<'EOF'
barostat montecarlo
pressure isotropic
friction 1.0
volume-scale molecular
volume-trial 25
volume-move 100.0
EOF
  if [[ "$PRODUCTION_SAVE_INDUCED" == "1" ]]; then
    echo "save-induced" >> ref_production_npt_mc.key
  fi

  copy_system_key ref_production_nvt.key
  append_periodic_common ref_production_nvt.key "$PRODUCTION_POLAR_EPS" 1000
  append_reference_integrator ref_production_nvt.key
  if [[ "$PRODUCTION_SAVE_INDUCED" == "1" ]]; then
    echo "save-induced" >> ref_production_nvt.key
  fi
}

write_keys() {
  require_file system.key
  require_file ref.key
  write_min_key
  write_ref_npt_key
  write_ref_nvt_key
  write_ref_production_key
}

latest_minimized_xyz() {
  local latest
  latest="$(ls -t system.xyz_* 2>/dev/null | head -n 1 || true)"
  if [[ -z "$latest" ]]; then
    echo "Tinker minimize did not create system.xyz_*; inspect minimize.log." >&2
    exit 1
  fi
  printf '%s\n' "$latest"
}

final_rms_gradient() {
  local log_file="$1"
  awk '/Final RMS Gradient[[:space:]]*:/ {value=$NF} END {if (value != "") print value; else exit 1}' "$log_file"
}

float_le() {
  local lhs="$1"
  local rhs="$2"
  awk -v lhs="$lhs" -v rhs="$rhs" 'BEGIN {exit !(lhs <= rhs)}'
}

check_dynamic_log() {
  local log_file="$1"
  if grep -Eiq 'segmentation|fatal|nan|not Converged|Not Converged|terminating|\*\*\*\*\*\*\*\*' "$log_file"; then
    echo "Dynamics failed or produced invalid values; inspect ${log_file}." >&2
    return 1
  fi
}

run_minimize_stage() {
  require_file system.xyz
  write_min_key
  rm -f system.xyz_* md_start.xyz minimize.log

  echo "[minimize] target gradient ${MIN_GRADIENT} kcal mol^-1 Angstrom^-1" | tee minimize.log
  run_cmd "$MINIMIZE_CMD" system.xyz -k min.key "$MIN_GRADIENT" >> minimize.log 2>&1

  local latest final_rms
  latest="$(latest_minimized_xyz)"
  if ! final_rms="$(final_rms_gradient minimize.log)"; then
    echo "Could not parse Final RMS Gradient from minimize.log." >&2
    exit 1
  fi
  echo "[minimize] final RMS gradient ${final_rms}; target ${MIN_GRADIENT}" | tee -a minimize.log
  if ! float_le "$final_rms" "$MIN_GRADIENT"; then
    echo "Minimization did not reach target gradient ${MIN_GRADIENT}; final RMS gradient is ${final_rms}." >&2
    exit 1
  fi

  cp -f "$latest" md_start.xyz
  echo "Wrote md_start.xyz from ${latest}"
}

run_npt_stage() {
  require_file md_start.xyz
  write_ref_npt_key
  rm -f md_start.dyn md_start.arc md_start.uind npt.log

  echo "[npt] ${NPT_STEPS} steps, ${NPT_TIMESTEP_FS} fs, save ${NPT_SAVE_PS} ps, ${TEMPERATURE_K} K, ${PRESSURE_ATM} atm"
  run_cmd "$DYNAMIC_CMD" md_start.xyz -k ref_npt.key "$NPT_STEPS" "$NPT_TIMESTEP_FS" "$NPT_SAVE_PS" 4 "$TEMPERATURE_K" "$PRESSURE_ATM" > npt.log 2>&1
  check_dynamic_log npt.log
  test -f md_start.dyn || { echo "NPT did not create md_start.dyn; inspect npt.log." >&2; exit 1; }
  test -f md_start.arc || { echo "NPT did not create md_start.arc; inspect npt.log." >&2; exit 1; }
}

run_nvt_stage() {
  require_file md_start.xyz
  require_file md_start.dyn
  write_ref_nvt_key
  rm -f md_start.arc md_start.uind nvt.log

  echo "[nvt] ${NVT_STEPS} steps, ${NVT_TIMESTEP_FS} fs, save ${NVT_SAVE_PS} ps, ${TEMPERATURE_K} K"
  run_cmd "$DYNAMIC_CMD" md_start.xyz -k ref_nvt.key "$NVT_STEPS" "$NVT_TIMESTEP_FS" "$NVT_SAVE_PS" 2 "$TEMPERATURE_K" > nvt.log 2>&1
  check_dynamic_log nvt.log
  test -f md_start.dyn || { echo "NVT did not keep/create md_start.dyn; inspect nvt.log." >&2; exit 1; }
  test -f md_start.arc || { echo "NVT did not create md_start.arc; inspect nvt.log." >&2; exit 1; }
}

run_production_stage() {
  require_file md_start.xyz
  require_file md_start.dyn
  write_ref_production_key
  rm -f md_start.arc md_start.uind production.log

  case "$PRODUCTION_ENSEMBLE" in
    npt|NPT)
      echo "[production:npt] ${PRODUCTION_STEPS} steps, ${PRODUCTION_TIMESTEP_FS} fs, save ${PRODUCTION_SAVE_PS} ps, ${TEMPERATURE_K} K, ${PRESSURE_ATM} atm"
      run_cmd "$DYNAMIC_CMD" md_start.xyz -k ref_production_npt_mc.key "$PRODUCTION_STEPS" "$PRODUCTION_TIMESTEP_FS" "$PRODUCTION_SAVE_PS" 4 "$TEMPERATURE_K" "$PRESSURE_ATM" > production.log 2>&1
      ;;
    nvt|NVT)
      echo "[production:nvt] ${PRODUCTION_STEPS} steps, ${PRODUCTION_TIMESTEP_FS} fs, save ${PRODUCTION_SAVE_PS} ps, ${TEMPERATURE_K} K"
      run_cmd "$DYNAMIC_CMD" md_start.xyz -k ref_production_nvt.key "$PRODUCTION_STEPS" "$PRODUCTION_TIMESTEP_FS" "$PRODUCTION_SAVE_PS" 2 "$TEMPERATURE_K" > production.log 2>&1
      ;;
    *)
      echo "Unknown PRODUCTION_ENSEMBLE=${PRODUCTION_ENSEMBLE}; use npt or nvt." >&2
      exit 2
      ;;
  esac

  check_dynamic_log production.log
  test -f md_start.dyn || { echo "Production did not keep/create md_start.dyn; inspect production.log." >&2; exit 1; }
  test -f md_start.arc || { echo "Production did not create md_start.arc; inspect production.log." >&2; exit 1; }
  if [[ "$PRODUCTION_SAVE_INDUCED" == "1" ]]; then
    test -f md_start.uind || { echo "Production did not create md_start.uind; inspect production.log." >&2; exit 1; }
  fi
}

stage="${1:-}"
case "$stage" in
  keys)       write_keys ;;
  minimize)   run_minimize_stage ;;
  npt)        run_npt_stage ;;
  nvt)        run_nvt_stage ;;
  production) run_production_stage ;;
  -h|--help|"") usage ;;
  *) usage >&2; exit 1 ;;
esac
