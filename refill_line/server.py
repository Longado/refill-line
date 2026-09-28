"""Local server: static page, AssemblyAI temporary token, and the refill gate.

Run: uv run python -m refill_line.server   (then open http://localhost:8790 in Chrome)
"""
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

from refill_line import gate, jev

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
LOG = ROOT / "runs" / "decisions.jsonl"
PORT = int(os.environ.get("PORT", "8790"))
MAX_BODY = 8_000
FIELDS = ("name", "date_of_birth", "medication", "request")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/pcm-processor.js": ("pcm-processor.js", "text/javascript"),
          "/compare": ("compare.html", "text/html; charset=utf-8")}
COMPARISON = ROOT / "runs" / "comparison.json"
DEMO = WEB / "demo"
TYPES = {".wav": "audio/wav", ".json": "application/json"}
PATIENTS = gate.load_patients()
AGENT = json.loads((Path(__file__).with_name("agent.json")).read_text())


def keychain(env: str, service: str) -> str:
    if os.environ.get(env):
        return os.environ[env]
    r = subprocess.run(["security", "find-generic-password", "-s", service, "-w"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Missing key: set {env} or store it in Keychain as '{service}'")
    return r.stdout.strip()


def voice_token() -> str:
    r = requests.get("https://agents.assemblyai.com/v1/token",
                     params={"expires_in_seconds": 120, "max_session_duration_seconds": 900},
                     headers={"Authorization": f"Bearer {keychain('ASSEMBLYAI_API_KEY', 'assemblyai')}"}, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


def refill(body: dict) -> dict:
    req = {k: str(body.get(k, ""))[:500] for k in FIELDS}  # untrusted: strings only, bounded
    t = time.time()
    out = gate.decide(req, PATIENTS, jev.ask)
    out["latency_ms"] = round((time.time() - t) * 1000)
    try:  # read-only filesystem when hosted; a lost log line never costs a caller their refill
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "model": jev.MODEL, "request": req, **out}) + "\n")
    except OSError as e:
        print(f"decision log unavailable: {e}")
    return out


def public_config() -> dict:
    """What a client needs: the agent config (one source for page and test caller) plus demo patients."""
    return {"patients": [{"name": p["name"], "date_of_birth": p["date_of_birth"],
                          "prescriptions": [f"{gate.label(rx)} ({rx['for']})" for rx in p["prescriptions"]]} for p in PATIENTS],
            "keyterms": sorted({rx["drug"] for p in PATIENTS for rx in p["prescriptions"]}),
            **AGENT}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj).encode())

    def do_GET(self):
        if self.path.startswith("/demo/"):
            f = DEMO / Path(self.path).name
            if not f.is_file() or f.suffix not in TYPES:
                return self._json(404, {"error": "not found"})
            return self._send(200, f.read_bytes(), TYPES[f.suffix])
        if self.path in STATIC:
            name, ctype = STATIC[self.path]
            return self._send(200, (WEB / name).read_bytes(), ctype)
        if self.path == "/api/comparison":
            if not COMPARISON.exists():
                return self._json(404, {"error": "no comparison run yet"})
            return self._send(200, COMPARISON.read_bytes())
        if self.path == "/api/config":
            return self._json(200, public_config())
        if self.path == "/api/voice-token":
            try:
                return self._json(200, {"token": voice_token()})
            except Exception as e:
                self.log_error("voice token failed: %s", e)
                return self._json(502, {"error": "Could not get a voice session token. Check the AssemblyAI key on the server."})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/refill":
            return self._json(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        if not 0 < n <= MAX_BODY:
            return self._json(413, {"error": "body missing or too large"})
        try:
            body = json.loads(self.rfile.read(n))
            if not isinstance(body, dict):
                raise ValueError("expected a JSON object")
        except ValueError as e:
            return self._json(400, {"error": f"bad JSON: {e}"})
        self._json(200, refill(body))


if __name__ == "__main__":
    print(f"Refill line on http://localhost:{PORT}  (Jev {jev.MODEL})")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
