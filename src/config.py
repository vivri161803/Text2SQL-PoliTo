"""Modelli, parametri e percorsi."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BASE_URL = "https://openrouter.ai/api/v1"
API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MATRICOLA = os.getenv("MATRICOLA", "")
NOME = os.getenv("NOME", "")
SPESA_MAX_USD = float(os.getenv("SPESA_MAX_USD", "12"))

CACHE_DIR = ROOT / "cache"
OUTPUTS = ROOT / "outputs"
DBS_DIR = OUTPUTS / "dbs"
NARRATIVES = OUTPUTS / "narratives"
REPORT_DIR = OUTPUTS / "report"
SCHEMAS_DIR = ROOT / "data" / "schemas"
GOLD_OVERRIDES = ROOT / "data" / "gold_overrides.json"
TEMPLATES = ROOT / "templates"
FIXTURES = ROOT / "fixtures"


def _m(id, params, max_tokens, part, in_report=False, params_b=None):
    return dict(id=id, params=params, max_tokens=max_tokens, base_url=BASE_URL,
                part=part, in_report=in_report, params_b=params_b)


T0 = {"temperature": 0}

MODELS = {
    # Parte 1
    "gpt": _m("openai/gpt-chat-latest", dict(T0), 4096, 1, True),
    "gemini": _m("google/gemini-3.8-flash", {"temperature": 0, "reasoning": {"effort": "minimal"}}, 4096, 1, True),
    "codestral": _m("mistralai/codestral-2508", dict(T0), 4096, 1, True),
    # Parte 2
    "llama-1b": _m("meta-llama/llama-3.2-1b-instruct", dict(T0), 4096, 2, True, 1),
    "llama-3b": _m("meta-llama/llama-3.2-3b-instruct", dict(T0), 4096, 2, True, 3),
    "gemma-4b": _m("google/gemma-3-4b-it", dict(T0), 4096, 2, True, 4),
    "ministral-8b": _m("mistralai/ministral-8b-2512", dict(T0), 4096, 2, True, 8),
    "qwen3-8b": _m("qwen/qwen3-vl-8b-instruct", dict(T0), 4096, 2, True, 8),
    # Parte 3
    "gemini-2.5": _m("google/gemini-2.5-flash", {"reasoning": {"enabled": True}}, 16000, 3, True),
    "qwen3-235b": _m("qwen/qwen3-235b-a22b-thinking-2507", {"reasoning": {"max_tokens": 4096}}, 16000, 3, True),
    "gpt-r": _m("openai/gpt-5.5", {"reasoning": {"effort": "medium"}}, 16000, 3, True),
    "gpt-nr": _m("openai/gpt-5.5", {"reasoning": {"effort": "none"}}, 4096, 3, True),
    # Supporto
    "opus-gold": _m("anthropic/claude-opus-5.5", {"reasoning": {"effort": "high"}}, 16000, 0),
    "opus-judge": _m("anthropic/claude-opus-5.5", {"reasoning": {"effort": "low"}}, 12000, 0),
    "opus-text": _m("anthropic/claude-opus-5.5", {"reasoning": {"effort": "low"}}, 6000, 0),
    "deepseek": _m("deepseek/deepseek-v4.1-flash-1017", {"reasoning": {"enabled": True}}, 8000, 0),
}

# Fallback di gpt-nr, attivato da `check` se effort="none" viene rifiutato
GPT_NR_FALLBACK = _m("openai/gpt-chat-latest", dict(T0), 4096, 3, True)

PART_MODELS = {p: [a for a, m in MODELS.items() if m["part"] == p and a != "gpt-nr"] for p in (1, 2, 3)}
