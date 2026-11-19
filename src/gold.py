"""Stadio gold: domande P1, soluzioni attese P1/P3, database, validazione."""
import json

import duckdb
import sqlglot
from sqlglot import exp

from . import assignment as A
from . import config, db, evaluate as ev, llm

GOLD_PATH = config.OUTPUTS / "gold.json"
P3_SCHEMA = {q: f"p3_ex{es}" for q, (es, _) in A.Q_P3.items()}
MAX_PATCH = 2
SQL_RULES = ("Usa il dialetto DuckDB. Colonne di output con i nomi dello schema. "
             "Nessun parametro, nessun commento nel codice SQL.")


def _chat_json(alias, prompt, tag, max_tokens=None, tries=2):
    last = None
    for k in range(tries):
        msg = prompt if k == 0 else prompt + f"\n\nLa risposta precedente non era valida ({last}). Rispondi solo con JSON valido."
        kw = {"max_tokens": max_tokens} if max_tokens else {}
        r = llm.chat(alias, [{"role": "user", "content": msg}], role="support",
                     meta={"part": 0, "item_id": tag, "round": k}, **kw)
        try:
            return llm.extract_json(r["raw_output"])
        except Exception as e:
            last = str(e)[:100]
    raise RuntimeError(f"JSON non valido per {tag}: {last}")


# ---------- 1. domande Parte 1 ----------
def gen_questions_p1():
    ddl = db.ddl_text("biblioteca")
    pat = "\n".join(
        f"- Pattern {p}: {desc}; chiavi di gold_sql: {', '.join(repr(s or 'unica') for s in strats)}"
        for p, (desc, strats) in A.PATTERNS.items())
    prompt = f"""Devi preparare le domande di un esercizio di Text-to-SQL sul seguente schema (DuckDB).

{ddl}

Genera 3 candidati per ciascun pattern di difficoltà (0-6), con la soluzione SQL attesa per ogni strategia indicata.
{pat}

Vincoli:
- Pattern 0: la domanda è esattamente: {A.DOMANDA_P0}
  (la soluzione usa numero_copie >= 3 e ORDER BY anno_pubblicazione DESC).
- Domande in italiano, senza ambiguità, con le colonne di output nominate esplicitamente nel testo.
- Copri tabelle diverse tra i pattern: sale, dipendenti, prenotazioni, non solo LIBRO.
- Pattern 3, 5 e 6: le strategie devono dare lo stesso identico risultato su qualsiasi istanza.
  Per INTERSECT proietta chiavi oppure usa DISTINCT; per NOT IN usa una colonna non nullabile.
- Pattern 4: domanda di tipo "per ogni / tutti" (es. lettori che hanno preso in prestito tutti i libri di un autore).
- Pattern 2: usa GROUP BY, HAVING e una funzione aggregata.
- Se la soluzione ha un ORDER BY esterno, order_by elenca [indice della colonna di output (da 0), "asc"|"desc"]; altrimenti [].
- {SQL_RULES}

Rispondi solo con JSON:
{{"candidati": [{{"pattern": 0, "domanda": "...", "colonne_output": ["..."], "order_by": [[1, "desc"]],
 "gold_sql": {{"unica": "SELECT ..."}}}}, ...]}}"""
    data = _chat_json("opus-gold", prompt, "p1-domande", max_tokens=32000)
    out = {p: [] for p in A.PATTERNS}
    for c in data["candidati"]:
        p = int(c["pattern"])
        expected = {s or "unica" for s in A.PATTERNS[p][1]}
        if p in out and set(c["gold_sql"]) == expected:
            if p == 0:
                c["domanda"] = A.DOMANDA_P0
            c["order_by"] = c.get("order_by") or []
            out[p].append(c)
    return out


# ---------- 2. gold Parte 3 ----------
def gen_gold_p3():
    res = {}
    for q, (es, domanda) in A.Q_P3.items():
        ddl = db.ddl_text(f"p3_ex{es}")
        prompt = f"""Scrivi la soluzione SQL attesa (DuckDB) per la seguente domanda.

Schema:
{ddl}

Domanda:
{domanda}

- interpretazioni: elenco esplicito delle scelte interpretative non banali (es. cosa significa "copie vendute", unità di Duration, estremi inclusi o esclusi).
- gold_sql: la soluzione secondo la lettura più naturale.
- varianti_accettate: una query per ogni altra interpretazione ragionevole (anche nessuna).
- order_by: [] salvo che la domanda richieda un ordinamento.
- {SQL_RULES}

Rispondi solo con JSON:
{{"interpretazioni": ["..."], "gold_sql": "SELECT ...", "varianti_accettate": [], "order_by": []}}"""
        d = _chat_json("opus-gold", prompt, f"p3-gold-q{q}")
        d["varianti_accettate"] = d.get("varianti_accettate") or []
        d["order_by"] = d.get("order_by") or []
        res[q] = d
    return res


# ---------- 3. dati ----------
def _tables_in(sql):
    try:
        return {t.name for t in sqlglot.parse_one(sql, read="duckdb").find_all(exp.Table)}
    except Exception:
        return set()


def _base_problem(schema, sql):
    """None se il gold dà un risultato utile sulla base, altrimenti un testo con il problema."""
    r = db.execute(schema, "base", sql)
    if r["status"] != "ok":
        return f"la query gold non si esegue sulla base: {r['error']}"
    n = len(r["rows"])
    if n == 0:
        return "la query gold restituisce 0 righe"
    counts = {t: v[0] for t, v in db.row_counts_base(schema).items()}
    if n >= 5 and any(counts.get(t) == n for t in _tables_in(sql)):
        return f"la query gold restituisce tutta una tabella ({n} righe)"
    return None


DATA_RULES = """Genera uno script SQL di soli INSERT (DuckDB) per popolare le tabelle.
- 20-60 righe per tabella (di più nelle tabelle figlie), chiavi primarie ed esterne rispettate, INSERT in ordine di dipendenza.
- Identificatori interi piccoli (1..N); nelle patch usa solo identificatori maggiori di 1000.
- Per ogni domanda inserisci righe che soddisfano le condizioni letterali (generi, date, aeroporti...) e righe "trappola" che fanno sbagliare gli errori tipici: DISTINCT mancante, > al posto di >=, HAVING dimenticato, prestiti con data_restituzione nulla, autori senza libri, pareggi, valori appena sotto o sopra le soglie.
- Le colonne nullabili (asterisco) devono contenere anche NULL. Le colonne usate da NOT IN non sono nullabili.
- Per soglie alte (es. più di 5000 copie vendute, 200 passeggeri su un volo) usa INSERT ... SELECT ... FROM range(n) invece di righe scritte a mano.
- Rispondi solo con un blocco ```sql```."""


def _items_for(schema, golds_p1, golds_p3):
    items = []
    if schema == "biblioteca":
        for p, cands in golds_p1.items():
            for k, c in enumerate(cands):
                items.append({"id": f"P{p}-c{k}", "domanda": c["domanda"],
                              "sql": next(iter(c["gold_sql"].values()))})
    else:
        for q, g in golds_p3.items():
            if P3_SCHEMA[q] == schema:
                items.append({"id": f"Q{q}", "domanda": A.Q_P3[q][1], "sql": g["gold_sql"]})
    return items


def gen_data(schema, items):
    ddl = db.ddl_text(schema)
    qs = "\n".join(f"- [{i['id']}] {i['domanda']}\n  SQL atteso: {i['sql']}" for i in items)
    prompt = f"{DATA_RULES}\n\nSchema:\n{ddl}\n\nDomande (con la soluzione attesa):\n{qs}"
    err = None
    for attempt in range(3):
        msg = prompt if not err else prompt + f"\n\nIl tentativo precedente ha prodotto questo errore, correggilo: {err}"
        r = llm.chat("opus-gold", [{"role": "user", "content": msg}], role="support",
                     meta={"part": 0, "item_id": f"dati-{schema}", "round": attempt}, max_tokens=32000)
        script = llm.extract_block(r["raw_output"])
        try:
            db.build_base(schema, script)
            return
        except duckdb.Error as e:
            err = str(e)[:400]
    raise RuntimeError(f"dati {schema}: script non valido dopo 3 tentativi: {err}")


def patch_data(schema, items):
    for it in items:
        for n in range(MAX_PATCH):
            problem = _base_problem(schema, it["sql"])
            if problem is None:
                break
            ddl = db.ddl_text(schema)
            prompt = (f"{DATA_RULES}\n\nSchema:\n{ddl}\n\nDevi aggiungere righe (sole INSERT, identificatori > 1000) "
                      f"per la domanda seguente: {problem}.\nDomanda: {it['domanda']}\nSQL atteso: {it['sql']}\n"
                      f"Tentativo {n + 1}.")
            r = llm.chat("opus-gold", [{"role": "user", "content": prompt}], role="support",
                         meta={"part": 0, "item_id": f"patch-{schema}-{it['id']}", "round": n})
            try:
                db.apply_patch(schema, llm.extract_block(r["raw_output"]))
            except duckdb.Error as e:
                print(f"   patch {it['id']} non applicabile: {str(e)[:100]}")


# ---------- 4. validazione ----------
def _ds_sql(schema, domanda, colonne=None, interpretazioni=None):
    ddl = db.ddl_text(schema)
    extra = ""
    if colonne:
        extra += f"\nColonne di output: {', '.join(colonne)}"
    if interpretazioni:
        extra += "\nInterpretazioni da adottare: " + "; ".join(interpretazioni)
    prompt = (f"Scrivi una query SQL (DuckDB) per la domanda.\nSchema:\n{ddl}\nDomanda: {domanda}{extra}\n"
              "Restituisci solo il codice SQL.")
    r = llm.chat("deepseek", [{"role": "user", "content": prompt}], role="support",
                 meta={"part": 0, "item_id": f"ds-{schema}-{hash(domanda) & 0xffff}"})
    return llm.extract_sql(r["raw_output"])[0]


def _agrees(golds_runs, schema, sql, order_by):
    runs = db.execute_all(schema, sql) if sql else None
    if runs is None:
        return False, None
    r = ev.compare(golds_runs, runs, sql, order_by)
    return (r["ex"] == 1 or r["flags"] == ["ordinamento"]), r


def _rows_ok(runs):
    return sum(1 for r in runs if r["status"] == "ok" and len(r["rows"]) >= 1) >= 3


def check_p1(p, c):
    """-> (ok, problemi, righe)"""
    schema = "biblioteca"
    pr = []
    strat_runs = {}
    for s, sql in c["gold_sql"].items():
        runs = db.execute_all(schema, sql)
        if any(r["status"] != "ok" for r in runs):
            return False, [f"{s}: non si esegue ({next(r['error'] for r in runs if r['status'] != 'ok')[:80]})"], None
        strat_runs[s] = runs
        req = ev.requirement_for(p, None if s == "unica" else s)
        if ev.static_check(sql, req, schema) not in (True, None):
            pr.append(f"{s}: controllo statico {req} fallito")
    first = next(iter(strat_runs))
    for s, runs in strat_runs.items():
        if s != first and ev.compare([strat_runs[first]], runs, c["gold_sql"][s], c["order_by"])["ex"] != 1:
            pr.append(f"{s}: risultato diverso da {first}")
    if not _rows_ok(strat_runs[first]):
        pr.append("meno di 1 riga su 3 istanze")
    if pr:
        return False, pr, None
    ds = _ds_sql(schema, c["domanda"], c.get("colonne_output"))
    ok, _ = _agrees([strat_runs[first]], schema, ds, c["order_by"])
    if not ok:
        return False, ["secondo parere in disaccordo"], None
    return True, [], [len(r["rows"]) for r in strat_runs[first]]


def check_p3(q, g):
    schema = P3_SCHEMA[q]
    runs = db.execute_all(schema, g["gold_sql"])
    if any(r["status"] != "ok" for r in runs):
        return "da_rivedere", ["gold non eseguibile"], None, None
    variants = [runs]
    kept = []
    for v in g["varianti_accettate"]:
        vr = db.execute_all(schema, v)
        if all(r["status"] == "ok" for r in vr):
            variants.append(vr)
            kept.append(v)
    g["varianti_accettate"] = kept
    righe = [len(r["rows"]) for r in runs]
    if not _rows_ok(runs):
        return "da_rivedere", ["meno di 1 riga su 3 istanze"], righe, None
    ds = _ds_sql(schema, A.Q_P3[q][1], interpretazioni=g["interpretazioni"])
    ok, res = _agrees(variants, schema, ds, g["order_by"])
    if ok:
        return "verificato", [], righe, ds
    return "da_rivedere", ["secondo parere in disaccordo"], righe, ds


# ---------- override ----------
def _load_overrides():
    try:
        return json.loads(config.GOLD_OVERRIDES.read_text(encoding="utf-8"))
    except Exception:
        return {"p1": {}, "p3": {}}


def _skeleton_p3(q, g, ds_sql):
    schema = P3_SCHEMA[q]
    diff = None
    if ds_sql:
        gr = db.execute_all(schema, g["gold_sql"])
        dr = db.execute_all(schema, ds_sql)
        diff = ev._diff(gr, dr) if all(r["status"] == "ok" for r in dr) else {"errore": "query DeepSeek non eseguibile"}
    return {"_domanda": A.Q_P3[q][1], "_gold_sql_attuale": g["gold_sql"], "_secondo_parere_sql": ds_sql,
            "_righe_diverse": diff, "gold_sql": None, "varianti_accettate": None, "order_by": None}


def apply_overrides(gold, ov):
    for sec in ("p1", "p3"):
        for k, o in (ov.get(sec) or {}).items():
            if not o.get("gold_sql"):
                continue
            entry = gold[sec].setdefault(k, {})
            for f in ("domanda", "colonne_output", "order_by", "gold_sql", "interpretazioni", "varianti_accettate"):
                if o.get(f) is not None:
                    entry[f] = o[f]
            entry["stato"] = "rivisto"


# ---------- orchestrazione ----------
def run():
    config.OUTPUTS.mkdir(exist_ok=True)
    print("[gold] domande P1 ...")
    cands = gen_questions_p1()
    print("   candidati:", {p: len(v) for p, v in cands.items()})
    print("[gold] soluzioni P3 ...")
    p3 = gen_gold_p3()
    ov = _load_overrides()
    for schema in db.SCHEMAS:
        items = _items_for(schema, cands, p3)
        print(f"[gold] dati {schema} ({len(items)} domande) ...")
        gen_data(schema, items)
        patch_data(schema, items)
        db.build_instances(schema)
    gold = {"p1": {}, "p3": {}, "righe": {}}
    for p, cs in cands.items():
        entry = {"stato": "da_rivedere", "note": []}
        for k, c in enumerate(cs):
            ok, pr, righe = check_p1(p, c)
            if ok:
                entry = {**c, "stato": "verificato", "candidato": k, "righe": righe, "note": []}
                break
            entry["note"].append(f"c{k}: " + "; ".join(pr))
        if entry["stato"] != "verificato" and cs:
            entry.update({k2: v for k2, v in cs[0].items()})
        gold["p1"][str(p)] = entry
        print(f"   P{p}: {entry['stato']} {entry['note']}")
    for q, g in p3.items():
        stato, pr, righe, ds = check_p3(q, g)
        entry = {**g, "stato": stato, "righe": righe, "note": pr}
        gold["p3"][str(q)] = entry
        if stato == "da_rivedere" and str(q) not in ov.get("p3", {}):
            ov.setdefault("p3", {})[str(q)] = _skeleton_p3(q, g, ds)
        print(f"   Q{q}: {stato} {pr} righe={righe}")
    for p, e in gold["p1"].items():
        if e["stato"] == "da_rivedere" and p not in ov.get("p1", {}):
            ov.setdefault("p1", {})[p] = {"_note": e["note"], "_candidati": [c["gold_sql"] for c in cands[int(p)]],
                                          "domanda": None, "colonne_output": None, "order_by": None, "gold_sql": None}
    apply_overrides(gold, ov)
    config.GOLD_OVERRIDES.write_text(json.dumps(ov, ensure_ascii=False, indent=1), encoding="utf-8")
    gold["righe"] = {s: db.row_counts(s) for s in db.SCHEMAS}
    GOLD_PATH.write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")
    pend = [f"P{p}" for p, e in gold["p1"].items() if e["stato"] == "da_rivedere"] + \
           [f"Q{q}" for q, e in gold["p3"].items() if e["stato"] == "da_rivedere"]
    print(f"[gold] spesa totale ${llm.total_spent():.3f}; da rivedere: {pend or 'nessuna'}")
    if pend:
        print(f"   compila {config.GOLD_OVERRIDES} (campo gold_sql) e rilancia `gold`")
