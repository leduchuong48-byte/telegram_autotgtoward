import logging
import os
import pytz
import asyncio
from utils.constants import TEMP_DIR
from utils.media import get_max_media_size
from enums.enums import HandleMode, PreviewMode

from filters.base_filter import BaseFilter

logger = logging.getLogger(__name__)

class InitFilter(BaseFilter):
    """
    初始化过滤器，为context添加基本信息
    """
    
    async def _process(self, context):
        """
        添加原始链接和发送者信息
        
        Args:
            context: 消息上下文
            
        Returns:
            bool: 是否继续处理
        """
        rule = context.rule
        event = context.event

        # logger.info(f"InitFilter处理消息前，context: {context.__dict__}")
        try:
            context.forward_via_forward_messages = self._should_forward_without_download(rule)
            if context.forward_via_forward_messages:
                logger.info("仅媒体类型过滤，启用原消息直接转发模式")

            #处理媒体组消息
            if event.message.grouped_id:
                # 等待更长时间让所有媒体消息到达
                # await asyncio.sleep(1)
                
                # 收集媒体组的所有消息
                try:
                    async for message in event.client.iter_messages(
                        event.chat_id,
                        limit=20,
                        min_id=event.message.id - 10,
                        max_id=event.message.id + 10
                    ):
                        if message.grouped_id == event.message.grouped_id:
                            if message.text:    
                                # 保存第一条消息的文本和按钮
                                context.message_text = message.text or ''
                                context.original_message_text = message.text or ''
                                context.check_message_text = message.text or ''
                                context.buttons = message.buttons if hasattr(message, 'buttons') else None
                            logger.info(f'获取到媒体组文本并添加到context: {message.text}')
                        
                except Exception as e:
                    logger.error(f'收集媒体组消息时出错: {str(e)}')
                    context.errors.append(f"收集媒体组消息错误: {str(e)}")
           
        finally:
            # logger.info(f"InitFilter处理消息后，context: {context.__dict__}")
            return True

    def _should_forward_without_download(self, rule):
        return (
            rule.use_bot
            and rule.enable_media_type_filter
            and not rule.is_replace
            and not rule.is_ai
            and not rule.enable_comment_button
            and not rule.is_original_link
            and not rule.is_original_sender
            and not rule.is_original_time
            and not rule.enable_extension_filter
            and not rule.enable_media_size_filter
            and not rule.enable_push
            and not rule.enable_only_push
            and not rule.only_rss
            and not rule.media_allow_text
            and rule.handle_mode == HandleMode.FORWARD
            and rule.is_preview == PreviewMode.FOLLOW
        )
