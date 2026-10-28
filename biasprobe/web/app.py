"""FastAPI web app: dashboard, annotation, review of predictions, ad-hoc prediction."""

from __future__ import annotations

import threading
import traceback
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from ..analysis import build_report
from ..config import AppConfig, load_config
from ..features import analyze
from ..model import BiasClassifier, load_model, predict_all, save_model, train_from_storage
from ..prompts import CATEGORIES, PROBE_BY_ID
from ..storage import Storage
from ..taxonomy import LABEL_BY_KEY, LABEL_KEYS, LABELS

HERE = Path(__file__).parent


class AnnotationIn(BaseModel):
    story_id: int
    labels: list[str] = Field(default_factory=list)
    spans: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""
    annotator: str = ""
    kind: str = "manual"
    decisions: dict[str, str] = Field(default_factory=dict)
    next_strategy: str = "uncertainty"
    model_filter: str | None = None


class PredictIn(BaseModel):
    text: str


class StoryIn(BaseModel):
    text: str
    model: str = "manual"
    labels: list[str] | None = None
    notes: str = ""
    annotator: str = ""


class AppState:
    def __init__(self, cfg: AppConfig, storage: Storage):
        self.cfg = cfg
        self.storage = storage
        self.clf: BiasClassifier | None = load_model(cfg.model_dir)
        self.train_lock = threading.Lock()
        self.train_status: dict[str, Any] = {"running": False, "last": None, "error": None, "log": []}

    def train(self, *, use_judge: bool | None = None, self_training: bool = True) -> None:
        if not self.train_lock.acquire(blocking=False):
            return
        self.train_status.update({"running": True, "error": None, "log": []})
        log = self.train_status["log"]
        try:
            clf, cv = train_from_storage(self.storage, use_judge=use_judge,
                                         self_training=self_training, progress=log.append)
            n = predict_all(self.storage, clf)
            save_model(clf, self.cfg.model_dir)
            self.clf = clf
            self.train_status["last"] = {"version": clf.version, "predicted": n,
                                         "metrics": cv.to_dict() if cv else None}
            log.append(f"trained {clf.version}; refreshed {n} predictions")
        except Exception as exc:  # noqa: BLE001
            self.train_status["error"] = f"{exc}"
            log.append(traceback.format_exc())
        finally:
            self.train_status["running"] = False
            self.train_lock.release()


def _label_payload() -> list[dict[str, Any]]:
    return [{"key": l.key, "name": l.name, "description": l.description, "examples": list(l.examples)}
            for l in LABELS]


def create_app(cfg: AppConfig | None = None, storage: Storage | None = None) -> FastAPI:
    cfg = cfg or load_config()
    storage = storage or Storage(cfg.db_path)
    state = AppState(cfg, storage)
    app = FastAPI(title="biasprobe")
    app.state.state = state
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    asset_version = str(int(max((HERE / "static" / f).stat().st_mtime for f in ("app.css", "app.js"))))
    templates.env.globals.update(LABELS=LABELS, LABEL_BY_KEY=LABEL_BY_KEY, CATEGORIES=CATEGORIES,
                                 asset_version=asset_version)

    def render(request: Request, name: str, **ctx) -> HTMLResponse:
        ctx.setdefault("model_version", state.clf.version if state.clf else None)
        ctx.setdefault("training", state.train_status["running"])
        return templates.TemplateResponse(request, name, ctx)

    def story_or_404(story_id: int) -> dict[str, Any]:
        story = storage.get_story(story_id)
        if story is None:
            raise HTTPException(404, f"story {story_id} not found")
        return story

    def prediction_payload(story: dict[str, Any]) -> dict[str, Any] | None:
        """Latest stored prediction, or a live one if the model is newer."""
        pred = storage.latest_prediction(story["id"])
        if state.clf and (pred is None or pred["model_version"] != state.clf.version):
            judge = storage.judge_for(story["id"])
            sample = {"id": story["id"], "text": story["text"],
                      "judge": judge["scores"] if judge else None}
            explanation = state.clf.explain(sample)
            scores = {k: v["score"] for k, v in explanation.items()}
            storage.save_prediction(story["id"], state.clf.version, scores,
                                    {"thresholds": state.clf.thresholds_, "labels": explanation})
            pred = storage.latest_prediction(story["id"])
        return pred

    # ------------------------------------------------------------------ pages
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        stats = storage.stats()
        metrics = state.clf.metrics_ if state.clf else None
        return render(request, "dashboard.html", stats=stats, metrics=metrics,
                      train_status=state.train_status, cfg=cfg, has_model=state.clf is not None,
                      models=storage.models())

    @app.get("/annotate")
    def annotate_next(strategy: str = "uncertainty", model: str | None = None, mode: str = "annotate"):
        story = storage.next_unannotated(strategy, model=model,
                                         require_prediction=(mode == "review"))
        if story is None:
            return RedirectResponse(f"/stories?annotated=0&done=1", status_code=303)
        return RedirectResponse(f"/annotate/{story['id']}?strategy={strategy}&mode={mode}"
                                + (f"&model={model}" if model else ""), status_code=303)

    @app.get("/review")
    def review_next(strategy: str = "confident", model: str | None = None):
        return annotate_next(strategy=strategy, model=model, mode="review")

    @app.get("/annotate/{story_id}", response_class=HTMLResponse)
    def annotate_page(request: Request, story_id: int, strategy: str = "uncertainty",
                      mode: str = "annotate", model: str | None = None):
        story = story_or_404(story_id)
        pred = prediction_payload(story)
        analysis = analyze(story["text"])
        existing = storage.latest_annotation(story_id)
        judge = storage.judge_for(story_id)
        probe = PROBE_BY_ID.get(story["probe_id"])
        return render(request, "annotate.html", story=story, prediction=pred, mode=mode,
                      strategy=strategy, model_filter=model, existing=existing, judge=judge,
                      lexical_evidence=[e.to_dict() for e in analysis.evidence], probe=probe,
                      labels_json=_label_payload(), models=storage.models())

    @app.get("/stories", response_class=HTMLResponse)
    def stories_page(request: Request, model: str | None = None, category: str | None = None,
                     label: str | None = None, annotated: str | None = None, q: str | None = None,
                     page: int = 1, done: int = 0):
        ann_filter = None if annotated in (None, "") else annotated == "1"
        per_page = 25
        filters = dict(model=model or None, category=category or None, label=label or None,
                       annotated=ann_filter, search=q or None)
        total = storage.count_stories(**filters)
        stories = storage.list_stories(limit=per_page, offset=(page - 1) * per_page, order="newest", **filters)
        latest = storage.latest_annotations()
        preds = storage.latest_predictions()
        rows = []
        for s in stories:
            ann = latest.get(s["id"])
            p = preds.get(s["id"])
            flagged = []
            if p:
                thr = (p.get("evidence") or {}).get("thresholds", {})
                flagged = [k for k, v in p["scores"].items() if v >= thr.get(k, 0.5)]
            rows.append({"story": s, "annotation": ann, "flagged": flagged,
                         "snippet": s["text"][:220] + ("…" if len(s["text"]) > 220 else "")})
        return render(request, "stories.html", rows=rows, total=total, page=page, per_page=per_page,
                      filters={"model": model or "", "category": category or "", "label": label or "",
                               "annotated": annotated or "", "q": q or ""},
                      models=storage.models(), done=done)

    @app.get("/story/{story_id}", response_class=HTMLResponse)
    def story_page(request: Request, story_id: int):
        story = story_or_404(story_id)
        pred = prediction_payload(story)
        return render(request, "story.html", story=story, prediction=pred,
                      annotations=storage.annotations_for(story_id), judge=storage.judge_for(story_id),
                      probe=PROBE_BY_ID.get(story["probe_id"]), labels_json=_label_payload())

    @app.get("/predict", response_class=HTMLResponse)
    def predict_page(request: Request):
        return render(request, "predict.html", has_model=state.clf is not None,
                      labels_json=_label_payload(), models=storage.models())

    @app.get("/report", response_class=HTMLResponse)
    def report_page(request: Request):
        report = build_report(storage)
        return render(request, "report.html", report=report)

    # -------------------------------------------------------------------- API
    @app.get("/api/stats")
    def api_stats():
        return storage.stats()

    @app.get("/api/labels")
    def api_labels():
        return _label_payload()

    @app.get("/api/story/{story_id}")
    def api_story(story_id: int):
        story = story_or_404(story_id)
        return {"story": story, "prediction": prediction_payload(story),
                "annotations": storage.annotations_for(story_id), "judge": storage.judge_for(story_id)}

    @app.post("/api/annotations")
    def api_add_annotation(payload: AnnotationIn):
        unknown = set(payload.labels) - set(LABEL_KEYS)
        if unknown:
            raise HTTPException(400, f"unknown labels: {sorted(unknown)}")
        story_or_404(payload.story_id)
        ann_id = storage.add_annotation(payload.story_id, payload.labels, spans=payload.spans,
                                        notes=payload.notes, annotator=payload.annotator,
                                        kind=payload.kind, decisions=payload.decisions)
        nxt = storage.next_unannotated(payload.next_strategy, model=payload.model_filter,
                                       require_prediction=(payload.kind == "review"))
        return {"annotation_id": ann_id, "next_story_id": nxt["id"] if nxt else None,
                "stats": storage.stats()}

    @app.delete("/api/annotations/{annotation_id}")
    def api_delete_annotation(annotation_id: int):
        storage.delete_annotation(annotation_id)
        return {"deleted": annotation_id}

    @app.post("/api/predict")
    def api_predict(payload: PredictIn):
        text = payload.text.strip()
        if not text:
            raise HTTPException(400, "empty text")
        analysis = analyze(text)
        if state.clf is None:
            return {"model_version": None, "labels": None,
                    "lexical_evidence": [e.to_dict() for e in analysis.evidence],
                    "message": "no trained model yet: showing lexical evidence only"}
        explanation = state.clf.explain({"text": text})
        return {"model_version": state.clf.version, "labels": explanation,
                "flagged": [k for k, v in explanation.items() if v["predicted"]],
                "lexical_evidence": [e.to_dict() for e in analysis.evidence]}

    @app.post("/api/stories")
    def api_add_story(payload: StoryIn):
        text = payload.text.strip()
        if not text:
            raise HTTPException(400, "empty text")
        sid = storage.add_story(text, payload.model or "manual", source="manual")
        if sid is None:
            existing = storage._fetchone("SELECT id FROM stories WHERE uid = ?",
                                         (Storage.story_uid(payload.model or "manual", "", text),))
            sid = int(existing["id"]) if existing else None
            if sid is None:
                raise HTTPException(409, "duplicate story")
        ann_id = None
        if payload.labels is not None:
            unknown = set(payload.labels) - set(LABEL_KEYS)
            if unknown:
                raise HTTPException(400, f"unknown labels: {sorted(unknown)}")
            ann_id = storage.add_annotation(sid, payload.labels, notes=payload.notes,
                                            annotator=payload.annotator, kind="review")
        return {"story_id": sid, "annotation_id": ann_id}

    @app.post("/api/train")
    def api_train(use_judge: bool | None = Query(default=None), self_training: bool = True):
        if state.train_status["running"]:
            return JSONResponse({"started": False, "reason": "training already running"}, status_code=409)
        if storage.count_stories(annotated=True) == 0:
            raise HTTPException(400, "annotate at least a few stories before training")
        thread = threading.Thread(target=state.train, kwargs={"use_judge": use_judge,
                                                              "self_training": self_training}, daemon=True)
        thread.start()
        return {"started": True}

    @app.get("/api/train/status")
    def api_train_status():
        return state.train_status

    @app.get("/api/report")
    def api_report():
        return build_report(storage)

    @app.get("/api/next")
    def api_next(strategy: str = "uncertainty", model: str | None = None, review: bool = False):
        story = storage.next_unannotated(strategy, model=model, require_prediction=review)
        return {"story_id": story["id"] if story else None}

    return app
