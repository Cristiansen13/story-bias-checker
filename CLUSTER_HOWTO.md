# FEP/UPB Slurm Cluster — How to Run GPU Jobs

Working recipe (verified across the Paper 2 experiments). Reusable for any project.

## 0. The one hard rule
**NEVER run compute on the login node.** It is for file I/O only. Every computation —
no matter how small — goes through Slurm (`sbatch`). The login node is shared; running
`python`/model-loading/`srun` compute there violates cluster policy.

- Login node **OK for**: `scp`/file writes, `git`, submitting `sbatch`, and lightweight
  monitoring (`squeue`, `sacct`, `cat *.out`).
- Login node **NOT for**: `python`, loading models, `srun` heavy compute, or anything
  that uses CPU/GPU/RAM.

## 1. Access
- SSH: `ssh fep` (passwordless; host `fep.grid.pub.ro`, user `mihai.strejaru`).
- If passwordless login isn't set up on a new machine, add your key to
  `~/.ssh/authorized_keys` on the cluster and a `Host fep` block to your local
  `~/.ssh/config`.

## 2. Partition (which GPUs)
- **Use `dgxa100`** (A100 80GB). This is the one that works.
- `dgxh100` and `h200` **reject jobs** instantly (restricted QOS → ExitCode 0:53, batch
  step CANCELLED, no output). Don't waste time on them.
- `haswell` = CPU-only partition (works for CPU jobs).
- Nodes shown as `mix` in `squeue` still have free GPUs available for `gpu:1`.

## 3. Container (the Python environment)
- Shared Apptainer image: `/export/projects/nlp/containers/torch-2.12.sif`
  (lives off your home quota — use it, don't build your own).
- Invoke: `srun apptainer exec --nv "$SIF" python3 <script>` (the `--nv` flag exposes
  the GPUs).
- Has torch + transformers + datasets + numpy. If a package is missing
  (e.g. `colbert`, `ragatouille`), reimplement with transformers rather than pip-installing
  into the read-only container.

## 4. Storage (home is over quota)
- Home directory is **over the 50 GB student quota** (enforced Feb 2026) — writes may
  fail if you fill it.
- `dgxa100` compute nodes have **internet** and **`/tmp` = ~1.7 TB free** (node-local).
- **Storage-safe pattern:** put big caches/datasets/images in a `/tmp` workdir, write only
  small result JSONs to home, and `rm -rf` the `/tmp` workdir at job end (a `trap` does
  this automatically; see template).
- `HF_HOME` on `/tmp` keeps the multi-GB HuggingFace model cache off your home quota.
- Do **not** set `HF_HUB_OFFLINE=1` inside Python after importing `transformers` — it's
  read at import time and will break loading. Set it as an env var before the process if
  you need offline mode.

## 5. The sbatch template
Save as `job.sbatch`, edit the job name / resources / script name:

```bash
#!/bin/bash
#SBATCH --job-name=myjob
#SBATCH --partition=dgxa100
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=%x-%j.out          # -> myjob-<jobid>.out
set -uo pipefail
SIF=/export/projects/nlp/containers/torch-2.12.sif
export HF_HOME=/tmp/${USER}_hf_${SLURM_JOB_ID}   # model cache off home quota
mkdir -p "$HF_HOME"
trap 'rm -rf "$HF_HOME"' EXIT                     # clean /tmp at job end
echo "node=$(hostname)  HF_HOME=$HF_HOME"
srun apptainer exec --nv \
  --env HF_HOME="$HF_HOME" \
  "$SIF" python3 myscript.py
echo "=== done (exit $?) ==="
```

Memory guidance (adjust `--mem`): a ~3B vision-language model (ColPali) ran fine at
`--mem=64G`; a larger one (ColQwen2) needed `--mem=160G`. Bump `--time` for long jobs.

## 6. Submit + monitor workflow (all from the login node — no compute)
```bash
# 1. write script + sbatch locally, then copy them up
scp myscript.py job.sbatch fep:~/mywork/

# 2. submit
ssh fep 'cd ~/mywork && sbatch job.sbatch'

# 3. watch the queue (R = running, PD = pending)
ssh fep 'squeue -u mihai.strejaru -o "%.10i %.12j %.3t %.10M %R"'

# 4. read the log while it runs / after it finishes
ssh fep 'tail -40 ~/mywork/myjob-<jobid>.out'

# 5. copy small results back
scp fep:~/mywork/results.json ./
```

Pass runtime config via `--env VAR=...` on the `apptainer exec` line and read it in Python
with `os.environ` (keeps one sbatch reusable across runs).

## 7. Gotchas learned the hard way
- A job with no `--mem` can OOM-kill on first model load — always set `--mem`.
- `squeue`/logs are fine from the login node; the actual work must be inside `srun`.
- Local `git push` to `master` may be blocked by the harness — use `scp` to move files to
  the cluster instead of pushing.
- Save results frequently; nodes can be preempted by other users' jobs.
- Since the Slurm 25.11 update (seen 23 Oct 2026), `srun` inside a dgxa100 job fails with
  `libslurmfull.so: cannot open shared object file`. Call `apptainer exec ...` directly in the
  batch script (it already runs on the allocated compute node), as `mneme/cluster/*.sbatch` does.
- The `normal` QOS allows **2 running jobs per user** across all partitions; a third waits
  with reason `QOSMaxJobsPerUserLimit`. Run several models inside one job rather than one job each.
- `haswell` caps memory at 1750 MB per CPU (`dgxa100`: 27000 MB). Asking for more `--mem` than
  that times `--cpus-per-task` silently raises the CPU count, and every `srun` in the job then
  fails with `cpus-per-task set by two different environment variables`. On haswell, keep
  `--mem` ≤ 1.7 GB × CPUs.
