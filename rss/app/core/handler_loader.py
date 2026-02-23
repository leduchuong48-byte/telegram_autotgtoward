# TODO: 将旧 Handler 的文件读写迁移至 ConfigManager 以支持热重载
import logging
from telethon import events

from handlers import bot_handler
from handlers.commands import dashboard_command_handler, help_handler, start_handler


logger = logging.getLogger(__name__)
_handlers_registered = False


async def register_all_handlers(client) -> None:
    global _handlers_registered
    if _handlers_registered:
        return

    client.add_event_handler(
        start_handler,
        events.NewMessage(pattern=r"^/start(?:@\w+)?(?:\s.*)?$")
    )
    client.add_event_handler(
        help_handler,
        events.NewMessage(pattern=r"^/help(?:@\w+)?(?:\s.*)?$")
    )
    client.add_event_handler(
        dashboard_command_handler,
        events.NewMessage(pattern=r"^/web(?:@\w+)?(?:\s.*)?$")
    )
    client.add_event_handler(
        dashboard_command_handler,
        events.NewMessage(pattern=r"^/dashboard(?:@\w+)?(?:\s.*)?$")
    )
    client.add_event_handler(bot_handler.message_handler, events.NewMessage(incoming=True))
    client.add_event_handler(bot_handler.callback_handler, events.CallbackQuery())

    logger.info("Legacy handlers loaded")
    _handlers_registered = True
