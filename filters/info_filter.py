import logging
import os
import pytz
import re
from datetime import datetime
from filters.base_filter import BaseFilter

logger = logging.getLogger(__name__)

class InfoFilter(BaseFilter):
    """
    信息过滤器，添加原始链接和发送者信息
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

        # logger.info(f"InfoFilter处理消息前，context: {context.__dict__}")
        try:

            # 添加原始链接
            if rule.is_original_link:
                # 获取原始链接的基本信息
                original_link = f"https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
                
                # 检查是否有原始链接模板
                if hasattr(rule, 'original_link_template') and rule.original_link_template:
                    try:
                        # 使用自定义链接模板
                        link_info = rule.original_link_template
                        link_info = link_info.replace("{original_link}", original_link)
                        
                        context.original_link = f"\n\n{link_info}"
                    except Exception as le:
                        logger.error(f'使用自定义链接模板出错: {str(le)}，使用默认格式')
                        context.original_link = f"\n\n原始消息: {original_link}"
                else:
                    # 使用默认格式
                    context.original_link = f"\n\n原始消息: {original_link}"
                
                logger.info(f'添加原始链接: {context.original_link}')
            
            # 添加发送者信息
            if rule.is_original_sender:
                try:
                    logger.info("开始获取发送者信息")
                    sender_name = "Unknown Sender"  # 默认值
                    sender_id = "Unknown"

                    if hasattr(event.message, 'sender_chat') and event.message.sender_chat:
                        # 用户以频道身份发送消息
                        sender = event.message.sender_chat
                        sender_name = sender.title if hasattr(sender, 'title') else "Unknown Channel"
                        sender_id = sender.id
                        logger.info(f"使用频道信息: {sender_name} (ID: {sender_id})")

                    elif event.sender:
                        # 用户以个人身份发送消息
                        sender = event.sender
                        sender_name = (
                            sender.title if hasattr(sender, 'title')
                            else f"{sender.first_name or ''} {sender.last_name or ''}".strip()
                        )
                        sender_id = sender.id
                        logger.info(f"使用发送者信息: {sender_name} (ID: {sender_id})")

                    elif hasattr(event.message, 'peer_id') and event.message.peer_id:
                        # 尝试从 peer_id 获取信息
                        peer = event.message.peer_id
                        if hasattr(peer, 'channel_id'):
                            sender_id = peer.channel_id
                            try:
                                # 尝试获取频道信息
                                channel = await event.client.get_entity(peer)
                                sender_name = channel.title if hasattr(channel, 'title') else "Unknown Channel"
                            except Exception as ce:
                                logger.error(f'获取频道信息失败: {str(ce)}')
                                sender_name = "Unknown Channel"
                        logger.info(f"使用peer_id信息: {sender_name} (ID: {sender_id})")
                    
                    # 检查是否有用户自定义模板
                    if hasattr(rule, 'userinfo_template') and rule.userinfo_template:
                        # 替换模板中的变量
                        user_info = rule.userinfo_template
                        user_info = user_info.replace("{name}", sender_name)
                        user_info = user_info.replace("{id}", str(sender_id))
                        
                        context.sender_info = f"{user_info}\n\n"
                    else:
                        # 使用默认格式
                        context.sender_info = f"{sender_name}\n\n"
                    
                    logger.info(f'添加发送者信息: {context.sender_info}')
                except Exception as e:
                    logger.error(f'获取发送者信息出错: {str(e)}')
            
            # 添加时间信息
            if rule.is_original_time:
                try:
                    # 创建时区对象
                    timezone = pytz.timezone(os.getenv('DEFAULT_TIMEZONE', 'Asia/Shanghai'))
                    local_time = event.message.date.astimezone(timezone)
                    
                    # 默认格式化的时间
                    formatted_time = local_time.strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 检查是否有时间模板
                    if hasattr(rule, 'time_template') and rule.time_template:
                        try:
                            # 使用自定义时间模板
                            time_info = rule.time_template.replace("{time}", formatted_time)
                            context.time_info = f"\n\n{time_info}"
                        except Exception as te:
                            logger.error(f'使用自定义时间模板出错: {str(te)}，使用默认格式')
                            context.time_info = f"\n\n{formatted_time}"
                    else:
                        # 使用默认格式
                        context.time_info = f"\n\n{formatted_time}"
                    
                    logger.info(f'添加时间信息: {context.time_info}')
                except Exception as e:
                    logger.error(f'处理时间信息时出错: {str(e)}')
            
            return True 
        finally:
            # logger.info(f"InfoFilter处理消息后，context: {context.__dict__}")
            pass