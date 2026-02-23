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

# 从环境变量获取配置
def get_required_env():
    required_keys = ['API_ID', 'API_HASH', 'BOT_TOKEN', 'USER_ID']
    values = {key: (os.getenv(key) or '').strip() for key in required_keys}
    missing = [key for key, value in values.items() if not value]
    if missing:
        logger.error(f"缺少必要环境变量: {', '.join(missing)}")
        raise SystemExit(1)

    try:
        api_id_value = int(values['API_ID'])
    except ValueError:
        logger.error('API_ID 必须为整数')
        raise SystemExit(1)

    phone_number = (os.getenv('PHONE_NUMBER') or '').strip()
    return api_id_value, values['API_HASH'], values['BOT_TOKEN'], phone_number


api_id, api_hash, bot_token, phone_number = get_required_env()

# 创建 DBOperations 实例
db_ops = None

scheduler = None
chat_updater = None


def schedule_forwarding_reload(_: dict | None = None) -> None:
    loop = bot_runtime.runtime_loop
    client = bot_runtime.user_client
    if loop is None or not loop.is_running() or client is None:
        logger.warning("ForwardingService: runtime 未就绪，跳过重载")
        return
    loop.call_soon_threadsafe(asyncio.create_task, forwarding_service.reload_rules(client))


config_manager.register_reload_handler(schedule_forwarding_reload)


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


# 创建客户端
user_client = TelegramClient('./sessions/user', api_id, api_hash)
bot_client = TelegramClient('./sessions/bot', api_id, api_hash)

# 初始化数据库
engine = init_db()


async def refresh_dialog_cache(client, label):
    try:
        await client.get_dialogs()
        logger.info(f"{label}对话列表缓存已刷新")
    except Exception as e:
        logger.warning(f"{label}对话列表缓存刷新失败: {str(e)}")

async def ensure_bot_authorized():
    if not bot_client.is_connected():
        await bot_client.connect()
        bot_runtime.mark_connect()
    if not await bot_client.is_user_authorized():
        await bot_client.sign_in(bot_token=bot_token)


async def start_services():
    global scheduler, chat_updater
    if bot_runtime.services_started:
        return

    await init_db_ops()
    await ensure_bot_authorized()
    await register_all_handlers(bot_client)
    await forwarding_service.reload_rules(user_client)

    # 预解析公开群组/频道实体，预热 Access Hash 缓存
    hardcoded_targets = [
        # "https://t.me/你的公开群组"
    ]
    env_targets = os.getenv("PRE_RESOLVE_TARGETS", "")
    targets = []
    if env_targets:
        targets.extend([item.strip() for item in env_targets.split(";") if item.strip()])
    targets.extend([item for item in hardcoded_targets if item])

    if targets:
        logger.info(f"开始预解析目标实体，共 {len(targets)} 个")
    for target in targets:
        try:
            entity = await bot_client.get_entity(target)
            title = getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(entity)
            logger.info(f"预解析成功: 目标={target} ID={getattr(entity, 'id', None)} 标题={title}")
        except Exception as e:
            logger.warning(f"预解析失败: 目标={target} err={str(e)}")
            if isinstance(target, str) and target.isdigit():
                try:
                    fallback_id = int(f"-100{target}")
                    entity = await bot_client.get_entity(fallback_id)
                    title = getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(entity)
                    logger.info(f"预解析成功(补前缀): 目标={fallback_id} ID={getattr(entity, 'id', None)} 标题={title}")
                except Exception as e2:
                    logger.warning(f"预解析失败(补前缀): 目标={target} err={str(e2)}")

    await refresh_dialog_cache(user_client, "用户客户端")
    await refresh_dialog_cache(bot_client, "机器人客户端")

    # 设置消息监听器
    await setup_listeners(user_client, bot_client, register_bot_handlers=False)

    # 注册命令
    await register_bot_commands(bot_client)

    # 创建并启动调度器
    scheduler = SummaryScheduler(user_client, bot_client)
    await scheduler.start()

    # 创建并启动聊天信息更新器
    chat_updater = ChatUpdater(user_client)
    await chat_updater.start()

    # 发送欢迎消息
    await send_welcome_message(bot_client)

    bot_runtime.mark_services_started()
    bot_runtime.set_login_status("logged_in")


async def bootstrap_clients():
    bot_runtime.set_login_status("waiting_for_phone")
    try:
        await user_client.connect()
        bot_runtime.mark_connect()
        await ensure_bot_authorized()
        if await user_client.is_user_authorized():
            bot_runtime.set_login_status("logged_in")
            await start_services()
        else:
            bot_runtime.set_login_status("waiting_for_phone")
    except Exception as exc:
        logger.error(f"启动 Telegram 客户端失败: {str(exc)}")
        bot_runtime.set_login_status("waiting_for_phone")


async def shutdown_services():
    if db_ops and hasattr(db_ops, 'close'):
        await db_ops.close()
    if scheduler:
        scheduler.stop()
    if chat_updater:
        chat_updater.stop()
    if user_client.is_connected():
        await user_client.disconnect()
    if bot_client.is_connected():
        await bot_client.disconnect()
    bot_runtime.mark_services_stopped()


async def run_app():
    bot_runtime.bind_clients(user_client, bot_client, asyncio.get_running_loop())
    bot_runtime.set_login_handler(start_services)

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
