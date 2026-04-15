from telethon import TelegramClient, types
from telethon.tl.types import BotCommand
from telethon.tl.functions.bots import SetBotCommandsRequest
from models.models import init_db
from dotenv import load_dotenv
from message_listener import setup_listeners
import os
import asyncio
import logging
import contextlib
import uvicorn
from models.db_operations import DBOperations
from scheduler.summary_scheduler import SummaryScheduler
from scheduler.chat_updater import ChatUpdater
from handlers.bot_handler import send_welcome_message
from rss.main import app as rss_app
from rss.app.core import bot_runtime
from rss.app.core.config_manager import config_manager
from rss.app.core.handler_loader import register_all_handlers
from rss.app.core.forwarding_service import forwarding_service
from utils.log_config import setup_logging

# 设置Docker日志的默认配置，如果docker-compose.yml中没有配置日志选项将使用这些值
os.environ.setdefault('DOCKER_LOG_MAX_SIZE', '10m')
os.environ.setdefault('DOCKER_LOG_MAX_FILE', '3')

# 设置日志配置
setup_logging()

logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 创建 DBOperations 实例
db_ops = None

scheduler = None
chat_updater = None

user_client = None
bot_client = None
bot_token = ''
phone_number = ''
_runtime_signature = None
_system_ready_lock = asyncio.Lock()
_service_start_lock = asyncio.Lock()


def _normalize_value(value) -> str:
    return (value or '').strip()


def get_telegram_settings() -> dict:
    config = config_manager.get_config()
    logger.info('Using config file: %s', config_manager.config_path)
    telegram = config.get('telegram', {}) if isinstance(config.get('telegram'), dict) else {}

    values = {
        'api_id': _normalize_value(telegram.get('api_id')) or _normalize_value(os.getenv('API_ID')),
        'api_hash': _normalize_value(telegram.get('api_hash')) or _normalize_value(os.getenv('API_HASH')),
        'bot_token': _normalize_value(telegram.get('bot_token')) or _normalize_value(os.getenv('BOT_TOKEN')),
        'phone': _normalize_value(telegram.get('phone')) or _normalize_value(os.getenv('PHONE_NUMBER')),
        'user_id': _normalize_value(telegram.get('user_id')) or _normalize_value(os.getenv('USER_ID')),
    }

    for key, env_key in (
        ('api_id', 'API_ID'),
        ('api_hash', 'API_HASH'),
        ('bot_token', 'BOT_TOKEN'),
        ('phone', 'PHONE_NUMBER'),
        ('user_id', 'USER_ID'),
    ):
        if values[key]:
            os.environ[env_key] = values[key]

    return values


def has_required_telegram_config(values: dict | None = None) -> tuple[bool, list[str]]:
    payload = values or get_telegram_settings()
    required = {
        'api_id': 'API_ID',
        'api_hash': 'API_HASH',
        'bot_token': 'BOT_TOKEN',
        'user_id': 'USER_ID',
    }
    missing = [label for key, label in required.items() if not payload.get(key)]
    return len(missing) == 0, missing


async def initialize_runtime_from_config(force: bool = False) -> bool:
    global user_client, bot_client, bot_token, phone_number, _runtime_signature

    values = get_telegram_settings()
    ok, missing = has_required_telegram_config(values)
    if not ok:
        bot_runtime.bind_clients(None, None, asyncio.get_running_loop())
        bot_runtime.set_login_status('config_missing')
        logger.info('Telegram 配置尚未完成，等待 WebUI 首次配置: %s', ', '.join(missing))
        return False

    try:
        api_id_value = int(values['api_id'])
    except ValueError:
        bot_runtime.set_login_status('config_invalid')
        logger.error('API_ID 必须为整数')
        return False

    if force and user_client is not None and user_client.is_connected():
        await user_client.disconnect()
    if force and bot_client is not None and bot_client.is_connected():
        await bot_client.disconnect()

    new_signature = (api_id_value, values['api_hash'])
    should_recreate_clients = user_client is None or bot_client is None
    if force and _runtime_signature is not None and _runtime_signature != new_signature:
        should_recreate_clients = True

    if should_recreate_clients:
        user_client = TelegramClient('./sessions/user', api_id_value, values['api_hash'])
        bot_client = TelegramClient('./sessions/bot', api_id_value, values['api_hash'])

    _runtime_signature = new_signature
    bot_token = values['bot_token']
    phone_number = values['phone']
    bot_runtime.bind_clients(user_client, bot_client, asyncio.get_running_loop())
    bot_runtime.set_login_status('waiting_for_phone')
    return True


def schedule_forwarding_reload(_: dict | None = None) -> None:
    loop = bot_runtime.runtime_loop
    client = bot_runtime.user_client
    if loop is None or not loop.is_running() or client is None:
        logger.warning('ForwardingService: runtime 未就绪，跳过重载')
        return
    loop.call_soon_threadsafe(asyncio.create_task, forwarding_service.reload_rules(client))


config_manager.register_reload_handler(schedule_forwarding_reload)
logger.info('Config file path resolved to: %s', config_manager.config_path)


async def init_db_ops():
    """初始化 DBOperations 实例"""
    global db_ops
    if db_ops is None:
        db_ops = await DBOperations.create()
    return db_ops


# 创建文件夹
os.makedirs('./sessions', exist_ok=True)
os.makedirs('./temp', exist_ok=True)


# 清空./temp文件夹
def clear_temp_dir():
    for file in os.listdir('./temp'):
        os.remove(os.path.join('./temp', file))


# 初始化数据库
engine = init_db()


async def refresh_dialog_cache(client, label):
    try:
        await client.get_dialogs()
        logger.info(f"{label}对话列表缓存已刷新")
    except Exception as e:
        logger.warning(f"{label}对话列表缓存刷新失败: {str(e)}")


async def ensure_bot_authorized():
    current_bot = bot_runtime.bot_client
    if current_bot is None:
        raise RuntimeError('bot client not initialized')
    if not current_bot.is_connected():
        await current_bot.connect()
        bot_runtime.mark_connect()
    if not await current_bot.is_user_authorized():
        await current_bot.sign_in(bot_token=bot_token)


async def start_services():
    global scheduler, chat_updater
    async with _service_start_lock:
        if bot_runtime.services_started:
            return

        current_user = bot_runtime.user_client
        current_bot = bot_runtime.bot_client
        if current_user is None or current_bot is None:
            logger.warning('Telegram 客户端未初始化，跳过启动服务')
            bot_runtime.set_runtime_reason('clients_not_initialized')
            return

        try:
            await init_db_ops()
            await ensure_bot_authorized()
            await register_all_handlers(current_bot)
            await forwarding_service.reload_rules(current_user)

            hardcoded_targets = [
                # "https://t.me/你的公开群组"
            ]
            env_targets = os.getenv('PRE_RESOLVE_TARGETS', '')
            targets = []
            if env_targets:
                targets.extend([item.strip() for item in env_targets.split(';') if item.strip()])
            targets.extend([item for item in hardcoded_targets if item])

            if targets:
                logger.info(f"开始预解析目标实体，共 {len(targets)} 个")
            for target in targets:
                try:
                    entity = await current_bot.get_entity(target)
                    title = getattr(entity, 'title', None) or getattr(entity, 'first_name', None) or str(entity)
                    logger.info(f"预解析成功: 目标={target} ID={getattr(entity, 'id', None)} 标题={title}")
                except Exception as e:
                    logger.warning(f"预解析失败: 目标={target} err={str(e)}")
                    if isinstance(target, str) and target.isdigit():
                        try:
                            fallback_id = int(f"-100{target}")
                            entity = await current_bot.get_entity(fallback_id)
                            title = getattr(entity, 'title', None) or getattr(entity, 'first_name', None) or str(entity)
                            logger.info(f"预解析成功(补前缀): 目标={fallback_id} ID={getattr(entity, 'id', None)} 标题={title}")
                        except Exception as e2:
                            logger.warning(f"预解析失败(补前缀): 目标={target} err={str(e2)}")

            await refresh_dialog_cache(current_user, '用户客户端')
            await refresh_dialog_cache(current_bot, '机器人客户端')

            await setup_listeners(current_user, current_bot, register_bot_handlers=False)
            await register_bot_commands(current_bot)

            scheduler = SummaryScheduler(current_user, current_bot)
            await scheduler.start()

            chat_updater = ChatUpdater(current_user)
            await chat_updater.start()

            await send_welcome_message(current_bot)

            bot_runtime.mark_services_started()
            bot_runtime.set_login_status('logged_in')
            bot_runtime.set_runtime_reason('')
        except Exception as exc:
            bot_runtime.mark_services_stopped()
            bot_runtime.set_login_status('waiting_for_phone')
            reason = f'service_start_failed:{exc}'
            if 'database is locked' in str(exc).lower():
                reason = 'db_locked'
            bot_runtime.set_runtime_reason(reason)
            logger.exception('start_services failed: %s', exc)
            raise

async def ensure_system_ready(force_runtime_init: bool = False) -> bool:
    async with _system_ready_lock:
        initialized = await initialize_runtime_from_config(force=force_runtime_init)
        if not initialized:
            bot_runtime.mark_services_stopped()
            bot_runtime.set_runtime_reason('missing_config')
            return False

        current_user = bot_runtime.user_client
        if current_user is None:
            bot_runtime.mark_services_stopped()
            bot_runtime.set_login_status('config_missing')
            bot_runtime.set_runtime_reason('missing_user_client')
            return False

        if not current_user.is_connected():
            await current_user.connect()
            bot_runtime.mark_connect()

        await ensure_bot_authorized()

        if not await current_user.is_user_authorized():
            bot_runtime.mark_services_stopped()
            bot_runtime.set_login_status('waiting_for_phone')
            bot_runtime.set_runtime_reason('user_auth_required')
            return False

        await start_services()

        if bot_runtime.services_started:
            bot_runtime.set_login_status('logged_in')
            bot_runtime.set_runtime_reason('')
            return True

        bot_runtime.set_runtime_reason('service_not_started')
        return False


async def bootstrap_clients():
    try:
        await ensure_system_ready()
    except Exception as exc:
        logger.error(f'启动 Telegram 客户端失败: {str(exc)}')
        bot_runtime.mark_services_stopped()
        bot_runtime.set_login_status('waiting_for_phone')
        bot_runtime.set_runtime_reason(f'bootstrap_failed:{exc}')


async def shutdown_services():
    global scheduler, chat_updater

    if db_ops and hasattr(db_ops, 'close'):
        await db_ops.close()
    if scheduler:
        scheduler.stop()
        scheduler = None
    if chat_updater:
        chat_updater.stop()
        chat_updater = None

    current_user = bot_runtime.user_client
    current_bot = bot_runtime.bot_client

    if current_user is not None and current_user.is_connected():
        await current_user.disconnect()
    if current_bot is not None and current_bot.is_connected():
        await current_bot.disconnect()
    bot_runtime.mark_services_stopped()


async def run_app():
    bot_runtime.bind_clients(None, None, asyncio.get_running_loop())
    bot_runtime.set_login_handler(start_services)
    bot_runtime.set_runtime_initializer(initialize_runtime_from_config)
    bot_runtime.set_service_stopper(shutdown_services)

    rss_host = os.getenv('RSS_HOST', '0.0.0.0')
    rss_port = int(os.getenv('RSS_PORT', '8000'))
    config = uvicorn.Config(rss_app, host=rss_host, port=rss_port)
    server = uvicorn.Server(config)

    bootstrap_task = asyncio.create_task(bootstrap_clients())
    try:
        await server.serve()
    finally:
        if bootstrap_task and not bootstrap_task.done():
            bootstrap_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bootstrap_task
        await shutdown_services()

async def register_bot_commands(bot):
    """注册机器人命令"""
    # # 先清空现有命令
    # try:
    #     await bot(SetBotCommandsRequest(
    #         scope=types.BotCommandScopeDefault(),
    #         lang_code='',
    #         commands=[]  # 空列表清空所有命令
    #     ))
    #     logger.info('已清空现有机器人命令')
    # except Exception as e:
    #     logger.error(f'清空机器人命令时出错: {str(e)}')

    commands = [
        # 基础命令
        BotCommand(
            command='start',
            description='开始使用'
        ),
        BotCommand(
            command='help',
            description='查看帮助'
        ),
        # 绑定和设置
        BotCommand(
            command='bind',
            description='绑定源聊天'
        ),
        BotCommand(
            command='settings',
            description='管理转发规则'
        ),
        BotCommand(
            command='switch',
            description='切换当前需要设置的聊天规则'
        ),
        BotCommand(
            command='backfill',
            description='回填历史消息'
        ),
        BotCommand(
            command='backfill_stop',
            description='停止历史回填'
        ),
        BotCommand(
            command='resolve',
            description='解决无法找到实体的问题'
        ),
        # 关键字管理
        BotCommand(
            command='add',
            description='添加关键字'
        ),
        BotCommand(
            command='add_regex',
            description='添加正则关键字'
        ),
        BotCommand(
            command='add_all',
            description='添加普通关键字到所有规则'
        ),
        BotCommand(
            command='add_regex_all',
            description='添加正则表达式到所有规则'
        ),
        BotCommand(
            command='list_keyword',
            description='列出所有关键字'
        ),
        BotCommand(
            command='remove_keyword',
            description='删除关键字'
        ),
        BotCommand(
            command='remove_keyword_by_id',
            description='按ID删除关键字'
        ),
        BotCommand(
            command='remove_all_keyword',
            description='删除当前频道绑定的所有规则的指定关键字'
        ),
        # 替换规则管理
        BotCommand(
            command='replace',
            description='添加替换规则'
        ),
        BotCommand(
            command='replace_all',
            description='添加替换规则到所有规则'
        ),
        BotCommand(
            command='list_replace',
            description='列出所有替换规则'
        ),
        BotCommand(
            command='remove_replace',
            description='删除替换规则'
        ),
        # 导入导出功能
        BotCommand(
            command='export_keyword',
            description='导出当前规则的关键字'
        ),
        BotCommand(
            command='export_replace',
            description='导出当前规则的替换规则'
        ),
        BotCommand(
            command='import_keyword',
            description='导入普通关键字'
        ),
        BotCommand(
            command='import_regex_keyword',
            description='导入正则表达式关键字'
        ),
        BotCommand(
            command='import_replace',
            description='导入替换规则'
        ),
        # UFB相关功能
        BotCommand(
            command='ufb_bind',
            description='绑定ufb域名'
        ),
        BotCommand(
            command='ufb_unbind',
            description='解绑ufb域名'
        ),
        BotCommand(
            command='ufb_item_change',
            description='切换ufb同步配置类型'
        ),
        BotCommand(
            command='clear_all_keywords',
            description='清除当前规则的所有关键字'
        ),
        BotCommand(
            command='clear_all_keywords_regex',
            description='清除当前规则的所有正则关键字'
        ),
        BotCommand(
            command='clear_all_replace',
            description='清除当前规则的所有替换规则'
        ),
        BotCommand(
            command='copy_keywords',
            description='复制参数规则的关键字到当前规则'
        ),
        BotCommand(
            command='copy_keywords_regex',
            description='复制参数规则的正则关键字到当前规则'
        ),
        BotCommand(
            command='copy_replace',
            description='复制参数规则的替换规则到当前规则'
        ),
        BotCommand(
            command='copy_rule',
            description='复制参数规则到当前规则'
        ),
        BotCommand(
            command='changelog',
            description='查看更新日志'
        ),
        BotCommand(
            command='list_rule',
            description='列出所有转发规则'
        ),
        BotCommand(
            command='delete_rule',
            description='删除转发规则'
        ),
        BotCommand(
            command='delete_rss_user',
            description='删除RSS用户'
        ),


        # BotCommand(
        #     command='clear_all',
        #     description='慎用！清空所有数据'
        # ),
    ]

    try:
        result = await bot(SetBotCommandsRequest(
            scope=types.BotCommandScopeDefault(),
            lang_code='',  # 空字符串表示默认语言
            commands=commands
        ))
        if result:
            logger.info('已成功注册机器人命令')
        else:
            logger.error('注册机器人命令失败')
    except Exception as e:
        logger.error(f'注册机器人命令时出错: {str(e)}')


if __name__ == '__main__':
    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        print("正在关闭客户端...")
