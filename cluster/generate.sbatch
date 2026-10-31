#!/bin/bash
#SBATCH --job-name=bp-gen
#SBATCH --partition=dgxa100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --time=08:00:00
#SBATCH --output=logs/%x-%j.out
# Generates biasprobe stories for every model in models.txt, one model after the other, on one
# A100. Submit from the folder holding this file, generate_hf.py, models.txt and prompts.jsonl:
#   sbatch generate.sbatch
# Options via `sbatch --export=ALL,VAR=value generate.sbatch`:
#   SAMPLES      stories per probe (default 3)
#   SMOKE        stories per model in a first quick pass over all models, so a broken model shows
#                up within minutes (default 4; 0 skips the pass)
#   MODELS_FILE  model list (default models.txt)
#   SIF          container to use (default: the first one whose transformers loads every model)
# Output is resumable: rerunning only generates what out/stories-<name>.jsonl does not hold yet.
# apptainer runs directly in the batch step (on the compute node): srun currently fails on the
# dgxa100 nodes with "libslurmfull.so: cannot open shared object file".
set -uo pipefail
cd "$SLURM_SUBMIT_DIR"
C=/export/projects/nlp/containers
MODELS_FILE=${MODELS_FILE:-models.txt}
SAMPLES=${SAMPLES:-3}
SMOKE=${SMOKE:-4}
export HF_HOME=/tmp/${USER}_hf_${SLURM_JOB_ID}   # downloaded models stay off the home quota
mkdir -p "$HF_HOME" out logs
trap 'rm -rf "$HF_HOME"' EXIT
echo "node=$(hostname)  HF_HOME=$HF_HOME  samples=$SAMPLES  smoke=$SMOKE"

mapfile -t MODELS < <(grep -v '^\s*#' "$MODELS_FILE" | grep -v '^\s*$')
PATHS=$(for m in "${MODELS[@]}"; do set -- $m; echo "$2"; done)
BIND="--bind $C:$C:ro --env PYTHONNOUSERSITE=1"

if [ -z "${SIF:-}" ]; then
  for cand in torch-2.13.sif torch-2.12.sif vllm.sif torch-2.10.sif; do
    echo "--- checking $cand"
    if apptainer exec $BIND --env HF_HOME="$HF_HOME" "$C/$cand" python3 generate_hf.py --check $PATHS; then
      SIF=$C/$cand; break
    fi
  done
fi
[ -n "${SIF:-}" ] || { echo "no container supports all models"; exit 1; }
echo "container: $SIF"

run() {  # name checkpoint batch [extra generate_hf.py args]
  local name=$1 path=$2 bs=$3; shift 3
  apptainer exec --nv $BIND --env HF_HOME="$HF_HOME" "$SIF" python3 generate_hf.py \
    --model-name "$name" --model-path "$path" --prompts prompts.jsonl \
    --out "out/stories-$name.jsonl" --samples "$SAMPLES" --batch-size "$bs" "$@" \
    || echo "!!! $name failed"
}

if [ "$SMOKE" -gt 0 ]; then
  echo "=== smoke pass: $SMOKE stories per model"
  for m in "${MODELS[@]}"; do set -- $m; run "$1" "$2" "$SMOKE" --limit "$SMOKE" "${@:4}"; done
fi
echo "=== full pass"
for m in "${MODELS[@]}"; do set -- $m; run "$1" "$2" "$3" "${@:4}"; done
echo "=== done"
