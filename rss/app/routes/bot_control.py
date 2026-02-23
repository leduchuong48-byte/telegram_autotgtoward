import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .auth import get_current_user
from ..core import bot_runtime


router = APIRouter(prefix="/api/bot")


class SendTestRequest(BaseModel):
    target: str
    message: str
    chat_id: Optional[str] = None


def _resolve_target(payload: SendTestRequest) -> str:
    target = (payload.target or "").strip()
    if not target:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标不能为空")
    if target == "me":
        return "me"
    if target == "chat_id":
        if not payload.chat_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 chat_id")
        return str(payload.chat_id).strip()
    return target


def _pick_client(target: str):
    if target == "me" and bot_runtime.user_client is not None:
        return bot_runtime.user_client
    if bot_runtime.bot_client is not None:
        return bot_runtime.bot_client
    if bot_runtime.user_client is not None:
        return bot_runtime.user_client
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram 客户端未就绪")


def _get_dc_id(client) -> Optional[int]:
    session = getattr(client, "session", None)
    return getattr(session, "dc_id", None)


@router.get("/status")
async def bot_status(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    client = bot_runtime.bot_client or bot_runtime.user_client
    if client is None or not client.is_connected():
        return {
            "status": "offline",
            "username": None,
            "id": None,
            "ping_ms": None,
            "dialogs_count": 0,
            "dc_id": None,
            "session_type": None,
            "last_reconnect_at": bot_runtime.get_last_connect_iso(),
            "messages_processed": bot_runtime.message_count
        }

    try:
        start = time.perf_counter()
        me = await client.get_me()
        ping_ms = int((time.perf_counter() - start) * 1000)

        dialogs_count = 0
        try:
            try:
                dialogs = await client.get_dialogs(limit=50)
            except TypeError:
                dialogs = await client.get_dialogs()
            dialogs_count = len(dialogs)
        except Exception:
            dialogs_count = 0

        session_type = None
        if bot_runtime.user_client is not None and bot_runtime.user_client.is_connected():
            try:
                if await bot_runtime.user_client.is_user_authorized():
                    session_type = "user"
            except Exception:
                session_type = None
        if session_type is None and bot_runtime.bot_client is not None and bot_runtime.bot_client.is_connected():
            try:
                if await bot_runtime.bot_client.is_user_authorized():
                    session_type = "bot"
            except Exception:
                session_type = session_type

        return {
            "status": "online",
            "username": getattr(me, "username", None),
            "id": getattr(me, "id", None),
            "ping_ms": ping_ms,
            "dialogs_count": dialogs_count,
            "dc_id": _get_dc_id(client),
            "session_type": session_type,
            "last_reconnect_at": bot_runtime.get_last_connect_iso(),
            "messages_processed": bot_runtime.message_count
        }
    except Exception:
        return {
            "status": "offline",
            "username": None,
            "id": None,
            "ping_ms": None,
            "dialogs_count": 0,
            "dc_id": None,
            "session_type": None,
            "last_reconnect_at": bot_runtime.get_last_connect_iso(),
            "messages_processed": bot_runtime.message_count
        }


@router.post("/send_test")
async def send_test(payload: SendTestRequest, user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息不能为空")

    target = _resolve_target(payload)
    client = _pick_client(target)
    if not client.is_connected():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram 客户端未连接")

    destination = target
    if target not in ("me",):
        try:
            destination = int(target)
        except ValueError:
            destination = target

    try:
        await client.send_message(destination, message)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return {"success": True}
