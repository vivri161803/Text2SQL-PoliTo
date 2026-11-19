"""Metriche aggregate da calls/evals (usate da narrative e report)."""
import json
from collections import Counter, defaultdict

from . import config


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def p12_tables(part):
    """-> {'ex': {pattern: {alias: [ex_full, ex_base]}}, 'overall': {alias: {...}}}"""
    evals = load(config.OUTPUTS / f"evals_p{part}.json")
    calls = load(config.OUTPUTS / f"calls_p{part}.json")
    acc = defaultdict(lambda: defaultdict(list))
    tot = defaultdict(lambda: defaultdict(list))
    cats = defaultdict(Counter)
    for cid, e in evals.items():
        c = calls[cid]
        a = e["alias"]
        acc[c["pattern"]][a].append((e["ex"], e["ex_base"]))
        t = tot[a]
        t["ex"].append(e["ex"])
        t["ex_base"].append(e["ex_base"])
        t["strategia"].append(e["rispetta_strategia"] is True)
        t["formato"].append(bool(e["format_ok"]))
        t["eseguibile"].append(e["statuses"][0] == "ok")
        cats[a].update(e.get("categorie_errore") or [])
    ex = {str(p): {a: [sum(x[0] for x in v) / len(v), sum(x[1] for x in v) / len(v)] for a, v in d.items()}
          for p, d in acc.items()}
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    overall = {a: {k: mean(v) for k, v in t.items()} for a, t in tot.items()}
    cost = defaultdict(lambda: [0, 0.0, 0.0])
    for c in calls.values():
        s = cost[c["model_alias"]]
        s[0] += 1
        s[1] += c.get("cost_usd") or 0.0
        s[2] += c.get("latency_s") or 0.0
    return {"ex": ex, "overall": overall, "categorie": {a: dict(c) for a, c in cats.items()},
            "costi": {a: {"chiamate": v[0], "costo": v[1], "latenza_media": v[2] / v[0]} for a, v in cost.items()}}


def p3_tables():
    evals = load(config.OUTPUTS / "evals_p3.json")
    r1, r2 = {}, {}
    coerenza = Counter()
    for e in evals.values():
        if e["alias"] == "gpt-nr":
            continue
        if e["round"] == 1:
            r1[(e["item_id"], e["alias"])] = e["ex"]
            coerenza[(e["reasoning_corretto"], e["segue_reasoning"])] += 1
        else:
            r2[(e["item_id"], e["alias"])] = e["ex"]
    per_model = defaultdict(lambda: {"r1": 0, "r2": 0, "n": 0, "reasoning_ok": 0})
    for (q, a), ex in r1.items():
        m = per_model[a]
        m["n"] += 1
        m["r1"] += ex
        m["r2"] += r2.get((q, a), ex)  # corretto al giro 1 resta corretto
    for e in evals.values():
        if e["alias"] != "gpt-nr" and e["round"] == 1 and e["reasoning_corretto"] == "sì":
            per_model[e["alias"]]["reasoning_ok"] += 1
    return {"per_model": dict(per_model), "coerenza": {f"{k[0]}|{k[1]}": v for k, v in coerenza.items()}}


def short_table(t):
    """Testo compatto per i prompt di sintesi."""
    return json.dumps(t, ensure_ascii=False, indent=1)
