"""Valutazione (eval), giudizi raggruppati, ottimizzatore di prompt e narrative."""
import json
import re

from . import assignment as A
from . import config, db, evaluate as ev, llm, metrics, runs

CATEGORIE = ["sintassi", "dialetto", "schema linking", "join", "filtro", "aggregazione", "HAVING", "NULL",
             "duplicati", "ordinamento", "colonne di output", "strategia non rispettata", "logica di divisione",
             "subquery o correlazione", "interpretazione della domanda", "formato dell'output"]

VOCE = ("Scrivi in italiano, in prima persona singolare, con il tono di uno studente che analizza le risposte "
        "(\"ho verificato\", \"ho notato\"). Non citare mai giudici, valutatori, modelli di supporto, procedure "
        "automatiche o la parola \"gold\": parla di \"soluzione attesa\". L'esito (corretta, parzialmente corretta, "
        "errata) è un dato di fatto verificato eseguendo le query: non lo puoi cambiare, ne spieghi le ragioni.")


def evals_path(part):
    return config.OUTPUTS / f"evals_p{part}.json"


def load_evals(part):
    return metrics.load(evals_path(part))


def _no_runs(msg="nessuna query estratta"):
    return [{"status": "parse_error", "cols": [], "rows": [], "error": msg, "exec_sql": None,
             "dialect_path": "native"} for _ in db.INSTANCES]


def _first_error(rs):
    return next((r["error"] for r in rs if r["status"] != "ok"), None)


def judge_json(prompt, tag, aliases, validate, effort):
    last = None
    for k in range(3):
        msg = prompt if k == 0 else prompt + (f"\n\nLa risposta precedente non era valida ({last}). Rispondi solo con JSON valido; "
                                              "i campi reasoning_corretto e segue_reasoning devono essere sempre \"sì\", \"parzialmente\" o \"no\", mai null.")
        r = llm.chat("opus-judge", [{"role": "user", "content": msg}], role="support",
                     meta={"part": 0, "item_id": tag, "round": k}, reasoning={"effort": effort})
        try:
            d = llm.extract_json(r["raw_output"])
            missing = [a for a in aliases if a not in d]
            if missing:
                raise ValueError(f"mancano gli alias {missing}")
            for a in aliases:
                validate(d[a])
            return d
        except Exception as e:
            last = str(e)[:150]
    raise RuntimeError(f"giudizio non valido per {tag}: {last} (revisione manuale)")


def _val_p12(v):
    if not isinstance(v.get("commento"), str) or not v["commento"].strip():
        raise ValueError("commento mancante")
    v["categorie_errore"] = [c for c in (v.get("categorie_errore") or []) if c in CATEGORIE]
    if v.get("divisione_ok") not in (True, False, None):
        v["divisione_ok"] = None


# ---------- Parti 1 e 2 ----------
def eval_p12(part):
    calls, gold = runs.load_calls(part), runs.load_gold()
    schema = "biblioteca"
    by_item = {}
    for c in calls.values():
        by_item.setdefault(c["item_id"], []).append(c)
    evals = {}
    for item_id, cs in by_item.items():
        pattern, strategy = cs[0]["pattern"], cs[0]["strategy"]
        g = gold["p1"][str(pattern)]
        gsql = g["gold_sql"][strategy or "unica"]
        gold_runs = db.execute_all(schema, gsql)
        req = ev.requirement_for(pattern, strategy)
        facts, recs = {}, {}
        for c in cs:
            sql = c.get("sql")
            mr = db.execute_all(schema, sql) if sql else _no_runs()
            cmp_ = ev.compare([gold_runs], mr, sql or "", g.get("order_by"))
            st = ev.static_check(sql, req, schema) if sql else False
            e = {"call_id": c["call_id"], "part": part, "item_id": item_id, "alias": c["model_alias"],
                 "round": 1, "ex": cmp_["ex"], "ex_base": cmp_["ex_base"], "flags": cmp_["flags"],
                 "esito": ev.esito(cmp_["ex"], cmp_["flags"]), "statuses": cmp_["statuses"],
                 "errore": _first_error(mr), "static": st, "format_ok": c["format_ok"], "diff": cmp_["diff"],
                 "dialect_path": mr[0]["dialect_path"]}
            recs[c["model_alias"]] = e
            facts[c["model_alias"]] = {
                "sql": sql, "esito": e["esito"], "flag": e["flags"], "errore_esecuzione": e["errore"],
                "righe_diverse_prima_istanza_che_fallisce": e["diff"],
                "controllo_strategia": ("rispettata" if st is True else "non rispettata" if st is False
                                        else "non verificabile" if st == "non verificabile" else "da valutare"),
                "solo_codice_sql_richiesto_rispettato": c["format_ok"],
                "testo_extra": (c.get("nl_output") or "")[:300]}
        aliases = list(recs)
        prompt = f"""{VOCE}

Esercizio: scrivere una query SQL a partire da una domanda sullo schema Biblioteca.
Domanda: {g['domanda']}
Strategia richiesta: {strategy or 'nessuna in particolare (pattern ' + str(pattern) + ')'}
Soluzione attesa: {gsql}

Dati verificati per ogni modello:
{json.dumps(facts, ensure_ascii=False, indent=1)}

Per ogni modello restituisci:
- categorie_errore: sottoinsieme di {CATEGORIE} ([] se corretta);
- commento: massimo 60 parole;
- divisione_ok: solo se il pattern è 4 e controllo_strategia è "da valutare", true/false se la query realizza la divisione relazionale (per ogni / tutti); altrimenti null.

Rispondi solo con JSON: {{"<alias>": {{"categorie_errore": [], "commento": "...", "divisione_ok": null}}}}"""
        j = judge_json(prompt, f"judge-p{part}-{item_id}", aliases, _val_p12, "low")
        for a, e in recs.items():
            v = j[a]
            cats = list(v["categorie_errore"])
            if e["esito"] != "corretta":
                if e["statuses"][0] == "parse_error" and "sintassi" not in cats:
                    cats.append("sintassi")
            if not e["format_ok"] and "formato dell'output" not in cats:
                cats.append("formato dell'output")
            st = e["static"]
            if st is None:
                e["rispetta_strategia"], e["strategy_source"] = v["divisione_ok"], "judge"
            else:
                e["rispetta_strategia"], e["strategy_source"] = st, "static"
            if e["rispetta_strategia"] is False and "strategia non rispettata" not in cats:
                cats.append("strategia non rispettata")
            e["categorie_errore"], e["commento"] = cats, v["commento"].strip()
            evals[e["call_id"]] = e
        print(f"  giudicato {item_id}: " + ", ".join(f"{a}={r['esito']}" for a, r in recs.items()))
    evals_path(part).write_text(json.dumps(evals, ensure_ascii=False, indent=1), encoding="utf-8")
    t = metrics.p12_tables(part)
    print(f"[eval p{part}] EX complessivo:", {a: round(v["ex"], 2) for a, v in t["overall"].items()})
    print(f"   spesa totale ${llm.total_spent():.3f}")


# ---------- Parte 3 ----------
def _tri(x):
    x = str(x).strip().lower().rstrip(".")
    if x in ("si", "sì", "yes", "true"):
        return "sì"
    if x in ("no", "false"):
        return "no"
    if x.startswith("parzial") or x.startswith("in parte"):
        return "parzialmente"
    return x


def _val_p3(v):
    for k in ("reasoning_corretto", "segue_reasoning"):
        v[k] = _tri(v.get(k))
        if v[k] not in ("sì", "parzialmente", "no"):
            raise ValueError(f"{k} non valido: {v[k][:40]}")
    for k in ("passi_mancanti", "passi_errati", "passi_fuori_ordine", "passi_ridondanti"):
        if not isinstance(v.get(k), list):
            v[k] = []
    for k in ("commento_reasoning", "commento_soluzione"):
        if not isinstance(v.get(k), str) or not v[k].strip():
            raise ValueError(f"{k} mancante")
    v["categorie_errore"] = [c for c in (v.get("categorie_errore") or []) if c in CATEGORIE]


def _val_nr(v):
    v["output_corretto"] = _tri(v.get("output_corretto"))
    if v["output_corretto"] not in ("sì", "parzialmente", "no"):
        raise ValueError("output_corretto non valido")
    for k in ("commento_output", "commento_soluzione", "confronto_gpt_reasoning", "confronto_gpt_soluzione"):
        if not isinstance(v.get(k), str) or not v[k].strip():
            raise ValueError(f"{k} mancante")
    v["categorie_errore"] = [c for c in (v.get("categorie_errore") or []) if c in CATEGORIE]


def _p3_golds(g):
    return [g["gold_sql"]] + list(g.get("varianti_accettate") or [])


def _p3_exec(q, g, call):
    schema = runs_schema(q)
    golds = [db.execute_all(schema, s) for s in _p3_golds(g)]
    sql = call.get("sql")
    mr = db.execute_all(schema, sql) if sql else _no_runs()
    cmp_ = ev.compare(golds, mr, sql or "", g.get("order_by"))
    return cmp_, mr


def runs_schema(q):
    from .gold import P3_SCHEMA
    return P3_SCHEMA[q]


def eval_p3(round_):
    calls, gold = runs.load_calls(3), runs.load_gold()
    old = load_evals(3)
    evals = {k: v for k, v in old.items() if v.get("round") != round_}
    for q in A.Q_P3:
        item = f"Q{q}"
        g = gold["p3"][str(q)]
        es, domanda = A.Q_P3[q]
        cs = [c for c in calls.values() if c["item_id"] == item and c["round"] == round_
              and c["model_alias"] != "gpt-nr"]
        if cs:
            facts, recs = {}, {}
            for c in cs:
                cmp_, mr = _p3_exec(q, g, c)
                e = {"call_id": c["call_id"], "part": 3, "item_id": item, "alias": c["model_alias"],
                     "round": round_, "ex": cmp_["ex"], "ex_base": cmp_["ex_base"], "flags": cmp_["flags"],
                     "esito": ev.esito(cmp_["ex"], cmp_["flags"]), "statuses": cmp_["statuses"],
                     "errore": _first_error(mr), "diff": cmp_["diff"], "format_ok": c["format_ok"],
                     "soluzione_corretta": "sì" if cmp_["ex"] == 1 else "no"}
                recs[c["model_alias"]] = e
                facts[c["model_alias"]] = {
                    "reasoning (" + str(c["reasoning_type"]) + ")": c.get("reasoning") or "(non disponibile)",
                    "sql": c.get("sql"), "esito_esecuzione": e["esito"], "flag": e["flags"],
                    "errore_esecuzione": e["errore"], "righe_diverse": e["diff"]}
            prompt = f"""{VOCE}

Esercizio: query complessa su schema {runs_schema(q)} (prompt in inglese).
Domanda: {domanda}
Soluzione attesa: {g['gold_sql']}
Varianti accettate (altre letture ragionevoli): {g.get('varianti_accettate') or 'nessuna'}
Interpretazioni considerate: {g.get('interpretazioni')}
Prompt usato (giro {round_}):
{cs[0]['prompt'] if len({c['prompt'] for c in cs}) == 1 else '(diverso per modello, vedi sotto)'}

Per ogni modello ti do il reasoning, lo SQL e l'esito dell'esecuzione. Analizza il reasoning passo per passo.
{json.dumps(facts, ensure_ascii=False, indent=1)}

Per ogni modello restituisci:
- reasoning_corretto: "sì" | "parzialmente" | "no";
- passi_mancanti, passi_errati, passi_fuori_ordine, passi_ridondanti: liste di stringhe brevi ([] se nessuno);
- commento_reasoning (max 80 parole);
- segue_reasoning: la soluzione SQL segue il reasoning? "sì" | "parzialmente" | "no";
- commento_soluzione (max 60 parole);
- categorie_errore: sottoinsieme di {CATEGORIE} ([] se corretta).

Rispondi solo con JSON: {{"<alias>": {{...}}}}"""
            j = judge_json(prompt, f"judge-p3-{item}-r{round_}", list(recs), _val_p3, "medium")
            for a, e in recs.items():
                v = j[a]
                e.update({k: v[k] for k in ("reasoning_corretto", "passi_mancanti", "passi_errati",
                                            "passi_fuori_ordine", "passi_ridondanti", "commento_reasoning",
                                            "segue_reasoning", "commento_soluzione", "categorie_errore")})
                evals[e["call_id"]] = e
            print(f"  {item} r{round_}: " + ", ".join(f"{a}=ex{r['ex']}" for a, r in recs.items()))
        if round_ == 2 and q in (4, 10):
            nr = next((c for c in calls.values() if c["item_id"] == item and c["model_alias"] == "gpt-nr"), None)
            if nr:
                _eval_nr(q, g, nr, calls, evals)
    evals_path(3).write_text(json.dumps(evals, ensure_ascii=False, indent=1), encoding="utf-8")
    if round_ == 1:
        optimize_prompts()
    print(f"[eval p3 r{round_}] spesa totale ${llm.total_spent():.3f}")


def _eval_nr(q, g, nr, calls, evals):
    es, domanda = A.Q_P3[q]
    cmp_, mr = _p3_exec(q, g, nr)
    gr = [c for c in calls.values() if c["item_id"] == f"Q{q}" and c["model_alias"] == "gpt-r"]
    gr = sorted(gr, key=lambda c: c["round"])[-1] if gr else None
    gr_ev = next((e for e in evals.values() if gr and e["call_id"] == gr["call_id"]), None)
    prompt = f"""{VOCE}

Confronto tra GPT senza reasoning e GPT con reasoning sulla stessa domanda (prompt in inglese).
Domanda: {domanda}
Soluzione attesa: {g['gold_sql']}

GPT senza reasoning: testo di output (oltre al codice): {nr.get('nl_output') or '(nessuno: solo codice SQL)'}
SQL: {nr.get('sql')}
Esito esecuzione: {ev.esito(cmp_['ex'], cmp_['flags'])} (errore: {_first_error(mr)}; righe diverse: {cmp_['diff']})

GPT con reasoning: reasoning ({gr['reasoning_type'] if gr else '-'}): {(gr or {}).get('reasoning') or '(non disponibile)'}
SQL: {(gr or {}).get('sql')}
Esito: {(gr_ev or {}).get('esito')}

Restituisci:
- output_corretto: "sì" | "parzialmente" | "no" (il testo di output è corretto/utile; se c'è solo codice SQL valuta se rispetta la richiesta "solo codice SQL");
- commento_output (max 50 parole);
- commento_soluzione (max 60 parole);
- confronto_gpt_reasoning: confronto tra GPT con e senza reasoning sul ragionamento visibile (max 80 parole);
- confronto_gpt_soluzione: confronto tra le due soluzioni SQL (max 80 parole);
- categorie_errore: sottoinsieme di {CATEGORIE}.

Rispondi solo con JSON: {{"gpt-nr": {{...}}}}"""
    j = judge_json(prompt, f"judge-p3-Q{q}-nr", ["gpt-nr"], _val_nr, "medium")["gpt-nr"]
    e = {"call_id": nr["call_id"], "part": 3, "item_id": f"Q{q}", "alias": "gpt-nr", "round": 2,
         "ex": cmp_["ex"], "ex_base": cmp_["ex_base"], "flags": cmp_["flags"],
         "esito": ev.esito(cmp_["ex"], cmp_["flags"]), "statuses": cmp_["statuses"], "errore": _first_error(mr),
         "diff": cmp_["diff"], "format_ok": nr["format_ok"], "soluzione_corretta": "sì" if cmp_["ex"] == 1 else "no",
         **{k: j[k] for k in ("output_corretto", "commento_output", "commento_soluzione",
                              "confronto_gpt_reasoning", "confronto_gpt_soluzione", "categorie_errore")}}
    evals[nr["call_id"]] = e
    print(f"  Q{q} gpt-nr: ex{e['ex']}")


# ---------- ottimizzatore dei prompt (giro 2) ----------
def _tokens(text, drop):
    return [t for t in re.findall(r"\w+|[^\w\s]", text.lower()) if t not in drop]


def leaks(notes_text, golds, schema_names):
    if re.search(r"\bSELECT\b[\s\S]*\bFROM\b", notes_text, flags=re.I):
        return "contiene una query SQL"
    drop = {s.lower() for s in schema_names}
    nt = _tokens(notes_text, drop)
    grams = {tuple(nt[i:i + 8]) for i in range(len(nt) - 7)}
    for g in golds:
        gt = _tokens(g, drop)
        for i in range(len(gt) - 7):
            if tuple(gt[i:i + 8]) in grams:
                return "contiene un frammento della soluzione"
    return None


def optimize_prompts():
    calls, gold, evals = runs.load_calls(3), runs.load_gold(), load_evals(3)
    out = {}
    for q in A.Q_P3:
        item = f"Q{q}"
        wrong = [e for e in evals.values() if e["item_id"] == item and e["round"] == 1 and e["ex"] == 0
                 and e["alias"] != "gpt-nr"]
        if not wrong:
            continue
        g = gold["p3"][str(q)]
        es, domanda = A.Q_P3[q]
        base = A.build_prompt_p3(q)
        schema_names = {n for t, cols, _ in A.SCHEMI_P3[es] for n in [t] + cols}
        facts = {}
        for e in wrong:
            c = calls[e["call_id"]]
            facts[e["alias"]] = {"reasoning": (c.get("reasoning") or "")[:8000], "sql": c.get("sql"),
                                 "esito": e["esito"], "categorie_errore": e["categorie_errore"],
                                 "flag": e["flags"], "errore_esecuzione": e["errore"]}
        feedback, notes = "", None
        for attempt in range(3):
            prompt = f"""Devo migliorare il prompt di un esercizio Text-to-SQL dopo un primo tentativo sbagliato di alcuni modelli.
Prompt originale:
{base}

Interpretazioni ragionevoli della domanda: {g.get('interpretazioni')}

Tentativi sbagliati:
{json.dumps(facts, ensure_ascii=False, indent=1)}

Per ciascun modello sbagliato scrivi 1-3 note brevi in inglese da aggiungere al prompt: chiarimenti sul significato dei termini della domanda, sulle assunzioni da adottare o sui punti in cui il suo ragionamento è andato fuori strada. Vietato inserire codice SQL, nomi di operatori da usare o frammenti di una soluzione.{feedback}
Rispondi solo con JSON: {{"<alias>": ["nota", ...]}}"""
            r = llm.chat("opus-text", [{"role": "user", "content": prompt}], role="support",
                         meta={"part": 0, "item_id": f"opt-{item}", "round": attempt})
            try:
                cand = llm.extract_json(r["raw_output"])
                bad = [(a, leaks(" ".join(cand[a]), _p3_golds(g), schema_names)) for a in facts]
                bad = [(a, why) for a, why in bad if why]
                if not bad:
                    notes = cand
                    break
                feedback = f"\nIl tentativo precedente è stato scartato ({bad}). Riscrivi senza SQL né frammenti di soluzione."
            except Exception as ex_:
                feedback = f"\nRisposta non valida ({str(ex_)[:80]}). Rispondi solo con JSON."
        if notes is None:
            print(f"  {item}: prompt aggiornato NON generato (anti-leak): decidere a mano in {runs.prompts_r2_path().name}")
            continue
        out[str(q)] = {}
        for a in facts:
            head, _ = base.rsplit("SQL code:", 1)
            bullets = "\n".join(f"- {n}" for n in notes[a])
            out[str(q)][a] = f"{head}Notes:\n{bullets}\n\nSQL code:"
        print(f"  {item}: prompt aggiornati per {list(facts)}")
    runs.prompts_r2_path().write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- narrative ----------
FORBIDDEN = "Opus, DeepSeek, Fable, Claude, Anthropic, giudice, gold, pipeline, LLM di supporto"
STILE = (f"Scrivi in italiano, in prima persona singolare, con i verbi della richiesta (\"ho formulato\", \"ho scritto "
         f"la soluzione attesa\", \"ho analizzato\"). Non nominare mai: {FORBIDDEN}. Usa solo paragrafi di testo "
         "semplice (niente elenchi, niente grassetto) e, dove indicato, titoli nella forma \"## Titolo\". "
         "Cita numeri concreti dai dati. Sii sintetico e specifico, evita frasi generiche.")


def _narrative(name, prompt):
    path = config.NARRATIVES / name
    if path.exists():
        return
    config.NARRATIVES.mkdir(parents=True, exist_ok=True)
    r = llm.chat("opus-text", [{"role": "user", "content": prompt}], role="support",
                 meta={"part": 0, "item_id": name})
    path.write_text(r["raw_output"].strip() + "\n", encoding="utf-8")
    print(f"  narrativa scritta: {name}")


def narrative_p1():
    t = metrics.p12_tables(1)
    _narrative("p1_commento_generale.md", f"""{STILE}
Parte 1: ho confrontato tre modelli proprietari (gpt, gemini, codestral) su 11 prompt SQL (pattern 0-6, con strategie imposte nei pattern 3, 5, 6).
Dati (EX = accuratezza di esecuzione su 5 istanze, [EX, EX sulla sola istanza base]; overall: ex, strategia rispettata, formato rispettato; categorie di errore):
{metrics.short_table(t)}
Scrivi il commento generale con tre sezioni: "## Punti forti e deboli di ciascun modello", "## Confronto tra i modelli", "## Confronto tra i tipi di prompt" (pattern semplici contro pattern con strategia imposta).""")


def narrative_p2():
    t1, t2 = metrics.p12_tables(1), metrics.p12_tables(2)
    sizes = {a: m["params_b"] for a, m in config.MODELS.items() if m["part"] == 2}
    _narrative("p2_sintesi.md", f"""{STILE}
Parte 2: gli stessi 11 prompt della Parte 1 su 5 modelli open source da 1B a 8B (parametri in miliardi: {sizes}).
Dati Parte 2: {metrics.short_table(t2)}
Dati Parte 1 (per confronto): {metrics.short_table(t1)}
Scrivi una sintesi (3-4 paragrafi) che risponda a: a che taglia il modello smette di produrre SQL eseguibile; quali pattern cedono per primi; quanto spesso i modelli ignorano il formato "solo codice SQL" o la strategia imposta; quanto distano dal migliore modello proprietario.""")


def narratives_p3():
    calls, gold, evals = runs.load_calls(3), runs.load_gold(), load_evals(3)
    for q in A.Q_P3:
        item = f"Q{q}"
        es = [e for e in evals.values() if e["item_id"] == item and e["alias"] != "gpt-nr"]
        if not es:
            continue
        rows = []
        for e in sorted(es, key=lambda e: (e["round"], e["alias"])):
            rows.append({"modello": e["alias"], "giro": e["round"], "esito": e["esito"],
                         "reasoning_corretto": e.get("reasoning_corretto"), "passi_errati": e.get("passi_errati"),
                         "segue_reasoning": e.get("segue_reasoning"), "categorie": e["categorie_errore"],
                         "commento_reasoning": e.get("commento_reasoning"),
                         "commento_soluzione": e.get("commento_soluzione")})
        _narrative(f"p3_q{q:02d}_confronti.md", f"""{STILE}
Query {item}: {A.Q_P3[q][1]}
Ho analizzato tre modelli con reasoning. Risultati (giro 1 ed eventuale giro 2 dopo il prompt aggiornato):
{json.dumps(rows, ensure_ascii=False, indent=1)}
Scrivi due sezioni, ciascuna di un solo paragrafo: "## Confronto modelli (reasoning)" (qualità e ordine dei ragionamenti a confronto) e "## Confronto modelli (soluzione SQL)" (correttezza e differenze tra le query).""")


def narrative_conclusioni():
    t1, t2, t3 = metrics.p12_tables(1), metrics.p12_tables(2), metrics.p3_tables()
    _narrative("conclusioni.md", f"""{STILE}
Scrivi le conclusioni complessive (mezza pagina, 2-3 paragrafi, senza titoli) dell'esercitazione Text2SQL.
Parte 1 (modelli proprietari): {metrics.short_table(t1['overall'])}
Parte 2 (modelli ≤ 8B): {metrics.short_table(t2['overall'])}
Parte 3 (modelli con reasoning, giro 1 contro giro 2): {metrics.short_table(t3)}""")
