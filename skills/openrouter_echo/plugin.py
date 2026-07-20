"""Minimal OpenRouter round-trip Skill for Ouroboros 6.61.4."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "google/gemini-3.5-flash"
_MAX_INPUT_CHARS = 4_000
_MAX_OUTPUT_TOKENS = 256


def register(api: Any) -> None:
    settings = api.get_settings(["OPENROUTER_API_KEY", "OUROBOROS_MODEL"])

    def ask(prompt: str = "") -> str:
        text = str(prompt or "").strip()
        if not text:
            return "Error: prompt must not be empty."
        if len(text) > _MAX_INPUT_CHARS:
            return f"Error: prompt exceeds {_MAX_INPUT_CHARS} characters."

        api_key = str(settings.get("OPENROUTER_API_KEY") or "").strip()
        if not api_key:
            return "Error: OpenRouter is not configured for this Skill."
        model = str(settings.get("OUROBOROS_MODEL") or _DEFAULT_MODEL).strip()

        payload = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": text}],
                "max_tokens": _MAX_OUTPUT_TOKENS,
                "temperature": 0,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            _OPENROUTER_URL,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/razzant/ouroboros",
                "X-Title": "Ouroboros OpenRouter Echo PoC",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return f"Error: OpenRouter returned HTTP {error.code}."
        except (urllib.error.URLError, TimeoutError):
            return "Error: OpenRouter request failed or timed out."
        except (json.JSONDecodeError, UnicodeDecodeError):
            return "Error: OpenRouter returned an unreadable response."

        try:
            answer = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return "Error: OpenRouter response did not contain an answer."
        return str(answer or "").strip()

    async def ask_route(request: Any) -> dict[str, str]:
        try:
            body = await request.json()
        except Exception:
            return {"error": "Request body must be JSON."}
        if not isinstance(body, dict):
            return {"error": "Request body must be a JSON object."}
        result = ask(str(body.get("prompt") or ""))
        return {"answer": result}

    api.register_tool(
        "ask",
        handler=lambda _ctx=None, prompt="": ask(prompt),
        description="Send one text prompt to the configured OpenRouter model and return its answer.",
        schema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "User text to send to the configured model.",
                    "maxLength": _MAX_INPUT_CHARS,
                }
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
        timeout_sec=45,
    )
    api.register_route("ask", handler=ask_route, methods=("POST",))
