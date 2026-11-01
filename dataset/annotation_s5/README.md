# Balanced round (round 5)

One story per premise for each of the 11 models (979 stories) under protocol v2.1, with every batch
holding the same mix of models, so that neither round leniency nor contrast between families can
move the comparison. Claude is represented by its one-call stories (`dataset/claude_single/`).

| path | what it is |
|---|---|
| `protocol.md`, `taxonomy.md` | what the annotators read |
| `batches/` | 22 batches of about 46 stories, anonymous ids `V####`, no model names |
| `results/` | raw annotator output, repeats included |
| `mapping.json` | anonymous id to story, model, premise, batch and role (`target` or `repeat`) |
| `scripts/build_batches.py` | builds the batches (rerunning needs the pre-round database) |
| `scripts/import_annotations.py` | validates, stores with `--store`, prints rates and agreement |
| `scripts/family_tests.py` | family gaps with premise-level intervals, categories, judge comparison |

A story's batch is (premise + 2 × model) mod 22, so no batch repeats a premise. 44 stories (4 per
model) appear a second time in another batch under a new id; they are scored for agreement and not
stored. A label counts as casting if the annotator's `casting` list names it, and a story is
"beyond casting" if it has a label that is not casting.

Run from the repository folder, after rebuilding the database:

```bash
PYTHONPATH=. python dataset/annotation_s5/scripts/import_annotations.py
PYTHONPATH=. python dataset/annotation_s5/scripts/family_tests.py
```
