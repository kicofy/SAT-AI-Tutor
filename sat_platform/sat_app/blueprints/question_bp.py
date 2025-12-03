"""Question blueprint placeholder."""

from __future__ import annotations

from flask import Blueprint, jsonify

question_bp = Blueprint("question_bp", __name__)


@question_bp.get("/ping")
def ping():
    return jsonify({"module": "question", "status": "ok"})

