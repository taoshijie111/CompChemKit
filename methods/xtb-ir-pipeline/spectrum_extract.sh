#!/bin/bash
#SBATCH --job-name=CONFORM
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=7-00:00:00
#SBATCH --partition=your_partition


python extract_spectrum.py --xyz-dir GDB17_XYZ -o GDB17_spectra.h5
