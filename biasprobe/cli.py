"""Command-line interface: python -m biasprobe <command> [options]."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import warnings
from pathlib import Path

from . import __version__
from .config import AppConfig, load_config
from .storage import Storage
from .taxonomy import LABELS, describe_taxonomy

warnings.filterwarnings("ignore", category=UserWarning)


def _open(args) -> tuple[AppConfig, Storage]:
    cfg = load_config(args.config)
    db = Path(args.db) if args.db else cfg.db_path
    return cfg, Storage(db)


# ----------------------------------------------------------------- commands

def cmd_init(args) -> int:
    target = Path(args.path or "config.toml")
    if target.exists() and not args.force:
        print(f"{target} already exists (use --force to overwrite)")
        return 1
    example = Path(__file__).resolve().parent.parent / "config.example.toml"
    shutil.copy(example, target)
    print(f"wrote {target}; edit the [server] block and the [[models]] entries, "
          f"then run `python -m biasprobe models` to check the connection.")
    return 0


def cmd_probes(args) -> int:
    from .prompts import select_probes
    for p in select_probes(args.category or None):
        print(f"{p.id:<24} {p.category:<12} targets={','.join(p.targets) or '-'}")
        if args.verbose:
            print(f"    {p.premise}")
    return 0


def cmd_labels(_args) -> int:
    print(describe_taxonomy())
    return 0


def cmd_models(args) -> int:
    from .llm_client import LLMClient, LLMError
    cfg, _ = _open(args)
    if not cfg.models:
        print("no models configured; run `python -m biasprobe init` and edit config.toml")
        return 1
    print(f"server: {cfg.server.base_url} ({cfg.server.api_style})")
    for m in cfg.models:
        print(f"  - {m.name}" + (f" ({m.label})" if m.label else ""))
    if args.ping:
        with LLMClient(cfg.server) as client:
            try:
                available = client.list_models()
                print(f"server lists {len(available)} models")
                for m in cfg.models:
                    flag = "ok" if m.name in available else "NOT LISTED by server"
                    print(f"  {m.name}: {flag}")
            except Exception as exc:  # noqa: BLE001
                print(f"could not list models: {exc}")
            if args.ping == "complete":
                for m in cfg.models:
                    try:
                        resp = client.complete(m, "Say hello in five words.", max_tokens=20, temperature=0.0,
                                               server=cfg.server_for(m))
                        print(f"  {m.name}: {resp.text[:60]!r} ({resp.latency_s:.1f}s)")
                    except LLMError as exc:
                        print(f"  {m.name}: FAILED {exc}")
    return 0


def cmd_generate(args) -> int:
    from .generate import run_generation
    from .prompts import select_probes
    cfg, storage = _open(args)
    if not cfg.models:
        print("no models configured; run `python -m biasprobe init` and edit config.toml")
        return 1
    models = [cfg.model(n) for n in args.models] if args.models else cfg.models
    probes = select_probes(args.categories or cfg.generation.categories, args.probes or None)
    summary = run_generation(cfg, storage, probes=probes, models=models, samples=args.samples,
                             words=args.words, workers=args.workers, dry_run=args.dry_run)
    print(summary)
    if summary.errors:
        print(f"{len(summary.errors)} errors; first: {summary.errors[0][:300]}")
    return 0 if summary.failed == 0 else 2


def cmd_export_prompts(args) -> int:
    from .generate import export_prompts
    from .prompts import select_probes
    cfg = load_config(args.config)
    probes = select_probes(args.categories or cfg.generation.categories, args.probes or None)
    n = export_prompts(args.path, probes, words=args.words or cfg.generation.target_words)
    print(f"wrote {n} prompts to {args.path}")
    return 0


def cmd_import_generations(args) -> int:
    from .generate import import_generations
    _, storage = _open(args)
    failed = 0
    for path in args.paths:
        summary = import_generations(storage, path)
        failed += summary.failed
        for err in summary.errors[:5]:
            print(f"    {err}")
    return 0 if failed == 0 else 2


def cmd_demo(args) -> int:
    from .demo_data import load_demo
    _, storage = _open(args)
    added, anns = load_demo(storage)
    print(f"demo data: {added} stories added, {anns} annotations added")
    return 0


def cmd_judge(args) -> int:
    from .judge import judge_missing
    cfg, storage = _open(args)
    if args.model:
        cfg.judge.model = args.model
    summary = judge_missing(cfg, storage, limit=args.limit, workers=args.workers)
    print(f"judged={summary.done} failed={summary.failed} requested={summary.requested}")
    return 0 if summary.failed == 0 else 2


def cmd_train(args) -> int:
    from .model import predict_all, save_model, train_from_storage
    cfg, storage = _open(args)
    use_judge = False if args.no_judge else None
    clf, _cv = train_from_storage(storage, use_judge=use_judge, self_training=not args.no_self_training,
                                  n_splits=args.folds, heuristic_weight=args.heuristic_weight,
                                  char_ngrams=args.char_ngrams)
    n = predict_all(storage, clf)
    path = save_model(clf, cfg.model_dir)
    print(f"saved {clf.version} to {path}; refreshed predictions for {n} stories")
    return 0


def cmd_predict(args) -> int:
    from .model import load_model
    cfg, storage = _open(args)
    clf = load_model(cfg.model_dir)
    if clf is None:
        print("no trained model; run `python -m biasprobe train` first")
        return 1
    if args.story_id:
        story = storage.get_story(args.story_id)
        if story is None:
            print(f"story {args.story_id} not found")
            return 1
        text = story["text"]
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        text = sys.stdin.read()
    explanation = clf.explain({"text": text})
    if args.json:
        print(json.dumps(explanation, indent=2))
        return 0
    flagged = [k for k, v in explanation.items() if v["predicted"]]
    print(f"model {clf.version}: " + (", ".join(flagged) if flagged else "no stereotype perceived"))
    for key, info in sorted(explanation.items(), key=lambda kv: -kv[1]["score"]):
        mark = "*" if info["predicted"] else " "
        print(f" {mark} {key:<16} {info['score']:.2f} (thr {info['threshold']:.2f})")
        if info["predicted"] or args.verbose:
            for e in info["evidence"][:3]:
                print(f"      - {e['sentence'][:110]}  [{', '.join(e['cues'])}]")
            if info["top_features"]:
                print("      cues: " + ", ".join(f["feature"] for f in info["top_features"][:5]))
    return 0


def cmd_serve(args) -> int:
    import uvicorn
    from .web.app import create_app
    cfg, storage = _open(args)
    app = create_app(cfg, storage)
    print(f"open http://{args.host}:{args.port}/")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_report(args) -> int:
    from .analysis import write_report
    cfg, storage = _open(args)
    md, js = write_report(storage, args.out or cfg.reports_dir)
    print(f"wrote {md} and {js}")
    if args.print:
        print(md.read_text(encoding="utf-8"))
    return 0


def cmd_stats(args) -> int:
    _, storage = _open(args)
    print(json.dumps(storage.stats(), indent=2))
    return 0


def cmd_export(args) -> int:
    _, storage = _open(args)
    n = storage.export_jsonl(args.path)
    print(f"exported {n} stories to {args.path}")
    return 0


def cmd_import(args) -> int:
    _, storage = _open(args)
    added, anns = storage.import_jsonl(args.path, keep_annotations=not args.no_annotations)
    print(f"imported {added} stories and {anns} annotations from {args.path}")
    return 0


# -------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="biasprobe",
                                description="Probe LLM story generation for perceived social biases.")
    p.add_argument("--version", action="version", version=f"biasprobe {__version__}")
    p.add_argument("--config", help="path to config.toml (default: ./config.toml or $BIASPROBE_CONFIG)")
    p.add_argument("--db", help="override the SQLite database path")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="write a config.toml template"); s.add_argument("path", nargs="?")
    s.add_argument("--force", action="store_true"); s.set_defaults(func=cmd_init)

    s = sub.add_parser("probes", help="list the probe prompts"); s.add_argument("--category", nargs="*")
    s.add_argument("-v", "--verbose", action="store_true"); s.set_defaults(func=cmd_probes)

    s = sub.add_parser("labels", help="print the bias taxonomy"); s.set_defaults(func=cmd_labels)

    s = sub.add_parser("models", help="show configured models and test the server")
    s.add_argument("--ping", nargs="?", const="list", choices=["list", "complete"],
                   help="list server models, or 'complete' to also run a tiny generation per model")
    s.set_defaults(func=cmd_models)

    s = sub.add_parser("generate", help="generate stories for every model x probe (resumable)")
    s.add_argument("--models", nargs="*", help="subset of configured model names")
    s.add_argument("--categories", nargs="*", help="probe categories (see `probes`)")
    s.add_argument("--probes", nargs="*", help="probe ids")
    s.add_argument("--samples", type=int, help="stories per (model, probe); default from config")
    s.add_argument("--words", type=int, help="target story length")
    s.add_argument("--workers", type=int, help="parallel requests; default server.max_concurrency")
    s.add_argument("--dry-run", action="store_true", help="only count what would be generated")
    s.set_defaults(func=cmd_generate)

    s = sub.add_parser("export-prompts", help="write the probe prompts as JSONL for an offline generator")
    s.add_argument("path"); s.add_argument("--categories", nargs="*"); s.add_argument("--probes", nargs="*")
    s.add_argument("--words", type=int, help="target story length")
    s.set_defaults(func=cmd_export_prompts)

    s = sub.add_parser("import-generations", help="import stories written by an offline generator")
    s.add_argument("paths", nargs="+"); s.set_defaults(func=cmd_import_generations)

    s = sub.add_parser("demo", help="load the built-in synthetic demo stories"); s.set_defaults(func=cmd_demo)

    s = sub.add_parser("judge", help="score stories with the LLM judge (extra classifier signal)")
    s.add_argument("--model", help="judge model name (default from [judge] in config)")
    s.add_argument("--limit", type=int); s.add_argument("--workers", type=int); s.set_defaults(func=cmd_judge)

    s = sub.add_parser("train", help="cross-validate, train and refresh predictions")
    s.add_argument("--folds", type=int, default=5); s.add_argument("--no-judge", action="store_true")
    s.add_argument("--no-self-training", action="store_true")
    s.add_argument("--heuristic-weight", type=float, default=5.0,
                   help="pseudo-examples given to the lexical heuristic per label (0 disables it)")
    s.add_argument("--char-ngrams", action="store_true", help="also use character n-gram TF-IDF features")
    s.set_defaults(func=cmd_train)

    s = sub.add_parser("predict", help="detect biases in a story")
    s.add_argument("--text"); s.add_argument("--file"); s.add_argument("--story-id", type=int)
    s.add_argument("--json", action="store_true"); s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_predict)

    s = sub.add_parser("serve", help="run the annotation web app")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("report", help="write the per-model bias report (markdown + json)")
    s.add_argument("--out"); s.add_argument("--print", action="store_true"); s.set_defaults(func=cmd_report)

    s = sub.add_parser("stats", help="print database statistics"); s.set_defaults(func=cmd_stats)
    s = sub.add_parser("export", help="export stories + annotations to JSONL"); s.add_argument("path")
    s.set_defaults(func=cmd_export)
    s = sub.add_parser("import", help="import stories (+annotations) from JSONL"); s.add_argument("path")
    s.add_argument("--no-annotations", action="store_true"); s.set_defaults(func=cmd_import)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
