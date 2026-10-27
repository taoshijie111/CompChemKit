#!/bin/bash
#SBATCH -J xtb_ohess
#SBATCH -p __PARTITION__
#SBATCH --qos=__QOS__
#SBATCH -N 1
#SBATCH --ntasks-per-node=1
#SBATCH -c __CORES__
#SBATCH --requeue
#SBATCH -t __HOURS__:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
#
# xTB: optimisation + numerical Hessian in one shot (--ohess), then keep the
# Gaussian-format frequency file. Run one xTB task per directory - xTB writes
# xtbopt.xyz / hessian into the CURRENT working directory, so do not try to
# redirect it into a subdirectory.

if [ -f "$SLURM_SUBMIT_DIR/env.sh" ]; then source "$SLURM_SUBMIT_DIR/env.sh"; fi
if [ -z "${HPC_XTB:-}" ]; then echo "ERROR: HPC_XTB is not set (missing env.sh)"; exit 3; fi

cd "$SLURM_SUBMIT_DIR" || exit 1
echo "job=${SLURM_JOB_NAME} id=${SLURM_JOB_ID} node=$(hostname) start=$(date)"

# xTB must see a writable scratch + the XTBPATH shipped with the distribution
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export OMP_STACKSIZE=1G

# charge / multiplicity: 0 0 for a closed-shell neutral molecule, 0 2 for a doublet, ...
"$HPC_XTB" start.xyz --gfn 2 --opt tight --ohess extreme \
    --chrg 0 --uhf 0 -P "${SLURM_CPUS_PER_TASK:-1}" > xtb.log 2>&1
rc=$?
echo "xtb rc=$rc"
[ -f xtbopt.xyz ] && echo "optimised structure: xtbopt.xyz"
[ -f g98.out ] && grep -c "Frequencies --" g98.out | sed 's/^/frequency lines: /'
# imaginary modes show up as negative frequencies in g98.out
grep "Frequencies --" g98.out 2>/dev/null | tr -s ' ' | cut -d' ' -f3- | tr ' ' '\n' | \
  awk '$1+0 < 0 {n++} END {printf "imaginary modes: %d\n", n+0}'
echo "end=$(date)"
exit $rc
