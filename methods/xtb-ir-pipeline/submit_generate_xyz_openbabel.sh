#!/bin/bash
#SBATCH --job-name=CONFORM
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=64
#SBATCH --cpus-per-task=1
#SBATCH --time=7-00:00:00
#SBATCH --partition=your_partition
#SBATCH --array=0-1

export OMP_NUM_THREADS=1
export PYTHONUNBUFFERED=1

echo "Working directory is $SLURM_SUBMIT_DIR"
cd "$SLURM_SUBMIT_DIR"
echo "Running on host $(hostname)"
echo "Time is $(date)"
echo "Node list: $SLURM_JOB_NODELIST"
echo "Current Array Task ID: $SLURM_ARRAY_TASK_ID" # 打印当前的任务ID

PART_ID=$(printf "%02d" $SLURM_ARRAY_TASK_ID)

echo "Processing Part: $PART_ID"

python generate_xyz_openbabel_single.py \
    --input-smi data/part_${PART_ID}.smi \
    --output-root xyz_out/part_${PART_ID} \
    --processes 64 \
    --force-field mmff94 \
    --timeout 600
