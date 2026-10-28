# Round 3 annotation (23 October 2026)

Claude's one-per-probe stories (the first story of each of the 89 probes, for Haiku, Sonnet and
Opus: 267 stories) re-annotated blind, so that the Claude/open-model comparison in FINDINGS.md
can be checked against a fresh round.

- `protocol.md`, `taxonomy.md`: identical to round 2 (`dataset/annotation_s2/`).
- `batches/`: the seven batch files the annotators (Claude Opus subagents) read; they were
  copied to a separate folder without `mapping.json` before the annotators saw them.
- `mapping.json`: anonymous id (`R001`…) → story id, model, role. `target` = Claude story, stored
  in the database as `annotator-s3-partN`; `anchor` = round-2 open-model story (5 labelled and 5
  clean per model in round 2), scored for drift and not stored.
- `results/batch_N.json`: the annotators' raw output, anchors included.
- `scripts/build_batches.py`: writes the batches and the mapping.
- `scripts/import_annotations.py`: validates quotes, stores targets with `--store` (skips stories
  that already have a round-3 annotation), prints the round-2 vs round-3 anchor comparison and
  the study-1 vs round-3 comparison on the Claude stories.
- `scripts/rates.py`: every number in the study-2 "Human-perceived bias" section of FINDINGS.md,
  including the within-round anchor estimates and the beyond-casting rate.

Run the scripts from the project folder, e.g.
`PYTHONPATH=. python dataset/annotation_s3/scripts/rates.py`.
