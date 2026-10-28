import numpy as np

from biasprobe.taxonomy import LABEL_KEYS


def test_add_story_dedupes(storage):
    a = storage.add_story("Once upon a time.", "m", probe_id="p")
    b = storage.add_story("once  upon a TIME.", "m", probe_id="p")
    c = storage.add_story("Once upon a time.", "other", probe_id="p")
    assert a is not None and b is None and c is not None
    assert storage.count_stories() == 2
    assert storage.models() == ["m", "other"]


def test_annotations_and_label_matrix(storage):
    s1 = storage.add_story("A story.", "m")
    s2 = storage.add_story("Another story.", "m")
    storage.add_annotation(s1, ["gender_role"], annotator="x")
    storage.add_annotation(s1, ["gender_role", "age"], annotator="y")
    stories, Y = storage.label_matrix(LABEL_KEYS)
    assert [s["id"] for s in stories] == [s1, s2]
    row = dict(zip(LABEL_KEYS, Y[0]))
    assert row["gender_role"] == 1 and row["age"] == 1 and row["class"] == 0
    assert np.all(Y[1] == -1)
    assert storage.latest_annotation(s1)["annotator"] == "y"
    assert storage.count_stories(annotated=True) == 1
    assert storage.count_stories(label="age") == 1
    assert storage.count_stories(label="class") == 0
    assert storage.stats()["label_counts"] == {"age": 1, "gender_role": 1}


def test_next_unannotated_uses_uncertainty(storage):
    ids = [storage.add_story(f"story {i}", "m") for i in range(3)]
    storage.save_prediction(ids[0], "v1", {"age": 0.95}, {"thresholds": {"age": 0.5}})
    storage.save_prediction(ids[1], "v1", {"age": 0.52}, {"thresholds": {"age": 0.5}})
    storage.save_prediction(ids[2], "v1", {"age": 0.05}, {"thresholds": {"age": 0.5}})
    assert storage.next_unannotated("uncertainty")["id"] == ids[1]
    assert storage.next_unannotated("confident")["id"] == ids[0]
    assert storage.next_unannotated("oldest")["id"] == ids[0]
    storage.add_annotation(ids[1], [])
    assert storage.next_unannotated("uncertainty")["id"] == ids[0]
    assert storage.next_unannotated("uncertainty", exclude=[ids[0], ids[2]]) is None


def test_judge_upsert(storage):
    sid = storage.add_story("story", "m")
    storage.save_judge(sid, "j", {"age": 0.2}, {"age": ""}, "raw")
    storage.save_judge(sid, "j", {"age": 0.9}, {"age": "quote"}, "raw2")
    assert storage.judge_scores("j") == {sid: {"age": 0.9}}
    assert storage.stories_without_judge("j") == []
    assert len(storage.stories_without_judge("other")) == 1


def test_export_import_roundtrip(storage, tmp_path):
    sid = storage.add_story("A long story about things.", "m", probe_id="p", probe_category="c")
    storage.add_annotation(sid, ["class"], notes="n", annotator="me")
    path = tmp_path / "dump.jsonl"
    assert storage.export_jsonl(path) == 1
    from biasprobe.storage import Storage
    other = Storage(":memory:")
    assert other.import_jsonl(path) == (1, 1)
    st = other.list_stories()[0]
    assert st["probe_id"] == "p" and other.latest_annotation(st["id"])["labels"] == ["class"]
    # importing again is a no-op thanks to the uid
    assert other.import_jsonl(path) == (0, 0)


def test_export_keeps_every_round_and_ids(storage, tmp_path):
    storage.add_story("first story", "m")
    sid = storage.add_story("second story", "m")
    storage.add_annotation(sid, ["age"], annotator="round1", spans=[{"start": 0, "end": 6, "label": "age"}])
    storage.add_annotation(sid, ["class"], annotator="round2", kind="review", decisions={"class": "added"})
    storage.delete_story(1)  # leaves a gap: the story keeps id 2 only with keep_ids
    path = tmp_path / "dump.jsonl"
    storage.export_jsonl(path)
    from biasprobe.storage import Storage
    other = Storage(":memory:")
    assert other.import_jsonl(path, keep_ids=True) == (1, 2)
    rounds = other.annotations_for(sid)
    assert [a["annotator"] for a in rounds] == ["round1", "round2"]
    assert rounds[0]["spans"][0]["label"] == "age" and rounds[1]["decisions"] == {"class": "added"}
    assert other.latest_annotation(sid)["labels"] == ["class"]
