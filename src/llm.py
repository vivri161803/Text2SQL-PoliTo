"""Client OpenRouter: cache, retry, costo, reasoning, controllo di spesa."""
import copy
import hashlib
import json
import re
import time
from datetime import datetime, timezone

import requests

from . import config


class FatalAPIError(RuntimeError):
    pass


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def make_call_id(part, item_id, strategy, round_, alias):
    return _sha([part, item_id, strategy, round_, alias])[:16]


def total_spent():
    tot = 0.0
    for f in config.CACHE_DIR.glob("*.json"):
        try:
            tot += json.loads(f.read_text(encoding="utf-8")).get("cost_usd") or 0.0
        except Exception:
            pass
    return tot


def _model_cfg(alias):
    cfg = copy.deepcopy(config.MODELS[alias])
    if alias == "gpt-nr" and _fallback_active():
        cfg = copy.deepcopy(config.GPT_NR_FALLBACK)
    return cfg


def _fallback_active():
    f = config.OUTPUTS / "check.json"
    try:
        return json.loads(f.read_text()).get("gpt_nr_fallback", False)
    except Exception:
        return False


def _post(body):
    if not config.API_KEY:
        raise FatalAPIError("OPENROUTER_API_KEY mancante in .env")
    headers = {"Authorization": f"Bearer {config.API_KEY}", "Content-Type": "application/json"}
    last = None
    for attempt in range(4):
        try:
            r = requests.post(f"{config.BASE_URL}/chat/completions", headers=headers, json=body, timeout=600)
        except requests.RequestException as e:
            last = e
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 402:
            raise FatalAPIError(f"402 credito esaurito: {r.text[:200]}")
        if r.status_code == 429 or r.status_code >= 500:
            last = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            time.sleep(2 ** attempt)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
        return r.json()
    raise RuntimeError(f"richiesta fallita dopo 4 tentativi: {last}")


def _call(cfg, messages, max_tokens, extra_params):
    params = {**cfg["params"], **extra_params}
    body = {"model": cfg["id"], "messages": messages, "max_tokens": max_tokens,
            "usage": {"include": True}, **params}
    if "reasoning" in params:
        body["provider"] = {"require_parameters": True}
    key = _sha({"base_url": cfg["base_url"], "model": cfg["id"], "messages": messages,
                "params": {**params, "max_tokens": max_tokens}})
    path = config.CACHE_DIR / f"{key}.json"
    if path.exists():
        c = json.loads(path.read_text(encoding="utf-8"))
        c["from_cache"] = True
        return c, params
    if total_spent() >= config.SPESA_MAX_USD:
        raise FatalAPIError(f"spesa massima {config.SPESA_MAX_USD}$ raggiunta")
    t0 = time.time()
    resp = _post(body)
    latency = time.time() - t0
    usage = resp.get("usage") or {}
    entry = {"response": resp, "cost_usd": usage.get("cost") or 0.0,
             "latency_s": round(latency, 2), "from_cache": False}
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    truncated_empty = choice.get("finish_reason") == "length" and not (msg.get("content") or "").strip()
    entry["_cacheable"] = not truncated_empty and bool(msg.get("content") or msg.get("reasoning"))
    if entry["_cacheable"]:
        path.write_text(json.dumps({k: v for k, v in entry.items() if k != "_cacheable"},
                                   ensure_ascii=False), encoding="utf-8")
    return entry, params


def extract_sql(text):
    """-> (sql, format_ok, nl_output). Tiene l'ultimo statement SELECT/WITH."""
    text = text or ""
    blocks = re.findall(r"```(?:sql)?\s*\n?(.*?)```", text, flags=re.S | re.I)
    code = blocks[-1] if blocks else text
    stmts = [s.strip() for s in code.split(";") if s.strip()]
    sel = [s for s in stmts if re.match(r"(?is)^(select|with)\b", s)]
    if not sel:
        # testo + codice senza blocchi: cerca il primo SELECT/WITH
        m = re.search(r"(?is)\b(select|with)\b.*", code)
        if not m:
            return None, False, text.strip()
        sel = [m.group(0).split(";")[0].strip()]
    sql = sel[-1]
    rest = text.replace(blocks[-1], "") if blocks else text.replace(sql, "")
    rest = re.sub(r"```(?:sql)?", "", rest, flags=re.I).replace(";", "").strip()
    other = [s for s in stmts if s is not sql and s not in sel]
    nl = rest
    format_ok = not nl and not other and (len(blocks) <= 1)
    if blocks and nl == "" and other:
        format_ok = False
    return sql, format_ok, nl


def chat(alias, messages, role="tested", meta=None, **overrides):
    """Esegue una chiamata e restituisce il record completo."""
    meta = meta or {}
    cfg = _model_cfg(alias)
    max_tokens = overrides.pop("max_tokens", cfg["max_tokens"])
    entry, params = _call(cfg, messages, max_tokens, overrides)
    resp = entry["response"]
    choice = (resp.get("choices") or [{}])[0]
    if choice.get("finish_reason") == "length" and not (choice.get("message", {}).get("content") or "").strip():
        entry, params = _call(cfg, messages, max_tokens * 2, overrides)
        resp = entry["response"]
        choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = msg.get("content") or ""
    details = msg.get("reasoning_details") or []
    rtype = details[0].get("type") if details and isinstance(details[0], dict) else None
    reasoning = msg.get("reasoning") or None
    if not reasoning:
        rtype = "non esposto dall'API"
    sql, format_ok, nl = extract_sql(content) if role == "tested" else (None, True, "")
    empty = not content.strip()
    if empty:
        format_ok = False
    usage = resp.get("usage") or {}
    return {
        "call_id": make_call_id(meta.get("part"), meta.get("item_id"), meta.get("strategy"),
                                meta.get("round"), alias),
        "role": role, "part": meta.get("part"), "item_id": meta.get("item_id"),
        "pattern": meta.get("pattern"), "strategy": meta.get("strategy"),
        "round": meta.get("round"), "model_alias": alias,
        "model_served": resp.get("model"), "provider": resp.get("provider"),
        "generation_id": resp.get("id"), "params_sent": params,
        "prompt": messages[-1]["content"], "raw_output": content,
        "reasoning": reasoning, "reasoning_type": rtype,
        "finish_reason": choice.get("finish_reason"),
        "sql": sql, "nl_output": nl, "format_ok": format_ok,
        "empty_or_truncated": empty,
        "usage": usage, "cost_usd": entry["cost_usd"], "latency_s": entry["latency_s"],
        "from_cache": entry.get("from_cache", False),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def extract_json(text):
    """Primo oggetto/array JSON contenuto nel testo (anche dentro un blocco ```json)."""
    text = text or ""
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, flags=re.S | re.I)
    if m:
        text = m.group(1)
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("nessun JSON nella risposta")
    i = min(starts)
    j = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[i:j + 1])


def extract_block(text, lang="sql"):
    """Contenuto dell'ultimo blocco di codice (qualsiasi linguaggio) o il testo intero."""
    blocks = re.findall(r"```[a-zA-Z]*\s*\n(.*?)```", text or "", flags=re.S)
    return (blocks[-1] if blocks else (text or "")).strip()
