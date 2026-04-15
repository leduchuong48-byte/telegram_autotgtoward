from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Request, Depends
from fastapi.responses import RedirectResponse
from pathlib import Path
import os
import time
from pydantic import BaseModel
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
)

from models.models import User, get_session
from rss.app.core import bot_runtime
from rss.app.core.config_manager import config_manager
from rss.app.core.app_state import build_app_state
from .auth import get_current_user


router = APIRouter()


class PhoneRequest(BaseModel):
    phone: str


class CodeRequest(BaseModel):
    code: str


class PasswordRequest(BaseModel):
    password: str


class BootstrapConfigRequest(BaseModel):
    api_id: str
    api_hash: str
    bot_token: str
    user_id: str
    phone: str = ""


class ReplaceConfigRequest(BaseModel):
    api_id: str
    api_hash: str
    bot_token: str
    user_id: str
    phone: str = ""
    confirm_text: str


def _clean(v) -> str:
    return (v or "").strip()


def _has_registered_user() -> bool:
    db_session = get_session()
    try:
        return db_session.query(User).first() is not None
    finally:
        db_session.close()


def _update_telegram_config(data: dict) -> None:
    config = config_manager.get_config()
    telegram = config.get("telegram", {}) if isinstance(config.get("telegram"), dict) else {}
    telegram.update(data)
    config["telegram"] = telegram
    config_manager.update_config(config)
    config_manager.reload_config()

def _current_telegram_config() -> dict:
    config = config_manager.get_config()
    telegram = config.get("telegram", {}) if isinstance(config.get("telegram"), dict) else {}
    return {
        "api_id": _clean(telegram.get("api_id")),
        "api_hash": _clean(telegram.get("api_hash")),
        "bot_token": _clean(telegram.get("bot_token")),
        "user_id": _clean(telegram.get("user_id")),
        "phone": _clean(telegram.get("phone")),
    }


def _resolve_replace_data(payload: ReplaceConfigRequest, current: dict) -> dict:
    incoming_bot_token = _clean(payload.bot_token)
    if incoming_bot_token == "******":
        incoming_bot_token = current.get("bot_token", "")

    return {
        "api_id": _clean(payload.api_id),
        "api_hash": _clean(payload.api_hash),
        "bot_token": incoming_bot_token,
        "user_id": _clean(payload.user_id),
        "phone": _clean(payload.phone),
    }


def _changed_fields(current: dict, updated: dict) -> list[str]:
    fields = []
    for key in ("api_id", "api_hash", "bot_token", "user_id", "phone"):
        if _clean(current.get(key)) != _clean(updated.get(key)):
            fields.append(key)
    return fields


def _reset_scope_from_changes(changed_fields: list[str]) -> str:
    if any(field in changed_fields for field in ("api_id", "api_hash")):
        return "all"
    if "bot_token" in changed_fields:
        return "bot_only"
    return "none"


def _require_auth_if_user_exists(user) -> None:
    if _has_registered_user() and not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


async def _require_user_client():
    await bot_runtime.ensure_runtime_initialized()
    client = bot_runtime.user_client
    if client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram 配置未完成，请先在向导填写 API 信息")
    return client


def _is_config_complete() -> bool:
    config = config_manager.get_config()
    telegram = config.get("telegram", {}) if isinstance(config.get("telegram"), dict) else {}
    return all(_clean(telegram.get(k)) for k in ("api_id", "api_hash", "bot_token", "user_id"))


@router.get("/api/tg/status")
async def tg_status():
    complete = _is_config_complete()
    if not complete:
        return {"status": "config_missing"}

    initialized = await bot_runtime.ensure_runtime_initialized()
    if not initialized:
        bot_runtime.set_login_status("config_missing")
        return {"status": "config_missing"}

    client = bot_runtime.user_client
    if client is not None:
        if not client.is_connected():
            await client.connect()
            bot_runtime.mark_connect()

        try:
            if await client.is_user_authorized():
                if not bot_runtime.services_started:
                    try:
                        await bot_runtime.trigger_login_handler()
                    except Exception:
                        pass
                if bot_runtime.services_started:
                    bot_runtime.set_login_status("logged_in")
                else:
                    bot_runtime.set_login_status("service_not_started")
            else:
                bot_runtime.set_login_status("waiting_for_phone")
        except Exception:
            pass

    return {"status": bot_runtime.get_login_status()}


@router.patch("/api/bootstrap/telegram-config")
async def bootstrap_telegram_config(payload: BootstrapConfigRequest, user=Depends(get_current_user)):
    _require_auth_if_user_exists(user)

    data = {
        "api_id": _clean(payload.api_id),
        "api_hash": _clean(payload.api_hash),
        "bot_token": _clean(payload.bot_token),
        "user_id": _clean(payload.user_id),
        "phone": _clean(payload.phone),
    }
    missing = [k for k in ("api_id", "api_hash", "bot_token", "user_id") if not data[k]]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"缺少必要字段: {', '.join(missing)}")

    _update_telegram_config(data)

    initialized = await bot_runtime.ensure_runtime_initialized(force=True)
    if initialized:
        bot_runtime.set_login_status("waiting_for_phone")

    return {"success": True, "initialized": initialized, "status": bot_runtime.get_login_status()}


@router.post("/api/bootstrap/telegram-config/replace")
async def replace_telegram_config(payload: ReplaceConfigRequest, user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    current = _current_telegram_config()
    data = _resolve_replace_data(payload, current)

    missing = [k for k in ("api_id", "api_hash", "bot_token", "user_id") if not data[k]]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"缺少必要字段: {', '.join(missing)}")

    changed_fields = _changed_fields(current, data)
    reset_scope = _reset_scope_from_changes(changed_fields)

    if reset_scope == "all" and _clean(payload.confirm_text).upper() != "REPLACE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入 REPLACE 确认替换")

    _update_telegram_config(data)

    restart_required = False
    reauth_required = False

    if reset_scope in ("all", "bot_only"):
        try:
            await bot_runtime.stop_services()
        except Exception:
            # Best-effort stop: continue replace flow to avoid blocking bot token updates.
            pass

        session_dir = Path("./sessions")
        if session_dir.exists():
            patterns = ["*.session*"] if reset_scope == "all" else ["bot.session*"]
            for pattern in patterns:
                for item in session_dir.glob(pattern):
                    try:
                        item.unlink()
                    except Exception:
                        pass

        bot_runtime.clear_login_state()
        bot_runtime.mark_services_stopped()

        if reset_scope == "bot_only":
            initialized = await bot_runtime.ensure_runtime_initialized(force=True)
            if initialized:
                try:
                    await bot_runtime.trigger_login_handler()
                    bot_runtime.set_login_status("logged_in")
                except Exception:
                    bot_runtime.set_login_status("config_updated_restart_required")
                    restart_required = True
            else:
                bot_runtime.set_login_status("config_updated_restart_required")
                restart_required = True
        else:
            bot_runtime.set_login_status("config_updated_restart_required")
            restart_required = True
            reauth_required = True

    if not changed_fields:
        message = "配置未发生变化。"
    elif reset_scope == "none":
        message = "配置已更新，无需重置 Telegram 会话。"
    elif reset_scope == "bot_only" and not restart_required:
        message = "仅检测到 BOT_TOKEN 变更：已自动刷新 bot 会话并生效，不影响用户账号会话。"
    elif reset_scope == "bot_only":
        message = "仅检测到 BOT_TOKEN 变更：bot 会话已重置，但自动激活失败。建议执行一次安全重启。"
    else:
        message = "检测到 API_ID/API_HASH 变更：已重置全部 Telegram 会话，建议执行一次安全重启并重新完成登录。"

    return {
        "success": True,
        "status": bot_runtime.get_login_status(),
        "changed_fields": changed_fields,
        "reset_scope": reset_scope,
        "restart_required": restart_required,
        "reauth_required": reauth_required,
        "session_preserved": reset_scope != "all",
        "message": message,
    }


@router.post("/api/bootstrap/telegram-session/reset")
async def reset_telegram_session(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    try:
        await bot_runtime.stop_services()
    except Exception:
        # Best-effort stop: continue reset flow.
        pass

    session_dir = Path("./sessions")
    if session_dir.exists():
        for item in session_dir.glob("*.session*"):
            try:
                item.unlink()
            except Exception:
                pass

    bot_runtime.clear_login_state()
    bot_runtime.mark_services_stopped()
    await bot_runtime.ensure_runtime_initialized(force=True)
    bot_runtime.set_login_status("waiting_for_phone")
    return {"success": True}


@router.post("/api/tg/auth/phone")
async def tg_auth_phone(payload: PhoneRequest, user=Depends(get_current_user)):
    _require_auth_if_user_exists(user)
    phone = (payload.phone or "").strip()
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number required")

    client = await _require_user_client()
    if not client.is_connected():
        await client.connect()
        bot_runtime.mark_connect()

    if await client.is_user_authorized():
        bot_runtime.set_login_status("logged_in")
        return {"status": "logged_in"}

    try:
        sent = await client.send_code_request(phone)
    except PhoneNumberInvalidError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid phone number")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    config = config_manager.get_config()
    telegram = config.get("telegram", {}) if isinstance(config.get("telegram"), dict) else {}
    telegram["phone"] = phone
    config["telegram"] = telegram
    config_manager.update_config(config)

    bot_runtime.set_login_phone(phone)
    bot_runtime.set_login_code_hash(sent.phone_code_hash)
    bot_runtime.set_login_status("waiting_for_code")
    return {"status": "code_sent"}


@router.post("/api/tg/auth/code")
async def tg_auth_code(payload: CodeRequest, user=Depends(get_current_user)):
    _require_auth_if_user_exists(user)
    code = (payload.code or "").strip()
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code required")

    phone = bot_runtime.login_phone
    code_hash = bot_runtime.login_phone_code_hash
    if not phone or not code_hash:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Send code first")

    client = await _require_user_client()
    if not client.is_connected():
        await client.connect()
        bot_runtime.mark_connect()

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=code_hash)
    except SessionPasswordNeededError:
        bot_runtime.set_login_status("waiting_for_password")
        return {"status": "2fa_required"}
    except PhoneCodeInvalidError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")
    except PhoneCodeExpiredError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code expired")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    bot_runtime.clear_login_state()
    bot_runtime.set_login_status("logged_in")
    await bot_runtime.trigger_login_handler()
    return {"status": "success"}


@router.post("/api/tg/auth/password")
async def tg_auth_password(payload: PasswordRequest, user=Depends(get_current_user)):
    _require_auth_if_user_exists(user)
    password = (payload.password or "").strip()
    if not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA password required")

    client = await _require_user_client()
    if not client.is_connected():
        await client.connect()
        bot_runtime.mark_connect()

    try:
        await client.sign_in(password=password)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    bot_runtime.clear_login_state()
    bot_runtime.set_login_status("logged_in")
    await bot_runtime.trigger_login_handler()
    return {"status": "success"}


@router.post("/api/tg/logout")
async def tg_logout(background_tasks: BackgroundTasks):
    client = bot_runtime.user_client
    if client is not None and client.is_connected():
        await client.disconnect()
    bot = bot_runtime.bot_client
    if bot is not None and bot.is_connected():
        await bot.disconnect()

    session_dir = Path("./sessions")
    if session_dir.exists():
        for item in session_dir.glob("*.session*"):
            try:
                item.unlink()
            except Exception:
                pass

    bot_runtime.clear_login_state()
    bot_runtime.set_login_status("waiting_for_phone")
    bot_runtime.mark_services_stopped()

    def _restart():
        time.sleep(1)
        os._exit(0)

    background_tasks.add_task(_restart)
    return {"success": True}


@router.get("/setup_wizard")
async def setup_wizard(request: Request, user=Depends(get_current_user)):
    state = build_app_state(bool(user))
    if not state["auth"]["authenticated"] and state["auth"]["user_exists"]:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    if state["auth"]["authenticated"] and not state["routing"]["allow_setup"]:
        return RedirectResponse(url=state["routing"]["default_route"], status_code=status.HTTP_302_FOUND)

    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="rss/app/templates")
    return templates.TemplateResponse("setup_wizard.html", {"request": request})
