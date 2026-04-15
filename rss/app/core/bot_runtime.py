import asyncio
from datetime import datetime
import time
from typing import Optional, TYPE_CHECKING, Any, Callable, Awaitable

if TYPE_CHECKING:
    from telethon import TelegramClient
else:
    TelegramClient = Any

user_client: Optional[TelegramClient] = None
bot_client: Optional[TelegramClient] = None
runtime_loop: Optional[asyncio.AbstractEventLoop] = None
login_status: str = "config_missing"
login_phone: Optional[str] = None
login_phone_code_hash: Optional[str] = None
services_started: bool = False
last_connect_time: Optional[float] = None
message_count: int = 0
runtime_reason: str = ""

_login_handler: Optional[Callable[[], Awaitable[None]]] = None
_runtime_initializer: Optional[Callable[[bool], Awaitable[bool]]] = None
_service_stopper: Optional[Callable[[], Awaitable[None]]] = None
_runtime_init_lock = asyncio.Lock()
_service_stop_lock = asyncio.Lock()


def bind_clients(user: Optional[TelegramClient], bot: Optional[TelegramClient], loop: asyncio.AbstractEventLoop) -> None:
    global user_client, bot_client, runtime_loop
    user_client = user
    bot_client = bot
    runtime_loop = loop


def set_runtime_initializer(initializer: Callable[[bool], Awaitable[bool]]) -> None:
    global _runtime_initializer
    _runtime_initializer = initializer


def set_service_stopper(stopper: Callable[[], Awaitable[None]]) -> None:
    global _service_stopper
    _service_stopper = stopper


async def ensure_runtime_initialized(force: bool = False) -> bool:
    global _runtime_initializer
    if not force and user_client is not None and bot_client is not None:
        return True
    if _runtime_initializer is None:
        return False

    async with _runtime_init_lock:
        if not force and user_client is not None and bot_client is not None:
            return True
        return await _runtime_initializer(force)


async def stop_services() -> None:
    global _service_stopper
    if _service_stopper is None:
        return

    async with _service_stop_lock:
        await _service_stopper()


def set_login_handler(handler: Callable[[], Awaitable[None]]) -> None:
    global _login_handler
    _login_handler = handler


async def trigger_login_handler() -> None:
    if _login_handler is None:
        return
    await _login_handler()


def set_login_status(status: str) -> None:
    global login_status
    login_status = status


def get_login_status() -> str:
    return login_status


def set_login_phone(phone: Optional[str]) -> None:
    global login_phone
    login_phone = phone


def set_login_code_hash(code_hash: Optional[str]) -> None:
    global login_phone_code_hash
    login_phone_code_hash = code_hash


def clear_login_state() -> None:
    global login_phone, login_phone_code_hash
    login_phone = None
    login_phone_code_hash = None


def mark_services_started() -> None:
    global services_started
    services_started = True
    set_runtime_reason("")


def mark_services_stopped() -> None:
    global services_started
    services_started = False


def mark_connect() -> None:
    global last_connect_time
    last_connect_time = time.time()


def get_last_connect_iso() -> Optional[str]:
    if last_connect_time is None:
        return None
    return datetime.utcfromtimestamp(last_connect_time).isoformat() + "Z"



def set_runtime_reason(reason: str) -> None:
    global runtime_reason
    runtime_reason = reason or ""


def get_runtime_reason() -> str:
    return runtime_reason

def increment_message_count() -> None:
    global message_count
    message_count += 1
