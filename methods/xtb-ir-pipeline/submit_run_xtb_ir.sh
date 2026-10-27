#!/bin/bash
#SBATCH --job-name=XTB
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=64
#SBATCH --cpus-per-task=1
#SBATCH --time=30-00:00:00
#SBATCH --partition=your_partition
#SBATCH --array=0-00

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

python run_xtb_ir.py \
    --root-dir xyz_out/part_${PART_ID} \
    --task-name XTB_OPT \
    --max-workers 64 \
    --cores-per-task 1 \
    --max-iterations 10 \
    --disp-scale 1 \
    --imag-threshold 0 \
    --skip-completed \
