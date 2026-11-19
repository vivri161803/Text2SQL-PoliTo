"""Genera fixtures/data.json: dati finti ma completi per `report --draft`."""
import json
from pathlib import Path

LONG = "\n".join(f"Passo {i}: ragiono sullo schema e sulla condizione richiesta (testo di prova PENDING)." for i in range(1, 200))
SQL = "SELECT titolo, anno_pubblicazione\nFROM LIBRO\nWHERE genere = 'fantasy' AND numero_copie >= 3\nORDER BY anno_pubblicazione DESC;"
P1M = ["gpt", "gemini", "codestral"]
P2M = ["llama-1b", "llama-3b", "gemma-4b", "ministral-8b", "qwen3-8b"]
P3M = ["gemini-2.5", "qwen3-235b", "gpt-r"]


def p12_card(i, pattern, strat, models):
    return {
        "id": i, "pattern": pattern, "pattern_desc": "Proiezione: WHERE (+ ORDER BY) (PENDING)",
        "strategia": strat, "domanda": "Mostra il titolo e l’anno di pubblicazione dei libri del genere “fantasy” (PENDING).",
        "soluzioni": [{"strategia": strat or "unica", "sql": SQL}],
        "prompt": "Sei un assistente AI (PENDING)...\n\nDomanda:\n\n...\n\nCodice SQL:",
        "modelli": [{"alias": m, "sql": SQL, "esito": ["corretta", "parzialmente corretta", "errata"][k % 3],
                     "analisi": "Ho verificato l'esecuzione sulle 5 istanze (PENDING)."} for k, m in enumerate(models)],
    }


def p3_model(a):
    return {
        "alias": a, "reasoning_tipo": "reasoning.text", "reasoning_estratto": "\n".join(LONG.split("\n")[:15]),
        "sql": SQL, "reasoning_corretto": "parzialmente", "passi_mancanti": ["PENDING"], "passi_errati": [],
        "passi_fuori_ordine": [], "passi_ridondanti": ["PENDING"], "commento_reasoning": "Ho letto il ragionamento (PENDING).",
        "soluzione_corretta": "no", "segue_reasoning": "sì", "commento_soluzione": "La soluzione (PENDING).",
        "prompt_aggiornato": "Prompt con chiarimenti (PENDING).",
        "r2": {"reasoning_estratto": "Ragionamento aggiornato (PENDING).", "sql": SQL, "reasoning_corretto": "sì",
               "commento_reasoning": "(PENDING)", "soluzione_corretta": "sì", "commento_soluzione": "(PENDING)"},
    }


def main():
    modelli_meta = lambda ms, part: [{"alias": m, "id": f"vendor/{m}", "params": "temperature=0", "parte": part} for m in ms]
    d = {
        "meta": {"titolo": "Text2SQL – Esercitazione", "nome": "Nome Cognome", "matricola": "000000",
                 "master": "Master Intelligenza Artificiale: Tecnologie, Modelli e Applicazioni", "data": "19 novembre 2026",
                 "draft": True},
        "metodologia": {"modelli": modelli_meta(P1M, 1) + modelli_meta(P2M, 2) + modelli_meta(P3M, 3),
                        "testo": "Ho interrogato i modelli tramite OpenRouter (PENDING).",
                        "note": ["Il testo cita i pattern “3, 6, 7”; l'elenco va da 0 a 6, quindi ho trattato 3, 5 e 6 come pattern a soluzione multipla."]},
        "p1": {"modelli": P1M, "tabella": {"0": {m: [1.0, 1.0] for m in P1M}, "3": {m: [0.67, 1.0] for m in P1M}},
               "schede": [p12_card(1, 0, None, P1M), p12_card(2, 3, "JOIN", P1M), p12_card(3, 3, "INTERSECT", P1M)],
               "intro": "Introduzione di prova (PENDING).", "commento": "## Punti forti e deboli\n\nPENDING\n\n## Confronto tra LLM\n\nPENDING"},
        "p2": {"modelli": P2M, "tabella": {"0": {m: [0.5, 1.0] for m in P2M}},
               "schede": [p12_card(1, 0, None, P2M)], "intro": "Introduzione di prova (PENDING).", "grafico": "p2_accuratezza.svg", "sintesi": "PENDING sintesi Parte 2."},
        "p3": {"intro": "Introduzione di prova (PENDING).", "tabella": {"modelli": P3M + ["gpt-nr"], "righe": [{"q": q, "celle": {**{m: {"r1": q % 2, "r2": None if q % 2 else 1} for m in P3M}, "gpt-nr": None}} for q in (1, 2)], "tot_r1": {m: "1/2" for m in P3M + ["gpt-nr"]}, "tot_finale": {m: "2/2" for m in P3M + ["gpt-nr"]}}, "queries": [{"q": q, "domanda": "Display the name of the authors (PENDING).",
                            "soluzione_attesa": SQL, "interpretazioni": ["“copie vendute” = righe di SALE per ISBN (PENDING)"],
                            "prompt": "You are an AI assistant (PENDING)...", "modelli": [p3_model(a) for a in P3M],
                            "confronto_reasoning": "PENDING", "confronto_soluzione": "PENDING"} for q in (1, 4)],
               "nr": [{"q": q, "output": "Il modello ha restituito solo codice SQL.", "sql": SQL, "output_corretto": "sì",
                       "commento_output": "(PENDING)", "soluzione_corretta": "no", "commento_soluzione": "(PENDING)",
                       "confronto_gpt_reasoning": "PENDING", "confronto_gpt_soluzione": "PENDING"} for q in (4, 10)]},
        "conclusioni": "PENDING conclusioni.",
        "appendici": {"A": [{"id": "P0", "prompt": "Sei un assistente AI (PENDING)"}],
                      "B": [{"q": "Q1", "alias": a, "reasoning": LONG} for a in P3M],
                      "C": {"ddl": [{"nome": "biblioteca", "sql": "CREATE TABLE AUTORE (...);"}],
                            "stats": [{"schema": "biblioteca", "tabella": "LIBRO", "righe": [30, 21, 30, 40, 25]}],
                            "mutazioni": ["m1: elimina il 30% delle righe figlie"]},
                      "D": [{"alias": a, "chiamate": 11, "costo": 0.12} for a in P1M + P2M + P3M]},
    }
    Path(__file__).with_name("data.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
