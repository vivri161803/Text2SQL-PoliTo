"""DDL, istanze base, mutazioni deterministiche, esecuzione con timeout."""
import random
import shutil
import threading

import duckdb
import sqlglot

from . import config

SCHEMAS = ["biblioteca", "p3_ex1", "p3_ex2", "p3_ex3", "p3_ex4", "p3_ex5"]
INSTANCES = ["base", "m1", "m2", "m3", "m4"]
MUTATIONS = [
    "m1: elimino il 30% delle righe di ogni tabella figlia (solo righe non referenziate)",
    "m2: metto a NULL il 50% dei valori delle colonne nullabili",
    "m3: duplico il 30% delle righe figlie con chiave nuova (intero: max+1; date: +1 giorno)",
    "m4: m1 + m2 + m3 con un seed diverso",
]
SEEDS = {"m1": 101, "m2": 202, "m3": 303, "m4": 404}
TIMEOUT_S = 10


def db_path(schema, inst):
    return config.DBS_DIR / f"{schema}_{inst}.duckdb"


def ddl_text(schema):
    return (config.SCHEMAS_DIR / f"{schema}.sql").read_text(encoding="utf-8")


def build_base(schema, inserts_sql):
    """Crea l'istanza base da DDL + INSERT. Solleva se qualcosa non compila."""
    config.DBS_DIR.mkdir(parents=True, exist_ok=True)
    p = db_path(schema, "base")
    p.unlink(missing_ok=True)
    con = duckdb.connect(str(p))
    try:
        con.execute(ddl_text(schema))
        con.execute(inserts_sql)
    finally:
        con.close()


def apply_patch(schema, inserts_sql):
    """Aggiunge INSERT alla base (patch di Opus). Poi vanno rigenerate le mutate."""
    con = duckdb.connect(str(db_path(schema, "base")))
    try:
        con.execute(inserts_sql)
    finally:
        con.close()


# ---------- metadata ----------
def _meta(con):
    tables = [r[0] for r in con.execute("select table_name from information_schema.tables "
                                        "where table_schema='main'").fetchall()]
    cols, pk, fks = {}, {}, {}
    for t in tables:
        cols[t] = con.execute("select column_name, data_type, is_nullable from information_schema.columns "
                              "where table_name=? order by ordinal_position", [t]).fetchall()
        pk[t], fks[t] = [], []
    for t, typ, cc, ref in con.execute("select table_name, constraint_type, constraint_column_names, referenced_table "
                                       "from duckdb_constraints()").fetchall():
        if typ == "PRIMARY KEY":
            pk[t] = list(cc)
        elif typ == "FOREIGN KEY":
            fks[t].append((list(cc), ref))
    return tables, cols, pk, fks


def _q(name):
    return '"' + name.replace('"', '""') + '"'


def _try(con, sql, params=None):
    try:
        con.execute(sql, params or [])
        return True
    except duckdb.Error:
        return False


# ---------- mutazioni ----------
def _m1(con, rng, meta):
    tables, cols, pk, fks = meta
    for t in tables:
        if not fks[t]:
            continue  # tabella padre pura: non si tocca
        rids = [r[0] for r in con.execute(f"select rowid from {_q(t)}").fetchall()]
        for rid in rng.sample(rids, int(len(rids) * 0.3)):
            _try(con, f"delete from {_q(t)} where rowid = ?", [rid])  # fallisce se referenziata


def _m2(con, rng, meta):
    tables, cols, pk, fks = meta
    for t in tables:
        protected = set(pk[t]) | {c for cc, _ in fks[t] for c in cc}
        for name, _, nullable in cols[t]:
            if nullable != "YES" or name in protected:
                continue
            rids = [r[0] for r in con.execute(f"select rowid from {_q(t)}").fetchall()]
            for rid in rng.sample(rids, int(len(rids) * 0.5)):
                _try(con, f"update {_q(t)} set {_q(name)} = NULL where rowid = ?", [rid])


def _m3(con, rng, meta):
    tables, cols, pk, fks = meta
    for t in tables:
        if not fks[t]:
            continue
        fk_cols = {c for cc, _ in fks[t] for c in cc}
        free_pk = [c for c in pk[t] if c not in fk_cols]
        if not free_pk:
            continue  # es. BOARDING_PASS: nessuna chiave nuova possibile
        types = {n: ty for n, ty, _ in cols[t]}
        date_cols = [n for n, ty, _ in cols[t] if ty == "DATE" and n not in fk_cols]
        int_pk = [c for c in free_pk if types[c] in ("INTEGER", "BIGINT")]
        by_date = any(types[c] == "DATE" for c in free_pk)
        counters = {c: con.execute(f"select max({_q(c)}) from {_q(t)}").fetchone()[0] or 0 for c in int_pk}
        rids = [r[0] for r in con.execute(f"select rowid from {_q(t)}").fetchall()]
        for rid in rng.sample(rids, int(len(rids) * 0.3)):
            for shift in range(1, 31):
                exprs = []
                for n, ty, _ in cols[t]:
                    if by_date and n in date_cols:
                        exprs.append(f"{_q(n)} + INTERVAL {shift} DAY")
                    elif n in int_pk and not by_date:
                        exprs.append(str(counters[n] + 1))
                    else:
                        exprs.append(_q(n))
                n_before = con.execute(f"select count(*) from {_q(t)}").fetchone()[0]
                ok = _try(con, f"insert or ignore into {_q(t)} select {', '.join(exprs)} "
                               f"from {_q(t)} where rowid = ?", [rid])
                grown = con.execute(f"select count(*) from {_q(t)}").fetchone()[0] > n_before
                if ok and grown:
                    for c in int_pk:
                        counters[c] += 1
                    break
                if not by_date:
                    break


def build_instances(schema):
    """Crea m1..m4 a partire dalla base."""
    base = db_path(schema, "base")
    for inst in ("m1", "m2", "m3", "m4"):
        p = db_path(schema, inst)
        p.unlink(missing_ok=True)
        shutil.copy(base, p)
        con = duckdb.connect(str(p))
        try:
            meta = _meta(con)
            steps = {"m1": [_m1], "m2": [_m2], "m3": [_m3], "m4": [_m1, _m2, _m3]}[inst]
            rng = random.Random(SEEDS[inst])
            for step in steps:
                step(con, rng, meta)
            con.execute("CHECKPOINT")
        finally:
            con.close()


def row_counts(schema):
    """{tabella: [righe per istanza in ordine INSTANCES]}"""
    out = {}
    for inst in INSTANCES:
        con = duckdb.connect(str(db_path(schema, inst)), read_only=True)
        for (t,) in con.execute("select table_name from information_schema.tables "
                                "where table_schema='main'").fetchall():
            out.setdefault(t, []).append(con.execute(f"select count(*) from {_q(t)}").fetchone()[0])
        con.close()
    return out


def table_names(schema):
    con = duckdb.connect(str(db_path(schema, "base")), read_only=True)
    try:
        return [r[0] for r in con.execute("select table_name from information_schema.tables "
                                          "where table_schema='main'").fetchall()]
    finally:
        con.close()


# ---------- esecuzione ----------
def _run(con, sql):
    timer = threading.Timer(TIMEOUT_S, con.interrupt)
    timer.start()
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        return cols, cur.fetchall()
    finally:
        timer.cancel()


def execute(schema, inst, sql):
    """-> {status, cols, rows, exec_sql, dialect_path, error}"""
    res = {"status": "exec_error", "cols": [], "rows": [], "exec_sql": sql,
           "dialect_path": "native", "error": None}
    if not sql or not sql.strip():
        res.update(status="parse_error", error="query vuota")
        return res
    con = duckdb.connect(str(db_path(schema, inst)), read_only=True)
    try:
        attempts = [("native", sql)]
        first_err = None
        i = 0
        while i < len(attempts):
            path, text = attempts[i]
            i += 1
            try:
                cols, rows = _run(con, text)
                res.update(status="ok", cols=cols, rows=rows, exec_sql=text, dialect_path=path, error=None)
                return res
            except duckdb.InterruptException:
                res.update(status="timeout", error="timeout 10 s", dialect_path=path)
                return res
            except (duckdb.ParserException, duckdb.BinderException, duckdb.CatalogException) as e:
                if first_err is None:
                    first_err = (type(e), str(e))
                    for d in ("postgres", "mysql"):  # fallback solo dopo errore nativo
                        try:
                            attempts.append((d, sqlglot.transpile(sql, read=d, write="duckdb")[0]))
                        except Exception:
                            pass
            except duckdb.Error as e:
                res.update(status="exec_error", error=str(e), dialect_path=path)
                return res
        etype, msg = first_err
        res.update(status="parse_error" if etype is duckdb.ParserException else "exec_error",
                   error=msg, dialect_path="native")
        return res
    finally:
        con.close()


def execute_all(schema, sql):
    return [execute(schema, inst, sql) for inst in INSTANCES]


def row_counts_base(schema):
    """{tabella: [righe nella base]}"""
    con = duckdb.connect(str(db_path(schema, "base")), read_only=True)
    try:
        return {t: [con.execute(f"select count(*) from {_q(t)}").fetchone()[0]]
                for (t,) in con.execute("select table_name from information_schema.tables "
                                        "where table_schema='main'").fetchall()}
    finally:
        con.close()
