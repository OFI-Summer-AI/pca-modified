import json
import logging
import os
import re
import urllib.request

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response."""
    # Strip markdown code fences
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1)
    text = text.strip()
    # Find outermost { ... }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return json.loads(text)


def call_ai(prompt: str, expect_json: bool = True, num_predict: int = 1024):
    """Call local Ollama. Raises RuntimeError if Ollama is unreachable."""
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    body: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.05,   # near-deterministic for structured output
            "num_predict": num_predict,
            "top_p": 0.9,
        },
    }
    if expect_json:
        body["format"] = "json"

    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        raise RuntimeError(
            f"Ollama unreachable at {host}. "
            f"Run 'ollama serve' and 'ollama pull {model}'. Error: {e}"
        )

    text = result.get("response", "").strip()
    if not text:
        raise RuntimeError("Ollama returned an empty response.")

    logger.info(
        "Ollama OK  model=%s  tokens=%s",
        model,
        result.get("eval_count", "?"),
    )
    return _extract_json(text) if expect_json else text


def stream_ai(prompt: str, num_predict: int = 256):
    """Generator that yields text chunks from Ollama as they are produced.

    Uses Ollama's streaming API (stream=True). Each chunk is a string of
    1–several tokens. Caller iterates and sends chunks to the client immediately
    — user sees the first word in ~300ms instead of waiting for full response.
    """
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
    host  = os.getenv("OLLAMA_HOST",  "http://localhost:11434")

    body = {
        "model":  model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.3,       # slightly higher for conversational tone
            "num_predict": num_predict,
            "top_p": 0.9,
        },
    }
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            while True:
                line = resp.readline()
                if not line:
                    break
                try:
                    data = json.loads(line.decode())
                    chunk = data.get("response", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.warning("Ollama stream error: %s", e)
        yield ""   # empty sentinel so caller can handle gracefully
