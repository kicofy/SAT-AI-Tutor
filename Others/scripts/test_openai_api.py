#!/usr/bin/env python3
"""
Simple smoke test for the OpenAI API.

Usage:
    python test_openai_api.py

Environment variables:
    OPENAI_API_KEY        - required, your API key.
    OPENAI_API_BASE       - optional, defaults to https://api.openai.com/v1.
    OPENAI_TEST_MODEL     - optional, defaults to gpt-4.1-mini.
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from typing import Any

import requests


def pick_random_prompt() -> str:
    prompts = [
        "Explain why the sky appears blue in clear weather using everyday language.",
        "List three creative ways a high school student can stay focused while studying.",
        "Describe a real-world scenario where probability helps inform a decision.",
        "If you could design a new feature for an educational app, what would it be and why?",
        "Summarize the main idea of the scientific method in two sentences.",
    ]
    return random.choice(prompts)


def load_dotenv_if_present() -> None:
    """Load a .env file if it exists somewhere above this script."""
    env_path = None
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.is_file():
            env_path = candidate
            break
    if not env_path:
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def call_openai(prompt: str, *, api_key: str, api_base: str, model: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful SAT study tutor."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    response = requests.post(
        f"{api_base}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=(15, 60),
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    load_dotenv_if_present()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_TEST_MODEL", "gpt-4.1-mini")

    prompt = pick_random_prompt()
    print(f"Using model: {model}")
    print(f"Prompt: {prompt}\n")

    try:
        data = call_openai(prompt, api_key=api_key, api_base=api_base, model=model)
    except requests.HTTPError as exc:
        print(f"HTTP {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        sys.exit(2)
    except requests.RequestException as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        sys.exit(3)

    message = data["choices"][0]["message"]["content"]
    tokens = data["usage"]

    print("Response:")
    print(message.strip())
    print("\nUsage:")
    print(json.dumps(tokens, indent=2))


if __name__ == "__main__":
    main()

