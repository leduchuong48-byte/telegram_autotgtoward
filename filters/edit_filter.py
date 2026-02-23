import logging
import os
from filters.base_filter import BaseFilter
from enums.enums import HandleMode, PreviewMode
from utils.common import get_main_module
from telethon.tl.types import Channel
import traceback

logger = logging.getLogger(__name__)

class EditFilter(BaseFilter):
    """
    编辑过滤器，用于在编辑模式下修改原始消息
    仅在频道消息中生效
    """
    
    async def _process(self, context):
        """
        处理消息编辑
        
        Args:
            context: 消息上下文
            
        Returns:
            bool: 是否继续处理
        """
        rule = context.rule
        event = context.event

        

        logger.debug(f"开始处理编辑过滤器，消息ID: {event.message.id}, 聊天ID: {event.chat_id}")
        
        # 如果不是编辑模式，继续后续处理
        if rule.handle_mode != HandleMode.EDIT:
            logger.debug(f"当前规则非编辑模式 (当前模式: {rule.handle_mode})，跳过编辑处理")
            return True
            
        # 检查是否为频道消息
        chat = await event.get_chat()
        logger.debug(f"聊天类型: {type(chat).__name__}, 聊天ID: {chat.id}, 聊天标题: {getattr(chat, 'title', '未知')}")
        
        if not isinstance(chat, Channel):
            logger.info(f"不是频道消息 (聊天类型: {type(chat).__name__})，跳过编辑")
            return False
            
        try:
            # 获取用户客户端
            logger.debug("尝试获取用户客户端")
            main = await get_main_module()
            user_client = main.user_client if (main and hasattr(main, 'user_client')) else None
            
            if not user_client:
                logger.error("无法获取用户客户端，无法执行编辑操作")
                return False
            
            logger.debug("成功获取用户客户端")
                
            # 根据预览模式设置 link_preview
            link_preview = {
                PreviewMode.ON: True,
                PreviewMode.OFF: False,
                PreviewMode.FOLLOW: event.message.media is not None  # 跟随原消息
            }[rule.is_preview]
            
            logger.debug(f"预览模式: {rule.is_preview}, link_preview值: {link_preview}")
            
            # 组合消息文本
            message_text = context.sender_info + context.message_text + context.time_info + context.original_link
            
            logger.debug(f"原始消息文本: '{event.message.text}'")
            logger.debug(f"新消息文本: '{message_text}'")
            
            # 检查文本是否有变化
            if message_text == event.message.text:
                logger.info("消息文本没有变化，跳过编辑")
                return False
            
            # 处理媒体组消息
            if context.is_media_group:
                logger.info(f"处理媒体组消息，媒体组ID: {context.media_group_id}, 消息数量: {len(context.media_group_messages) if context.media_group_messages else '未知'}")
                # 尝试编辑媒体组中的每条消息
                if not context.media_group_messages:
                    logger.warning("媒体组消息列表为空，无法编辑")
                    return False
                    
                for message in context.media_group_messages:
                    try:
                        # 只在第一条消息上添加文本
                        text_to_edit = message_text if message.id == event.message.id else ""
                        logger.debug(f"尝试编辑媒体组消息 {message.id}, 媒体类型: {type(message.media).__name__ if message.media else '无媒体'}")
                        
                        await user_client.edit_message(
                            event.chat_id,
                            message.id,
                            text=text_to_edit,
                            parse_mode=rule.message_mode.value,
                            link_preview=link_preview
                        )
                        logger.info(f"成功编辑媒体组消息 {message.id}")
                    except Exception as e:
                        error_details = str(e)
                        if "was not modified" not in error_details:
                            logger.error(f"编辑媒体组消息 {message.id} 失败: {error_details}")
                            logger.debug(f"异常详情: {traceback.format_exc()}")
                        else:
                            logger.debug(f"媒体组消息 {message.id} 内容未修改，无需编辑")
                return False
            # 处理所有其他消息（包括单条媒体消息和纯文本消息）
            else:
                try:
                    logger.debug(f"尝试编辑单条消息 {event.message.id}, 消息类型: {type(event.message).__name__}, 媒体类型: {type(event.message.media).__name__ if event.message.media else '无媒体'}")
                    logger.debug(f"使用解析模式: {rule.message_mode.value}")
                    
                    await user_client.edit_message(
                        event.chat_id,
                        event.message.id,
                        text=message_text,
                        parse_mode=rule.message_mode.value,
                        link_preview=link_preview
                    )
                    logger.info(f"成功编辑消息 {event.message.id}")
                    return False
                except Exception as e:
                    error_details = str(e)
                    if "was not modified" not in error_details:
                        logger.error(f"编辑消息 {event.message.id} 失败: {error_details}")
                        logger.debug(f"尝试编辑的消息ID: {event.message.id}, 聊天ID: {event.chat_id}")
                        logger.debug(f"消息文本长度: {len(message_text)}, 解析模式: {rule.message_mode.value}")
                        logger.debug(f"异常详情: {traceback.format_exc()}")
                    else:
                        logger.debug(f"消息 {event.message.id} 内容未修改，无需编辑")
                    return False
                
        except Exception as e:
            logger.error(f"编辑过滤器处理出错: {str(e)}")
            logger.debug(f"异常详情: {traceback.format_exc()}")
            logger.debug(f"上下文信息 - 消息ID: {event.message.id}, 聊天ID: {event.chat_id}, 规则ID: {rule.id if hasattr(rule, 'id') else '未知'}")
            return False 