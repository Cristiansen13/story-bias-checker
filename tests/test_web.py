import time

import pytest
from fastapi.testclient import TestClient

from biasprobe.model import predict_all, save_model, train_from_storage
from biasprobe.web.app import create_app


@pytest.fixture
def client(cfg, demo_storage):
    app = create_app(cfg, demo_storage)
    return TestClient(app)


def test_pages_render_without_model(client):
    for url in ["/", "/stories", "/stories?model=demo-model-a&annotated=1&label=gender_role",
                "/predict", "/report", "/story/1"]:
        r = client.get(url)
        assert r.status_code == 200, url
    assert client.get("/story/99999").status_code == 404
    r = client.get("/annotate", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/annotate/")
    # review needs predictions; none yet -> redirected to the stories list
    r = client.get("/review", follow_redirects=False)
    assert r.headers["location"].startswith("/stories")


def test_predict_without_model_returns_lexical_only(client):
    r = client.post("/api/predict", json={"text": "Grandma Edith squinted at the smartphone, confused."})
    data = r.json()
    assert data["labels"] is None and data["lexical_evidence"][0]["label"] == "age"
    assert client.post("/api/predict", json={"text": "  "}).status_code == 400


def test_annotation_flow(client, demo_storage):
    nxt = client.get("/api/next?strategy=oldest").json()["story_id"]
    assert nxt is not None
    r = client.post("/api/annotations", json={"story_id": nxt, "labels": ["age", "class"],
                                               "spans": [{"start": 0, "end": 5, "label": "age"}],
                                               "notes": "n", "annotator": "t", "next_strategy": "oldest"})
    data = r.json()
    assert data["annotation_id"] and data["next_story_id"] != nxt
    ann = demo_storage.latest_annotation(nxt)
    assert ann["labels"] == ["age", "class"] and ann["spans"][0]["label"] == "age"
    assert client.post("/api/annotations", json={"story_id": nxt, "labels": ["nope"]}).status_code == 400
    assert client.get(f"/annotate/{nxt}").status_code == 200


def test_train_review_and_confirm_flow(client, demo_storage, cfg):
    r = client.post("/api/train")
    assert r.json()["started"] is True
    for _ in range(600):
        st = client.get("/api/train/status").json()
        if not st["running"]:
            break
        time.sleep(0.2)
    assert st["error"] is None, st
    assert st["last"]["predicted"] == 56
    assert (cfg.model_dir / "latest.joblib").exists()

    r = client.get("/review", follow_redirects=False)
    assert r.headers["location"].startswith("/annotate/")
    sid = int(r.headers["location"].split("/")[2].split("?")[0])
    page = client.get(r.headers["location"])
    assert page.status_code == 200 and "Review the model" in page.text

    r = client.post("/api/annotations", json={"story_id": sid, "labels": ["gender_role"], "kind": "review",
                                               "decisions": {"gender_role": "accepted", "age": "rejected"},
                                               "next_strategy": "confident"})
    assert r.status_code == 200
    assert demo_storage.latest_annotation(sid)["decisions"]["age"] == "rejected"

    pred = client.post("/api/predict", json={"text": "Nurse Emily wept while Dr. Harris, the surgeon, took charge."}).json()
    assert pred["model_version"] and "gender_role" in pred["labels"]
    r = client.post("/api/stories", json={"text": "A brand new story about a lighthouse keeper named Maren.",
                                          "model": "gpt-test", "labels": [], "annotator": "me"})
    sid2 = r.json()["story_id"]
    assert demo_storage.get_story(sid2)["model"] == "gpt-test"
    assert demo_storage.latest_annotation(sid2)["labels"] == []
    # posting the same text again returns the same story id rather than failing
    assert client.post("/api/stories", json={"text": "A brand new story about a lighthouse keeper named Maren.",
                                             "model": "gpt-test"}).json()["story_id"] == sid2
    assert client.get("/").status_code == 200 and client.get("/report").status_code == 200
    assert client.get(f"/story/{sid2}").status_code == 200
