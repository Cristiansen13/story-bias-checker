#!/bin/bash
#SBATCH --job-name=bp-judge
#SBATCH --partition=dgxa100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --time=08:00:00
#SBATCH --output=logs/%x-%j.out
# Scores stories with an LLM judge on one A100. Write the prompts locally with
#   python -m biasprobe export-judge-prompts cluster/judge_prompts.jsonl --judge phi-4
# copy them next to this file and generate_hf.py, then:  sbatch judge.sbatch
# Options via `sbatch --export=ALL,VAR=value judge.sbatch`:
#   JUDGE_NAME   name stored with the scores (default phi-4; must match --judge above)
#   JUDGE_PATH   local checkpoint or Hugging Face id (default microsoft/phi-4)
#   BATCH        batch size (default 16)
#   SIF          container (default torch-2.13.sif)
# Output out/judge-<name>.jsonl is resumable; import it with `python -m biasprobe import-judge`.
set -uo pipefail
cd "$SLURM_SUBMIT_DIR"
C=/export/projects/nlp/containers
JUDGE_NAME=${JUDGE_NAME:-phi-4}
JUDGE_PATH=${JUDGE_PATH:-microsoft/phi-4}
BATCH=${BATCH:-16}
SIF=${SIF:-$C/torch-2.13.sif}
export HF_HOME=/tmp/${USER}_hf_${SLURM_JOB_ID}   # downloaded models stay off the home quota
mkdir -p "$HF_HOME" out logs
trap 'rm -rf "$HF_HOME"' EXIT
echo "node=$(hostname)  judge=$JUDGE_NAME ($JUDGE_PATH)  container=$SIF"
apptainer exec --nv --bind $C:$C:ro --env PYTHONNOUSERSITE=1 --env HF_HOME="$HF_HOME" "$SIF" \
  python3 generate_hf.py --task judge --model-name "$JUDGE_NAME" --model-path "$JUDGE_PATH" \
  --prompts judge_prompts.jsonl --out "out/judge-$JUDGE_NAME.jsonl" --batch-size "$BATCH"
echo "=== done"
