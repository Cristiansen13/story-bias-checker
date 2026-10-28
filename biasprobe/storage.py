"""SQLite persistence for stories, annotations, predictions and judge scores."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL UNIQUE,
    model TEXT NOT NULL,
    probe_id TEXT NOT NULL DEFAULT '',
    probe_category TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'llm',
    meta TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stories_model ON stories(model);
CREATE INDEX IF NOT EXISTS idx_stories_probe ON stories(probe_id);

CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    annotator TEXT NOT NULL DEFAULT '',
    labels TEXT NOT NULL DEFAULT '[]',
    spans TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'manual',
    decisions TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_annotations_story ON annotations(story_id);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    model_version TEXT NOT NULL,
    scores TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_predictions_story ON predictions(story_id);

CREATE TABLE IF NOT EXISTS judge_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    judge_model TEXT NOT NULL,
    scores TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '{}',
    raw TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(story_id, judge_model)
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

JSON_COLUMNS = {"meta", "labels", "spans", "decisions", "scores", "evidence", "taxonomy"}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for key in JSON_COLUMNS:
        if key in out and isinstance(out[key], str):
            try:
                out[key] = json.loads(out[key])
            except ValueError:
                pass
    return out


class Storage:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)
        self._lock = threading.RLock()
        self._migrate()

    def _migrate(self) -> None:
        """Add columns introduced after the first release."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(annotations)").fetchall()}
        if "taxonomy" not in cols:
            from .taxonomy import LEGACY_LABEL_KEYS_V1
            self._conn.execute("ALTER TABLE annotations ADD COLUMN taxonomy TEXT NOT NULL DEFAULT '[]'")
            # Annotations made before the column existed were made under the v1 taxonomy.
            self._conn.execute("UPDATE annotations SET taxonomy = ? WHERE taxonomy = '[]'",
                               (json.dumps(LEGACY_LABEL_KEYS_V1),))
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------------------------------------------------------------- helpers
    def _fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [_row_to_dict(r) for r in rows]

    def _fetchone(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(sql, tuple(params)).fetchone()
        return _row_to_dict(row)

    @staticmethod
    def story_uid(model: str, probe_id: str, text: str) -> str:
        normalised = " ".join(text.split()).lower()
        return hashlib.sha1(f"{model}\n{probe_id}\n{normalised}".encode("utf-8")).hexdigest()

    # ---------------------------------------------------------------- stories
    def add_story(self, text: str, model: str, *, probe_id: str = "", probe_category: str = "",
                  prompt: str = "", source: str = "llm", meta: dict[str, Any] | None = None,
                  created_at: str | None = None) -> int | None:
        """Insert a story; returns its id, or None if an identical story exists."""
        uid = self.story_uid(model, probe_id, text)
        with self._lock:
            try:
                cur = self._conn.execute(
                    "INSERT INTO stories (uid, model, probe_id, probe_category, prompt, text, "
                    "source, meta, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (uid, model, probe_id, probe_category, prompt, text, source,
                     json.dumps(meta or {}), created_at or _now()))
                self._conn.commit()
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                return None

    def get_story(self, story_id: int) -> dict[str, Any] | None:
        return self._fetchone("SELECT * FROM stories WHERE id = ?", (story_id,))

    def delete_story(self, story_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM stories WHERE id = ?", (story_id,))
            self._conn.commit()

    def _story_filter(self, model=None, probe_id=None, category=None, source=None,
                      annotated: bool | None = None, label: str | None = None,
                      search: str | None = None) -> tuple[str, list[Any]]:
        clauses, params = [], []
        if model:
            clauses.append("s.model = ?"); params.append(model)
        if probe_id:
            clauses.append("s.probe_id = ?"); params.append(probe_id)
        if category:
            clauses.append("s.probe_category = ?"); params.append(category)
        if source:
            clauses.append("s.source = ?"); params.append(source)
        if search:
            clauses.append("s.text LIKE ?"); params.append(f"%{search}%")
        if annotated is True:
            clauses.append("EXISTS (SELECT 1 FROM annotations a WHERE a.story_id = s.id)")
        elif annotated is False:
            clauses.append("NOT EXISTS (SELECT 1 FROM annotations a WHERE a.story_id = s.id)")
        if label:
            clauses.append(
                "EXISTS (SELECT 1 FROM annotations a WHERE a.story_id = s.id AND a.id = "
                "(SELECT MAX(id) FROM annotations b WHERE b.story_id = s.id) "
                "AND a.labels LIKE ?)")
            params.append(f'%"{label}"%')
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def list_stories(self, *, limit: int | None = None, offset: int = 0, order: str = "id",
                     **filters) -> list[dict[str, Any]]:
        where, params = self._story_filter(**filters)
        order_sql = {"id": "s.id", "newest": "s.id DESC", "random": "RANDOM()"}[order]
        sql = f"SELECT s.* FROM stories s{where} ORDER BY {order_sql}"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        return self._fetchall(sql, params)

    def count_stories(self, **filters) -> int:
        where, params = self._story_filter(**filters)
        row = self._fetchone(f"SELECT COUNT(*) AS n FROM stories s{where}", params)
        return int(row["n"]) if row else 0

    def existing_count(self, model: str, probe_id: str) -> int:
        return self.count_stories(model=model, probe_id=probe_id)

    def models(self) -> list[str]:
        return [r["model"] for r in self._fetchall("SELECT DISTINCT model FROM stories ORDER BY model")]

    def probe_ids(self) -> list[str]:
        return [r["probe_id"] for r in self._fetchall(
            "SELECT DISTINCT probe_id FROM stories ORDER BY probe_id")]

    # ------------------------------------------------------------ annotations
    def add_annotation(self, story_id: int, labels: list[str], *, spans: list[dict] | None = None,
                       notes: str = "", annotator: str = "", kind: str = "manual",
                       decisions: dict[str, str] | None = None,
                       taxonomy: list[str] | None = None) -> int:
        """`taxonomy` records which labels the annotator could choose from; labels
        outside it count as unknown (not negative) when training."""
        if self.get_story(story_id) is None:
            raise KeyError(f"story {story_id} does not exist")
        if taxonomy is None:
            from .taxonomy import LABEL_KEYS
            taxonomy = LABEL_KEYS
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO annotations (story_id, annotator, labels, spans, notes, kind, "
                "decisions, taxonomy, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (story_id, annotator, json.dumps(sorted(set(labels))), json.dumps(spans or []),
                 notes, kind, json.dumps(decisions or {}), json.dumps(list(taxonomy)), _now()))
            self._conn.commit()
            return int(cur.lastrowid)

    def annotations_for(self, story_id: int) -> list[dict[str, Any]]:
        return self._fetchall("SELECT * FROM annotations WHERE story_id = ? ORDER BY id", (story_id,))

    def latest_annotation(self, story_id: int) -> dict[str, Any] | None:
        return self._fetchone(
            "SELECT * FROM annotations WHERE story_id = ? ORDER BY id DESC LIMIT 1", (story_id,))

    def latest_annotations(self) -> dict[int, dict[str, Any]]:
        rows = self._fetchall(
            "SELECT a.* FROM annotations a WHERE a.id = "
            "(SELECT MAX(id) FROM annotations b WHERE b.story_id = a.story_id)")
        return {int(r["story_id"]): r for r in rows}

    def delete_annotation(self, annotation_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))
            self._conn.commit()

    # ------------------------------------------------------------ predictions
    def save_prediction(self, story_id: int, model_version: str, scores: dict[str, float],
                        evidence: dict[str, Any] | None = None) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO predictions (story_id, model_version, scores, evidence, created_at) "
                "VALUES (?,?,?,?,?)",
                (story_id, model_version, json.dumps(scores), json.dumps(evidence or {}), _now()))
            self._conn.commit()
            return int(cur.lastrowid)

    def latest_prediction(self, story_id: int) -> dict[str, Any] | None:
        return self._fetchone(
            "SELECT * FROM predictions WHERE story_id = ? ORDER BY id DESC LIMIT 1", (story_id,))

    def latest_predictions(self) -> dict[int, dict[str, Any]]:
        rows = self._fetchall(
            "SELECT p.* FROM predictions p WHERE p.id = "
            "(SELECT MAX(id) FROM predictions q WHERE q.story_id = p.story_id)")
        return {int(r["story_id"]): r for r in rows}

    # ------------------------------------------------------------------ judge
    def save_judge(self, story_id: int, judge_model: str, scores: dict[str, float],
                   evidence: dict[str, str] | None = None, raw: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO judge_scores (story_id, judge_model, scores, evidence, raw, created_at) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(story_id, judge_model) DO UPDATE SET "
                "scores = excluded.scores, evidence = excluded.evidence, raw = excluded.raw, "
                "created_at = excluded.created_at",
                (story_id, judge_model, json.dumps(scores), json.dumps(evidence or {}), raw, _now()))
            self._conn.commit()

    def judge_scores(self, judge_model: str | None = None) -> dict[int, dict[str, float]]:
        if judge_model:
            rows = self._fetchall("SELECT * FROM judge_scores WHERE judge_model = ?", (judge_model,))
        else:
            rows = self._fetchall("SELECT * FROM judge_scores ORDER BY id")
        return {int(r["story_id"]): r["scores"] for r in rows}

    def judge_for(self, story_id: int, judge_model: str | None = None) -> dict[str, Any] | None:
        if judge_model:
            return self._fetchone("SELECT * FROM judge_scores WHERE story_id = ? AND judge_model = ?",
                                  (story_id, judge_model))
        return self._fetchone("SELECT * FROM judge_scores WHERE story_id = ? ORDER BY id DESC LIMIT 1",
                              (story_id,))

    def stories_without_judge(self, judge_model: str, limit: int | None = None) -> list[dict[str, Any]]:
        sql = ("SELECT s.* FROM stories s WHERE NOT EXISTS (SELECT 1 FROM judge_scores j "
               "WHERE j.story_id = s.id AND j.judge_model = ?) ORDER BY s.id")
        params: list[Any] = [judge_model]
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return self._fetchall(sql, params)

    # --------------------------------------------------------------- datasets
    def label_matrix(self, labels: list[str]) -> tuple[list[dict[str, Any]], np.ndarray]:
        """All stories plus an (n_stories, n_labels) matrix with 1/0 for annotated
        stories and -1 for stories without an annotation (unlabelled)."""
        stories = self.list_stories()
        latest = self.latest_annotations()
        Y = np.full((len(stories), len(labels)), -1, dtype=int)
        index = {label: j for j, label in enumerate(labels)}
        for i, story in enumerate(stories):
            ann = latest.get(story["id"])
            if ann is None:
                continue
            known = ann.get("taxonomy") or labels
            for j, label in enumerate(labels):
                if label in known:
                    Y[i, j] = 0
            for label in ann["labels"]:
                if label in index:
                    Y[i, index[label]] = 1
        return stories, Y

    def next_unannotated(self, strategy: str = "uncertainty", *, require_prediction: bool = False,
                         exclude: Iterable[int] = (), model: str | None = None) -> dict[str, Any] | None:
        """Pick the next story to show a human. `uncertainty` prefers stories whose
        predicted scores sit closest to the decision boundary (active learning)."""
        exclude = set(exclude)
        candidates = self.list_stories(annotated=False, model=model,
                                       order="random" if strategy == "random" else "id")
        candidates = [s for s in candidates if s["id"] not in exclude]
        if not candidates:
            return None
        if strategy in ("uncertainty", "confident"):
            preds = self.latest_predictions()
            scored = []
            for s in candidates:
                p = preds.get(s["id"])
                if p is None:
                    continue
                thresholds = (p.get("evidence") or {}).get("thresholds", {})
                dists = [abs(v - thresholds.get(k, 0.5)) for k, v in p["scores"].items()]
                maxscore = max(p["scores"].values()) if p["scores"] else 0.0
                scored.append((min(dists) if dists else 1.0, -maxscore, s))
            if scored:
                if strategy == "uncertainty":
                    scored.sort(key=lambda t: (t[0], t[1], t[2]["id"]))
                else:
                    scored.sort(key=lambda t: (t[1], t[0], t[2]["id"]))
                return scored[0][2]
            if require_prediction:
                return None
        return candidates[0]

    # ------------------------------------------------------------------- misc
    def set_kv(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) "
                               "DO UPDATE SET value = excluded.value", (key, json.dumps(value)))
            self._conn.commit()

    def get_kv(self, key: str, default: Any = None) -> Any:
        row = self._fetchone("SELECT value FROM kv WHERE key = ?", (key,))
        return json.loads(row["value"]) if row else default

    def stats(self) -> dict[str, Any]:
        total = self.count_stories()
        annotated = self.count_stories(annotated=True)
        latest = self.latest_annotations()
        label_counts: dict[str, int] = {}
        for ann in latest.values():
            for label in ann["labels"]:
                label_counts[label] = label_counts.get(label, 0) + 1
        per_model = []
        for model in self.models():
            per_model.append({
                "model": model,
                "stories": self.count_stories(model=model),
                "annotated": self.count_stories(model=model, annotated=True),
            })
        predicted = self._fetchone("SELECT COUNT(DISTINCT story_id) AS n FROM predictions")
        judged = self._fetchone("SELECT COUNT(DISTINCT story_id) AS n FROM judge_scores")
        return {
            "stories": total,
            "annotated": annotated,
            "unannotated": total - annotated,
            "predicted": int(predicted["n"]) if predicted else 0,
            "judged": int(judged["n"]) if judged else 0,
            "label_counts": dict(sorted(label_counts.items())),
            "per_model": per_model,
            "no_bias": sum(1 for ann in latest.values() if not ann["labels"]),
        }

    # ------------------------------------------------------------- import/export
    def export_jsonl(self, path: str | Path) -> int:
        latest = self.latest_annotations()
        n = 0
        with open(path, "w", encoding="utf-8") as fh:
            for story in self.list_stories():
                record = dict(story)
                record["annotation"] = latest.get(story["id"])
                record["judge"] = self.judge_for(story["id"])
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                n += 1
        return n

    def import_jsonl(self, path: str | Path, *, keep_annotations: bool = True) -> tuple[int, int]:
        """Import stories (and their annotations) exported by export_jsonl, or any
        JSONL with at least a `text` field. Returns (stories_added, annotations_added)."""
        added = anns = 0
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                text = rec.get("text")
                if not text:
                    continue
                sid = self.add_story(text, rec.get("model", "import"),
                                     probe_id=rec.get("probe_id", ""),
                                     probe_category=rec.get("probe_category", ""),
                                     prompt=rec.get("prompt", ""),
                                     source=rec.get("source", "import"),
                                     meta=rec.get("meta") or {},
                                     created_at=rec.get("created_at"))
                if sid is None:
                    continue
                added += 1
                ann = rec.get("annotation")
                labels = rec.get("labels")
                if keep_annotations and ann:
                    self.add_annotation(sid, ann.get("labels", []), spans=ann.get("spans"),
                                        notes=ann.get("notes", ""), annotator=ann.get("annotator", ""),
                                        kind=ann.get("kind", "import"), taxonomy=ann.get("taxonomy"))
                    anns += 1
                elif keep_annotations and isinstance(labels, list):
                    self.add_annotation(sid, labels, notes=rec.get("notes", ""), kind="import")
                    anns += 1
        return added, anns
