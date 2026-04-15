from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .auth import get_current_user
from ..core.config_manager import config_manager


router = APIRouter()
templates = Jinja2Templates(directory="rss/app/templates")


@router.get("/config_editor", response_class=HTMLResponse)
async def config_editor(request: Request):
    return templates.TemplateResponse("config_editor.html", {"request": request})


@router.get("/api/config")
async def get_config(user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return config_manager.get_config()


@router.put("/api/config")
async def update_config(payload: dict, user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    try:
        updated = config_manager.update_config(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"success": True, "config": updated}


@router.post("/api/config/reload")
async def reload_config(user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    config_manager.reload_config()
    return {"success": True, "message": "Config reloaded"}




class InviteCodePayload(BaseModel):
    invite_code: str


@router.get("/api/config/invite-code")
async def get_invite_code(user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return {"invite_code": config_manager.get_invite_code()}


@router.patch("/api/config/invite-code")
async def update_invite_code(payload: InviteCodePayload, user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    try:
        code = config_manager.set_invite_code(payload.invite_code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return {"success": True, "invite_code": code}


@router.post("/api/config/invite-code/rotate")
async def rotate_invite_code(user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    code = config_manager.rotate_invite_code()
    return {"success": True, "invite_code": code}


@router.get("/api/config/global")
async def get_global_config(user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    config = config_manager.get_config()
    telegram = config.get("telegram", {}) if isinstance(config.get("telegram"), dict) else {}
    ai_service = config.get("ai_service", {}) if isinstance(config.get("ai_service"), dict) else {}

    base_dir = config_manager.config_path.parent
    sessions_dir = base_dir / "sessions"
    user_session = sessions_dir / "user.session"
    bot_session = sessions_dir / "bot.session"

    return {
        "telegram": {
            "api_id": telegram.get("api_id", ""),
            "api_hash": telegram.get("api_hash", ""),
            "phone": telegram.get("phone", ""),
            "user_id": telegram.get("user_id", ""),
            "bot_token_set": bool(telegram.get("bot_token")),
        },
        "ai_service": {
            "enabled": ai_service.get("enabled", False),
            "provider": ai_service.get("provider", "openai"),
            "base_url": ai_service.get("base_url", ""),
            "model": ai_service.get("model", ""),
            "key_strategy": ai_service.get("key_strategy", "sequence"),
            "api_key_set": bool(ai_service.get("api_key")),
        },
        "session": {
            "user_session_exists": user_session.exists(),
            "bot_session_exists": bot_session.exists(),
        },
    }


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _is_masked_value(value) -> bool:
    if not isinstance(value, str):
        return False
    cleaned = value.strip()
    if not cleaned:
        return False
    return set(cleaned) == {"*"}


def _maybe_set(target: dict, key: str, value, allow_empty: bool = False) -> None:
    if value is None:
        return
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned and not allow_empty:
            return
        target[key] = cleaned
        return
    target[key] = value


@router.patch("/api/config/global")
async def update_global_config(request: Request, user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    payload = {}
    try:
        payload = await request.json()
        if payload is None:
            payload = {}
    except Exception:
        form = await request.form()
        payload = dict(form)

    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    config = config_manager.get_config()
    telegram = config.get("telegram", {}) if isinstance(config.get("telegram"), dict) else {}
    ai_service = config.get("ai_service", {}) if isinstance(config.get("ai_service"), dict) else {}

    telegram_payload = payload.get("telegram", {}) if isinstance(payload.get("telegram"), dict) else {}
    ai_payload = payload.get("ai_service", {}) if isinstance(payload.get("ai_service"), dict) else {}

    _maybe_set(telegram, "api_id", telegram_payload.get("api_id"))
    _maybe_set(telegram, "api_hash", telegram_payload.get("api_hash"))
    _maybe_set(telegram, "phone", telegram_payload.get("phone"))
    _maybe_set(telegram, "user_id", telegram_payload.get("user_id"))

    bot_token_value = telegram_payload.get("bot_token")
    if bot_token_value and not _is_masked_value(bot_token_value):
        _maybe_set(telegram, "bot_token", bot_token_value)

    if "enabled" in ai_payload:
        enabled_value = _parse_bool(ai_payload.get("enabled"))
        if enabled_value is not None:
            ai_service["enabled"] = enabled_value
    _maybe_set(ai_service, "provider", ai_payload.get("provider"))
    _maybe_set(ai_service, "model", ai_payload.get("model"))
    _maybe_set(ai_service, "base_url", ai_payload.get("base_url"))
    _maybe_set(ai_service, "key_strategy", ai_payload.get("key_strategy"))

    api_key_value = ai_payload.get("api_key")
    if api_key_value and not _is_masked_value(api_key_value):
        _maybe_set(ai_service, "api_key", api_key_value)

    config["telegram"] = telegram
    config["ai_service"] = ai_service

    updated = config_manager.update_config(config)
    config_manager.reload_config()
    return {"success": True, "config": updated}


@router.patch("/api/config/settings")
async def update_settings(request: Request, user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    payload = {}
    try:
        payload = await request.json()
        if payload is None:
            payload = {}
    except Exception:
        form = await request.form()
        payload = dict(form)

    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    config = config_manager.get_config()
    telegram = config.get("telegram", {}) if isinstance(config.get("telegram"), dict) else {}
    ai_service = config.get("ai_service", {}) if isinstance(config.get("ai_service"), dict) else {}

    telegram_payload = payload.get("telegram", {}) if isinstance(payload.get("telegram"), dict) else {}
    ai_payload = payload.get("ai_service", {}) if isinstance(payload.get("ai_service"), dict) else {}

    _maybe_set(telegram, "api_id", telegram_payload.get("api_id"))
    _maybe_set(telegram, "api_hash", telegram_payload.get("api_hash"))
    _maybe_set(telegram, "bot_token", telegram_payload.get("bot_token"))
    _maybe_set(telegram, "phone", telegram_payload.get("phone"))
    _maybe_set(telegram, "user_id", telegram_payload.get("user_id"))

    if "enabled" in ai_payload:
        enabled_value = _parse_bool(ai_payload.get("enabled"))
        if enabled_value is not None:
            ai_service["enabled"] = enabled_value
    _maybe_set(ai_service, "provider", ai_payload.get("provider"))
    _maybe_set(ai_service, "api_key", ai_payload.get("api_key"))
    _maybe_set(ai_service, "model", ai_payload.get("model"))
    _maybe_set(ai_service, "base_url", ai_payload.get("base_url"))
    _maybe_set(ai_service, "key_strategy", ai_payload.get("key_strategy"))

    config["telegram"] = telegram
    config["ai_service"] = ai_service

    updated = config_manager.update_config(config)
    config_manager.reload_config()
    return {"success": True, "config": updated}
