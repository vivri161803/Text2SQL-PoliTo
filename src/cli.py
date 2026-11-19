import argparse
import json
import sys

from . import config


def cmd_check(args):
    import duckdb
    import sqlglot
    import typst

    from . import assignment, llm

    config.OUTPUTS.mkdir(exist_ok=True)
    check = {"gpt_nr_fallback": False}
    ok = True

    # 4. colonne accentate in DuckDB e sqlglot
    try:
        con = duckdb.connect(":memory:")
        con.execute("CREATE TABLE AUTORE(nazionalità VARCHAR, capacità INTEGER)")
        con.execute("SELECT nazionalità, capacità FROM AUTORE")
        sqlglot.parse_one("SELECT nazionalità, capacità FROM AUTORE")
        print("[accenti] DuckDB e sqlglot ok")
    except Exception as e:
        ok = False
        print(f"[accenti] FALLITO ({e}): mettere le colonne tra virgolette doppie nei DDL e nei prompt")

    # 5. Typst
    try:
        d = config.OUTPUTS / "check_typst"
        d.mkdir(exist_ok=True)
        (d / "t.typ").write_text('#set text(lang: "it")\n= Prova àèìòù\n```sql\nSELECT nazionalità FROM AUTORE;\n```\n',
                                 encoding="utf-8")
        typst.compile(str(d / "t.typ"), output=str(d / "t.pdf"))
        print("[typst] ok")
    except Exception as e:
        ok = False
        print(f"[typst] FALLITO: {e}")

    # 1. una chiamata per alias
    q1 = assignment.build_prompt_p3(1)
    for alias in config.MODELS:
        try:
            if alias == "gpt-nr":
                try:
                    r = llm.chat(alias, [{"role": "user", "content": "Rispondi solo: SELECT 1"}],
                                 meta={"part": 0, "item_id": "check"})
                except llm.FatalAPIError:
                    raise
                except Exception as e:
                    check["gpt_nr_fallback"] = True
                    (config.OUTPUTS / "check.json").write_text(json.dumps(check))
                    print(f"[gpt-nr] effort=none rifiutato ({str(e)[:120]}): attivo fallback gpt-chat-latest")
                    r = llm.chat(alias, [{"role": "user", "content": "Rispondi solo: SELECT 1"}],
                                 meta={"part": 0, "item_id": "check"})
            else:
                r = llm.chat(alias, [{"role": "user", "content": "Rispondi solo: SELECT 1"}],
                             role="support" if config.MODELS[alias]["part"] == 0 else "tested",
                             meta={"part": 0, "item_id": "check"})
            print(f"[{alias}] served={r['model_served']} provider={r['provider']} "
                  f"cost=${r['cost_usd']:.5f} params={r['params_sent']}")
            # 2. reasoning dei modelli P3 con Q1
            if alias in config.PART_MODELS[3]:
                r3 = llm.chat(alias, [{"role": "user", "content": q1}],
                              meta={"part": 0, "item_id": "check-q1"})
                has = bool(r3["reasoning"])
                print(f"   Q1: reasoning {'presente' if has else 'VUOTO'}, tipo={r3['reasoning_type']}, "
                      f"finish={r3['finish_reason']}")
                ok &= has
        except llm.FatalAPIError as e:
            print(f"[{alias}] ERRORE FATALE: {e}")
            sys.exit(1)
        except Exception as e:
            ok = False
            print(f"[{alias}] FALLITO: {e} (cambiare l'ID in config.py)")

    (config.OUTPUTS / "check.json").write_text(json.dumps(check))
    print(f"speso finora: ${llm.total_spent():.4f}")
    print("check", "OK" if ok else "con problemi")


def cmd_run(a):
    from . import runs
    runs.run_p12(a.part) if a.part in (1, 2) else runs.run_p3(a.round)


def cmd_eval(a):
    from . import judge
    if a.part in (1, 2):
        judge.eval_p12(a.part)
        (judge.narrative_p1 if a.part == 1 else judge.narrative_p2)()
    else:
        judge.eval_p3(a.round)
        if a.round == 2:
            judge.narratives_p3()


def _todo(name):
    def f(args):
        raise SystemExit(f"{name}: non ancora implementato")
    return f


def main():
    ap = argparse.ArgumentParser(prog="src.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("gold").set_defaults(fn=lambda a: __import__("src.gold", fromlist=["run"]).run())
    for name in ("run", "eval"):
        p = sub.add_parser(name)
        p.add_argument("--part", type=int, choices=[1, 2, 3], required=True)
        p.add_argument("--round", type=int, choices=[1, 2], default=1)
        p.set_defaults(fn=cmd_run if name == "run" else cmd_eval)
    p = sub.add_parser("report")
    p.add_argument("--draft", action="store_true")
    p.set_defaults(fn=lambda a: __import__("src.report", fromlist=["run"]).run(draft=a.draft))
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
