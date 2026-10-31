"""Collect the one-call Claude stories into importable JSONL (one file per model).

Each story was written by a fresh Claude Code subagent (Haiku, Sonnet or Opus) that read one task
file holding the generator's system prompt and the premise prompt verbatim, and saved the story
under a neutral number (s001..s089). This script pairs the saved texts with their premises:

    python dataset/claude_single/collect.py STORY_DIR      # STORY_DIR holds manifest.json, haiku/, sonnet/, opus/
    python -m biasprobe import-generations dataset/claude_single/stories-claude-*-single.jsonl
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

src = Path(sys.argv[1])
out_dir = Path(__file__).resolve().parent
manifest = json.loads((src / "manifest.json").read_text("utf-8"))
for model in ("haiku", "sonnet", "opus"):
    rows, missing = [], []
    for task in manifest:
        f = src / model / f"{task['task']}.txt"
        if not f.exists():
            missing.append(task["task"])
            continue
        stamp = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        rows.append({"model": f"claude-{model}-single", "probe_id": task["probe_id"],
                     "probe_category": task["probe_category"], "prompt": task["prompt"], "sample_index": 0,
                     "text": f.read_text("utf-8").strip(), "source": "agent", "engine": "claude-code-subagent",
                     "model_path": model, "generation": "one story per fresh subagent", "created_at": stamp})
    path = out_dir / f"stories-claude-{model}-single.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    print(f"{path.name}: {len(rows)} stories" + (f"; missing {', '.join(missing)}" if missing else ""))
