# CLAUDE.md

This file gives Claude Code (claude.ai/code) guidance for working in this repository.

## Current state

The specification is `design/PianoDiImplementazione.md` (v2, in Italian). It is the source of truth, and when it disagrees with this file, the spec wins. The assignment text is `EsercitazionePoliTo.pdf`, and the spec's Appendice copies its verbatim parts. `design/PianoDiImplementazione_v1.md` is an archive only, so do not implement it.

All stages are implemented and the final PDF has been built (`outputs/report/<MATRICOLA>_TextSQL.pdf`). Remaining work is manual review of the narratives and the delivery.

Project policy: **easier is better**. Only the shape of the final PDF matters. Prefer the simplest mechanism that produces it.

## Stack and commands

The stack is Python ≥ 3.11 with `requests`, `duckdb`, `sqlglot`, `matplotlib`, `typst` (pip) and `python-dotenv`. It uses no `openai` SDK, pydantic, yaml, pandas, jinja2, weasyprint or faker.

Setup: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, then copy `.env.example` to `.env` (OPENROUTER_API_KEY, MATRICOLA numeric, NOME, SPESA_MAX_USD).

```
python -m src.cli check                          # step 0: real call per model, reasoning probe, accents, Typst
python -m src.cli gold
python -m src.cli run  --part 1|2|3 [--round 1|2]
python -m src.cli eval --part 1|2|3 [--round 1|2]
python -m src.cli report [--draft]               # -> outputs/report/<MATRICOLA>_TextSQL.pdf
```

Order: `check` → `gold` → `run/eval --part 1` → `--part 2` → `run/eval --part 3 --round 1` (its eval also writes `outputs/p3_prompts_r2.json`) → `--round 2` (also runs `gpt-nr` on Q4/Q10 and writes the Part 3 narratives) → `report` (writes `conclusioni.md`, runs the final checks, compiles). `report --draft` uses `fixtures/data.json` (regenerate with `python fixtures/make_fixture.py`).

Module map: `config.py` models/paths, `assignment.py` verbatim texts, `llm.py` client, `db.py` instances/mutations/execution, `evaluate.py` comparison and static checks, `gold.py`, `runs.py`, `judge.py` (eval, prompt optimizer, narratives), `metrics.py`, `report.py`, `templates/report.typ`. Long stages (`gold`, Part 3 runs) take 10+ minutes: run them in the background with `python -u`.

## Invariants that are easy to get wrong

- **Stage outputs.** Every stage rewrites its whole output file, keyed by `call_id`. Do not append. Exception: `calls_p3.json` and `evals_p3.json` are merged by round (a round-2 run keeps the round-1 records). After a gold change, rerun the downstream stages.
- **Gold overrides.** `data/gold_overrides.json` holds manual decisions for `da_rivedere` entries (fill `gold_sql`); `gold` applies them last and never removes existing ones. `report` refuses to build while any entry is `da_rivedere`.
- **Final checks.** `report` (without `--draft`) fails on a non-numeric MATRICOLA, empty fields, `PENDING`/`TODO`, or forbidden words in `data.json`, `narratives/` and the template.
- **The `src/llm.py` client:**
  - It sends only the parameters listed for each model in `src/config.py`, with no global `seed`.
  - It sets `require_parameters` only on calls that carry `reasoning`.
  - The cache key is the canonical JSON of base_url, model, messages and params.
  - HTTP 402 is fatal.
  - It never caches responses that are truncated or empty.
  - It checks the spending cap before every uncached call.
- **Correctness comes from execution only:**
  - EX=1 means the result matches on all 5 DuckDB instances, or matches any accepted variant in Part 3.
  - `esito` is derived deterministically from EX and the flags.
  - The judge writes only comments and error categories.
  - There is no `incoerenza` flag.
- **Execution order.** Run native DuckDB first. Use the sqlglot transpile (postgres, then mysql) only on error, and give the gold the same path.
- **Batched judging.** Make one judge call per prompt (Parts 1-2) or per query and round (Part 3), covering all models.
- **Part 1 prompts and strategy lines.** Part 1 has 11 prompts, using patterns 3, 5 and 6 as multi-strategy. The base prompt is copied verbatim from the spec's Appendice A1, and the strategy lines come from A2. Part 2 reuses those prompts byte for byte.
- **Part 3 prompts:**
  - The English prompt comes from A4.
  - Q1-Q10 are copied verbatim.
  - There is no Italian round.
  - Updated prompts never see the gold, and they must pass the anti-leak check.
- **Report voice.** The report is in Italian, in the first person singular. The PDF must never mention Opus, DeepSeek, Fable, Claude, Anthropic, "giudice", "gold" or the pipeline. Only tested models appear in its tables.
- **Narratives.** `outputs/narratives/*.md` are generated only if missing, and the code never overwrites them.
