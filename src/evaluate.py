"""Confronto dei risultati, controlli statici ed esito deterministico."""
import datetime
import decimal
import itertools
from collections import Counter
from functools import lru_cache

import duckdb
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope

from . import config, db

NULL = "<NULL>"
MAX_PERM_COLS = 6
MAX_SELECTIONS = 50000
PARTIAL_FLAGS = {"colonne_extra", "duplicati", "ordinamento"}


# ---------- normalizzazione ----------
def norm_value(v):
    if v is None:
        return NULL
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float, decimal.Decimal)):
        return float(f"{float(v):.6g}")  # ~ rel_tol 1e-6
    if isinstance(v, (datetime.date, datetime.time, datetime.datetime)):
        return v.isoformat()
    return str(v).strip()


def norm_rows(rows):
    return [tuple(norm_value(v) for v in r) for r in rows]


# ---------- confronto ----------
def _select(rows, sel):
    return [tuple(r[i] for i in sel) for r in rows]


def _selections(w, g):
    if w == g:
        if g <= MAX_PERM_COLS:
            return itertools.permutations(range(w))
        return iter([tuple(range(w))])
    n = 1
    for i in range(g):
        n *= (w - i)
    if n > MAX_SELECTIONS:
        return iter([])
    return itertools.permutations(range(w), g)


def _has_outer_order(sql):
    for d in ("duckdb", "postgres", "mysql"):
        try:
            ast = sqlglot.parse_one(sql, read=d)
            return bool(ast.args.get("order"))
        except Exception:
            continue
    return True  # non analizzabile: non penalizzo


def _cmp_key(a, b, desc):
    """-1/0/1 con NULL sempre ultimi."""
    if a is None and b is None:
        return 0
    if a is None:
        return 1
    if b is None:
        return -1
    try:
        c = (a > b) - (a < b)
    except TypeError:
        return 0
    return -c if desc else c


def _monotone(rows, order_by, sel):
    """rows: righe del modello (non normalizzate); order_by: [[col_gold, 'asc'|'desc'], ...]."""
    spec = [(sel[ci], d.lower() == "desc") for ci, d in order_by]
    for r1, r2 in zip(rows, rows[1:]):
        for ci, desc in spec:
            c = _cmp_key(r1[ci], r2[ci], desc)
            if c < 0:
                break
            if c > 0:
                return False
    return True


def _compare_one(gold_runs, model_runs, idx, order_by, model_sql):
    """Confronto su un sottoinsieme di istanze (indici idx). -> (ex, flags, selection, fail_idx)"""
    g_rows = [norm_rows(gold_runs[i]["rows"]) for i in idx]
    g_width = len(gold_runs[idx[0]]["cols"])
    m_rows = [norm_rows(model_runs[i]["rows"]) for i in idx]
    m_width = len(model_runs[idx[0]]["cols"])
    if m_width < g_width or g_width == 0:
        return 0, [], None
    g_counters = [Counter(r) for r in g_rows]
    g_sets = [set(r) for r in g_rows]
    exact = setmatch = None
    for sel in _selections(m_width, g_width):
        sel_rows = [_select(r, sel) for r in m_rows]
        if all(Counter(s) == gc for s, gc in zip(sel_rows, g_counters)):
            exact = sel
            break
        if setmatch is None and all(set(s) == gs for s, gs in zip(sel_rows, g_sets)):
            setmatch = sel
    flags = []
    extra = m_width > g_width
    if exact is not None:
        sel, ex = exact, 1
        if extra:
            flags.append("colonne_extra")
            ex = 0
    elif setmatch is not None:
        sel, ex = setmatch, 0
        flags.append("duplicati")
        if extra:
            flags.append("colonne_extra")
    else:
        return 0, [], None
    if order_by and (exact is not None or setmatch is not None):
        ok_order = _has_outer_order(model_sql) and all(
            _monotone(model_runs[i]["rows"], order_by, sel) for i in idx)
        if not ok_order:
            flags.append("ordinamento")
            ex = 0
    return ex, flags, sel


def _diff(gold_runs, model_runs, sel_hint=None):
    """Fino a 5 righe mancanti / in più sulla prima istanza che differisce."""
    for i, (g, m) in enumerate(zip(gold_runs, model_runs)):
        if m["status"] != "ok":
            return {"instance": db.INSTANCES[i], "errore": m["error"], "mancanti": [], "in_piu": []}
        gw = len(g["cols"])
        gc = Counter(norm_rows(g["rows"]))
        rows = norm_rows(m["rows"])
        if len(m["cols"]) >= gw:
            rows = [r[:gw] for r in rows]
        mc = Counter(rows)
        if gc != mc:
            return {"instance": db.INSTANCES[i],
                    "mancanti": [list(r) for r in list((gc - mc).elements())[:5]],
                    "in_piu": [list(r) for r in list((mc - gc).elements())[:5]],
                    "righe_attese": len(g["rows"]), "righe_modello": len(m["rows"])}
    return None


def compare(golds, model_runs, model_sql, order_by=None):
    """golds: lista di varianti accettate, ognuna = lista di 5 risultati di execute().
    -> {ex, ex_base, flags, statuses, variant, diff}"""
    statuses = [r["status"] for r in model_runs]
    out = {"ex": 0, "ex_base": 0, "flags": [], "statuses": statuses, "variant": None, "diff": None}
    if any(s != "ok" for s in statuses):
        out["diff"] = _diff(golds[0], model_runs)
        if statuses[0] == "ok":  # EX base può essere 1 anche se le istanze mutate falliscono
            pass
        return out
    all_idx = list(range(len(model_runs)))
    best_partial = None
    for v, g in enumerate(golds):
        if any(r["status"] != "ok" for r in g):
            continue
        ex, flags, _ = _compare_one(g, model_runs, all_idx, order_by, model_sql)
        exb, _, _ = _compare_one(g, model_runs, [0], order_by, model_sql)
        out["ex_base"] = max(out["ex_base"], exb)
        if ex == 1:
            out.update(ex=1, flags=[], variant=v)
            return out
        if flags and best_partial is None:
            best_partial = (v, flags)
    if best_partial:
        out["variant"], out["flags"] = best_partial
    out["diff"] = _diff(golds[0], model_runs)
    return out


def esito(ex, flags, statuses=None):
    if ex == 1:
        return "corretta"
    if flags and set(flags) <= PARTIAL_FLAGS:
        return "parzialmente corretta"
    return "errata"


# ---------- controlli statici ----------
def _parse(sql):
    for d in ("duckdb", "postgres", "mysql"):
        try:
            return sqlglot.parse_one(sql, read=d), d
        except Exception:
            continue
    return None, None


@lru_cache(maxsize=None)
def schema_dict(schema):
    con = duckdb.connect(str(db.db_path(schema, "base")), read_only=True)
    try:
        tables, cols, _, _ = db._meta(con)
        return {t: {c: ty for c, ty, _ in cols[t]} for t in tables}
    finally:
        con.close()


def _is_subq_in(n):
    return isinstance(n, exp.In) and (n.args.get("query") is not None or
                                      any(isinstance(e, (exp.Subquery, exp.Select)) for e in n.expressions))


def requirement_for(pattern, strategy):
    return strategy if strategy else f"P{pattern}"


def static_check(sql, requirement, schema=None):
    """-> True | False | 'non verificabile' | None (P4 non riconosciuta: decide il giudice)."""
    ast, dialect = _parse(sql)
    if ast is None:
        return False
    find = lambda t: ast.find(t) is not None
    r = requirement
    if r == "P0":
        return find(exp.Where)
    if r in ("P1", "JOIN"):
        return find(exp.Join)
    if r == "P2":
        return find(exp.Group) and find(exp.Having) and find(exp.AggFunc)
    if r == "IN":
        return any(_is_subq_in(n) and not isinstance(n.parent, exp.Not) for n in ast.find_all(exp.In))
    if r == "NOT IN":
        return any(_is_subq_in(n) and isinstance(n.parent, exp.Not) for n in ast.find_all(exp.In))
    if r == "INTERSECT":
        return find(exp.Intersect)
    if r == "EXCEPT":
        return find(exp.Except)
    if r == "CTE":
        return find(exp.With)
    if r == "Correlazione":
        try:
            q = qualify(ast.copy(), schema=schema_dict(schema) if schema else None, dialect=dialect)
            return any(s.is_correlated_subquery for s in traverse_scope(q))
        except Exception:
            return "non verificabile"
    if r == "P4":
        nots = [n for n in ast.find_all(exp.Not) if isinstance(n.this, exp.Exists)]
        if len(nots) >= 2:
            return True
        for h in ast.find_all(exp.Having):
            if h.find(exp.Count) and (h.find(exp.Subquery) or h.find(exp.Select)):
                return True
        for e in ast.find_all(exp.Except):
            if e.find_ancestor(exp.Subquery, exp.CTE):
                return True
        return None
    raise ValueError(f"requisito sconosciuto: {r}")
