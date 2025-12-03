"""Student blueprint placeholder."""

from __future__ import annotations

from flask import Blueprint, jsonify

student_bp = Blueprint("student_bp", __name__)


@student_bp.get("/ping")
def ping():
    return jsonify({"module": "student", "status": "ok"})

