"""SAT AI Tutor application entry point.

Loads environment variables, instantiates the Flask app via the sat_app factory,
and exposes `app` for `flask --app app run`.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Ensure `.env` files are loaded before configuration happens inside `create_app`.
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

from sat_app import create_app  # noqa: E402  (import after load_dotenv)

app = create_app()


def _resolve_port() -> int:
    """Return the port that should be used when running via `python app.py`."""

    return int(os.getenv("PORT", os.getenv("FLASK_RUN_PORT", 5080)))


if __name__ == "__main__":  # pragma: no cover
    app.run(
        debug=app.config.get("DEBUG", False),
        host=os.getenv("HOST", "0.0.0.0"),
        port=_resolve_port(),
    )

