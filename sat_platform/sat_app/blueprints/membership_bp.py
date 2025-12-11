" ""Membership related endpoints for subscription intent requests.""" 

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, current_user
from marshmallow import ValidationError

from ..extensions import db
from ..models import MembershipOrder
from ..schemas import (
    MembershipOrderSchema,
    MembershipOrderCreateSchema,
)
from ..services import membership_service


membership_bp = Blueprint("membership_bp", __name__)

order_schema = MembershipOrderSchema()
orders_schema = MembershipOrderSchema(many=True)
create_schema = MembershipOrderCreateSchema()


def _plan_definition(plan: str) -> dict:
    plans = {
        "monthly": {
            "price_cents": current_app.config.get("MEMBERSHIP_MONTHLY_PRICE_CENTS", 3900),
            "days": current_app.config.get("MEMBERSHIP_MONTHLY_DAYS", 30),
        },
        "quarterly": {
            "price_cents": current_app.config.get("MEMBERSHIP_QUARTERLY_PRICE_CENTS", 9900),
            "days": current_app.config.get("MEMBERSHIP_QUARTERLY_DAYS", 90),
        },
    }
    if plan not in plans:
        raise ValidationError({"plan": "Invalid plan"})
    return plans[plan]


@membership_bp.errorhandler(ValidationError)
def handle_validation(err: ValidationError):
    return jsonify({"errors": err.messages}), HTTPStatus.BAD_REQUEST


@membership_bp.post("/orders")
@jwt_required()
def create_order():
    payload = create_schema.load(request.get_json() or {})
    plan = payload["plan"]
    definition = _plan_definition(plan)
    order = MembershipOrder(
        user_id=current_user.id,
        plan=plan,
        price_cents=definition["price_cents"],
        currency=current_app.config.get("MEMBERSHIP_CURRENCY", "USD"),
        user_note=payload.get("note"),
    )
    db.session.add(order)
    db.session.commit()
    return jsonify({"order": order_schema.dump(order)}), HTTPStatus.CREATED


@membership_bp.get("/orders")
@jwt_required()
def list_orders():
    orders = (
        MembershipOrder.query.filter_by(user_id=current_user.id)
        .order_by(MembershipOrder.created_at.desc())
        .all()
    )
    return jsonify({"orders": orders_schema.dump(orders)})

