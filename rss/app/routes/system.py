import os
import time
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
import psutil
from pydantic import BaseModel

from .auth import get_current_user
from ..core.forwarding_service import forwarding_service
from rss.app.core.app_state import build_app_state

router = APIRouter()


class RestartRequest(BaseModel):
    confirm_text: str


def format_uptime(seconds: int) -> str:
    seconds = max(0, seconds)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    if days > 0:
        return f"{days}天 {hours}小时 {minutes}分钟"
    if hours > 0:
        return f"{hours}小时 {minutes}分钟"
    return f"{minutes}分钟"


@router.get("/api/app/state")
async def app_state(user=Depends(get_current_user)):
    return build_app_state(bool(user))


@router.get("/api/system/bootstrap-status")
async def bootstrap_status(user=Depends(get_current_user)):
    state = build_app_state(bool(user))
    if not state["auth"]["authenticated"] and state["auth"]["user_exists"]:
        return {"status": "auth_required"}

    return {
        "status": state["telegram"]["auth_status"] if state["bootstrap"]["config_complete"] else "config_missing",
        "config_complete": state["bootstrap"]["config_complete"],
        "required_fields": state["bootstrap"]["required_fields"],
        "services_started": state["runtime"]["services_started"],
        "reason": state["runtime"].get("reason", ""),
        "user_session_exists": state["telegram"]["user_session_exists"],
        "bot_session_exists": state["telegram"]["bot_session_exists"],
    }


@router.post("/api/system/restart")
async def request_restart(payload: RestartRequest, background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    if (payload.confirm_text or "").strip().upper() != "RESTART":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入 RESTART 确认重启")

    def _restart():
        time.sleep(1)
        os._exit(0)

    background_tasks.add_task(_restart)
    return {"success": True, "message": "重启指令已接收，容器将自动拉起"}


@router.get("/api/system/status")
async def system_status(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    try:
        uptime_seconds = int(time.time() - psutil.Process(os.getpid()).create_time())
    except Exception:
        uptime_seconds = int(time.time() - psutil.boot_time())
    return {
        "cpu_percent": round(cpu_percent, 1),
        "memory_percent": round(memory.percent, 1),
        "uptime_seconds": max(0, uptime_seconds),
        "uptime": format_uptime(uptime_seconds),
        "status": "online",
    }


@router.get("/api/system/forwarding")
async def forwarding_status(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    return forwarding_service.get_status()
