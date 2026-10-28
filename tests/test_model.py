import numpy as np
import pytest

from biasprobe.model import (BiasClassifier, ConstantEstimator, load_model, make_samples, predict_all,
                             save_model, train_from_storage)
from biasprobe.taxonomy import LABEL_KEYS


def test_cross_validate_requires_labels():
    clf = BiasClassifier(LABEL_KEYS)
    with pytest.raises(ValueError):
        clf.cross_validate([{"text": "a"}, {"text": "b"}], np.full((2, len(LABEL_KEYS)), -1))


def test_train_predict_explain_roundtrip(demo_storage, tmp_path):
    clf, cv = train_from_storage(demo_storage, n_splits=3, progress=None)
    assert cv is not None and cv.n_labeled == 46 and cv.n_unlabeled == 10
    assert 0.0 <= cv.label_accuracy <= 1.0
    assert isinstance(clf.estimators_["other"], ConstantEstimator)  # no positives for "other"
    assert not isinstance(clf.estimators_["gender_role"], ConstantEstimator)

    proba = clf.predict_proba([{"text": "Nurse Emily cried while Dr. Michael Harris, the surgeon, took charge."}])
    assert proba.shape == (1, len(LABEL_KEYS))
    assert np.all((proba >= 0) & (proba <= 1))

    ex = clf.explain({"text": "The Romanian immigrants were loud, suspicious and probably stealing tools."})
    assert set(ex) == set(LABEL_KEYS)
    assert any(e["label"] == "xenophobia" for e in ex["xenophobia"]["evidence"])
    assert ex["xenophobia"]["score"] > ex["disability"]["score"]
    for info in ex.values():
        assert {"score", "threshold", "predicted", "top_features", "evidence", "trained"} <= set(info)

    n = predict_all(demo_storage, clf)
    assert n == 56
    assert predict_all(demo_storage, clf, only_missing=True) == 0
    pred = demo_storage.latest_prediction(1)
    assert pred["model_version"] == clf.version and "thresholds" in pred["evidence"]

    path = save_model(clf, tmp_path / "models")
    loaded = load_model(tmp_path / "models")
    assert loaded is not None and loaded.version == clf.version
    assert (tmp_path / "models" / "metrics.json").exists()
    np.testing.assert_allclose(loaded.predict_proba([{"text": "x"}]), clf.predict_proba([{"text": "x"}]))


def test_judge_features_change_predictions(demo_storage):
    stories, Y = demo_storage.label_matrix(LABEL_KEYS)
    # fake judge that is perfectly informative on the labelled rows
    judge = {}
    for s, row in zip(stories, Y):
        if (row >= 0).any():
            judge[s["id"]] = {l: float(v == 1) for l, v in zip(LABEL_KEYS, row)}
    samples = make_samples(stories, judge)
    clf = BiasClassifier(LABEL_KEYS, use_judge=True, self_training=False).fit(samples, Y)
    assert any(name.startswith("judge_") for name in clf.feature_names_)
    hi = clf.predict_proba([{"text": "Plain story.", "judge": {"age": 1.0}}])[0][LABEL_KEYS.index("age")]
    lo = clf.predict_proba([{"text": "Plain story.", "judge": {"age": 0.0}}])[0][LABEL_KEYS.index("age")]
    assert hi > lo


def test_self_training_uses_unlabelled(demo_storage):
    stories, Y = demo_storage.label_matrix(LABEL_KEYS)
    samples = make_samples(stories)
    clf = BiasClassifier(LABEL_KEYS, self_training=True).fit(samples, Y)
    est = clf.estimators_["gender_role"]
    assert hasattr(est, "transduction_")  # SelfTrainingClassifier was used
    assert clf.n_unlabeled_ == 10
