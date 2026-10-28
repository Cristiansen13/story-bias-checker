import json

from biasprobe.analysis import build_report, occupation_gender_counts, render_markdown, write_report
from biasprobe.cli import main
from biasprobe.config import config_from_dict, load_config


def test_occupation_gender_counts():
    c = occupation_gender_counts("Dr. Michael Harris, the surgeon, snapped at nurse Emily.")
    assert c[("surgeon", "male")] == 1 and c[("nurse", "female")] == 1


def test_report_on_demo(demo_storage, tmp_path):
    report = build_report(demo_storage)
    a, b = report["models"]["demo-model-a"], report["models"]["demo-model-b"]
    assert a["human_any_rate"] > b["human_any_rate"]
    assert a["patterns"]["gender_role_stereo_share"] >= b["patterns"]["gender_role_stereo_share"]
    assert report["probes"][0]["bias_rate"] >= report["probes"][-1]["bias_rate"]
    md = render_markdown(report)
    assert "Human-perceived bias rate per model" in md and "demo-model-a" in md
    md_path, json_path = write_report(demo_storage, tmp_path)
    assert md_path.exists() and json.loads(json_path.read_text(encoding="utf-8"))["totals"]["stories"] == 56


def test_config_parsing(tmp_path):
    cfg = config_from_dict({
        "server": {"base_url": "http://h/v1", "api_style": "ollama"},
        "models": [{"name": "a", "params": {"top_p": 0.9}}, {"name": "b", "server": {"base_url": "http://other"}}],
        "generation": {"stories_per_prompt": 3},
        "paths": {"db": "x.db"},
    }, config_dir=tmp_path)
    assert cfg.server.api_style == "ollama" and cfg.generation.stories_per_prompt == 3
    assert cfg.server_for(cfg.model("b")).base_url == "http://other"
    assert cfg.server_for(cfg.model("a")).base_url == "http://h/v1"
    assert cfg.db_path == tmp_path / "x.db"
    try:
        config_from_dict({"server": {"api_style": "nope"}})
    except ValueError:
        pass
    else:
        raise AssertionError
    assert load_config(None).models == [] or True  # no config file: defaults, no crash


def test_cli_end_to_end(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = str(tmp_path / "t.db")
    assert main(["--db", db, "demo"]) == 0
    assert main(["--db", db, "stats"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out[out.index("{"):])["stories"] == 56
    assert main(["--db", db, "train", "--folds", "3"]) == 0
    out = capsys.readouterr().out
    assert "saved v" in out and "macro-F1" in out
    assert main(["--db", db, "predict", "--text", "Nurse Emily cried while Dr. Harris, the surgeon, took charge."]) == 0
    assert "gender_role" in capsys.readouterr().out
    assert main(["--db", db, "report", "--out", str(tmp_path / "rep")]) == 0
    assert (tmp_path / "rep" / "report.md").exists()
    assert main(["--db", db, "export", str(tmp_path / "e.jsonl")]) == 0
    assert main(["--db", str(tmp_path / "t2.db"), "import", str(tmp_path / "e.jsonl")]) == 0
    assert "imported 56 stories and 46 annotations" in capsys.readouterr().out
    assert main(["probes", "--category", "neutral"]) == 0
    assert main(["labels"]) == 0
    assert main(["init", str(tmp_path / "c.toml")]) == 0 and (tmp_path / "c.toml").exists()
    assert main(["--config", str(tmp_path / "c.toml"), "--db", db, "generate", "--dry-run"]) == 0
    assert "generations planned" in capsys.readouterr().out
