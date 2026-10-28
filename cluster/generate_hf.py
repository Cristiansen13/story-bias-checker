"""Generate biasprobe stories with a local Hugging Face model (runs inside the cluster container).

Reads the prompt file written by `python -m biasprobe export-prompts`, writes one JSON line per
story and resumes from whatever the output file already holds, so a preempted job loses at most
one batch. Import the result locally with `python -m biasprobe import-generations`.

Only torch and transformers are needed; biasprobe itself is not imported here.

    python3 generate_hf.py --check MODEL_DIR [MODEL_DIR ...]
    python3 generate_hf.py --model-name qwen3.5-9b --model-path /path/Qwen3.5-9B \
        --prompts prompts.jsonl --out out/stories-qwen3.5-9b.jsonl --samples 3
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import torch
import transformers
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, GenerationConfig

# End-of-turn markers of the common chat templates; generation stops at any of them.
END_OF_TURN = ["<|im_end|>", "<turn|>", "<end_of_turn>", "<|eot_id|>", "<|end|>", "<|endoftext|>", "</s>"]
REASONING = re.compile(r"<think>.*?(?:</think>|$)|<\|channel>.*?(?:<channel\|>|$)", re.DOTALL)


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def check(paths: list[str]) -> int:
    """Exit 0 if this environment's transformers knows every model's architecture."""
    log(f"python {sys.version.split()[0]}  torch {torch.__version__}  transformers {transformers.__version__}  "
        f"cuda {torch.cuda.is_available()}")
    ok = True
    for path in paths:
        try:
            cfg = AutoConfig.from_pretrained(path)
            log(f"  ok   {path}: {type(cfg).__name__}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            log(f"  FAIL {path}: {str(exc).splitlines()[0][:160]}")
    return 0 if ok else 1


def load_model(path: str, dtype: torch.dtype, device: str):
    """Multimodal checkpoints (…ForConditionalGeneration) load through the image-text-to-text
    auto class, everything else as a causal LM. Refuse to run if weights are missing: a wrong
    class would silently generate from randomly initialised layers."""
    from transformers.utils import is_accelerate_available
    cfg = AutoConfig.from_pretrained(path)
    arch = (getattr(cfg, "architectures", None) or [""])[0]
    tied = any(getattr(c, "tie_word_embeddings", False) for c in (cfg, getattr(cfg, "text_config", None)) if c)
    classes = [AutoModelForCausalLM]
    if arch.endswith("ForConditionalGeneration"):
        from transformers import AutoModelForImageTextToText
        classes.insert(0, AutoModelForImageTextToText)
    direct = device == "cuda" and is_accelerate_available()
    kw = {"dtype": dtype, "device_map": "cuda"} if direct else {"dtype": dtype}
    last_exc = None
    for cls in classes:
        try:
            model, info = cls.from_pretrained(path, output_loading_info=True, **kw)
        except (ValueError, KeyError) as exc:
            last_exc = exc
            continue
        missing = [k for k in info.get("missing_keys", [])
                   if not re.search(r"rotary|inv_freq", k) and not (tied and "lm_head" in k)]
        if missing:
            raise RuntimeError(f"{cls.__name__} left {len(missing)} weights uninitialised, e.g. {missing[:3]}")
        if not direct:
            model = model.to(device)
        log(f"loaded {arch or type(model).__name__} via {cls.__name__}")
        return model.eval()
    raise RuntimeError(f"no auto class could load {path}: {last_exc}")


def render(tokenizer, system: str, prompt: str) -> str:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    try:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                             enable_thinking=False)
    except Exception:  # noqa: BLE001 - templates without a system role
        merged = [{"role": "user", "content": f"{system}\n\n{prompt}"}]
        return tokenizer.apply_chat_template(merged, tokenize=False, add_generation_prompt=True,
                                             enable_thinking=False)


def stop_ids(tokenizer, model) -> list[int]:
    ids = set()
    for src in (model.generation_config.eos_token_id, tokenizer.eos_token_id):
        if isinstance(src, int):
            ids.add(src)
        elif src:
            ids.update(src)
    vocab = tokenizer.get_vocab()
    ids.update(vocab[t] for t in END_OF_TURN if t in vocab)
    return sorted(ids)


def decode(tokenizer, ids: list[int], stops: set[int]) -> tuple[str, str, bool]:
    """Return (raw, text, finished): raw keeps special tokens for auditing, text has reasoning
    blocks and special tokens removed. `finished` is False if the story hit max_new_tokens."""
    cut = next((i for i, t in enumerate(ids) if t in stops), None)
    raw = tokenizer.decode(ids[:cut], skip_special_tokens=False)
    text = REASONING.sub("", raw).split("</think>")[-1]
    for tok in tokenizer.all_special_tokens:
        text = text.replace(tok, "")
    return raw, text.strip(), cut is not None


def done_keys(path: str) -> set[tuple[str, int]]:
    keys = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a line cut off by preemption; it is regenerated
                keys.add((rec["probe_id"], rec["sample_index"]))
    return keys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--check", nargs="+", metavar="MODEL_DIR", help="only check that the models' configs load")
    p.add_argument("--model-name", help="name stored with every story, e.g. qwen3.5-9b")
    p.add_argument("--model-path", help="local checkpoint directory or Hugging Face id")
    p.add_argument("--prompts", default="prompts.jsonl")
    p.add_argument("--out")
    p.add_argument("--samples", type=int, default=3, help="stories per probe")
    p.add_argument("--limit", type=int, help="generate at most this many stories in this run (smoke test)")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--max-new-tokens", type=int, default=700)
    p.add_argument("--temperature", type=float, default=0.9)
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = p.parse_args(argv)
    if args.check:
        return check(args.check)
    if not (args.model_name and args.model_path and args.out):
        p.error("--model-name, --model-path and --out are required")

    with open(args.prompts, encoding="utf-8") as fh:
        probes = [json.loads(line) for line in fh if line.strip()]
    have = done_keys(args.out)
    # sample 0 of every probe first, then sample 1, ...: a run cut short stays balanced
    todo = [(k, pr) for k in range(args.samples) for pr in probes if (pr["probe_id"], k) not in have]
    if args.limit is not None:
        todo = todo[:args.limit]
    log(f"{args.model_name}: {len(have)} stories present, {len(todo)} to generate")
    if not todo:
        return 0

    dtype = torch.bfloat16 if args.device == "cuda" else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = load_model(args.model_path, dtype, args.device)
    stops = stop_ids(tokenizer, model)
    gen_cfg = GenerationConfig(do_sample=True, temperature=args.temperature, top_p=args.top_p, top_k=0,
                               max_new_tokens=args.max_new_tokens, eos_token_id=stops,
                               pad_token_id=tokenizer.pad_token_id)
    params = {"temperature": args.temperature, "top_p": args.top_p, "top_k": 0,
              "max_new_tokens": args.max_new_tokens}
    engine = f"transformers-{transformers.__version__}"
    log(f"stop tokens {stops}; sampling {params}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    out = open(args.out, "a", encoding="utf-8")
    batch_size, i, started = args.batch_size, 0, time.time()
    while i < len(todo):
        batch = todo[i:i + batch_size]
        texts = [render(tokenizer, pr["system"], pr["prompt"]) for _, pr in batch]
        enc = tokenizer(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(args.device)
        torch.manual_seed(args.seed + i)
        t0 = time.time()
        try:
            with torch.inference_mode():
                gen = model.generate(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"],
                                     generation_config=gen_cfg)
        except torch.OutOfMemoryError:
            if batch_size == 1:
                raise
            batch_size = max(1, batch_size // 2)
            torch.cuda.empty_cache()
            log(f"out of memory; batch size -> {batch_size}")
            continue
        dt = time.time() - t0
        new = gen[:, enc["input_ids"].shape[1]:].tolist()
        n_tokens = 0
        for (k, pr), ids in zip(batch, new):
            raw, text, finished = decode(tokenizer, ids, set(stops))
            n_new = next((j for j, t in enumerate(ids) if t in stops), len(ids))
            n_tokens += n_new
            out.write(json.dumps({
                "model": args.model_name, "probe_id": pr["probe_id"], "probe_category": pr["probe_category"],
                "targets": pr.get("targets", []), "prompt": pr["prompt"], "sample_index": k,
                "text": text, "raw": raw, "finished": finished, "new_tokens": n_new,
                "latency_s": round(dt / len(batch), 2), "params": params, "engine": engine,
                "model_path": args.model_path,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }, ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())
        i += len(batch)
        log(f"{args.model_name} [{i}/{len(todo)}] batch {len(batch)} in {dt:.0f}s, "
            f"{n_tokens / dt:.0f} tok/s, {len(text.split())} words last; elapsed {time.time() - started:.0f}s")
    out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
