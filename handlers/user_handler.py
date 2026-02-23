from models.models import ForwardMode, MediaTypes, get_session
import re
import logging
import asyncio
from utils.common import check_keywords, get_sender_info
from utils.throttle import get_realtime_throttle
from enums.enums import AddMode
from telethon.errors import FloodWaitError
from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeVideo


logger = logging.getLogger(__name__)

def _get_media_type_filter_mode(rule):
    mode = getattr(rule, "media_type_filter_mode", AddMode.BLACKLIST)
    if isinstance(mode, AddMode):
        return mode
    if isinstance(mode, str):
        try:
            return AddMode(mode)
        except ValueError:
            try:
                return AddMode[mode]
            except KeyError:
                return AddMode.BLACKLIST
    return AddMode.BLACKLIST

def _get_selected_media_types(media_types):
    if not media_types:
        return set()
    fields = ["photo", "document", "video", "audio", "voice", "text"]
    return {field for field in fields if getattr(media_types, field, False)}

def _detect_message_type(message):
    if getattr(message, "photo", None):
        return "photo"
    if getattr(message, "video", None):
        return "video"
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "audio", None):
        return "audio"

    document = getattr(message, "document", None)
    if document and getattr(document, "attributes", None):
        for attr in document.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                return "video"
            if isinstance(attr, DocumentAttributeAudio):
                return "voice" if getattr(attr, "voice", False) else "audio"

    if document:
        return "document"

    return "text"

def _is_message_type_blocked(message_type, filter_mode, selected_types):
    if not message_type:
        logger.info("无法识别消息类型，默认放行")
        return False

    if filter_mode == AddMode.WHITELIST:
        if not selected_types:
            logger.info("消息类型白名单为空，跳过类型过滤")
            return False
        if message_type not in selected_types:
            logger.info(f"消息类型为 {message_type}，不在白名单中")
            return True
        return False

    if message_type in selected_types:
        logger.info(f"消息类型为 {message_type}，已被屏蔽")
        return True

    return False

async def _forward_with_flood_wait(client, target_chat_id, message_ids, source_chat_id, rule_id, throttle=None):
    max_attempts = 2
    last_wait_seconds = None
    for attempt in range(1, max_attempts + 1):
        try:
            if throttle:
                await throttle.wait()
            await client.forward_messages(target_chat_id, message_ids, source_chat_id)
            if throttle:
                throttle.on_success()
            return True, last_wait_seconds
        except FloodWaitError as e:
            wait_seconds = e.seconds
            last_wait_seconds = wait_seconds
            if throttle:
                throttle.on_flood_wait(wait_seconds)
            logger.warning(
                f"规则 {rule_id} 触发限流，需要等待 {wait_seconds} 秒 (尝试 {attempt}/{max_attempts})"
            )
            if attempt >= max_attempts:
                return False, last_wait_seconds
            await asyncio.sleep(wait_seconds + 1)
        except Exception as e:
            if throttle:
                throttle.on_failure()
            logger.error(f"规则 {rule_id} 转发失败: {str(e)}")
            return False, last_wait_seconds
    return False, last_wait_seconds

async def process_forward_rule(client, event, chat_id, rule):
    """处理转发规则（用户模式）"""

    
    if not rule.enable_rule:
        logger.info(f'规则 ID: {rule.id} 已禁用，跳过处理')
        return False
    
    message_text = event.message.text or ''
    check_message_text = message_text
    # 添加日志
    logger.info(f'处理规则 ID: {rule.id}')
    logger.info(f'消息内容: {message_text}')
    logger.info(f'规则模式: {rule.forward_mode.value}')


    if rule.is_filter_user_info:
        sender_info = await get_sender_info(event, rule.id)  # 调用新的函数获取 sender_info
        if sender_info:
            check_message_text = f"{sender_info}:\n{message_text}"
            logger.info(f'附带用户信息后的消息: {message_text}')
        else:
            logger.warning(f"规则 ID: {rule.id} - 无法获取发送者信息")
    
    should_forward = await check_keywords(rule,check_message_text)
    
    logger.info(f'最终决定: {"转发" if should_forward else "不转发"}')
    
    flood_wait_seconds = None
    if should_forward:
        target_chat = rule.target_chat
        target_chat_id = int(target_chat.telegram_chat_id)
        throttle = get_realtime_throttle("user")
        
        try:
            media_types = None
            selected_types = set()
            filter_mode = _get_media_type_filter_mode(rule)
            if rule.enable_media_type_filter:
                session = get_session()
                try:
                    media_types = session.query(MediaTypes).filter_by(rule_id=rule.id).first()
                    selected_types = _get_selected_media_types(media_types)
                finally:
                    session.close()

            if event.message.grouped_id:
                # 等待一段时间以确保收到所有媒体组消息
                await asyncio.sleep(1)
                
                # 收集媒体组的所有消息
                messages = []
                async for message in client.iter_messages(
                    event.chat_id,
                    limit=20,  # 限制搜索范围
                    min_id=event.message.id - 10,
                    max_id=event.message.id + 10
                ):
                    if message.grouped_id == event.message.grouped_id:
                        messages.append(message)
                        logger.info(f'找到媒体组消息: ID={message.id}')
                
                # 按照ID排序，确保转发顺序正确
                messages.sort(key=lambda item: item.id)

                message_ids = [message.id for message in messages]
                if rule.enable_media_type_filter and media_types:
                    allowed_ids = []
                    for message in messages:
                        message_type = _detect_message_type(message)
                        if _is_message_type_blocked(message_type, filter_mode, selected_types):
                            logger.info(f'媒体类型被屏蔽，跳过消息 ID={message.id}')
                            continue
                        allowed_ids.append(message.id)
                    message_ids = allowed_ids

                if not message_ids:
                    logger.info('媒体组消息全部被屏蔽，取消转发')
                    return False
                
                # 一次性转发所有消息
                ok, flood_wait_seconds = await _forward_with_flood_wait(
                    client, target_chat_id, message_ids, event.chat_id, rule.id, throttle
                )
                if not ok:
                    logger.error("媒体组转发失败：触发限流或重试失败")
                    return False
                logger.info(f'[用户] 已转发 {len(message_ids)} 条媒体组消息到: {target_chat.name} ({target_chat_id})')
                
            else:
                if rule.enable_media_type_filter and media_types:
                    message_type = _detect_message_type(event.message)
                    if _is_message_type_blocked(message_type, filter_mode, selected_types):
                        logger.info(f'消息类型被屏蔽，跳过消息 ID={event.message.id}')
                        return False
                # 处理单条消息
                ok, flood_wait_seconds = await _forward_with_flood_wait(
                    client, target_chat_id, event.message.id, event.chat_id, rule.id, throttle
                )
                if not ok:
                    logger.error("消息转发失败：触发限流或重试失败")
                    return False
                logger.info(f'[用户] 消息已转发到: {target_chat.name} ({target_chat_id})')
                
                
            return True, flood_wait_seconds
        except FloodWaitError as e:
            logger.error(f'转发消息频率限制，需要等待 {e.seconds} 秒')
            flood_wait_seconds = e.seconds
            return False, flood_wait_seconds
        except Exception as e:
            logger.error(f'转发消息时出错: {str(e)}')
            logger.exception(e)
            return False, None

    return False, flood_wait_seconds
