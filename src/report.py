"""Costruzione di data.json, grafico e PDF finale (Typst)."""
import json
import shutil

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import typst

from . import config, metrics


def load_fixture():
    return json.loads((config.FIXTURES / "data.json").read_text(encoding="utf-8"))


def p2_chart(points, path):
    """points: lista di (alias, params_b, ex). I due punti a 8B sono etichettati a parte."""
    fig, ax = plt.subplots(figsize=(6, 3.2))
    for alias, x, y in points:
        ax.scatter([x], [y], color="#1f6feb")
        ax.annotate(alias, (x, y), textcoords="offset points", xytext=(5, 5), fontsize=7)
    ax.set_xlabel("Parametri (miliardi)")
    ax.set_ylabel("Accuratezza (EX)")
    ax.set_ylim(0, 1.05)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, format="svg")
    plt.close(fig)


MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
        "ottobre", "novembre", "dicembre"]
NO_QUERY = "(il modello non ha restituito alcuna query)"
FORBIDDEN = ["opus", "deepseek", "fable", "claude", "anthropic", "giudice", "gold", "pipeline", "llm di supporto"]


def _read_narr(name):
    f = config.NARRATIVES / name
    return f.read_text(encoding="utf-8").strip() if f.exists() else ""


def _sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def _params_str(rec):
    p = rec.get("params_sent") or {}
    parts = []
    for k, v in p.items():
        if k == "reasoning":
            parts.append("reasoning " + ", ".join(f"{a}={b}" for a, b in v.items()))
        else:
            parts.append(f"{k}={v}")
    return "; ".join(parts) or "-"


def _first_lines(text, n=15):
    if not text:
        return "Reasoning non esposto dall'API."
    return "\n".join(text.strip().splitlines()[:n])


def _p12_section(part, gold):
    from . import assignment as A
    calls, evals = metrics.load(config.OUTPUTS / f"calls_p{part}.json"), metrics.load(config.OUTPUTS / f"evals_p{part}.json")
    t = metrics.p12_tables(part)
    models = config.PART_MODELS[part]
    schede = []
    for i, (pattern, strategy) in enumerate(A.prompt_items(), 1):
        g = gold["p1"][str(pattern)]
        item = f"P{pattern}" + (f"-{strategy}" if strategy else "")
        sols = [{"strategia": s or "unica", "sql": g["gold_sql"][s or "unica"]} for s in A.PATTERNS[pattern][1]]
        full = A.build_prompt_p1(g["domanda"], strategy)
        prompt = full if pattern == 0 else ("Domanda: " + g["domanda"] +
                                            (("\n" + A.STRATEGY_LINES[strategy]) if strategy else "") +
                                            "\n(schema e istruzioni come nel prompt completo, Appendice A)")
        mods = []
        for alias in models:
            c = next((c for c in calls.values() if c["item_id"] == item and c["model_alias"] == alias), None)
            e = next((e for e in evals.values() if c and e["call_id"] == c["call_id"]), None)
            if not c or not e:
                continue
            extra = []
            if e["rispetta_strategia"] is False:
                extra.append("Strategia richiesta non rispettata.")
            if not c["format_ok"]:
                extra.append("Ha scritto altro oltre al codice SQL.")
            mods.append({"alias": alias, "sql": c.get("sql") or NO_QUERY, "esito": e["esito"],
                         "analisi": (e["commento"] + " " + " ".join(extra)).strip()})
        schede.append({"id": item, "pattern": pattern, "pattern_desc": A.PATTERNS[pattern][0], "strategia": strategy,
                       "domanda": g["domanda"], "soluzioni": sols, "prompt": prompt, "modelli": mods,
                       "_full_prompt": full})
    return {"modelli": models, "tabella": {p: v for p, v in sorted(t["ex"].items(), key=lambda kv: int(kv[0]))},
            "schede": schede, "_overall": t["overall"]}


def _p3_section(gold):
    from . import assignment as A
    calls, evals = metrics.load(config.OUTPUTS / "calls_p3.json"), metrics.load(config.OUTPUTS / "evals_p3.json")
    r2p = metrics.load(config.OUTPUTS / "p3_prompts_r2.json")
    queries, nr = [], []
    for q in A.Q_P3:
        item = f"Q{q}"
        g = gold["p3"][str(q)]
        mods = []
        for alias in config.PART_MODELS[3]:
            def get(rnd):
                c = next((c for c in calls.values() if c["item_id"] == item and c["model_alias"] == alias
                          and c["round"] == rnd), None)
                e = next((e for e in evals.values() if c and e["call_id"] == c["call_id"]), None)
                return c, e
            c1, e1 = get(1)
            if not c1 or not e1:
                continue
            c2, e2 = get(2)
            m = {"alias": alias, "reasoning_tipo": c1["reasoning_type"], "reasoning_estratto": _first_lines(c1.get("reasoning")),
                 "sql": c1.get("sql") or NO_QUERY, "reasoning_corretto": e1["reasoning_corretto"],
                 "passi_mancanti": e1["passi_mancanti"], "passi_errati": e1["passi_errati"],
                 "passi_fuori_ordine": e1["passi_fuori_ordine"], "passi_ridondanti": e1["passi_ridondanti"],
                 "commento_reasoning": e1["commento_reasoning"], "soluzione_corretta": e1["soluzione_corretta"],
                 "segue_reasoning": e1["segue_reasoning"], "commento_soluzione": e1["commento_soluzione"],
                 "prompt_aggiornato": (r2p.get(str(q)) or {}).get(alias) or "Non necessario: la soluzione era corretta al primo giro.", "r2": None}
            if c2 and e2:
                m["r2"] = {"reasoning_estratto": _first_lines(c2.get("reasoning")), "sql": c2.get("sql") or NO_QUERY,
                           "reasoning_corretto": e2["reasoning_corretto"], "commento_reasoning": e2["commento_reasoning"],
                           "soluzione_corretta": e2["soluzione_corretta"], "commento_soluzione": e2["commento_soluzione"]}
                m["prompt_aggiornato"] = c2["prompt"]
            mods.append(m)
        sec = _sections(_read_narr(f"p3_q{q:02d}_confronti.md"))
        queries.append({"q": q, "domanda": A.Q_P3[q][1], "soluzione_attesa": g["gold_sql"],
                        "interpretazioni": g.get("interpretazioni") or [], "prompt": A.build_prompt_p3(q),
                        "modelli": mods,
                        "confronto_reasoning": sec.get("Confronto modelli (reasoning)", ""),
                        "confronto_soluzione": sec.get("Confronto modelli (soluzione SQL)", "")})
        if q in (4, 10):
            e = next((e for e in evals.values() if e["item_id"] == item and e["alias"] == "gpt-nr"), None)
            c = e and calls.get(e["call_id"])
            if e and c:
                nr.append({"q": q, "output": c.get("nl_output") or "Il modello ha restituito solo codice SQL.",
                           "sql": c.get("sql") or NO_QUERY, "output_corretto": e["output_corretto"],
                           "commento_output": e["commento_output"], "soluzione_corretta": e["soluzione_corretta"],
                           "commento_soluzione": e["commento_soluzione"],
                           "confronto_gpt_reasoning": e["confronto_gpt_reasoning"],
                           "confronto_gpt_soluzione": e["confronto_gpt_soluzione"]})
    models = list(config.PART_MODELS[3])
    righe, tot = [], {a: [0, 0, 0] for a in models + ["gpt-nr"]}
    find = lambda q, a, r: next((e for e in evals.values() if e["item_id"] == f"Q{q}" and e["alias"] == a
                                 and e["round"] == r), None)
    for q in A.Q_P3:
        celle = {}
        for a in models:
            e1, e2 = find(q, a, 1), find(q, a, 2)
            if e1 is None:
                celle[a] = None
                continue
            r1, r2 = e1["ex"], (e2["ex"] if e2 else None)
            tot[a][0] += 1
            tot[a][1] += r1
            tot[a][2] += r2 if (r1 == 0 and r2 is not None) else r1
            celle[a] = {"r1": r1, "r2": r2}
        e = find(q, "gpt-nr", 2)
        if e:
            tot["gpt-nr"][0] += 1
            tot["gpt-nr"][1] += e["ex"]
            tot["gpt-nr"][2] += e["ex"]
        celle["gpt-nr"] = {"r1": e["ex"], "r2": None} if e else None
        righe.append({"q": q, "celle": celle})
    tabella = {"modelli": models + ["gpt-nr"], "righe": righe,
               "tot_r1": {a: f"{v[1]}/{v[0]}" for a, v in tot.items()},
               "tot_finale": {a: f"{v[2]}/{v[0]}" for a, v in tot.items()}}
    return {"queries": queries, "nr": nr, "tabella": tabella}


INTRO = {
    1: ("In questa parte ho messo alla prova tre modelli proprietari (gpt, gemini e codestral) sulla generazione di "
        "query SQL a partire da domande in italiano sullo schema Biblioteca. Ho coperto i sette pattern di difficoltà "
        "(da 0 a 6): proiezione con filtro e ordinamento, join, raggruppamento con HAVING e aggregate, query risolvibili "
        "in più modi, divisione (\"per ogni / tutti\"), esclusione con NOT IN o EXCEPT, CTE e subquery correlate.\n\n"
        "Nei pattern 3, 5 e 6 ho imposto esplicitamente la strategia di soluzione (JOIN, IN o INTERSECT; NOT IN o "
        "EXCEPT; CTE o correlazione), per un totale di 11 prompt. Lo scopo è misurare tre cose: se la query restituisce "
        "il risultato corretto (accuratezza di esecuzione su 5 istanze del database), se il modello rispetta la "
        "strategia richiesta e se si limita a restituire solo il codice SQL come chiesto."),
    2: ("In questa parte ho ripetuto gli stessi 11 prompt della Parte 1, identici carattere per carattere, su cinque "
        "modelli open source di piccole dimensioni, da 1 a 8 miliardi di parametri (llama-1b, llama-3b, gemma-4b, "
        "ministral-8b e qwen3-8b). Cambia quindi solo il modello, e ogni differenza di risultato è attribuibile a lui.\n\n"
        "Lo scopo è capire come cambia la capacità di generare SQL al ridursi delle dimensioni: a quale taglia le "
        "query smettono di essere eseguibili, quali pattern cedono per primi, quanto spesso i modelli ignorano il "
        "formato o la strategia imposta e quanto distano dai modelli proprietari della Parte 1."),
    3: ("In questa parte ho affrontato dieci query complesse (Q1-Q10) su cinque schemi diversi, con prompt in inglese e "
        "tre modelli dotati di reasoning (gemini-2.5, qwen3-235b e gpt-r). Le query richiedono più passaggi: soglie su "
        "aggregati, confronti tra periodi, condizioni di tipo \"mai\" e \"tutti\", confronti tra coppie.\n\n"
        "Qui non analizzo solo la query finale ma anche il ragionamento del modello: se è corretto, se ci sono passi "
        "mancanti, errati, in ordine sbagliato o ridondanti, e se la soluzione lo segue. Per le risposte sbagliate ho "
        "poi aggiornato il prompt con chiarimenti mirati, senza mostrare la soluzione, e ho ripetuto la prova una sola "
        "volta (giro 2). Per Q4 e Q10 ho infine confrontato GPT con e senza reasoning."),
}


def build_data(draft):
    from . import assignment as A
    from . import db, judge
    if draft:
        return load_fixture()
    gold = metrics.load(config.OUTPUTS / "gold.json")
    judge.narrative_conclusioni()
    p1, p2, p3 = _p12_section(1, gold), _p12_section(2, gold), _p3_section(gold)
    calls = {}
    for part in (1, 2, 3):
        calls.update(metrics.load(config.OUTPUTS / f"calls_p{part}.json"))
    tested = [a for a, m in config.MODELS.items() if m["in_report"]]
    first = {}
    for c in calls.values():
        if c.get("model_served") and c["model_alias"] not in first:
            first[c["model_alias"]] = c
    modelli = [{"alias": a, "id": first[a]["model_served"], "params": _params_str(first[a]),
                "parte": config.MODELS[a]["part"]} for a in tested if a in first]
    note = ["Il testo dell'esercitazione cita i pattern “3, 6, 7” per le soluzioni multiple; l'elenco dei pattern va "
            "però da 0 a 6, quindi ho trattato come pattern a soluzione multipla il 3, il 5 e il 6 (11 prompt in totale).",
            "Il reasoning di GPT e di Gemini 2.5 è esposto dall'API solo in forma riassunta; quello di Qwen3 è il testo completo."]
    if (metrics.load(config.OUTPUTS / "check.json") or {}).get("gpt_nr_fallback"):
        note.append("GPT senza reasoning: l'API non accetta effort=none su gpt-5.5, quindi ho usato openai/gpt-chat-latest "
                    "(temperature=0).")
    today = __import__("datetime").date.today()
    meta = {"titolo": "Text2SQL – Esercitazione", "nome": config.NOME, "matricola": config.MATRICOLA,
            "master": "Master Intelligenza Artificiale: Tecnologie, Modelli e Applicazioni",
            "data": f"{today.day} {MESI[today.month - 1]} {today.year}", "draft": False}
    testo = ("Ho interrogato tutti i modelli tramite OpenRouter, al posto delle web app e di LM Studio, con prompt "
             "identici per ogni modello e parametri fissati (temperature 0 dove supportata). Nella tabella sono "
             "indicati l'ID effettivamente servito e i parametri inviati; per i modelli piccoli il provider "
             "(e quindi la quantizzazione) è quello scelto da OpenRouter. Ho eseguito ogni query su 5 istanze di "
             "database: una base, con righe pensate per far emergere gli errori tipici, e 4 derivate da questa per "
             "mutazione (righe figlie eliminate, valori nulli, righe duplicate). Una risposta è corretta (EX=1) solo "
             "se il suo risultato coincide con quello della soluzione attesa su tutte e 5 le istanze; è parzialmente "
             "corretta se differisce solo per colonne in più, duplicati o ordinamento. Ho controllato la strategia "
             "richiesta analizzando la struttura della query.")
    app_a = [{"id": s["id"], "prompt": s["_full_prompt"]} for s in p1["schede"]] + \
            [{"id": f"Q{q}", "prompt": A.build_prompt_p3(q)} for q in A.Q_P3]
    app_b = []
    for c in sorted(calls.values(), key=lambda c: (c["part"], str(c["item_id"]), c["round"] or 0)):
        if c["part"] == 3 and c.get("reasoning"):
            app_b.append({"q": f"{c['item_id']} (giro {c['round']})", "alias": c["model_alias"], "reasoning": c["reasoning"]})
    ddl = [{"nome": sc, "sql": db.ddl_text(sc)} for sc in db.SCHEMAS]
    stats = [{"schema": sc, "tabella": t, "righe": v} for sc in db.SCHEMAS for t, v in db.row_counts(sc).items()]
    cost = {}
    for c in calls.values():
        if config.MODELS[c["model_alias"]]["in_report"]:
            x = cost.setdefault(c["model_alias"], [0, 0.0])
            x[0] += 1
            x[1] += c.get("cost_usd") or 0.0
    data = {"meta": meta,
            "metodologia": {"modelli": modelli, "testo": testo, "note": note},
            "p1": {**{k: v for k, v in p1.items() if not k.startswith("_")},
                   "commento": _read_narr("p1_commento_generale.md"), "intro": INTRO[1]},
            "p2": {**{k: v for k, v in p2.items() if not k.startswith("_")}, "grafico": "p2_accuratezza.svg",
                   "sintesi": _read_narr("p2_sintesi.md"), "intro": INTRO[2]},
            "p3": {**p3, "intro": INTRO[3]}, "conclusioni": _read_narr("conclusioni.md"),
            "appendici": {"A": app_a, "B": app_b,
                          "C": {"ddl": ddl, "stats": stats, "mutazioni": db.MUTATIONS},
                          "D": [{"alias": a, "chiamate": v[0], "costo": v[1]} for a, v in cost.items()]}}
    for s in data["p1"]["schede"] + data["p2"]["schede"]:
        s.pop("_full_prompt", None)
    data["_p2_points"] = [(a, config.MODELS[a]["params_b"], v["ex"]) for a, v in p2["_overall"].items()]
    return data


def _walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, o


def final_checks(data, pdf_name):
    import re
    problems = []
    if not re.fullmatch(r"\d+_TextSQL\.pdf", pdf_name):
        problems.append(f"nome file non conforme: {pdf_name} (MATRICOLA in .env deve essere numerica)")
    for path, v in _walk(data):
        if isinstance(v, str):
            if not v.strip():
                problems.append(f"campo vuoto: {path}")
            if re.search(r"PENDING|TODO", v):
                problems.append(f"PENDING/TODO in {path}")
    gold = metrics.load(config.OUTPUTS / "gold.json")
    for sec in ("p1", "p3"):
        for k, e in gold.get(sec, {}).items():
            if e.get("stato") == "da_rivedere":
                problems.append(f"gold {sec}/{k} ancora da_rivedere")
    corpora = {"data.json": json.dumps({k: v for k, v in data.items() if not k.startswith("_")},
                                       ensure_ascii=False, indent=1)}
    for f in sorted(config.NARRATIVES.glob("*.md")):
        corpora[f"narratives/{f.name}"] = f.read_text(encoding="utf-8")
    corpora["templates/report.typ"] = (config.TEMPLATES / "report.typ").read_text(encoding="utf-8")
    for name, text in corpora.items():
        for n, line in enumerate(text.splitlines(), 1):
            for w in FORBIDDEN:
                if re.search(re.escape(w), line, flags=re.I):
                    problems.append(f"{name}:{n}: '{w}' -> {line.strip()[:110]}")
    return problems


def compile_pdf(data):
    d = config.REPORT_DIR
    d.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in data.items() if not k.startswith("_")}
    (d / "data.json").write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copy(config.TEMPLATES / "report.typ", d / "report.typ")
    out = d / ("draft.pdf" if data["meta"]["draft"] else f"{config.MATRICOLA}_TextSQL.pdf")
    typst.compile(str(d / "report.typ"), output=str(out), root=str(d))
    return out


def run(draft=False):
    data = build_data(draft)
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    pts = data.get("_p2_points") or [(a, m["params_b"], 0.5) for a, m in config.MODELS.items() if m["part"] == 2]
    p2_chart(pts, config.REPORT_DIR / "p2_accuratezza.svg")
    if not draft:
        name = f"{config.MATRICOLA}_TextSQL.pdf"
        problems = final_checks(data, name)
        if problems:
            print("CONTROLLI FINALI FALLITI:")
            for p in problems:
                print("  -", p)
            raise SystemExit(1)
    out = compile_pdf(data)
    import re
    n = len(re.findall(rb"/Type\s*/Page[^s]", out.read_bytes()))
    print(f"PDF: {out} ({n} pagine)")
    return out
