from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Request
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

from rss.app.core import bot_runtime


router = APIRouter()


class PhoneRequest(BaseModel):
    phone: str


class CodeRequest(BaseModel):
    code: str


class PasswordRequest(BaseModel):
    password: str


def _require_user_client():
    client = bot_runtime.user_client
    if client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram client not initialized")
    return client


@router.get("/api/tg/status")
async def tg_status():
    client = bot_runtime.user_client
    if client is not None and client.is_connected():
        try:
            if await client.is_user_authorized():
                bot_runtime.set_login_status("logged_in")
        except Exception:
            pass
    return {"status": bot_runtime.get_login_status()}


@router.post("/api/tg/auth/phone")
async def tg_auth_phone(payload: PhoneRequest):
    phone = (payload.phone or "").strip()
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number required")

    client = _require_user_client()
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

    bot_runtime.set_login_phone(phone)
    bot_runtime.set_login_code_hash(sent.phone_code_hash)
    bot_runtime.set_login_status("waiting_for_code")
    return {"status": "code_sent"}


@router.post("/api/tg/auth/code")
async def tg_auth_code(payload: CodeRequest):
    code = (payload.code or "").strip()
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code required")

    phone = bot_runtime.login_phone
    code_hash = bot_runtime.login_phone_code_hash
    if not phone or not code_hash:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Send code first")

    client = _require_user_client()
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
async def tg_auth_password(payload: PasswordRequest):
    password = (payload.password or "").strip()
    if not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA password required")

    client = _require_user_client()
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
async def setup_wizard(request: Request):
    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="rss/app/templates")
    return templates.TemplateResponse("setup_wizard.html", {"request": request})
