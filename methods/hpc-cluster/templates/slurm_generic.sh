#!/bin/bash
#SBATCH -J __JOB_NAME__
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
# Generic Slurm job template. Placeholders to replace (the agent fills them from
# ~/.compchemkit/config.json -> scheduler.*):
#   __JOB_NAME__ __PARTITION__ __QOS__ __CORES__ __HOURS__
#
# Rules that keep this portable:
#   * NEVER use BASH_SOURCE / dirname to locate the project: Slurm copies the
#     batch script into its spool directory before running it. Use
#     $SLURM_SUBMIT_DIR or --export=ALL,STAGE="$PWD".
#   * Do not add --mem on clusters where the node memory is misconfigured;
#     check platforms/<name>.md first.
#   * Write the file with LF line endings and keep a final newline.

# environment: generated locally with
#   python scripts/hpc_config.py env > env.sh && scp env.sh <alias>:<WORKDIR>/
if [ -f "$SLURM_SUBMIT_DIR/env.sh" ]; then source "$SLURM_SUBMIT_DIR/env.sh"; fi
if [ -z "${HPC_ORCA:-}" ]; then echo "ERROR: HPC_ORCA is not set (missing env.sh)"; exit 3; fi

cd "$SLURM_SUBMIT_DIR" || exit 1
echo "job=${SLURM_JOB_NAME} id=${SLURM_JOB_ID} node=$(hostname) start=$(date)"
echo "cpus=${SLURM_CPUS_PER_TASK} cwd=$(pwd)"

# optional: single-socket / NUMA sanity check (see platforms/ustc.md section 3.3)
# ids=$(scontrol show job "$SLURM_JOB_ID" -d | tr ' ' '\n' | sed -n 's/^CPU_IDs=//p')
# echo "CPU_IDs=$ids"

"$HPC_ORCA" input.inp > output.out 2>&1
rc=$?
echo "return code: $rc"
grep -E "ORCA TERMINATED NORMALLY|FINAL SINGLE POINT ENERGY|TOTAL RUN TIME" output.out | tail -3
echo "end=$(date)"
exit $rc
