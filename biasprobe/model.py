"""Semi-supervised multi-label bias classifier with explanations.

One linear model per label on top of shared features (word + character
TF-IDF, stereotype co-occurrence features, optional LLM-judge scores).
Unlabelled stories take part through self-training (pseudo-labelling) and
through the TF-IDF vocabulary. Decision thresholds are tuned per label on
out-of-fold predictions so that the reported accuracy is honest.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import MaxAbsScaler
from sklearn.semi_supervised import SelfTrainingClassifier

from .features import FEATURE_NAMES, JudgeFeaturizer, StereotypeFeaturizer, TextSelector, analyze
from .storage import Storage
from .taxonomy import LABEL_KEYS

MODEL_FILENAME = "latest.joblib"
METRICS_FILENAME = "metrics.json"


class ConstantEstimator:
    """Stand-in for labels with too few examples: predicts the label prior."""

    def __init__(self, p: float):
        self.p = float(p)
        self.classes_ = np.array([0, 1])

    def fit(self, X, y=None):
        return self

    def predict_proba(self, X):
        n = X.shape[0]
        return np.column_stack([np.full(n, 1.0 - self.p), np.full(n, self.p)])


@dataclass
class LabelMetrics:
    label: str
    positives: int
    negatives: int
    precision: float
    recall: float
    f1: float
    accuracy: float
    threshold: float
    trained: bool


@dataclass
class CVResult:
    n_labeled: int
    n_unlabeled: int
    n_splits: int
    per_label: list[LabelMetrics]
    macro_f1: float
    micro_f1: float
    label_accuracy: float
    exact_match: float
    any_bias_accuracy: float
    thresholds: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def summary(self) -> str:
        lines = [f"labeled={self.n_labeled} unlabeled={self.n_unlabeled} folds={self.n_splits}",
                 f"macro-F1={self.macro_f1:.3f} micro-F1={self.micro_f1:.3f} "
                 f"label-accuracy={self.label_accuracy:.3f} exact-match={self.exact_match:.3f} "
                 f"bias-vs-none accuracy={self.any_bias_accuracy:.3f}",
                 f"{'label':<16}{'pos':>5}{'neg':>5}{'P':>7}{'R':>7}{'F1':>7}{'acc':>7}{'thr':>6}"]
        for m in self.per_label:
            flag = "" if m.trained else "  (too few examples)"
            lines.append(f"{m.label:<16}{m.positives:>5}{m.negatives:>5}{m.precision:>7.2f}"
                         f"{m.recall:>7.2f}{m.f1:>7.2f}{m.accuracy:>7.2f}{m.threshold:>6.2f}{flag}")
        return "\n".join(lines)


def _prf(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float, float]:
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def _best_threshold(y_true: np.ndarray, proba: np.ndarray) -> float:
    best_thr, best_f1 = 0.5, -1.0
    for thr in np.linspace(0.15, 0.85, 29):
        _, _, f1 = _prf(y_true, (proba >= thr).astype(int))
        # prefer the threshold nearest 0.5 on ties
        if f1 > best_f1 + 1e-9 or (abs(f1 - best_f1) <= 1e-9 and abs(thr - 0.5) < abs(best_thr - 0.5)):
            best_thr, best_f1 = float(thr), f1
    return round(best_thr, 3)


class BiasClassifier:
    def __init__(self, labels: list[str] | None = None, *, use_judge: bool = False,
                 self_training: bool = True, C: float = 1.0, st_threshold: float = 0.9,
                 min_df: int = 2, stereo_weight: float = 3.0, judge_weight: float = 3.0,
                 char_ngrams: bool = False, heuristic_weight: float = 5.0,
                 random_state: int = 0):
        self.labels = list(labels or LABEL_KEYS)
        self.use_judge = use_judge
        self.self_training = self_training
        self.C = C
        self.st_threshold = st_threshold
        self.min_df = min_df
        self.stereo_weight = stereo_weight
        self.judge_weight = judge_weight
        self.char_ngrams = char_ngrams
        # The lexical heuristic acts like this many pseudo-examples per label: with
        # few human positives it dominates, with many it fades out.
        self.heuristic_weight = heuristic_weight
        self.random_state = random_state
        self.features_: FeatureUnion | None = None
        self.feature_names_: list[str] = []
        self.estimators_: dict[str, Any] = {}
        self.priors_: dict[str, float] = {}
        self.positives_: dict[str, int] = {}
        self.thresholds_: dict[str, float] = {l: 0.5 for l in self.labels}
        self.trained_at: str | None = None
        self.n_labeled_: int = 0
        self.n_unlabeled_: int = 0
        self.metrics_: dict[str, Any] | None = None

    # ----------------------------------------------------------------- params
    def get_params(self) -> dict[str, Any]:
        return {"labels": self.labels, "use_judge": self.use_judge, "self_training": self.self_training,
                "C": self.C, "st_threshold": self.st_threshold, "min_df": self.min_df,
                "stereo_weight": self.stereo_weight, "judge_weight": self.judge_weight,
                "char_ngrams": self.char_ngrams, "heuristic_weight": self.heuristic_weight,
                "random_state": self.random_state}

    def clone(self) -> "BiasClassifier":
        return BiasClassifier(**self.get_params())

    @property
    def version(self) -> str:
        stamp = (self.trained_at or "untrained").replace("-", "").replace(":", "").replace("T", "")[:14]
        return f"v{stamp}-n{self.n_labeled_}"

    # --------------------------------------------------------------- features
    def _make_features(self) -> FeatureUnion:
        parts = [
            ("word", Pipeline([
                ("text", TextSelector()),
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=self.min_df, sublinear_tf=True,
                                          max_features=40000, lowercase=True)),
            ])),
            ("stereo", Pipeline([("feat", StereotypeFeaturizer()), ("scale", MaxAbsScaler())])),
        ]
        if self.char_ngrams:
            parts.insert(1, ("char", Pipeline([
                ("text", TextSelector()),
                ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=self.min_df,
                                          sublinear_tf=True, max_features=40000)),
            ])))
        weights = {"stereo": self.stereo_weight}
        if self.use_judge:
            parts.append(("judge", JudgeFeaturizer(self.labels)))
            weights["judge"] = self.judge_weight
        return FeatureUnion(parts, transformer_weights=weights)

    def _collect_feature_names(self) -> list[str]:
        assert self.features_ is not None
        names: list[str] = []
        for name, trans in self.features_.transformer_list:
            if name in ("word", "char"):
                names += [f"{name}:{t}" for t in trans.named_steps["tfidf"].get_feature_names_out()]
            elif name == "stereo":
                names += [f"stereo:{t}" for t in FEATURE_NAMES]
            elif name == "judge":
                names += [f"{t}" for t in trans.get_feature_names_out()]
        return names

    def _transform(self, samples: list[Any]) -> sparse.csr_matrix:
        assert self.features_ is not None, "classifier is not trained"
        X = self.features_.transform(samples)
        return sparse.csr_matrix(X)

    # -------------------------------------------------------------------- fit
    def fit(self, samples: list[Any], Y: np.ndarray) -> "BiasClassifier":
        Y = np.asarray(Y, dtype=int)
        if Y.ndim != 2 or Y.shape[1] != len(self.labels):
            raise ValueError(f"Y must have shape (n, {len(self.labels)})")
        if len(samples) != Y.shape[0]:
            raise ValueError("samples and Y have different lengths")
        self.features_ = self._make_features().fit(samples)
        X = self._transform(samples)
        self.feature_names_ = self._collect_feature_names()
        labeled_rows = (Y >= 0).any(axis=1)
        self.n_labeled_ = int(labeled_rows.sum())
        self.n_unlabeled_ = int((~labeled_rows).sum())
        self.estimators_ = {}
        for j, label in enumerate(self.labels):
            y = Y[:, j]
            labeled = y >= 0
            pos, neg = int((y == 1).sum()), int((y == 0).sum())
            prior = (pos + 0.5) / (pos + neg + 1.0)
            self.priors_[label] = prior
            self.positives_[label] = pos
            if pos < 2 or neg < 2:
                self.estimators_[label] = ConstantEstimator(prior)
                continue
            base = LogisticRegression(class_weight="balanced", C=self.C, max_iter=5000,
                                      random_state=self.random_state)
            if self.self_training and (~labeled).any():
                est = SelfTrainingClassifier(base, threshold=self.st_threshold, max_iter=10)
                est.fit(X, y)
            else:
                est = base.fit(X[labeled], y[labeled])
            self.estimators_[label] = est
        self.trained_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        return self

    # ---------------------------------------------------------------- predict
    def heuristic_proba(self, samples: list[Any]) -> np.ndarray:
        """Lexical prior: probability from the number of evidence sentences the
        stereotype analyzer finds for each label (0 -> 0.05, 1 -> 0.41, 2 -> 0.63, 3 -> 0.76)."""
        out = np.zeros((len(samples), len(self.labels)))
        for i, sample in enumerate(samples):
            text = sample["text"] if isinstance(sample, dict) else str(sample)
            counts: dict[str, int] = {}
            for e in analyze(text).evidence:
                counts[e.label] = counts.get(e.label, 0) + 1
            for j, label in enumerate(self.labels):
                out[i, j] = 0.05 + 0.9 * (1.0 - 0.6 ** counts.get(label, 0))
        return out

    def heuristic_blend(self, label: str) -> float:
        """Share of the final score that comes from the lexical heuristic."""
        if self.heuristic_weight <= 0:
            return 0.0
        pos = self.positives_.get(label, 0)
        return float(self.heuristic_weight / (self.heuristic_weight + pos))

    def model_proba(self, samples: list[Any]) -> np.ndarray:
        X = self._transform(samples)
        out = np.zeros((X.shape[0], len(self.labels)))
        for j, label in enumerate(self.labels):
            est = self.estimators_[label]
            proba = est.predict_proba(X)
            classes = list(getattr(est, "classes_", [0, 1]))
            col = classes.index(1) if 1 in classes else proba.shape[1] - 1
            out[:, j] = proba[:, col]
        return out

    def predict_proba(self, samples: list[Any]) -> np.ndarray:
        model = self.model_proba(samples)
        if self.heuristic_weight <= 0:
            return model
        heur = self.heuristic_proba(samples)
        w = np.array([self.heuristic_blend(l) for l in self.labels])
        return (1.0 - w) * model + w * heur

    def predict(self, samples: list[Any]) -> np.ndarray:
        proba = self.predict_proba(samples)
        thr = np.array([self.thresholds_.get(l, 0.5) for l in self.labels])
        return (proba >= thr).astype(int)

    def scores_dict(self, sample: Any) -> dict[str, float]:
        proba = self.predict_proba([sample])[0]
        return {label: round(float(p), 4) for label, p in zip(self.labels, proba)}

    # ---------------------------------------------------------------- explain
    def _coef(self, label: str) -> np.ndarray | None:
        est = self.estimators_[label]
        inner = getattr(est, "estimator_", est)
        coef = getattr(inner, "coef_", None)
        return None if coef is None else np.asarray(coef).ravel()

    def explain(self, sample: Any, top_k: int = 8) -> dict[str, dict[str, Any]]:
        """Per-label score, decision, top contributing features and evidence sentences."""
        X = self._transform([sample])
        proba = self.predict_proba([sample])[0]
        model_p = self.model_proba([sample])[0]
        heur_p = self.heuristic_proba([sample])[0]
        text = sample["text"] if isinstance(sample, dict) else str(sample)
        analysis = analyze(text)
        xs = X.tocoo()
        result: dict[str, dict[str, Any]] = {}
        for j, label in enumerate(self.labels):
            coef = self._coef(label)
            top: list[dict[str, Any]] = []
            if coef is not None and xs.nnz:
                contrib = xs.data * coef[xs.col]
                order = np.argsort(-contrib)
                for idx in order[:top_k]:
                    if contrib[idx] <= 0:
                        break
                    name = self.feature_names_[xs.col[idx]] if xs.col[idx] < len(self.feature_names_) else str(xs.col[idx])
                    top.append({"feature": name, "weight": round(float(contrib[idx]), 4)})
            thr = self.thresholds_.get(label, 0.5)
            evidence = [e.to_dict() for e in analysis.evidence if e.label == label]
            result[label] = {
                "score": round(float(proba[j]), 4),
                "model_score": round(float(model_p[j]), 4),
                "heuristic_score": round(float(heur_p[j]), 4),
                "heuristic_share": round(self.heuristic_blend(label), 3),
                "threshold": thr,
                "predicted": bool(proba[j] >= thr),
                "top_features": top,
                "evidence": evidence,
                "trained": not isinstance(self.estimators_[label], ConstantEstimator),
            }
        return result

    # ------------------------------------------------------------ evaluation
    def cross_validate(self, samples: list[Any], Y: np.ndarray, *, n_splits: int = 5,
                       tune_thresholds: bool = True, seed: int = 0) -> CVResult:
        Y = np.asarray(Y, dtype=int)
        labeled_idx = np.where((Y >= 0).any(axis=1))[0]
        unlabeled_idx = np.where(~(Y >= 0).any(axis=1))[0]
        n = len(labeled_idx)
        if n < 4:
            raise ValueError(f"need at least 4 labelled stories for cross-validation, have {n}")
        k = max(2, min(n_splits, n))
        oof = np.zeros((n, len(self.labels)))
        kf = KFold(n_splits=k, shuffle=True, random_state=seed)
        for train_pos, test_pos in kf.split(labeled_idx):
            train_rows = np.concatenate([labeled_idx[train_pos], unlabeled_idx]).astype(int)
            test_rows = labeled_idx[test_pos]
            clf = self.clone()
            clf.fit([samples[i] for i in train_rows], Y[train_rows])
            oof[test_pos] = clf.predict_proba([samples[i] for i in test_rows])
        Y_l = Y[labeled_idx]
        known = Y_l >= 0  # a story may be labelled for some labels and unknown for newer ones
        per_label: list[LabelMetrics] = []
        thresholds: dict[str, float] = {}
        preds = np.zeros_like(Y_l)
        for j, label in enumerate(self.labels):
            mask = known[:, j]
            y = Y_l[mask, j]
            scores = oof[mask, j]
            pos, neg = int((y == 1).sum()), int((y == 0).sum())
            trained = pos >= 2 and neg >= 2
            thr = _best_threshold(y, scores) if (tune_thresholds and pos >= 5 and trained) else 0.5
            thresholds[label] = thr
            preds[:, j] = (oof[:, j] >= thr).astype(int)
            y_pred = preds[mask, j]
            p, r, f1 = _prf(y, y_pred)
            acc = float((y_pred == y).mean()) if len(y) else 0.0
            per_label.append(LabelMetrics(label, pos, neg, round(p, 4), round(r, 4), round(f1, 4),
                                          round(acc, 4), thr, trained))
        tp = int(((Y_l == 1) & (preds == 1)).sum())
        fp = int(((Y_l == 0) & (preds == 1)).sum())
        fn = int(((Y_l == 1) & (preds == 0)).sum())
        micro_p = tp / (tp + fp) if tp + fp else 0.0
        micro_r = tp / (tp + fn) if tp + fn else 0.0
        micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if micro_p + micro_r else 0.0
        present = [m for m in per_label if m.positives > 0]
        macro_f1 = float(np.mean([m.f1 for m in present])) if present else 0.0
        any_true = (Y_l == 1).any(axis=1)
        any_pred = ((preds == 1) & known).any(axis=1)
        correct = (preds == Y_l) | ~known
        result = CVResult(
            n_labeled=n, n_unlabeled=int(len(unlabeled_idx)), n_splits=k, per_label=per_label,
            macro_f1=round(macro_f1, 4), micro_f1=round(micro_f1, 4),
            label_accuracy=round(float((preds == Y_l)[known].mean()), 4),
            exact_match=round(float(correct.all(axis=1).mean()), 4),
            any_bias_accuracy=round(float((any_true == any_pred).mean()), 4),
            thresholds=thresholds,
        )
        return result

    # ------------------------------------------------------------ persistence
    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path

    @staticmethod
    def load(path: str | Path) -> "BiasClassifier":
        return joblib.load(path)


# ---------------------------------------------------------------------------
# Convenience functions working against Storage
# ---------------------------------------------------------------------------

def make_samples(stories: list[dict[str, Any]], judge: dict[int, dict[str, float]] | None = None) -> list[dict[str, Any]]:
    judge = judge or {}
    return [{"id": s["id"], "text": s["text"], "judge": judge.get(s["id"])} for s in stories]


def train_from_storage(storage: Storage, *, labels: list[str] | None = None,
                       use_judge: bool | None = None, judge_model: str | None = None,
                       n_splits: int = 5, self_training: bool = True,
                       progress=print, **params) -> tuple[BiasClassifier, CVResult | None]:
    labels = list(labels or LABEL_KEYS)
    stories, Y = storage.label_matrix(labels)
    judge_scores = storage.judge_scores(judge_model)
    if use_judge is None:
        use_judge = bool(judge_scores)
    samples = make_samples(stories, judge_scores if use_judge else None)
    clf = BiasClassifier(labels, use_judge=use_judge, self_training=self_training, **params)
    n_labeled = int((Y >= 0).any(axis=1).sum())
    if n_labeled == 0:
        raise ValueError("no annotated stories yet; annotate some stories first")
    cv: CVResult | None = None
    if n_labeled >= 4:
        if progress:
            progress(f"cross-validating on {n_labeled} labelled stories "
                     f"(+{len(samples) - n_labeled} unlabelled, judge={'on' if use_judge else 'off'})...")
        cv = clf.cross_validate(samples, Y, n_splits=n_splits)
        clf.thresholds_ = dict(cv.thresholds)
        if progress:
            progress(cv.summary())
    elif progress:
        progress(f"only {n_labeled} labelled stories: skipping cross-validation")
    clf.fit(samples, Y)
    clf.metrics_ = cv.to_dict() if cv else None
    return clf, cv


def predict_all(storage: Storage, clf: BiasClassifier, *, judge_model: str | None = None,
                only_missing: bool = False) -> int:
    """Store a fresh prediction (scores + explanations) for every story."""
    stories = storage.list_stories()
    judge_scores = storage.judge_scores(judge_model) if clf.use_judge else {}
    existing = storage.latest_predictions() if only_missing else {}
    n = 0
    for story in stories:
        prev = existing.get(story["id"])
        if prev and prev["model_version"] == clf.version:
            continue
        sample = {"id": story["id"], "text": story["text"], "judge": judge_scores.get(story["id"])}
        explanation = clf.explain(sample)
        scores = {label: info["score"] for label, info in explanation.items()}
        evidence = {"thresholds": clf.thresholds_, "labels": explanation}
        storage.save_prediction(story["id"], clf.version, scores, evidence)
        n += 1
    return n


def save_model(clf: BiasClassifier, model_dir: str | Path) -> Path:
    model_dir = Path(model_dir)
    path = clf.save(model_dir / MODEL_FILENAME)
    if clf.metrics_ is not None:
        with open(model_dir / METRICS_FILENAME, "w", encoding="utf-8") as fh:
            json.dump({"version": clf.version, "trained_at": clf.trained_at, **clf.metrics_}, fh, indent=2)
    return path


def load_model(model_dir: str | Path) -> BiasClassifier | None:
    path = Path(model_dir) / MODEL_FILENAME
    if not path.exists():
        return None
    return BiasClassifier.load(path)
