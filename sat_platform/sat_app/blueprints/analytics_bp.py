"""Analytics blueprint placeholder."""

from __future__ import annotations

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, current_user

from ..services import analytics_service

analytics_bp = Blueprint("analytics_bp", __name__)


@analytics_bp.get("/ping")
def ping():
    return jsonify({"module": "analytics", "status": "ok"})


@analytics_bp.get("/progress")
@jwt_required()
def progress():
    data = analytics_service.get_progress(current_user.id)
    return jsonify({"progress": data})

