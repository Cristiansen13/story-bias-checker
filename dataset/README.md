# Dataset

All data the study has produced, so that a fresh clone can rebuild the database and reproduce
every number in [FINDINGS.md](../FINDINGS.md) and the Milestone 1 document.

| path | what it is |
|---|---|
| `stories.jsonl` | every story in the database (1,436) with every annotation round (1,170 annotations) |
| `annotation_s2/` | round 2: 356 open-weight stories, 30 hidden Claude anchors (8 LLM annotators) |
| `annotation_s3/` | round 3: 267 Claude stories, 40 hidden open-weight anchors (7 LLM annotators) |
| `annotation_s4/` | pilot of the casting criteria: 79 stories, two independent groups (not stored in the database) |
| `cluster_outputs/` | raw `stories-<model>.jsonl` files written on the FEP cluster, before cleaning |

## Rebuild the database

From the repository folder, into an empty `data/`:

```bash
python -m biasprobe import dataset/stories.jsonl --keep-ids
python -m biasprobe train      # trained model and predictions are not part of the export
python -m biasprobe stats
```

`--keep-ids` keeps the story ids, which the round records (`mapping.json`) refer to. Do not
import into a database that already has stories.

## `stories.jsonl`

One JSON object per line:

- `id`, `uid` (hash of model, probe and text), `model`, `probe_id`, `probe_category`, `prompt`,
  `text`, `created_at`;
- `source`: `agent` (study 1, Claude models via subagents), `llm` (study 2, cluster), `demo`
  (56 synthetic examples, models `demo-model-a/b`);
- `meta`: generation details (sampling parameters, sample index, latency, token usage, engine);
- `annotations`: every annotation of the story, oldest first, each with `annotator`, `labels`,
  `spans` (`start`, `end`, `label` in the story text), `notes` ("Casting only: …" marks casting),
  `kind`, `decisions` (review decisions), `taxonomy` (the labels the annotator could choose from)
  and `created_at`; `annotation` repeats the latest one, which is what training uses;
- `judge`: LLM-judge scores (none yet).

Annotators: `annotator-part1…4` and `annotator-re1…4` are study 1 (the `re` annotators
re-annotated the first batch under the 17-label taxonomy), `annotator-s2-part1…8` round 2,
`annotator-s3-part1…7` round 3, `demo` the synthetic examples. All annotators so far are Claude
Opus subagents.

## Round records

Each `annotation_s*` folder holds what the annotators read (protocol, taxonomy, batches), their raw
output with the anchors (`results/`), the anonymous-id mapping (`mapping.json`) and the scripts
that built and scored the round. Run the scripts from the repository folder after rebuilding the
database:

```bash
PYTHONPATH=. python dataset/annotation_s3/scripts/rates.py          # study-2 tables in FINDINGS.md
PYTHONPATH=. python dataset/annotation_s4/scripts/analyze_pilot.py  # docs/annotation/pilot_results.md
```

The protocol v2.1 and the pilot write-up are in [`docs/annotation/`](../docs/annotation/).

## Keeping it current

After adding stories or annotations, refresh the export and commit it:

```bash
python -m biasprobe export dataset/stories.jsonl
```
