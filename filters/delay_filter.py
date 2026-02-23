import asyncio
import logging
from filters.base_filter import BaseFilter
from utils.common import get_main_module

logger = logging.getLogger(__name__)

class DelayFilter(BaseFilter):
    """
    延迟过滤器，等待消息可能的编辑后再处理
    
    有些频道在发送消息后会有自己的机器人对消息进行编辑，
    添加引用、标注等内容。此过滤器会等待一段时间后，
    重新获取消息的最新内容再进行处理。
    """
    
    async def _process(self, context):
        """
        根据规则配置，决定是否等待并获取最新的消息内容
        
        Args:
            context: 消息上下文
        
        Returns:
            bool: 是否继续处理
        """
        rule = context.rule
        message = context.event
        
        # 如果规则未启用延迟处理或延迟秒数为0，则直接通过
        if not rule.enable_delay or rule.delay_seconds <= 0:
            logger.debug(f"[规则ID:{rule.id}] 延迟处理未启用或延迟秒数为0，跳过延迟处理")
            return True
        
        # 如果消息不完整，则直接通过
        if not message or not hasattr(message, "chat_id") or not hasattr(message, "id"):
            logger.debug(f"[规则ID:{rule.id}] 消息不完整，无法应用延迟处理")
            return True
            
        try:

            original_id = message.id
            chat_id = message.chat_id
            
            logger.info(f"[规则ID:{rule.id}] 延迟处理消息 {original_id}，等待 {rule.delay_seconds} 秒...")
            
            # 等待指定的秒数
            await asyncio.sleep(rule.delay_seconds)
            logger.info(f"[规则ID:{rule.id}] 延迟 {rule.delay_seconds} 秒结束，正在获取最新消息...")
            
            # 尝试获取用户客户端
            try:
                main = await get_main_module()
                client = main.user_client if (main and hasattr(main, 'user_client')) else context.client
                
                # 获取更新后的消息
                logger.info(f"[规则ID:{rule.id}] 正在获取聊天 {chat_id} 的消息 {original_id}...")
                updated_message = await client.get_messages(chat_id, ids=original_id)

                
                if updated_message:
                    updated_text = getattr(updated_message, "text", "")
                    
                    # 不管消息内容是否有变化，都更新上下文中的所有相关字段
                    logger.info(f"[规则ID:{rule.id}] 正在更新上下文中的消息数据...")
                    
                    # 更新上下文中的消息文本相关字段
                    context.message_text = updated_text
                    context.check_message_text = updated_text
                    
                    # 更新事件中的消息对象
                    context.event.message = updated_message
                    
                    # 更新其他相关字段
                    context.original_message_text = updated_text
                    context.buttons = updated_message.buttons if hasattr(updated_message, 'buttons') else None
                    
                    # 更新媒体相关信息
                    if hasattr(updated_message, 'media') and updated_message.media:
                        context.is_media_group = updated_message.grouped_id is not None
                        context.media_group_id = updated_message.grouped_id
                    
                    logger.info(f"[规则ID:{rule.id}] 上下文消息数据已更新完成")
                else:
                    logger.warning(f"[规则ID:{rule.id}] 无法获取更新的消息，使用原始消息")
            except Exception as e:
                logger.warning(f"[规则ID:{rule.id}] 获取更新消息时出错: {str(e)}")
                # 继续使用原始消息
            
            logger.info(f"[规则ID:{rule.id}] 延迟处理完成，继续后续过滤器")
            return True
            
        except Exception as e:
            logger.error(f"[规则ID:{rule.id}] 延迟处理消息时出现错误: {str(e)}")
            return True 
