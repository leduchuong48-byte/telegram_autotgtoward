import time
from fastapi import APIRouter, Depends, HTTPException, status
import psutil
from .auth import get_current_user
from ..core.forwarding_service import forwarding_service

router = APIRouter()

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

@router.get("/api/system/status")
async def system_status(user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    uptime_seconds = int(time.time() - psutil.boot_time())
    return {
        "cpu_percent": round(cpu_percent, 1),
        "memory_percent": round(memory.percent, 1),
        "uptime_seconds": max(0, uptime_seconds),
        "uptime": format_uptime(uptime_seconds),
        "status": "online"
    }


@router.get("/api/system/forwarding")
async def forwarding_status(user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    return forwarding_service.get_status()
