import numpy as np

from biasprobe.features import FEATURE_NAMES, StereotypeFeaturizer, analyze, feature_vector, split_sentences


def test_split_sentences_keeps_offsets():
    text = "First one. Second one!  Third"
    sents = split_sentences(text)
    assert [s for _, _, s in sents] == ["First one.", "Second one!", "Third"]
    for start, end, s in sents:
        assert text[start:end] == s


def test_nearest_gender_attribution():
    a = analyze("Dr. Michael Harris, the surgeon, snapped at nurse Emily.")
    assert a.counts["male_x_male_job"] == 1
    assert a.counts["female_x_female_job"] == 1
    assert a.counts["male_x_female_job"] == 0
    assert a.counts["female_x_male_job"] == 0
    labels = {e.label for e in a.evidence}
    assert labels == {"gender_role"}


def test_counter_stereotype_is_not_evidence():
    a = analyze("Dr. Priya Raman, the surgeon, listened to nurse Daniel.")
    assert a.counts["female_x_male_job"] == 1
    assert a.counts["male_x_female_job"] == 1
    assert a.features["gender_role_ratio"] < 0.5
    assert not [e for e in a.evidence if e.label == "gender_role"]


def test_outgroup_negative_cooccurrence():
    a = analyze("The new Romanian neighbours were loud, and soon tools went missing. Later they baked bread.")
    assert a.counts["natl_x_neg"] == 1
    ev = [e for e in a.evidence if e.label == "xenophobia"]
    assert ev and "romanian" in ev[0].cues
    assert a.counts["natl_x_pos"] == 0
    assert a.features["outgroup_neg_ratio"] == 0.5
    b = analyze("The Romanian neighbours were welcoming and generous.")
    assert b.counts["natl_x_pos"] == 1 and b.features["outgroup_neg_ratio"] == 0.0


def test_other_pairs():
    assert analyze("Grandma Edith squinted at the smartphone, confused.").counts["old_x_stereo"] == 1
    assert analyze("Despite being confined to a wheelchair, Ben smiled.").counts["disab_x_stereo"] == 1
    assert analyze("The homeless man reeked of cheap liquor.").counts["poor_x_stereo"] == 1
    assert analyze("Her gay best friend squealed and dragged her shopping.").counts["sexuality_x_stereo"] == 1
    assert analyze("The fat clerk wheezed and reached for another doughnut.").counts["appearance_x_stereo"] == 1


def test_feature_vector_shape_and_empty_text():
    v = feature_vector("")
    assert v.shape == (len(FEATURE_NAMES),)
    assert np.all(np.isfinite(v))
    X = StereotypeFeaturizer().fit_transform(["", {"text": "She is a nurse."}])
    assert X.shape == (2, len(FEATURE_NAMES))
    assert list(StereotypeFeaturizer().get_feature_names_out()) == FEATURE_NAMES
