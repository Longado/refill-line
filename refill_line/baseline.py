"""The comparison judge: an ordinary chat model answering the same questions as Jev.

Same signature as `jev.ask`, so `gate.decide` runs unchanged with either one — the gate, the
questions and the thresholds stay fixed and only the judge is swapped. It is asked for exactly
what Jev is asked for (probabilities, no prose): asking it to reason out loud would make it
slower and dearer, not faster, and the point of the comparison is what a judgment costs.
"""
import json
import time
from pathlib import Path

import requests

from refill_line import jev

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-5-mini"  # pinned; OpenRouter resolves one build at a time — record it with every run
PROMPT = Path(__file__).parents[1] / "prompts" / "baseline_judge.md"
PROMPT_VERSION = "baseline_judge/1"
TIMEOUT_S = 60


def _schema(questions: dict) -> dict:
    props = {k: {"type": "number", "minimum": 0, "maximum": 1} for k in questions}
    return {"type": "json_schema", "json_schema": {"name": "judgments", "strict": True, "schema": {
        "type": "object", "properties": props, "required": list(props), "additionalProperties": False}}}


def _render(state, questions: dict) -> str:
    lines = []
    for key, q in questions.items():
        ins = q["instructions"]
        what = ins if isinstance(ins, str) else ins["what"] + (f" ({ins['not_for']})" if "not_for" in ins else "")
        lines.append(f"- {key}: {what} — 1 means \"{q['criteria']['true']}\", 0 means \"{q['criteria']['false']}\".")
    return PROMPT.read_text().replace("{state}", json.dumps(state, ensure_ascii=False, indent=1)).replace("{questions}", "\n".join(lines))


def ask_with_meta(state, questions: dict, key: str | None = None, model: str | None = None,
                  thinking: bool = True) -> tuple[dict, dict]:
    """Returns ({question: {"noul": p}}, {latency_s, cost, model, prompt_version}).

    `thinking=False` turns the model's own reasoning off, so a reasoning model can also be
    measured on the same footing as Jev, which never reasons out loud."""
    started = time.time()
    payload = {"model": model or MODEL, "messages": [{"role": "user", "content": _render(state, questions)}],
               "response_format": _schema(questions), "usage": {"include": True}}
    if not thinking:
        payload["reasoning"] = {"enabled": False}
    r = requests.post(URL, headers={"Authorization": f"Bearer {key or jev.api_key()}"}, json=payload, timeout=TIMEOUT_S)
    r.raise_for_status()
    body = r.json()
    answers = json.loads(body["choices"][0]["message"]["content"])
    out = {}
    for k in questions:  # wrong shape is an error, never a guess
        p = answers[k]
        if not isinstance(p, (int, float)) or not 0 <= p <= 1:
            raise ValueError(f"{k}: probability out of range: {p!r}")
        out[k] = {"noul": float(p)}
    meta = {"latency_s": round(time.time() - started, 2), "cost": (body.get("usage") or {}).get("cost"),
            "model": body.get("model", model or MODEL), "prompt_version": PROMPT_VERSION}
    return out, meta


def ask(state, questions: dict, key: str | None = None) -> dict:
    return ask_with_meta(state, questions, key)[0]
