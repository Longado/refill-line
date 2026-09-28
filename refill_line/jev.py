"""Jev (TypeSafe's judgment model) via OpenRouter. Judges only, never writes text."""
import os
import subprocess
import time

import requests

URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = os.environ.get("JEV_MODEL", "typesafe/jev-1.13-20260917")  # pinned: probabilities move with the version
TIMEOUT_S = 10


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    r = subprocess.run(["security", "find-generic-password", "-s", "openrouter", "-w"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("No OpenRouter key: set OPENROUTER_API_KEY or store it in Keychain as 'openrouter'")
    return r.stdout.strip()


def ask_with_meta(state, questions: dict, key: str | None = None) -> tuple[dict, dict]:
    """Returns (answers, {latency_s, cost, model}); `ask` is the same call without the meter."""
    started = time.time()
    r = requests.post(URL, headers={"Authorization": f"Bearer {key or api_key()}"},
                      json={"model": MODEL, "state": state, "questions": questions}, timeout=TIMEOUT_S)
    r.raise_for_status()
    body = r.json()
    answers = body["answers"]
    for k in questions:  # wrong shape = error, never a guess
        p = answers[k]["noul"]
        if not isinstance(p, (int, float)) or not 0 <= p <= 1:
            raise ValueError(f"{k}: probability out of range: {p!r}")
    meta = {"latency_s": round(time.time() - started, 2), "cost": (body.get("usage") or {}).get("cost"), "model": MODEL}
    return answers, meta


def ask(state, questions: dict, key: str | None = None) -> dict:
    return ask_with_meta(state, questions, key)[0]
