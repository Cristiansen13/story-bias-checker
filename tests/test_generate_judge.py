import json

from biasprobe.generate import clean_story, export_prompts, import_generations, plan_jobs, run_generation
from biasprobe.judge import build_judge_prompt, judge_missing, parse_judge_output
from biasprobe.llm_client import LLMClient
from biasprobe.prompts import PROBES, select_probes
from biasprobe.taxonomy import LABEL_KEYS

from conftest import FakeServer


def test_clean_story():
    assert clean_story("**The Night Shift**\n\nOnce upon a time.") == "Once upon a time."
    assert clean_story("Title: Storm\nThe sea rose.") == "The sea rose."
    assert clean_story('"Quoted story."') == "Quoted story."
    assert clean_story("```\nfenced\n```") == "fenced"
    assert clean_story("A single line without title.") == "A single line without title."
    assert clean_story("<think>\nplan\n</think>\n\nThe sea rose.") == "The sea rose."
    assert clean_story("plan only closed</think>The sea rose.") == "The sea rose."
    assert clean_story("<|channel>thought\nhmm<channel|>The sea rose.") == "The sea rose."


def test_export_and_import_generations(storage, tmp_path):
    probes = select_probes(ids=["occ_surgeon_nurse", "neutral_robot"])
    prompts = tmp_path / "prompts.jsonl"
    assert export_prompts(prompts, probes, words=200) == 2
    rows = [json.loads(line) for line in prompts.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["probe_id"] == "occ_surgeon_nurse" and "about 200 words" in rows[0]["prompt"]
    assert rows[0]["system"] and rows[0]["targets"] == ["gender_role"]

    story = "Dr. Ana Popescu argued with nurse Mihai about the patient. " * 4
    out = tmp_path / "stories-m.jsonl"
    recs = [dict(model="m", probe_id=r["probe_id"], probe_category=r["probe_category"], prompt=r["prompt"],
                 sample_index=0, text=f"<think>\n\n</think>\n\n{story} {r['probe_id']}", new_tokens=80,
                 finished=True, params={"temperature": 0.9}) for r in rows]
    recs.append(dict(recs[0], sample_index=1, text="Too short."))
    out.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    summary = import_generations(storage, out, progress=None)
    assert (summary.generated, summary.failed, summary.duplicates) == (2, 1, 0)
    s = storage.list_stories(model="m")[0]
    assert s["source"] == "llm" and not s["text"].startswith("<think>")
    assert s["meta"]["targets"] and s["meta"]["usage"]["completion_tokens"] == 80
    again = import_generations(storage, out, progress=None)
    assert again.generated == 0 and again.duplicates == 2 and storage.count_stories() == 2


def test_select_probes_and_prompt_text():
    occ = select_probes(["occupation"])
    assert occ and all(p.category == "occupation" for p in occ)
    assert "about 250 words" in PROBES[0].build(250)
    assert len({p.id for p in PROBES}) == len(PROBES)


def test_plan_jobs_is_resumable(cfg, storage):
    probes = select_probes(ids=["occ_surgeon_nurse", "neutral_robot"])
    jobs, skipped = plan_jobs(cfg, storage, probes=probes, samples=2)
    assert len(jobs) == 2 * 2 * 2 and skipped == 0
    storage.add_story("existing text " * 10, "model-a", probe_id="occ_surgeon_nurse")
    jobs, skipped = plan_jobs(cfg, storage, probes=probes, samples=2)
    assert len(jobs) == 7 and skipped == 1


def test_run_generation_stores_stories(cfg, storage):
    fake = FakeServer(reply=lambda body: "**Title**\n" + body["messages"][-1]["content"][-40:] + " " + "lorem " * 60)
    client = LLMClient(cfg.server, transport=fake.transport(), sleep=lambda s: None)
    probes = select_probes(ids=["occ_surgeon_nurse", "natl_train"])
    summary = run_generation(cfg, storage, probes=probes, samples=1, client=client, workers=2, progress=None)
    assert summary.generated == 4 and summary.failed == 0
    stories = storage.list_stories()
    assert {s["model"] for s in stories} == {"model-a", "model-b"}
    assert all(s["probe_category"] in ("occupation", "nationality") for s in stories)
    assert all(not s["text"].startswith("**") for s in stories)
    assert stories[0]["meta"]["targets"]
    # second run: nothing left to do
    again = run_generation(cfg, storage, probes=probes, samples=1, client=client, progress=None)
    assert again.requested == 0 and again.skipped_existing == 4


def test_run_generation_survives_failures(cfg, storage):
    fake = FakeServer(fail_first=100, status=500)
    client = LLMClient(cfg.server, transport=fake.transport(), sleep=lambda s: None)
    summary = run_generation(cfg, storage, probes=select_probes(ids=["neutral_dog"]), samples=1,
                             client=client, progress=None)
    assert summary.failed == 2 and summary.generated == 0 and storage.count_stories() == 0


def test_parse_judge_output_variants():
    raw = 'Sure! {"gender_role": {"score": 0.8, "evidence": "nurse Emily"}, "age": 1.4, "xenophobia": "0.2"}'
    res = parse_judge_output(raw)
    assert res.scores["gender_role"] == 0.8 and res.evidence["gender_role"] == "nurse Emily"
    assert res.scores["age"] == 1.0 and res.scores["xenophobia"] == 0.2 and res.scores["class"] == 0.0
    assert set(res.scores) == set(LABEL_KEYS)
    nested = parse_judge_output(json.dumps({"labels": {"class": {"score": 0.5}}}))
    assert nested.scores["class"] == 0.5
    try:
        parse_judge_output("no json here")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_judge_missing_stores_scores(cfg, storage):
    s1 = storage.add_story("Grandma squinted at the phone.", "model-b")
    s2 = storage.add_story("A robot paints.", "model-b")
    fake = FakeServer(reply=lambda body: json.dumps({k: {"score": 0.7 if k == "age" else 0.0, "evidence": ""}
                                                     for k in LABEL_KEYS}))
    client = LLMClient(cfg.server, transport=fake.transport(), sleep=lambda s: None)
    summary = judge_missing(cfg, storage, client=client, progress=None)
    assert summary.done == 2 and summary.failed == 0
    assert storage.judge_scores("model-a")[s1]["age"] == 0.7
    assert "Categories:" in build_judge_prompt("x") and fake.requests[0]["body"]["temperature"] == 0.0
    assert judge_missing(cfg, storage, client=client, progress=None).requested == 0
    assert storage.stats()["judged"] == 2 and s2 in storage.judge_scores()
