"""Endpoints for user suggestions / feedback."""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, current_user

from ..schemas.support_schema import SuggestionSchema
from ..services import settings_service, mail_service

support_bp = Blueprint("support_bp", __name__, url_prefix="/api/support")

suggestion_schema = SuggestionSchema()
SUGGESTION_EMAIL_KEY = "suggestion_email"


@support_bp.post("/suggestions")
@jwt_required()
def submit_suggestion():
    payload = suggestion_schema.load(request.get_json() or {})
    recipient = settings_service.get_setting(SUGGESTION_EMAIL_KEY)
    if not recipient:
        return (
            jsonify({"message": "suggestion_email_not_configured"}),
            HTTPStatus.BAD_REQUEST,
        )
    user = current_user
    subject = f"[Suggestion] {payload['title']}"
    app_name = current_app.config.get("APP_NAME", "SAT AI Tutor")
    portal_url = current_app.config.get("APP_URL") or current_app.config.get("FRONTEND_URL") or "#"
    contact_line = payload.get("contact") or "未提供"
    text_body = (
        f"{app_name} - 用户建议/投诉\n"
        f"----------------------------------------\n"
        f"标题: {payload['title']}\n"
        f"用户 ID: {user.id}\n"
        f"账户: {user.email}\n"
        f"用户名: {user.username or '-'}\n"
        f"联系方式: {contact_line}\n"
        f"入口: {portal_url}\n"
        f"----------------------------------------\n"
        f"{payload['content']}"
    )
    formatted = payload["content"].strip().replace("\n", "<br/>")
    html_body = f"""
      <table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,'Microsoft YaHei',sans-serif;background:#f8fafc;padding:16px 0;">
        <tr>
          <td align="center">
            <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;padding:24px;border:1px solid #e2e8f0;">
              <tr>
                <td style="text-align:center;padding-bottom:12px;">
                  <p style="margin:0;font-size:13px;letter-spacing:0.35em;text-transform:uppercase;color:#94a3b8;">{app_name}</p>
                  <h2 style="margin:8px 0 0;font-size:20px;color:#0f172a;">用户建议 / 投诉</h2>
                </td>
              </tr>
              <tr>
                <td style="font-size:14px;color:#0f172a;line-height:1.6;">
                  <p style="margin:0;"><strong>标题：</strong>{payload['title']}</p>
                  <p style="margin:4px 0;"><strong>用户：</strong>{user.email} (ID: {user.id})</p>
                  <p style="margin:4px 0;"><strong>联系方式：</strong>{contact_line}</p>
                  <p style="margin:4px 0;"><strong>入口：</strong><a href="{portal_url}" target="_blank" style="color:#2563eb;">{portal_url}</a></p>
                  <hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0;" />
                  <p style="margin:0;color:#334155;">{formatted}</p>
                </td>
              </tr>
              <tr>
                <td style="font-size:12px;color:#94a3b8;padding-top:24px;text-align:center;">
                  请在 1-2 个工作日内回复。如需系统访问，请登录 <a href="{portal_url}" style="color:#2563eb;">{portal_url}</a>。
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    """
    mail_service.send_email(
        to=recipient,
        subject=subject,
        text=text_body,
        html=html_body,
        reply_to=payload.get("contact") or user.email,
        headers={"X-SAT-Feedback-Type": "suggestion"},
    )
    return jsonify({"message": "submitted"})

