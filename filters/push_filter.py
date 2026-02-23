import logging
import os
import pytz
import asyncio
import apprise
from datetime import datetime
import traceback

from filters.base_filter import BaseFilter
from models.models import get_session, PushConfig
from enums.enums import PreviewMode

logger = logging.getLogger(__name__)

class PushFilter(BaseFilter):
    """
    推送过滤器，利用apprise库推送消息
    """
    
    async def _process(self, context):
        """
        推送消息
        
        Args:
            context: 消息上下文
            
        Returns:
            bool: 若消息应继续处理则返回True，否则返回False
        """
        rule = context.rule
        client = context.client
        event = context.event
        
        # 如果规则没有启用推送，直接返回
        if not rule.enable_push:
            logger.info('推送未启用，跳过推送')
            return True
        
        # 获取规则ID和所有启用的推送配置
        rule_id = rule.id
        session = get_session()
        
 
        logger.info(f"推送过滤器开始处理 - 规则ID: {rule_id}")
        logger.info(f"是否是媒体组: {context.is_media_group}")
        logger.info(f"媒体组消息数量: {len(context.media_group_messages) if context.media_group_messages else 0}")
        logger.info(f"已有媒体文件数量: {len(context.media_files) if context.media_files else 0}")
        logger.info(f"是否只推送不转发: {rule.enable_only_push}")
        
        # 跟踪已处理的文件
        processed_files = []
        
        try:
            # 获取所有启用的推送配置
            push_configs = session.query(PushConfig).filter(
                PushConfig.rule_id == rule_id,
                PushConfig.enable_push_channel == True
            ).all()
            
            if not push_configs:
                logger.info(f'规则 {rule_id} 没有启用的推送配置，跳过推送')
                return True
            
            # 对媒体组消息进行推送
            if context.is_media_group or (context.media_group_messages and context.skipped_media):
                processed_files = await self._push_media_group(context, push_configs)
            # 对单条媒体消息进行推送
            elif context.media_files or context.skipped_media:
                processed_files = await self._push_single_media(context, push_configs)
            # 对纯文本消息进行推送
            else:
                processed_files = await self._push_text_message(context, push_configs)
            
            logger.info(f'推送已发送到 {len(push_configs)} 个配置')
            return True
            
        except Exception as e:
            logger.error(f'推送过滤器处理出错: {str(e)}')
            logger.error(traceback.format_exc())
            context.errors.append(f"推送错误: {str(e)}")
            return False
        finally:
            session.close()
            
            # 只清理已处理的媒体文件
            if processed_files:
                logger.info(f'清理已处理的媒体文件，共 {len(processed_files)} 个')
                for file_path in processed_files:
                    try:
                        if os.path.exists(str(file_path)):
                            os.remove(file_path)
                            logger.info(f'删除已处理的媒体文件: {file_path}')
                    except Exception as e:
                        logger.error(f'删除媒体文件失败: {str(e)}')
    
    async def _push_media_group(self, context, push_configs):
        """推送媒体组消息"""
        rule = context.rule
        client = context.client
        event = context.event
        
        # 初始化文件列表
        files = []
        need_cleanup = False
        
        try:
            # 如果没有媒体组消息（都超限了），发送文本和提示
            if not context.media_group_messages and context.skipped_media:
                logger.info(f'所有媒体都超限，发送文本和提示')
                # 构建提示信息
                text_to_send = context.message_text or ''
                
                # 设置原始消息链接
                if rule.is_original_link:
                    context.original_link = f"\n原始消息: https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
                
                # 添加每个超限文件的信息
                for message, size, name in context.skipped_media:
                    text_to_send += f"\n\n⚠️ 媒体文件 {name if name else '未命名文件'} ({size}MB) 超过大小限制"
                
                # 组合完整文本
                if rule.is_original_sender:
                    text_to_send = context.sender_info + text_to_send
                if rule.is_original_time:
                    text_to_send += context.time_info
                if rule.is_original_link:
                    text_to_send += context.original_link
                
                # 发送文本推送
                await self._send_push_notification(push_configs, text_to_send)
                return
            
            # 检查是否有媒体组消息但没有媒体文件（这是关键修复）
            if context.media_group_messages and not context.media_files:
                logger.info(f'检测到媒体组消息但没有媒体文件，开始下载...')
                need_cleanup = True
                for message in context.media_group_messages:
                    if message.media:
                        file_path = await message.download_media(os.path.join(os.getcwd(), 'temp'))
                        if file_path:
                            files.append(file_path)
                            logger.info(f'已下载媒体组文件: {file_path}')
            # 如果SenderFilter已经下载了文件，使用它们
            elif context.media_files:
                logger.info(f'使用SenderFilter已下载的文件: {len(context.media_files)}个')
                files = context.media_files
            # 否则，需要自己下载文件
            elif rule.enable_only_push:
                logger.info(f'需要自己下载文件，开始下载媒体组消息...')
                need_cleanup = True
                for message in context.media_group_messages:
                    if message.media:
                        file_path = await message.download_media(os.path.join(os.getcwd(), 'temp'))
                        if file_path:
                            files.append(file_path)
                            logger.info(f'已下载媒体文件: {file_path}')
            
            # 如果有可用的媒体文件，构建推送内容
            if files:
                # 添加发送者信息和消息文本
                caption_text = ""
                if rule.is_original_sender and context.sender_info:
                    caption_text += context.sender_info
                caption_text += context.message_text or ""
                
                # 如果有超限文件，添加提示信息
                for message, size, name in context.skipped_media:
                    caption_text += f"\n\n⚠️ 媒体文件 {name if name else '未命名文件'} ({size}MB) 超过大小限制"
                
                # 添加原始链接
                if rule.is_original_link and context.skipped_media:
                    original_link = f"\n原始消息: https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
                    caption_text += original_link
                
                # 添加时间信息
                if rule.is_original_time and context.time_info:
                    caption_text += context.time_info
                
                # 设置默认描述（如果没有文本内容）
                default_caption = f"收到一组媒体文件 (共{len(files)}个)"
                
                # 按配置的媒体发送方式分别处理每个推送配置
                processed_files = []
                
                for config in push_configs:
                    # 获取该配置的媒体发送模式
                    send_mode = config.media_send_mode  # "Single" 或 "Multiple"
                    
                    # 检查所有文件是否存在
                    valid_files = [f for f in files if os.path.exists(str(f))]
                    if not valid_files:
                        continue
                    
                    # 根据媒体发送模式来决定发送方式
                    if send_mode == "Multiple":
                        try:
                            logger.info(f'尝试一次性发送 {len(valid_files)} 个文件到 {config.push_channel}，模式: {send_mode}')
                            await self._send_push_notification(
                                [config], 
                                caption_text or f"收到一组媒体文件 (共{len(valid_files)}个)", 
                                None,  # 不使用单附件参数
                                valid_files  # 使用多附件参数
                            )
                            processed_files.extend(valid_files)
                        except Exception as e:
                            logger.error(f'尝试一次性发送多个文件失败，错误: {str(e)}')
                            # 如果一次性发送失败，则尝试逐个发送
                            for i, file_path in enumerate(valid_files):
                                # 第一个文件使用完整文本，后续文件使用简短描述
                                file_caption = caption_text if i == 0 else f"媒体组的第 {i+1} 个文件"
                                await self._send_push_notification([config], file_caption, file_path)
                                processed_files.append(file_path)
                    # 逐个发送文件
                    else:
                        for i, file_path in enumerate(valid_files):
                            # 第一个文件使用完整文本，后续文件使用简短描述
                            if i == 0:
                                file_caption = caption_text or f"收到一组媒体文件 (共{len(valid_files)}个)"
                            else:
                                file_caption = f"媒体组的第 {i+1} 个文件" if len(valid_files) > 1 else ""
                            
                            await self._send_push_notification([config], file_caption, file_path)
                            processed_files.append(file_path)
                
        except Exception as e:
            logger.error(f'推送媒体组消息时出错: {str(e)}')
            logger.error(traceback.format_exc())
            raise
        finally:
            # 如果是自己下载的文件，立即清理
            if need_cleanup:
                for file_path in files:
                    try:
                        if os.path.exists(str(file_path)):
                            os.remove(file_path)
                            logger.info(f'删除临时文件: {file_path}')
                            # 移除已删除的文件，避免重复删除
                            if file_path in processed_files:
                                processed_files.remove(file_path)
                    except Exception as e:
                        logger.error(f'删除临时文件失败: {str(e)}')
            
            # 返回处理过但未删除的文件
            return processed_files
    
    async def _push_single_media(self, context, push_configs):
        """推送单条媒体消息"""
        rule = context.rule
        client = context.client
        event = context.event
        
        logger.info(f'推送单条媒体消息')
        
        # 初始化处理文件列表
        processed_files = []
        
        # 检查是否所有媒体都超限
        if context.skipped_media and not context.media_files:
            # 构建提示信息
            file_size = context.skipped_media[0][1]
            file_name = context.skipped_media[0][2]
            
            text_to_send = context.message_text or ''
            text_to_send += f"\n\n⚠️ 媒体文件 {file_name} ({file_size}MB) 超过大小限制"
            
            # 添加发送者信息
            if rule.is_original_sender:
                text_to_send = context.sender_info + text_to_send
            
            # 添加时间信息
            if rule.is_original_time:
                text_to_send += context.time_info
            
            # 添加原始链接
            if rule.is_original_link:
                original_link = f"\n原始消息: https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
                text_to_send += original_link
            
            # 发送文本推送
            await self._send_push_notification(push_configs, text_to_send)
            return processed_files
        
        # 处理媒体文件
        files = []
        need_cleanup = False
        
        try:
            # 如果SenderFilter已经下载了文件，使用它们
            if context.media_files:
                logger.info(f'使用SenderFilter已下载的文件: {len(context.media_files)}个')
                files = context.media_files
            # 否则，需要自己下载文件
            elif rule.enable_only_push and event.message and event.message.media:
                logger.info(f'需要自己下载文件，开始下载单个媒体消息...')
                need_cleanup = True
                file_path = await event.message.download_media(os.path.join(os.getcwd(), 'temp'))
                if file_path:
                    files.append(file_path)
                    logger.info(f'已下载媒体文件: {file_path}')
            
            # 发送媒体文件
            for file_path in files:
                try:
                    # 构建推送内容
                    caption = ""
                    if rule.is_original_sender and context.sender_info:
                        caption += context.sender_info
                    caption += context.message_text or ""
                    
                    # 添加时间信息
                    if rule.is_original_time and context.time_info:
                        caption += context.time_info
                    
                    # 添加原始链接
                    if rule.is_original_link and context.original_link:
                        caption += context.original_link
                    
                    # 如果没有文本内容，添加默认描述
                    if not caption:
                        # 根据文件类型设置描述
                        caption = " "
                        # ext = os.path.splitext(str(file_path))[1].lower()
                        # if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                        #     caption = "收到一张图片"
                        # elif ext in ['.mp4', '.avi', '.mkv', '.mov', '.webm']:
                        #     caption = "收到一个视频"
                        # elif ext in ['.mp3', '.wav', '.ogg', '.flac']:
                        #     caption = "收到一个音频文件"
                        # else:
                        #     caption = f"收到一个文件 ({ext})"
                    
                    # 发送推送
                    await self._send_push_notification(push_configs, caption, file_path)
                    # 添加到已处理文件列表
                    processed_files.append(file_path)
                    
                except Exception as e:
                    logger.error(f'推送单个媒体文件时出错: {str(e)}')
                    logger.error(traceback.format_exc())
                    raise
                
        except Exception as e:
            logger.error(f'推送单条媒体消息时出错: {str(e)}')
            logger.error(traceback.format_exc())
            raise
        finally:
            # 如果是自己下载的文件，需要清理
            if need_cleanup:
                for file_path in files:
                    try:
                        if os.path.exists(str(file_path)):
                            os.remove(file_path)
                            logger.info(f'删除临时文件: {file_path}')
                            # 从已处理列表中移除
                            if file_path in processed_files:
                                processed_files.remove(file_path)
                    except Exception as e:
                        logger.error(f'删除临时文件失败: {str(e)}')
    
            # 返回处理过但未删除的文件
            return processed_files
    
    async def _push_text_message(self, context, push_configs):
        """推送纯文本消息"""
        rule = context.rule
        
        if not context.message_text:
            logger.info('没有文本内容，不发送推送')
            return []
        
        # 组合消息文本
        message_text = ""
        if rule.is_original_sender and context.sender_info:
            message_text += context.sender_info
        message_text += context.message_text
        if rule.is_original_time and context.time_info:
            message_text += context.time_info
        if rule.is_original_link and context.original_link:
            message_text += context.original_link
        
        # 发送推送
        await self._send_push_notification(push_configs, message_text)
        logger.info(f'文本消息推送已发送')
        
        # 返回空列表，表示没有处理任何文件
        return []
    
    async def _send_push_notification(self, push_configs, body, attachment=None, all_attachments=None):
        """发送推送通知"""
        if not body and not attachment and not all_attachments:
            logger.warning('没有内容可推送')
            return
        
        for config in push_configs:
            try:
                # 创建Apprise对象
                apobj = apprise.Apprise()
                
                # 添加推送服务
                service_url = config.push_channel
                if apobj.add(service_url):
                    logger.info(f'成功添加推送服务: {service_url}')
                else:
                    logger.error(f'添加推送服务失败: {service_url}')
                    continue
                
                # 发送推送
                if all_attachments and len(all_attachments) > 0 and config.media_send_mode == "Multiple":
                    # 尝试一次性发送所有附件
                    logger.info(f'发送带{len(all_attachments)}个附件的推送，模式: {config.media_send_mode}')
                    send_result = await asyncio.to_thread(
                        apobj.notify,
                        body=body or f"收到{len(all_attachments)}个媒体文件",
                        attach=all_attachments
                    )
                elif attachment and os.path.exists(str(attachment)):
                    # 单附件推送
                    logger.info(f'发送带单个附件的推送: {os.path.basename(str(attachment))}')
                    send_result = await asyncio.to_thread(
                        apobj.notify,
                        body=body or " ",
                        attach=attachment
                    )
                else:
                    # 纯文本推送
                    logger.info('发送纯文本推送')
                    send_result = await asyncio.to_thread(
                        apobj.notify,
                        body=body
                    )
                
                if send_result:
                    logger.info(f'推送发送成功: {service_url}')
                else:
                    logger.error(f'推送发送失败: {service_url}')
                
            except Exception as e:
                logger.error(f'发送推送时出错: {str(e)}')
                logger.error(traceback.format_exc())