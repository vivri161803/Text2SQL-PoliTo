"""Run delle Parti 1, 2 e 3 verso i modelli testati."""
import json

from . import assignment as A
from . import config, llm


def calls_path(part):
    return config.OUTPUTS / f"calls_p{part}.json"


def load_calls(part):
    try:
        return json.loads(calls_path(part).read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_gold():
    return json.loads((config.OUTPUTS / "gold.json").read_text(encoding="utf-8"))


def p1_item_id(pattern, strategy):
    return f"P{pattern}" + (f"-{strategy}" if strategy else "")


def _safe_chat(alias, prompt, meta):
    try:
        return llm.chat(alias, [{"role": "user", "content": prompt}], meta=meta)
    except llm.FatalAPIError:
        raise
    except Exception as e:  # modello irraggiungibile: record con errore, non in cache, rilanciabile
        return {"call_id": llm.make_call_id(meta.get("part"), meta.get("item_id"), meta.get("strategy"),
                                            meta.get("round"), alias),
                "role": "tested", "part": meta.get("part"), "item_id": meta.get("item_id"),
                "pattern": meta.get("pattern"), "strategy": meta.get("strategy"), "round": meta.get("round"),
                "model_alias": alias, "prompt": prompt, "raw_output": "", "sql": None, "nl_output": "",
                "reasoning": None, "reasoning_type": "non esposto dall'API", "format_ok": False,
                "empty_or_truncated": True, "cost_usd": 0.0, "latency_s": 0.0, "error": str(e)[:300],
                "model_served": None, "provider": None, "params_sent": None, "finish_reason": None}


def p1_prompt(gold, pattern, strategy):
    return A.build_prompt_p1(gold["p1"][str(pattern)]["domanda"], strategy)


def run_p12(part):
    gold = load_gold()
    calls = {}
    for pattern, strategy in A.prompt_items():
        prompt = p1_prompt(gold, pattern, strategy)
        for alias in config.PART_MODELS[part]:
            meta = {"part": part, "item_id": p1_item_id(pattern, strategy), "pattern": pattern,
                    "strategy": strategy, "round": 1}
            r = _safe_chat(alias, prompt, meta)
            calls[r["call_id"]] = r
            print(f"  {alias:13} {meta['item_id']:16} cost=${r['cost_usd']:.4f}"
                  + (f" ERRORE {r['error']}" if r.get("error") else ""))
    calls_path(part).write_text(json.dumps(calls, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[run p{part}] {len(calls)} chiamate, spesa totale ${llm.total_spent():.3f}")


# ---------- Parte 3 ----------
def prompts_r2_path():
    return config.OUTPUTS / "p3_prompts_r2.json"


def load_prompts_r2():
    try:
        return json.loads(prompts_r2_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_p3(round_):
    old = load_calls(3)
    calls = {k: v for k, v in old.items() if v.get("round") != round_ and not (round_ == 2 and v.get("model_alias") == "gpt-nr")}
    r2 = load_prompts_r2()
    for q in A.Q_P3:
        base = A.build_prompt_p3(q)
        for alias in config.PART_MODELS[3]:
            if round_ == 1:
                prompt = base
            else:
                prompt = (r2.get(str(q)) or {}).get(alias)
                if not prompt:
                    continue
            meta = {"part": 3, "item_id": f"Q{q}", "pattern": None, "strategy": None, "round": round_}
            r = _safe_chat(alias, prompt, meta)
            calls[r["call_id"]] = r
            print(f"  {alias:12} Q{q} r{round_} reasoning={r['reasoning_type']} cost=${r['cost_usd']:.4f}"
                  + (f" ERRORE {r['error']}" if r.get("error") else ""))
        if round_ == 2 and q in (4, 10):  # GPT senza reasoning: stesso prompt di gpt-r (aggiornato se esiste)
            prompt = (r2.get(str(q)) or {}).get("gpt-r") or base
            meta = {"part": 3, "item_id": f"Q{q}", "pattern": None, "strategy": None, "round": 2}
            r = _safe_chat("gpt-nr", prompt, meta)
            calls[r["call_id"]] = r
            print(f"  gpt-nr       Q{q} cost=${r['cost_usd']:.4f}")
    calls_path(3).write_text(json.dumps(calls, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[run p3 r{round_}] {len(calls)} chiamate in file, spesa totale ${llm.total_spent():.3f}")
