from __future__ import annotations

import os
from pathlib import Path

from models.models import User, get_session
from rss.app.core import bot_runtime
from rss.app.core.config_manager import config_manager


def has_registered_user() -> bool:
    db_session = get_session()
    try:
        return db_session.query(User).first() is not None
    finally:
        db_session.close()


def _effective_telegram_required() -> dict:
    config = config_manager.get_config()
    telegram = config.get("telegram", {}) if isinstance(config.get("telegram"), dict) else {}

    def pick(key: str, env_key: str) -> bool:
        return bool((telegram.get(key) or "").strip() or (os.getenv(env_key) or "").strip())

    return {
        "api_id": pick("api_id", "API_ID"),
        "api_hash": pick("api_hash", "API_HASH"),
        "bot_token": pick("bot_token", "BOT_TOKEN"),
        "user_id": pick("user_id", "USER_ID"),
    }


def _session_flags() -> dict:
    sessions_dir = Path('./sessions').resolve()
    return {
        "user_session_exists": (sessions_dir / "user.session").exists(),
        "bot_session_exists": (sessions_dir / "bot.session").exists(),
    }


def build_app_state(authenticated: bool) -> dict:
    user_exists = has_registered_user()
    required = _effective_telegram_required()
    config_complete = all(required.values())
    status = bot_runtime.get_login_status() or "config_missing"

    if not user_exists:
        phase = "first_admin_setup"
    elif not authenticated:
        phase = "unauthenticated"
    elif status == "config_updated_restart_required":
        phase = "restart_required"
    elif not config_complete:
        phase = "telegram_config_required"
    elif status in {"waiting_for_phone", "waiting_for_code", "waiting_for_password", "config_invalid"}:
        phase = "telegram_auth_in_progress"
    elif status == "service_not_started":
        phase = "degraded"
    elif status == "logged_in":
        phase = "ready" if bot_runtime.services_started else "degraded"
    else:
        phase = "telegram_auth_in_progress"

    allow_setup = phase in {"telegram_config_required", "telegram_auth_in_progress"}
    allow_dashboard = phase in {"ready", "degraded", "restart_required"}

    if not user_exists:
        default_route = "/register"
    elif not authenticated:
        default_route = "/login"
    elif allow_dashboard:
        default_route = "/dashboard"
    else:
        default_route = "/setup_wizard"

    return {
        "phase": phase,
        "auth": {
            "authenticated": authenticated,
            "user_exists": user_exists,
        },
        "bootstrap": {
            "config_complete": config_complete,
            "required_fields": required,
        },
        "telegram": {
            "auth_status": status,
            **_session_flags(),
        },
        "runtime": {
            "services_started": bool(bot_runtime.services_started),
            "reason": bot_runtime.get_runtime_reason(),
        },
        "maintenance": {
            "restart_required": phase == "restart_required",
            "reason": bot_runtime.get_runtime_reason(),
            "session_continuity_expected": True,
        },
        "routing": {
            "allow_setup": allow_setup,
            "allow_dashboard": allow_dashboard,
            "default_route": default_route,
        },
    }
