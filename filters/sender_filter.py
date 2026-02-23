import asyncio
import logging
import os
import time
from filters.base_filter import BaseFilter
from enums.enums import PreviewMode
from telethon.errors import FloodWaitError
from telethon.errors.rpcerrorlist import ChannelPrivateError, ChatWriteForbiddenError, UserNotParticipantError
from utils.throttle import get_realtime_throttle

logger = logging.getLogger(__name__)

class SenderFilter(BaseFilter):
    """
    消息发送过滤器，用于发送处理后的消息
    """

    _refresh_lock = asyncio.Lock()
    _last_refresh_time = 0.0
    _refresh_cooldown = 60

    def _build_target_id_candidates(self, raw_id):
        candidates = []
        try:
            base_id = int(raw_id)
        except (TypeError, ValueError):
            return candidates

        def add(value):
            if value not in candidates:
                candidates.append(value)

        add(base_id)

        raw_str = str(base_id)
        if base_id > 0 and raw_str.startswith("100"):
            add(int(f"-{raw_str}"))
        if base_id > 0:
            add(-base_id)
            add(int(f"-100{base_id}"))
        if base_id < 0 and not raw_str.startswith("-100"):
            add(int(f"-100{abs(base_id)}"))

        return candidates

    def _build_target_hint_candidates(self, target_chat_name, target_chat_username=None):
        hints = []

        def add(value):
            if value and value not in hints:
                hints.append(value)

        add(target_chat_username)

        if not target_chat_name:
            return hints

        raw = str(target_chat_name).strip()
        if raw.startswith("@"):
            add(raw)

        if "t.me/" in raw:
            add(raw)
            if raw.startswith("t.me/"):
                add(f"https://{raw}")
            tail = raw.split("t.me/", 1)[1]
            tail = tail.split("?", 1)[0].strip("/")
            if tail and not tail.startswith("+") and not tail.startswith("joinchat/"):
                add(f"@{tail}")
        elif raw.startswith("http://") or raw.startswith("https://"):
            add(raw)

        return hints

    async def _refresh_dialog_cache(self, client):
        current_time = time.time()
        if current_time - type(self)._last_refresh_time < type(self)._refresh_cooldown:
            logger.info("对话列表缓存刷新过于频繁，跳过本次刷新")
            return

        async with self._refresh_lock:
            current_time = time.time()
            if current_time - type(self)._last_refresh_time < type(self)._refresh_cooldown:
                logger.info("对话列表缓存刷新过于频繁，跳过本次刷新")
                return
            type(self)._last_refresh_time = current_time
            try:
                await client.get_dialogs()
                logger.info("已刷新对话列表缓存")
            except FloodWaitError as e:
                logger.warning(f"刷新对话列表缓存触发流控，需要等待 {e.seconds} 秒")
                if e.seconds < type(self)._refresh_cooldown:
                    await asyncio.sleep(e.seconds)
                else:
                    raise
            except Exception as e:
                logger.warning(f"刷新对话列表缓存失败: {str(e)}")

    async def _resolve_target_entity(self, client, target_chat_id, target_chat_name, target_chat_username=None):
        candidates = self._build_target_id_candidates(target_chat_id)
        if not candidates:
            raise ValueError(f"无效的目标聊天ID: {target_chat_id}")

        last_error = None
        for attempt in range(2):
            for candidate_id in candidates:
                try:
                    entity = await client.get_entity(candidate_id)
                    if candidate_id != target_chat_id:
                        logger.info(f"使用候选ID获取实体: {target_chat_name} (ID: {candidate_id})")
                    return entity, candidate_id
                except FloodWaitError as e:
                    last_error = e
                    logger.warning(f"获取目标聊天实体触发流控，需要等待 {e.seconds} 秒")
                    if e.seconds < 60:
                        await asyncio.sleep(e.seconds)
                        continue
                    raise
                except Exception as e:
                    last_error = e
            if attempt == 0:
                logger.info("获取目标聊天实体失败，刷新对话列表后重试")
                await self._refresh_dialog_cache(client)

        hint_candidates = self._build_target_hint_candidates(target_chat_name, target_chat_username)
        for hint in hint_candidates:
            try:
                entity = await client.get_entity(hint)
                resolved_id = getattr(entity, "id", target_chat_id)
                logger.info(f"使用备用标识获取实体: {target_chat_name} (标识: {hint})")
                return entity, resolved_id
            except FloodWaitError as e:
                last_error = e
                logger.warning(f"使用备用标识获取实体触发流控，需要等待 {e.seconds} 秒")
                if e.seconds < 60:
                    await asyncio.sleep(e.seconds)
                    continue
                raise
            except Exception as e:
                last_error = e

        raise last_error if last_error else ValueError("无法获取目标聊天实体")

    async def _check_target_access(self, client, entity, target_chat_name, target_chat_id):
        try:
            me = await client.get_me()
            await client.get_permissions(entity, me)
        except UserNotParticipantError:
            logger.warning(f"当前客户端不在目标聊天内，记录并跳过: {target_chat_name} ({target_chat_id})")
            return False
        except (ChannelPrivateError, ChatWriteForbiddenError) as e:
            logger.warning(f"当前客户端无访问权限，记录并跳过: {target_chat_name} ({target_chat_id}) err={str(e)}")
            return False
        except Exception as e:
            logger.warning(f"检查目标聊天权限时出错，记录并跳过: {target_chat_name} ({target_chat_id}) err={str(e)}")
            return False

        return True

    async def _send_with_throttle(self, throttle, send_func):
        if throttle:
            await throttle.wait()
        try:
            result = await send_func()
            if throttle:
                throttle.on_success()
            return result
        except FloodWaitError as e:
            if throttle:
                throttle.on_flood_wait(e.seconds)
            raise
        except Exception:
            if throttle:
                throttle.on_failure()
            raise
    
    async def _process(self, context):
        """
        发送处理后的消息
        
        Args:
            context: 消息上下文
            
        Returns:
            bool: 是否继续处理
        """
        rule = context.rule
        client = context.client
        event = context.event
        
        if not context.should_forward:
            logger.info('消息不满足转发条件，跳过发送')
            return False
        
        if rule.enable_only_push:
            logger.info('只转发到推送配置，跳过发送')
            return True
            
        # 获取目标聊天信息
        target_chat = rule.target_chat
        target_chat_id = int(target_chat.telegram_chat_id)
        target_chat_username = getattr(target_chat, "username", None)
        throttle = get_realtime_throttle("bot")

        try:
            target_entity, resolved_id = await self._resolve_target_entity(
                client, target_chat_id, target_chat.name, target_chat_username
            )
            target_chat_id = resolved_id
        except Exception as e:
            logger.error(f"无法解析目标聊天实体，跳过发送: {target_chat.name} ({target_chat_id}) err={str(e)}")
            context.errors.append(f"无法解析目标聊天实体: {target_chat.name} ({target_chat_id})")
            return False

        if not await self._check_target_access(client, target_entity, target_chat.name, target_chat_id):
            context.errors.append(f"目标聊天不可访问或无权限: {target_chat.name} ({target_chat_id})")
            return False
        
        # 设置消息格式
        parse_mode = rule.message_mode.value  # 使用枚举的值（字符串）
        logger.info(f'使用消息格式: {parse_mode}')

        try:
            if context.forward_via_forward_messages and not getattr(context, "media_blocked", False):
                logger.info("原消息直接转发模式，跳过重新发送")
                await self._forward_original_message(context, target_entity, throttle)
                logger.info(f'消息已转发到: {target_chat.name} ({target_chat_id})')
                return True

            # 处理媒体组消息
            if context.is_media_group or (context.media_group_messages and context.skipped_media):
                logger.info(f'准备发送媒体组消息')
                await self._send_media_group(context, target_entity, parse_mode, throttle)
            # 处理单条媒体消息
            elif context.media_files or context.skipped_media:
                logger.info(f'准备发送单条媒体消息')
                await self._send_single_media(context, target_entity, parse_mode, throttle)
            # 处理纯文本消息
            else:
                logger.info(f'准备发送纯文本消息')
                await self._send_text_message(context, target_entity, parse_mode, throttle)
                
            logger.info(f'消息已发送到: {target_chat.name} ({target_chat_id})')
            return True
        except FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f'发送消息频率限制，需要等待 {wait_time} 秒')
            if wait_time < 60:
                await asyncio.sleep(wait_time)
            context.errors.append(f"发送消息频率限制，需要等待 {wait_time} 秒")
            return False
        except Exception as e:
            logger.error(f'发送消息时出错: {str(e)}')
            context.errors.append(f"发送消息错误: {str(e)}")
            return False

    async def _forward_original_message(self, context, target_chat, throttle):
        """直接转发原消息，避免下载"""
        client = context.client
        event = context.event
        if context.is_media_group:
            if context.media_group_messages:
                message_ids = sorted([message.id for message in context.media_group_messages])
            else:
                message_ids = [event.message.id]
        else:
            message_ids = event.message.id
        await self._send_with_throttle(
            throttle,
            lambda: client.forward_messages(target_chat, message_ids, event.chat_id),
        )
    
    async def _send_media_group(self, context, target_chat, parse_mode, throttle):
        """发送媒体组消息"""
        rule = context.rule
        client = context.client
        event = context.event
        # 初始化转发消息列表
        context.forwarded_messages = []
        
        # if not context.media_group_messages:
        #     logger.info(f'所有媒体都超限，发送文本和提示')
        #     # 构建提示信息
        #     text_to_send = context.message_text or ''

        #     # 设置原始消息链接
        #     context.original_link = f"\n原始消息: https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
            
        #     # 添加每个超限文件的信息
        #     for message, size, name in context.skipped_media:
        #         text_to_send += f"\n\n⚠️ 媒体文件 {name if name else '未命名文件'} ({size}MB) 超过大小限制"
            
        #     # 组合完整文本
        #     text_to_send = context.sender_info + text_to_send + context.time_info + context.original_link
            
        #     await client.send_message(
        #         target_chat_id,
        #         text_to_send,
        #         parse_mode=parse_mode,
        #         link_preview=True,
        #         buttons=context.buttons
        #     )
        #     logger.info(f'媒体组所有文件超限，已发送文本和提示')
        #     return
            
        # 如果有可以发送的媒体，作为一个组发送
        files = []
        try:
            for message in context.media_group_messages:
                if message.media:
                    file_path = await message.download_media(os.path.join(os.getcwd(), 'temp'))
                    if file_path:
                        files.append(file_path)
            
            # 修改：保存下载的文件路径到context.media_files
            if files:
                # 初始化 media_files 如果它不存在
                if not hasattr(context, 'media_files') or context.media_files is None:
                    context.media_files = []
                # 将当前下载的文件添加到列表中
                context.media_files.extend(files)
                logger.info(f'已将 {len(files)} 个下载的媒体文件路径保存到context.media_files')
                
                # 添加发送者信息和消息文本
                caption_text = context.sender_info + context.message_text
                
                # 如果有超限文件，添加提示信息
                for message, size, name in context.skipped_media:
                    caption_text += f"\n\n⚠️ 媒体文件 {name if name else '未命名文件'} ({size}MB) 超过大小限制"
                
                if context.skipped_media:
                    context.original_link = f"\n原始消息: https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
                # 添加时间信息和原始链接
                caption_text += context.time_info + context.original_link
                
                # 作为一个组发送所有文件
                sent_messages = await self._send_with_throttle(
                    throttle,
                    lambda: client.send_file(
                        target_chat,
                        files,
                        caption=caption_text,
                        parse_mode=parse_mode,
                        buttons=context.buttons,
                        link_preview={
                            PreviewMode.ON: True,
                            PreviewMode.OFF: False,
                            PreviewMode.FOLLOW: context.event.message.media is not None
                        }[rule.is_preview],
                    ),
                )
                # 保存发送的消息到上下文
                if isinstance(sent_messages, list):
                    context.forwarded_messages = sent_messages
                else:
                    context.forwarded_messages = [sent_messages]
                
                logger.info(f'媒体组消息已发送，保存了 {len(context.forwarded_messages)} 条已转发消息')
        except Exception as e:
            logger.error(f'发送媒体组消息时出错: {str(e)}')
            raise
        finally:
            # 删除临时文件，但如果启用了推送则保留
            if not rule.enable_push:
                for file_path in files:
                    try:
                        os.remove(file_path)
                        logger.info(f'删除临时文件: {file_path}')
                    except Exception as e:
                        logger.error(f'删除临时文件失败: {str(e)}')
            else:
                logger.info(f'推送功能已启用，保留临时文件')
    
    async def _send_single_media(self, context, target_chat, parse_mode, throttle):
        """发送单条媒体消息"""
        rule = context.rule
        client = context.client
        event = context.event
        
        logger.info(f'发送单条媒体消息')
        
        # 检查是否所有媒体都超限
        if context.skipped_media and not context.media_files:
            # 构建提示信息
            file_size = context.skipped_media[0][1]
            file_name = context.skipped_media[0][2]
            original_link = f"\n原始消息: https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
            
            text_to_send = context.message_text or ''
            text_to_send += f"\n\n⚠️ 媒体文件 {file_name} ({file_size}MB) 超过大小限制"
            text_to_send = context.sender_info + text_to_send + context.time_info
            
            text_to_send += original_link
                
            await self._send_with_throttle(
                throttle,
                lambda: client.send_message(
                    target_chat,
                    text_to_send,
                    parse_mode=parse_mode,
                    link_preview=True,
                    buttons=context.buttons,
                ),
            )
            logger.info(f'媒体文件超过大小限制，仅转发文本')
            return
        
        # 确保context.media_files存在
        if not hasattr(context, 'media_files') or context.media_files is None:
            context.media_files = []
        
        # 发送媒体文件
        for file_path in context.media_files:
            try:
                caption = (
                    context.sender_info + 
                    context.message_text + 
                    context.time_info + 
                    context.original_link
                )
                
                await self._send_with_throttle(
                    throttle,
                    lambda: client.send_file(
                        target_chat,
                        file_path,
                        caption=caption,
                        parse_mode=parse_mode,
                        buttons=context.buttons,
                        link_preview={
                            PreviewMode.ON: True,
                            PreviewMode.OFF: False,
                            PreviewMode.FOLLOW: context.event.message.media is not None
                        }[rule.is_preview],
                    ),
                )
                logger.info(f'媒体消息已发送')
            except Exception as e:
                logger.error(f'发送媒体消息时出错: {str(e)}')
                raise
            finally:
                # 删除临时文件，但如果启用了推送则保留
                if not rule.enable_push:
                    try:
                        os.remove(file_path)
                        logger.info(f'删除临时文件: {file_path}')
                    except Exception as e:
                        logger.error(f'删除临时文件失败: {str(e)}')
                else:
                    logger.info(f'推送功能已启用，保留临时文件: {file_path}')
    
    async def _send_text_message(self, context, target_chat, parse_mode, throttle):
        """发送纯文本消息"""
        rule = context.rule
        client = context.client
        
        if not context.message_text:
            logger.info('没有文本内容，不发送消息')
            return
            
        # 根据预览模式设置 link_preview
        link_preview = {
            PreviewMode.ON: True,
            PreviewMode.OFF: False,
            PreviewMode.FOLLOW: context.event.message.media is not None  # 跟随原消息
        }[rule.is_preview]
        
        # 组合消息文本
        message_text = context.sender_info + context.message_text + context.time_info + context.original_link
        
        await self._send_with_throttle(
            throttle,
            lambda: client.send_message(
                target_chat,
                str(message_text),
                parse_mode=parse_mode,
                link_preview=link_preview,
                buttons=context.buttons,
            ),
        )
        logger.info(f'{"带预览的" if link_preview else "无预览的"}文本消息已发送') 
