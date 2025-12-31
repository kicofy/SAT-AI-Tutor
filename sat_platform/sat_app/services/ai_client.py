"""Simple AI client for calling LLM providers (e.g., OpenAI)."""

from __future__ import annotations

import json
from dataclasses import dataclass
import time

import requests
from flask import current_app


@dataclass
class AIClient:
    api_key: str
    api_base: str
    default_model: str

    def chat(self, messages, model: str | None = None, temperature: float = 0.2):
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY / AI_API_KEY is not configured")

        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        app = current_app
        connect_timeout = app.config.get("AI_CONNECT_TIMEOUT_SEC", 15)
        read_timeout = app.config.get("AI_READ_TIMEOUT_SEC", 60)
        max_retries = max(1, int(app.config.get("AI_API_MAX_RETRIES", 3)))
        backoff = float(app.config.get("AI_API_RETRY_BACKOFF", 2.0))

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        attempt = 0
        while True:
            attempt += 1
            try:
                response = requests.post(
                    f"{self.api_base}/chat/completions",
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=(connect_timeout, read_timeout),
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                if attempt >= max_retries:
                    raise
                delay = backoff * attempt
                app.logger.warning(
                    "AI client call failed (attempt %s/%s): %s. Retrying in %.1fs",
                    attempt,
                    max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)


def get_ai_client() -> AIClient:
    app = current_app
    client = app.extensions.get("ai_client")
    if client is None:
        client = AIClient(
            api_key=app.config.get("OPENAI_API_KEY", ""),
            api_base=app.config.get("AI_API_BASE", "https://api.openai.com/v1"),
            default_model=app.config.get("AI_EXPLAINER_MODEL", "gpt-5.2"),
        )
        app.extensions["ai_client"] = client
    return client

