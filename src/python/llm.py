"""Small OpenAI completion shim used by Python modules."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def complete(system: str, user: str) -> str:
    """Return a text completion from OpenAI Chat Completions."""
    _load_env()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; copy .env.example to .env and fill it in.")

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    # OpenAI by default; point OPENAI_BASE_URL at any OpenAI-compatible endpoint (e.g. a free
    # provider like Groq) to run without an OpenAI key. See .env.example.
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    req = request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Browser-like UA: some OpenAI-compatible hosts (e.g. Groq behind Cloudflare)
            # return 403 "error code: 1010" for the default Python-urllib agent.
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI request failed ({exc.code}): {detail}") from exc
    return data["choices"][0]["message"]["content"].strip()
