#!/bin/bash
#SBATCH -J orca_optfreq
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
# ORCA: geometry optimisation, then (only if it converged) the analytic Hessian
# in the same job. Submit from the SYSTEM directory so that opt.inp / opt.xyz /
# freq.inp are all in $SLURM_SUBMIT_DIR:
#
#     cd <WORKDIR>/<step>/<system> && sbatch ../slurm_orca_optfreq.sh
#
# If the pair cannot fit in one wall time, split it: keep opt.xyz + opt.gbw and
# submit a second job that only runs freq.inp (%moinp "opt.gbw" reuses the
# converged orbitals and saves a lot of time).

if [ -f "$SLURM_SUBMIT_DIR/env.sh" ]; then source "$SLURM_SUBMIT_DIR/env.sh"; fi
if [ -z "${HPC_ORCA:-}" ]; then echo "ERROR: HPC_ORCA is not set (missing env.sh)"; exit 3; fi

cd "$SLURM_SUBMIT_DIR" || exit 1
echo "job=${SLURM_JOB_NAME} id=${SLURM_JOB_ID} node=$(hostname) start=$(date)"
echo "cpus=${SLURM_CPUS_PER_TASK} system=$(basename "$(pwd)")"

# ---- 1) optimisation
"$HPC_ORCA" opt.inp > opt.out 2>&1
rc=$?
echo "opt rc=$rc"
grep -E "THE OPTIMIZATION HAS CONVERGED|FINAL SINGLE POINT ENERGY" opt.out | tail -2
if [ ! -f opt.xyz ]; then echo "ERROR: no opt.xyz produced"; exit 2; fi
if ! grep -q "THE OPTIMIZATION HAS CONVERGED" opt.out; then
  echo "ERROR: optimisation did not converge - keeping opt.xyz for a resume"
  exit 2
fi

# ---- 2) frequencies on the optimised geometry
"$HPC_ORCA" freq.inp > freq.out 2>&1
rc=$?
echo "freq rc=$rc"
if grep -q "ORCA TERMINATED NORMALLY" freq.out; then
  echo "freq TERMINATED NORMALLY"
else
  echo "WARNING: freq did not terminate normally (timeout / OOM? check freq.out)"
fi
grep -E "Zero point energy|Total Enthalpy\s+\.\.\.|Final Gibbs free energy" freq.out | tail -3
nimg=$(grep -cE "^ *[0-9]+: *-[0-9]+\.[0-9]+ cm" freq.out)
echo "imaginary modes: $nimg"
echo "end=$(date)"
exit $rc
