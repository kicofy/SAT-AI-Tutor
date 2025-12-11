"""Utility helpers for application-wide settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..extensions import db
from ..models import GeneralSetting


@lru_cache(maxsize=64)
def get_setting(key: str, default: str | None = None) -> str | None:
    setting = GeneralSetting.query.filter_by(key=key).first()
    if setting:
        return setting.value
    return default


def set_setting(key: str, value: str | None) -> None:
    setting = GeneralSetting.query.filter_by(key=key).first()
    if not setting:
        setting = GeneralSetting(key=key)
    setting.value = value
    db.session.add(setting)
    db.session.commit()
    get_setting.cache_clear()


def get_many(keys: list[str]) -> dict[str, str | None]:
    settings = GeneralSetting.query.filter(GeneralSetting.key.in_(keys)).all()
    mapping = {setting.key: setting.value for setting in settings}
    return {key: mapping.get(key) for key in keys}

