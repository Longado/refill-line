"""WSGI entrypoint for the hosted version. Same handlers as the local server, no framework.

Locally: `uv run python -m refill_line.server` (http.server). Hosted: Vercel loads `app` here.
Keys come from the environment in both cases; the Keychain fallback only exists on the laptop.
"""
import json

from refill_line import server

STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/compare": ("compare.html", "text/html; charset=utf-8"),
          "/pcm-processor.js": ("pcm-processor.js", "text/javascript; charset=utf-8")}
MAX_BODY = 8_000


def _reply(start, code: str, body: bytes, ctype: str):
    start(code, [("Content-Type", ctype), ("Content-Length", str(len(body))), ("Cache-Control", "no-store")])
    return [body]


def _json(start, code: str, obj) -> list:
    return _reply(start, code, json.dumps(obj).encode(), "application/json")


def app(environ, start_response):
    path, method = environ.get("PATH_INFO", "/"), environ.get("REQUEST_METHOD", "GET")

    if method == "GET" and path.startswith("/demo/"):
        f = server.DEMO / path.rsplit("/", 1)[-1]
        if not f.is_file() or f.suffix not in server.TYPES:
            return _json(start_response, "404 Not Found", {"error": "not found"})
        return _reply(start_response, "200 OK", f.read_bytes(), server.TYPES[f.suffix])

    if method == "GET" and path in STATIC:
        name, ctype = STATIC[path]
        return _reply(start_response, "200 OK", (server.WEB / name).read_bytes(), ctype)

    if method == "GET" and path == "/api/config":
        return _json(start_response, "200 OK", server.public_config())

    if method == "GET" and path == "/api/comparison":
        if not server.COMPARISON.exists():
            return _json(start_response, "404 Not Found", {"error": "no comparison run yet"})
        return _reply(start_response, "200 OK", server.COMPARISON.read_bytes(), "application/json")

    if method == "GET" and path == "/api/voice-token":
        try:
            return _json(start_response, "200 OK", {"token": server.voice_token()})
        except Exception as e:
            print(f"voice token failed: {e}")  # the reason goes to the logs, never to the caller
            return _json(start_response, "502 Bad Gateway",
                         {"error": "Could not get a voice session token. Check the AssemblyAI key on the server."})

    if method == "POST" and path == "/api/refill":
        try:
            size = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            size = 0
        if not 0 < size <= MAX_BODY:
            return _json(start_response, "413 Payload Too Large", {"error": "body missing or too large"})
        try:
            body = json.loads(environ["wsgi.input"].read(size))
            if not isinstance(body, dict):
                raise ValueError("expected a JSON object")
        except ValueError as e:
            return _json(start_response, "400 Bad Request", {"error": f"bad JSON: {e}"})
        return _json(start_response, "200 OK", server.refill(body))

    return _json(start_response, "404 Not Found", {"error": "not found"})
