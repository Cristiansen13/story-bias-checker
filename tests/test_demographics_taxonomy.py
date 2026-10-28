import numpy as np

from biasprobe.demographics import analyze_demographics, summarize
from biasprobe.features import analyze
from biasprobe.storage import Storage
from biasprobe.taxonomy import LABEL_KEYS, LEGACY_LABEL_KEYS_V1


def test_new_label_lexicons_fire():
    cases = {
        "regional": "The villagers crossed themselves when the laptop lit up.",
        "profession": "The lawyer smiled the way lawyers do, calculating the fee.",
        "family_structure": "A single mother, the teacher noted, which explained the boy's manners.",
        "mental_health": "Since the breakdown, the team kept sharp objects away from Ivan's desk.",
        "political": "Gary, who voted the way his truck told him to, had never left the county.",
        "savior": "By August the villagers had learned to boil water, and Emma had learned what mattered.",
    }
    for label, text in cases.items():
        assert label in {e.label for e in analyze(text).evidence}, label


def test_demographics_extraction():
    d = analyze_demographics("Dr. Ayesha Karimi stared at the dish. Mr. Anselm Duarte leaned in. "
                             "Ayesha stared at him. Anselm shrugged; he had seen it before. She smiled.")
    names = {c.name: c for c in d.characters}
    assert set(names) == {"Ayesha", "Anselm"}  # surname not counted as a character
    assert names["Ayesha"].origin == "south_asian" and names["Ayesha"].gender == "female"
    assert names["Anselm"].gender == "male"
    assert d.protagonist.name == "Ayesha"
    assert analyze_demographics("Nobody here has a name.").protagonist is None


def test_demographics_summary():
    s = summarize([{"text": "Emily laughed. Emily ran. Wei watched her."},
                   {"text": "Kwame fixed the engine while James watched him."},
                   {"text": "No names at all."}])
    assert s["stories_with_named_characters"] == 2
    assert s["protagonist_gender"]["female"] == 0.5 and s["protagonist_gender"]["male"] == 0.5
    assert s["share_stories_with_non_western_name"] == 1.0
    assert abs(sum(s["protagonist_origin"].values()) - 1.0) < 1e-6
    assert s["distinct_names"] == 4 and len(s["top_names"]) == 4


def test_name_reuse():
    s = summarize([{"text": "Elias Thorne fixed the light. Elara watched Elias."},
                   {"text": "Captain Elias Thorne gripped the yoke while Maya prayed."},
                   {"text": "Sarah baked bread."}])
    assert s["top_names"][0] == {"name": "Elias", "share": round(2 / 3, 3)}
    assert {d["name"] for d in s["top_names"]} == {"Elias", "Elara", "Maya", "Sarah"}
    assert s["protagonist_gender"]["male"] == round(2 / 3, 3)


def test_word_like_names_only_count_mid_sentence():
    assert [c.name for c in analyze_demographics('"Can you hear me?" Sarah asked. Can it wait?').characters] == ["Sarah"]
    assert "Can" in [c.name for c in analyze_demographics("Sarah and Can left early.").characters]


def test_taxonomy_versioning_marks_new_labels_unknown(storage):
    sid = storage.add_story("A story.", "m")
    storage.add_annotation(sid, ["gender_role"], taxonomy=LEGACY_LABEL_KEYS_V1)
    sid2 = storage.add_story("Another story.", "m")
    storage.add_annotation(sid2, ["savior"])
    _, Y = storage.label_matrix(LABEL_KEYS)
    row1 = dict(zip(LABEL_KEYS, Y[0]))
    assert row1["gender_role"] == 1 and row1["age"] == 0 and row1["savior"] == -1
    row2 = dict(zip(LABEL_KEYS, Y[1]))
    assert row2["savior"] == 1 and row2["gender_role"] == 0
    assert storage.latest_annotation(sid2)["taxonomy"] == LABEL_KEYS


def test_migration_backfills_legacy_rows(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE stories (id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL UNIQUE,
          model TEXT NOT NULL, probe_id TEXT NOT NULL DEFAULT '', probe_category TEXT NOT NULL DEFAULT '',
          prompt TEXT NOT NULL DEFAULT '', text TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'llm',
          meta TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
        CREATE TABLE annotations (id INTEGER PRIMARY KEY AUTOINCREMENT, story_id INTEGER NOT NULL,
          annotator TEXT NOT NULL DEFAULT '', labels TEXT NOT NULL DEFAULT '[]', spans TEXT NOT NULL DEFAULT '[]',
          notes TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'manual', decisions TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL);
        INSERT INTO stories (uid, model, text, created_at) VALUES ('u', 'm', 'old story', 't');
        INSERT INTO annotations (story_id, labels, created_at) VALUES (1, '["age"]', 't');
    """)
    conn.commit(); conn.close()
    s = Storage(path)
    ann = s.latest_annotation(1)
    assert ann["taxonomy"] == LEGACY_LABEL_KEYS_V1
    _, Y = s.label_matrix(LABEL_KEYS)
    assert Y[0, LABEL_KEYS.index("age")] == 1 and Y[0, LABEL_KEYS.index("political")] == -1
    assert int((Y[0] == 0).sum()) == len(LEGACY_LABEL_KEYS_V1) - 1
