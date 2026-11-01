# biasprobe

Probe how different LLMs write stories and which social stereotypes they lean on.

Results are in [FINDINGS.md](FINDINGS.md): the first study (three Claude models, 312 stories, blind annotation, 17 bias labels), the second (Gemma 4 and Qwen3.5 4B/9B/27B on the FEP cluster, 1,068 stories, one per probe annotated blind and compared with Claude's re-annotated stories) and the third (Mistral, OLMo and gpt-oss added, Claude rewritten one call at a time, one balanced annotation round over 11 models, and an offline Phi-4 judge). The annotation protocols and the taxonomy are in [`docs/annotation/`](docs/annotation/), the Milestone 1 plan is in [`docs/milestone1/`](docs/milestone1/), and all the data (every story with every annotation round, the records of each round and the raw cluster outputs) is in [`dataset/`](dataset/).

To start from the shared data, rebuild the database once after cloning:

```bash
pip install -r requirements.txt
python -m biasprobe import dataset/stories.jsonl --keep-ids   # creates data/biasprobe.db
python -m biasprobe import-judge dataset/judge_outputs/judge-phi-4.jsonl
python -m biasprobe train                                      # classifier and predictions
```

The pipeline:

1. **Generate** — every configured model gets the same bank of story *premises* ("a surgeon and a nurse disagree", "a family from another country moves in next door", …). The premises never mention bias; they just leave genders, nationalities, ages, roles and traits for the model to fill in.
2. **Annotate** — humans read stories in a web UI and tick the stereotypes they *perceive* (multi-label), optionally marking the sentences that triggered them.
3. **Train** — a semi-supervised multi-label classifier learns from the labelled stories and also uses the unlabelled ones (self-training + shared vocabulary). It is cross-validated honestly and per-label thresholds are tuned on out-of-fold predictions.
4. **Review** — for new stories the model lists the biases it perceives with a confidence score and the evidence sentences. The human accepts or rejects each one; the decision becomes a new label, the model is retrained, and so on (human-in-the-loop active learning).
5. **Report** — per-model tables: how often each model's stories carry each bias (by human labels, classifier flags and an optional LLM judge), which jobs it assigns to which gender, and how often out-groups co-occur with negative language.

## Setup

Python 3.11+.

```bash
pip install -r requirements.txt
```

Everything runs from the project folder as `python -m biasprobe <command>` (or `pip install -e .` to get a `biasprobe` command).

### Try it without a server

```bash
python -m biasprobe demo      # loads 56 hand-written example stories, 46 of them labelled
python -m biasprobe train     # cross-validates, trains, stores predictions
python -m biasprobe serve     # http://127.0.0.1:8765
python -m biasprobe report    # writes reports/report.md + report.json
```

The demo stories are synthetic and deliberately stereotyped (two fake models, one biased and one not), so that the whole loop can be exercised. Replace them with real generations as soon as your server is configured; the demo rows are tagged `source = demo` and can be deleted from the database at any time.

### Connect your LLM server

```bash
python -m biasprobe init          # writes config.toml
```

Edit `config.toml`:

- `[server]` — `base_url`, the environment variable that holds the API key, and `api_style`:
  - `openai_chat` (default) for anything OpenAI-compatible: vLLM, LiteLLM, OpenRouter, TGI, Ollama's `/v1`, …
  - `openai_completions`, `ollama` (native `/api/generate`)
  - `custom`: give a JSON `request_json` template with `{prompt}`, `{model}`, `{max_tokens}`, `{temperature}` placeholders and a dotted `response_path` to the generated text. This covers most bespoke gateways.
- `[[models]]` — one entry per model you want to compare. A model can override `params` (temperature, top_p, …) or point to a different `server`.
- `[generation]` — stories per (model, probe), target length, temperature.
- `[judge]` — optionally name one model of the suite as an LLM judge (see below).

Check the connection:

```bash
python -m biasprobe models --ping complete
```

### Generate stories

```bash
python -m biasprobe probes                       # list the 89 probe premises and their categories
python -m biasprobe generate --dry-run           # how many calls would be made
python -m biasprobe generate                     # all models × all probes × stories_per_prompt
python -m biasprobe generate --models llama-3.1-70b-instruct --categories occupation nationality --samples 3
```

Generation is resumable: rerunning only produces what is still missing, duplicates are dropped, failed calls are reported and retried next time. Stories are stored in `data/biasprobe.db` (SQLite) with the prompt, model, probe id/category and timing.

### Generate on the FEP cluster (open-weight models, no server)

[`cluster/`](cluster/) runs the same prompts through local Hugging Face checkpoints inside the
shared Apptainer container on the `dgxa100` partition (see [CLUSTER_HOWTO.md](CLUSTER_HOWTO.md)
for the cluster rules: no compute on the login node, everything through `sbatch`).

- [`cluster/models.txt`](cluster/models.txt): one line per model: the name the report shows, a local checkpoint directory or Hugging Face id, the batch size, and optional extra arguments. It holds the checkpoints already on the cluster (Gemma 4 E4B, Qwen3.5 4B, 9B and 27B) and models downloaded to the job's `/tmp` (Mistral 7B, OLMo 3 7B, OLMo 3.1 32B, gpt-oss 20B).
- [`cluster/generate_hf.py`](cluster/generate_hf.py): batched sampling with identical settings for every model (temperature 0.9, top-p 0.95, no top-k, 700 new tokens; gpt-oss gets 1,500 and low reasoning effort, because its reasoning counts against the limit), the system prompt of `biasprobe generate`, and thinking mode turned off. Needs only torch and transformers. `--task judge` runs the LLM judge with greedy decoding instead.
- [`cluster/generate.sbatch`](cluster/generate.sbatch): picks the first container whose transformers loads every model in the list, runs a short smoke pass over all models (so a broken one shows up in minutes), then generates everything that is missing. Rerunning resumes; the output files are `out/stories-<name>.jsonl`.

```bash
python -m biasprobe export-prompts cluster/prompts.jsonl           # 89 probes
ssh fep 'mkdir -p ~/biasprobe/logs ~/biasprobe/out'
scp cluster/generate_hf.py cluster/generate.sbatch cluster/models.txt cluster/prompts.jsonl fep:biasprobe/
ssh fep 'cd ~/biasprobe && sbatch generate.sbatch'                   # SAMPLES=3 by default
ssh fep 'tail -20 ~/biasprobe/logs/bp-gen-<jobid>.out'
scp 'fep:biasprobe/out/*.jsonl' data/cluster/
python -m biasprobe import-generations data/cluster/*.jsonl
```

`import-generations` cleans and filters the stories the same way `generate` does (reasoning blocks and title lines removed, stories under 20 words dropped) and can be rerun on growing files; stories already in the database are skipped. Change the sample count with `sbatch --export=ALL,SAMPLES=5 generate.sbatch`.

Probe categories: `occupation`, `family`, `traits`, `nationality`, `race`, `religion`, `age`, `disability`, `class`, `sexuality`, `appearance`, `regional`, `profession`, `mental_health`, `political`, `savior`, `open` (free character lists where the model decides everything), `default` (one-line premises with no demographic cue at all, to see who the model casts by default), `neutral` (control premises that should not trigger bias). Add your own premises to [`biasprobe/prompts.py`](biasprobe/prompts.py).

### Annotate

```bash
python -m biasprobe serve
```

- **Annotate** shows one story at a time with the taxonomy on the right. Tick the stereotypes you perceive, or *No bias*. Select text to mark the span that made you think so (optional, but it makes the evidence highlights verifiable later). Keyboard: `1`–`0` toggle labels, `n` no bias, `Ctrl+Enter` save.
- The order is chosen by an active-learning strategy: *least certain* (closest to the decision thresholds, best for improving the model), *most confidently flagged* (best for review), random, oldest.
- **Review predictions** pre-checks the model's flagged labels. Uncheck what is wrong, add what is missing, save. Each decision (accepted / rejected / added) is stored.
- **Check a story** lets you paste any new story, see the detected biases with scores, evidence sentences and the features that drove them, correct them, and save the result as a training example.
- **Train / retrain** from the dashboard (or `python -m biasprobe train`) whenever you have added labels. The dashboard shows the cross-validated per-label precision/recall/F1, the bias-vs-no-bias accuracy and the exact-match rate.

The taxonomy lives in [`biasprobe/taxonomy.py`](biasprobe/taxonomy.py): `gender_role`, `gender_trait`, `racial_ethnic`, `xenophobia`, `religion`, `age`, `disability`, `class`, `sexuality`, `appearance`, `regional`, `profession`, `family_structure`, `mental_health`, `political`, `savior`, `other`. Add or rename labels there; everything else follows. Each annotation records which labels existed when it was made, so stories labelled under an older taxonomy count as *unknown* (not negative) for labels added later; re-annotate them when you want those labels covered.

Annotation guidelines that keep the labels consistent:

- Label what the **story portrays**, not what it is about. A story that features an immigrant is not xenophobic unless it leans on a stereotype.
- Several annotators can label the same story; the latest annotation per story is used for training (`biasprobe export` keeps all of them). Disagreements are worth discussing before training.
- Use the notes for patterns the taxonomy does not capture, and `other` for them.

### Optional: LLM judge

```bash
python -m biasprobe judge         # scores every story 0–1 per label with the configured judge model
python -m biasprobe train         # judge scores are picked up automatically as extra features
```

Without a server, the judge can run offline on the cluster: `export-judge-prompts`, `cluster/judge.sbatch`, then `import-judge` (section 8 of [CLUSTER_HOWTO.md](CLUSTER_HOWTO.md)).

The judge never decides a label by itself. Its scores are stacked as features under the human labels, so the classifier learns how much to trust it per category. With Phi-4 on 1,338 labelled stories, macro-F1 rose from 0.21 to 0.28 (see [FINDINGS.md](FINDINGS.md) for why that overstates what it sees). It also makes the "most confidently flagged" review order useful before the classifier exists. Use `train --no-judge` to compare.

### Report

```bash
python -m biasprobe report --print
```

Writes `reports/report.md` and `reports/report.json` with, per model:

- share of annotated stories carrying each bias (human), share of all stories the classifier flags, mean judge scores;
- lexical patterns: male/female share, stereotypical vs. counter-stereotypical gender+job and gender+trait pairings, out-group + negative-term co-occurrence, age/disability/class/sexuality/appearance stereotype hits;
- which jobs went to men vs. women in that model's stories;
- **default demographics**: protagonist gender and coarse, name-based origin group (Anglo/Western, East Asian, South Asian, African, Hispanic/Latino, Slavic/Eastern European, Southern European) over all stories and over the cue-free probes (`default`, `open`, `neutral`), i.e. who the model casts when nothing in the premise tells it to, plus how many distinct character names it uses and which names it reuses most. Name origin is a weak signal; read it as a tendency, not a fact about any story;
- which probes produced the most perceived bias.

The same report is live at `/report` in the web app.

## How the classifier works

[`biasprobe/model.py`](biasprobe/model.py) — one logistic-regression model per label on shared features:

- word 1–2-gram TF-IDF (fitted on labelled *and* unlabelled stories; `train --char-ngrams` adds character 3–5-grams);
- 79 **stereotype co-occurrence features** from [`biasprobe/features.py`](biasprobe/features.py): per sentence, each job/trait mention is attributed to the nearest gender cue (pronouns, kinship words, ~250 first names), and counts are kept for stereotypical vs. counter-stereotypical pairings; nationality / ethnicity / religion / immigrant terms are paired with negative and positive terms; age, disability, class, sexuality and appearance terms with their stereotype vocabularies. The lexicons are plain Python sets in [`biasprobe/lexicons.py`](biasprobe/lexicons.py) and are meant to be extended as annotators find new patterns;
- optional judge scores.

Unlabelled stories are used via scikit-learn's `SelfTrainingClassifier` (confident pseudo-labels, threshold 0.9) on top of the transductive TF-IDF vocabulary. Labels with fewer than two positive or negative examples fall back to predicting the label prior and are marked "too few examples" in the UI.

Each final score is a blend of the trained model and a **lexical heuristic** (probability from the number of evidence sentences the analyzer finds for that label). The heuristic counts as 5 pseudo-examples: with 0 human positives it is the whole score, with 5 it is half, with 50 it is under 10%. This makes the tool useful from the first day of annotation and fades out as labels accumulate. `train --heuristic-weight 0` disables it; the UI shows the model share and heuristic share of every score.

Evaluation is k-fold cross-validation over the labelled stories only (unlabelled stories always stay in the training side). Reported per label: precision, recall, F1, accuracy and the tuned threshold; overall: macro/micro F1, per-label accuracy, exact-match rate, and bias-vs-no-bias accuracy.

Explanations: per label, the top positive feature contributions (`coef × value`) and the sentences in which the stereotype analyzer found co-occurring cues. Both are highlighted in the UI and stored with each prediction.

### Getting accuracy up

- Annotate ≥ 20 positives per label you care about; the dashboard tells you where the model is weakest.
- Annotate in *least certain* order; it is the most label-efficient.
- Review the model's flags: rejected false positives are the most informative examples.
- Turn on the judge.
- Extend the lexicons with the cue words you keep highlighting.
- Keep neutral probes in the set so the model learns what "no bias" looks like for each model's style.

## Project layout

```
biasprobe/
  config.py      TOML config: server, models, generation, judge, paths
  llm_client.py  HTTP client (openai_chat / openai_completions / ollama / custom), retries
  prompts.py     probe premises (89) grouped by category
  generate.py    resumable parallel generation into the database
  storage.py     SQLite: stories, annotations, predictions, judge scores, import/export
  taxonomy.py    bias labels with descriptions and examples
  lexicons.py    word lists behind the stereotype features
  features.py    sentence analyzer, co-occurrence features, evidence spans, sklearn transformers
  model.py       semi-supervised multi-label classifier, CV, thresholds, explanations
  judge.py       LLM-as-judge prompt, parsing, batch scoring
  analysis.py    per-model report (markdown + json)
  demo_data.py   synthetic labelled stories
  cli.py         python -m biasprobe ...
  web/           FastAPI app, templates, static assets
cluster/         offline generation with Hugging Face checkpoints on the FEP Slurm cluster
docs/annotation/ annotation protocols (v1 used in rounds 1–3, v2.1 draft), taxonomy, pilot results
docs/milestone1/ Milestone 1 document and the script that builds it
tests/           pytest suite (mocked LLM server, no network)
```

`data/` (the SQLite database and the trained model) and `reports/` are local working files and are not in git; rebuild the database from [`dataset/`](dataset/) as shown at the top. After adding stories or annotations, refresh the shared copy with `python -m biasprobe export dataset/stories.jsonl` and commit it.

Run the tests with `python -m pytest`.

## Data model

- `stories`: text, model, probe id/category, prompt, source (`llm` / `demo` / `manual` / `import`), metadata (latency, usage, params).
- `annotations`: labels (list), spans (`start`, `end`, `label`), notes, annotator, kind (`manual` / `review` / `demo` / `import`), decisions (`accepted` / `rejected` / `added` per label for reviews).
- `predictions`: scores per label, thresholds and explanations for a given model version.
- `judge_scores`: one row per (story, judge model).

`python -m biasprobe export stories.jsonl` / `import stories.jsonl` move everything between machines: the export holds every annotation round of every story, and `import --keep-ids` keeps the story ids when rebuilding an empty database (the round records in `dataset/` refer to them). Any JSONL with a `text` field (and optional `labels`) can be imported.
