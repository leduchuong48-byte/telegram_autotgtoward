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
login_status: str = "waiting_for_phone"
login_phone: Optional[str] = None
login_phone_code_hash: Optional[str] = None
services_started: bool = False
_login_handler: Optional[Callable[[], Awaitable[None]]] = None
last_connect_time: Optional[float] = None
message_count: int = 0


def bind_clients(user: TelegramClient, bot: TelegramClient, loop: asyncio.AbstractEventLoop) -> None:
    global user_client, bot_client, runtime_loop
    user_client = user
    bot_client = bot
    runtime_loop = loop


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


def increment_message_count() -> None:
    global message_count
    message_count += 1
