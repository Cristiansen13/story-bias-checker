# Study 2 annotation round (23 October 2026)

- `protocol.md`, `taxonomy.md`: exactly what the eight blind annotators (Claude Opus subagents)
  were given, together with one batch file of story texts each.
- `mapping.json`: anonymous id (`T001`…) → story id, model, and role (`target` = study-2 story,
  stored in the database as `annotator-s2-partN`; `anchor` = hidden study-1 Claude story, scored
  for drift and not stored).
- `results/batch_N.json`: the annotators' raw output, anchors included.
- `scripts/`: `build_batches.py` (writes the batches and mapping), `import_annotations.py`
  (validates quotes, stores targets with `--store`, prints the anchor drift check; run it from
  the project folder with `PYTHONPATH=. python dataset/annotation_s2/scripts/import_annotations.py
  dataset/annotation_s2`; it skips stories that already have a study-2 annotation), `rates.py`
  (the tables in FINDINGS.md).
