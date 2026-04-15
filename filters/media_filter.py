import logging
import os
import asyncio
from utils.media import get_media_size
from utils.constants import TEMP_DIR
from filters.base_filter import BaseFilter
from utils.media import get_max_media_size
from enums.enums import PreviewMode, CompareMode
from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeVideo
from models.models import MediaTypes
from models.models import get_session
from sqlalchemy import text
from utils.common import get_db_ops
from enums.enums import AddMode
logger = logging.getLogger(__name__)

class MediaFilter(BaseFilter):
    """
    媒体过滤器，处理消息中的媒体内容
    """
    
    async def _process(self, context):
        """
        处理媒体内容
        
        Args:
            context: 消息上下文
            
        Returns:
            bool: 是否继续处理
        """
        # 确保临时目录存在
        os.makedirs(TEMP_DIR, exist_ok=True)
        
        rule = context.rule
        event = context.event
        client = context.client


        
        # 如果是媒体组消息
        if event.message.grouped_id:
            await self._process_media_group(context)
        else:
            await self._process_single_media(context)
        
        return True
    
    async def _process_media_group(self, context):
        """处理媒体组消息"""
        event = context.event
        rule = context.rule
        client = context.client
        is_backfill = getattr(event, "is_backfill", False)
        backfill_max_mb = self._get_backfill_max_media_size_mb() if is_backfill else None
        
        logger.info(f'处理媒体组消息 组ID: {event.message.grouped_id}')
        
        # 等待更长时间让所有媒体消息到达
        await asyncio.sleep(1)
        
        # 获取媒体类型设置
        media_types = None
        selected_types = set()
        filter_mode = self._get_media_type_filter_mode(rule)
        if rule.enable_media_type_filter:
            session = get_session()
            try:
                media_types = session.query(MediaTypes).filter_by(rule_id=rule.id).first()
                if media_types:
                    selected_types = self._get_selected_media_types(media_types)
            finally:
                session.close()
        
        # 收集媒体组的所有消息
        total_media_count = 0  # 总媒体数量
        blocked_media_count = 0  # 被屏蔽的媒体数量
        try:
            async for message in event.client.iter_messages(
                event.chat_id,
                limit=20,
                min_id=event.message.id - 10,
                max_id=event.message.id + 10
            ):
                if message.grouped_id == event.message.grouped_id:
                    if message.media:
                        total_media_count += 1
                        # 检查媒体类型
                        if rule.enable_media_type_filter and media_types and message.media:
                            if await self._is_media_type_blocked(message, media_types, filter_mode, selected_types):
                                logger.info(f'媒体类型被屏蔽，跳过消息 ID={message.id}')
                                blocked_media_count += 1
                                continue
                        
                        # 检查媒体扩展名
                        if rule.enable_extension_filter and message.media:
                            if not await self._is_media_extension_allowed(rule, message.media):
                                logger.info(f'媒体扩展名被屏蔽，跳过消息 ID={message.id}')
                                blocked_media_count += 1
                                continue
                    
                        # 检查媒体大小
                    if message.media:
                        file_size = await get_media_size(message.media)
                        file_size = round(file_size/1024/1024, 2)  # 转换为MB
                        logger.info(f'媒体文件大小: {file_size}MB')
                        logger.info(f'规则最大媒体大小: {rule.max_media_size}MB')
                        logger.info(f'是否启用媒体大小过滤: {rule.enable_media_size_filter}')
                        logger.info(f'是否发送媒体大小超限提醒: {rule.is_send_over_media_size_message}')

                        size_limit_mb = rule.max_media_size if rule.enable_media_size_filter else None
                        size_mode = self._get_compare_mode(getattr(rule, "media_size_filter_mode", CompareMode.LESS))
                        max_cap_mb = backfill_max_mb

                        if size_limit_mb and self._is_size_filtered(file_size, size_limit_mb, size_mode):
                            file_name = ''
                            if hasattr(message.media, 'document') and message.media.document:
                                for attr in message.media.document.attributes:
                                    if hasattr(attr, 'file_name'):
                                        file_name = attr.file_name
                                        break
                            logger.info(f'媒体文件 {file_name} 未通过大小筛选 (阈值 {size_limit_mb}MB)')
                            context.skipped_media.append((message, file_size, file_name))
                            continue

                        if max_cap_mb and file_size > max_cap_mb:
                            if not rule.enable_media_size_filter:
                                logger.info(f'回填限制媒体大小: {backfill_max_mb}MB')
                            file_name = ''
                            if hasattr(message.media, 'document') and message.media.document:
                                for attr in message.media.document.attributes:
                                    if hasattr(attr, 'file_name'):
                                        file_name = attr.file_name
                                        break
                            logger.info(f'媒体文件 {file_name} 超过回填大小上限 ({max_cap_mb}MB)')
                            context.skipped_media.append((message, file_size, file_name))
                            continue

                    # 检查媒体时长
                    if rule.enable_media_duration_filter and message.media:
                        duration_seconds = self._get_media_duration_seconds(message)
                        if duration_seconds is not None:
                            duration_minutes = round(duration_seconds / 60, 2)
                            duration_limit = rule.media_duration_minutes
                            duration_mode = self._get_compare_mode(
                                getattr(rule, "media_duration_filter_mode", CompareMode.LESS)
                            )
                            if duration_limit and self._is_duration_filtered(
                                duration_minutes, duration_limit, duration_mode
                            ):
                                logger.info(
                                    f'媒体时长 {duration_minutes} 分钟未通过筛选 (阈值 {duration_limit} 分钟)'
                                )
                                blocked_media_count += 1
                                continue
                    
                    context.media_group_messages.append(message)
                    logger.info(f'找到媒体组消息: ID={message.id}, 类型={type(message.media).__name__ if message.media else "无媒体"}')
        except Exception as e:
            logger.error(f'收集媒体组消息时出错: {str(e)}')
            context.errors.append(f"收集媒体组消息错误: {str(e)}")
        
        logger.info(f'共找到 {len(context.media_group_messages)} 条媒体组消息，{len(context.skipped_media)} 条超限')
        
        # 如果所有媒体都被屏蔽，设置不转发
        if total_media_count > 0 and total_media_count == blocked_media_count:
            logger.info('媒体组中所有媒体都被屏蔽，设置不转发')
            if not getattr(context, 'stop_reason', None):
                context.stop_reason = 'media_type'
                context.stop_reason_detail = 'all media in group blocked by media type filter'
            # 检查是否允许文本通过
            if rule.media_allow_text:
                logger.info('媒体被屏蔽但允许文本通过')
                context.media_blocked = True  # 标记媒体被屏蔽
            else:
                context.should_forward = False
            return True
            
        # 如果所有媒体都超限且不发送超限提醒，则设置不转发
        if len(context.skipped_media) > 0 and len(context.media_group_messages) == 0 and not rule.is_send_over_media_size_message:
            if not getattr(context, 'stop_reason', None):
                context.stop_reason = 'media_size'
                context.stop_reason_detail = 'all media in group over size limit and no over-limit message'
            # 检查是否允许文本通过
            if rule.media_allow_text:
                logger.info('媒体超限但允许文本通过')
                context.media_blocked = True  # 标记媒体被屏蔽
            else:
                context.should_forward = False
                logger.info('所有媒体都超限且不发送超限提醒，设置不转发')
    
    async def _process_single_media(self, context):
        """处理单条媒体消息"""
        event = context.event
        rule = context.rule
        message = event.message
        is_backfill = getattr(event, "is_backfill", False)
        backfill_max_mb = self._get_backfill_max_media_size_mb() if is_backfill else None
        # logger.info(f'context属性: {context.rule.__dict__}')
        # 检查是否有实际媒体（使用 Telethon Message 的便捷属性，避免把 video/audio/voice 误判成 document）
        has_media = any(
            [
                getattr(message, "photo", None),
                getattr(message, "video", None),
                getattr(message, "audio", None),
                getattr(message, "voice", None),
                getattr(message, "document", None),
            ]
        )

        # 检查是否是纯链接预览消息
        is_pure_link_preview = bool(message.media and hasattr(message.media, "webpage") and not has_media)

        # 处理实际媒体
        if has_media:
            # 检查媒体类型是否被屏蔽
            if rule.enable_media_type_filter:
                session = get_session()
                try:
                    media_types = session.query(MediaTypes).filter_by(rule_id=rule.id).first()
                    filter_mode = self._get_media_type_filter_mode(rule)
                    selected_types = self._get_selected_media_types(media_types) if media_types else set()
                    if media_types and await self._is_media_type_blocked(message, media_types, filter_mode, selected_types):
                        logger.info(f'媒体类型被屏蔽，跳过消息 ID={event.message.id}')
                        context.stop_reason = 'media_type'
                        context.stop_reason_detail = 'media type blocked by whitelist/blacklist rule'
                        # 检查是否允许文本通过
                        if rule.media_allow_text:
                            logger.info('媒体被屏蔽但允许文本通过')
                            context.media_blocked = True  # 标记媒体被屏蔽
                        else:
                            context.should_forward = False
                        return True
                finally:
                    session.close()
            
            # 检查媒体扩展名
            if rule.enable_extension_filter and event.message.media:
                if not await self._is_media_extension_allowed(rule, event.message.media):
                    logger.info(f'媒体扩展名被屏蔽，跳过消息 ID={event.message.id}')
                    context.stop_reason = 'extension'
                    context.stop_reason_detail = 'media extension blocked'
                    # 检查是否允许文本通过
                    if rule.media_allow_text:
                        logger.info('媒体被屏蔽但允许文本通过')
                        context.media_blocked = True  # 标记媒体被屏蔽
                    else:
                        context.should_forward = False
                    return True
            
            # 检查媒体大小
            file_size = await get_media_size(event.message.media)
            file_size = round(file_size/1024/1024, 2)
            logger.info(f'event.message.document: {event.message.document}')
            
            logger.info(f'媒体文件大小: {file_size}MB')
            logger.info(f'规则最大媒体大小: {rule.max_media_size}MB')
            
            logger.info(f'是否启用媒体大小过滤: {rule.enable_media_size_filter}')

            size_limit_mb = rule.max_media_size if rule.enable_media_size_filter else None
            size_mode = self._get_compare_mode(getattr(rule, "media_size_filter_mode", CompareMode.LESS))
            max_cap_mb = backfill_max_mb

            if size_limit_mb and self._is_size_filtered(file_size, size_limit_mb, size_mode):
                file_name = ''
                if event.message.document:
                    # 正确地从文档属性中获取文件名
                    for attr in event.message.document.attributes:
                        if hasattr(attr, 'file_name'):
                            file_name = attr.file_name
                            break
                
                logger.info(f'媒体文件未通过大小筛选 (阈值 {size_limit_mb}MB)')
                context.stop_reason = 'media_size'
                context.stop_reason_detail = f'media size {file_size}MB over limit {size_limit_mb}MB'
                if rule.is_send_over_media_size_message:
                    logger.info(f'是否发送媒体大小超限提醒: {rule.is_send_over_media_size_message}')
                    context.should_forward = True
                else:
                    # 检查是否允许文本通过
                    if rule.media_allow_text:
                        logger.info('媒体超限但允许文本通过')
                        context.media_blocked = True  # 标记媒体被屏蔽
                        context.skipped_media.append((event.message, file_size, file_name))
                        return True  # 跳过后续的媒体下载
                    else:
                        context.should_forward = False
                context.skipped_media.append((event.message, file_size, file_name))
                return True  # 不论如何都跳过后续的媒体下载

            if max_cap_mb and file_size > max_cap_mb:
                if not rule.enable_media_size_filter:
                    logger.info(f'回填限制媒体大小: {backfill_max_mb}MB')
                file_name = ''
                if event.message.document:
                    for attr in event.message.document.attributes:
                        if hasattr(attr, 'file_name'):
                            file_name = attr.file_name
                            break
                logger.info(f'媒体文件超过回填大小上限 ({max_cap_mb}MB)')
                context.stop_reason = 'media_size'
                context.stop_reason_detail = f'media size {file_size}MB over backfill cap {max_cap_mb}MB'
                if rule.is_send_over_media_size_message:
                    context.should_forward = True
                else:
                    if rule.media_allow_text:
                        logger.info('媒体超限但允许文本通过')
                        context.media_blocked = True
                        context.skipped_media.append((event.message, file_size, file_name))
                        return True
                    else:
                        context.should_forward = False
                context.skipped_media.append((event.message, file_size, file_name))
                return True
            # 检查媒体时长
            if rule.enable_media_duration_filter and event.message.media:
                duration_seconds = self._get_media_duration_seconds(event.message)
                if duration_seconds is not None:
                    duration_minutes = round(duration_seconds / 60, 2)
                    duration_limit = rule.media_duration_minutes
                    duration_mode = self._get_compare_mode(
                        getattr(rule, "media_duration_filter_mode", CompareMode.LESS)
                    )
                    if duration_limit and self._is_duration_filtered(
                        duration_minutes, duration_limit, duration_mode
                    ):
                        logger.info(
                            f'媒体时长 {duration_minutes} 分钟未通过筛选 (阈值 {duration_limit} 分钟)'
                        )
                        context.stop_reason = 'media_duration'
                        context.stop_reason_detail = f'media duration {duration_minutes}m filtered by threshold {duration_limit}m'
                        if rule.media_allow_text:
                            logger.info('媒体时长不满足但允许文本通过')
                            context.media_blocked = True
                        else:
                            context.should_forward = False
                        return True

            # 如果只转发到RSS，则跳过下载媒体文件，交给RSS处理下载
            if rule.only_rss:
                return True
            if context.forward_via_forward_messages:
                logger.info("原消息直接转发模式，跳过媒体下载")
                return True
            try:
                # 下载媒体文件
                file_path = await event.message.download_media(TEMP_DIR)
                if file_path:
                    context.media_files.append(file_path)
                    logger.info(f'媒体文件已下载到: {file_path}')
            except Exception as e:
                logger.error(f'下载媒体文件时出错: {str(e)}')
                context.errors.append(f"下载媒体文件错误: {str(e)}")
        else:
            if is_pure_link_preview:
                # 记录这是纯链接预览消息
                context.is_pure_link_preview = True
                logger.info('这是一条纯链接预览消息')

            if rule.enable_media_type_filter:
                session = get_session()
                try:
                    media_types = session.query(MediaTypes).filter_by(rule_id=rule.id).first()
                    filter_mode = self._get_media_type_filter_mode(rule)
                    selected_types = self._get_selected_media_types(media_types) if media_types else set()
                    if media_types and self._is_message_type_blocked("text", filter_mode, selected_types):
                        logger.info(f'文本类型被屏蔽，跳过消息 ID={event.message.id}')
                        context.stop_reason = 'media_type'
                        context.stop_reason_detail = 'text type blocked by media type filter'
                        context.should_forward = False
                finally:
                    session.close()
            
    async def _is_media_type_blocked(self, message, media_types, filter_mode, selected_types):
        """
        检查媒体类型是否被屏蔽
        
        Args:
            message: Telethon Message 对象
            media_types: MediaTypes对象
            filter_mode: AddMode
            selected_types: 选中的媒体类型集合
            
        Returns:
            bool: 如果媒体类型被屏蔽返回True，否则返回False
        """
        media_type = self._detect_media_type(message)
        if not media_type:
            logger.info("无法识别媒体类型，默认放行")
            return False

        if filter_mode == AddMode.WHITELIST:
            if not selected_types:
                logger.info("媒体类型白名单为空，跳过类型过滤")
                return False
            if media_type not in selected_types:
                logger.info(f"媒体类型为 {media_type}，不在白名单中")
                return True
            return False

        if media_type in selected_types:
            logger.info(f"媒体类型为 {media_type}，已被屏蔽")
            return True

        return False

    def _is_message_type_blocked(self, message_type, filter_mode, selected_types):
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

    def _get_selected_media_types(self, media_types):
        if not media_types:
            return set()
        fields = ["photo", "document", "video", "audio", "voice", "text"]
        return {field for field in fields if getattr(media_types, field, False)}

    def _get_media_type_filter_mode(self, rule):
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

    def _get_compare_mode(self, value):
        if isinstance(value, CompareMode):
            return value
        if isinstance(value, str):
            try:
                return CompareMode(value)
            except ValueError:
                try:
                    return CompareMode[value]
                except KeyError:
                    return CompareMode.LESS
        return CompareMode.LESS

    def _is_size_filtered(self, size_mb: float, limit_mb: float, mode: CompareMode) -> bool:
        if mode == CompareMode.GREATER:
            return size_mb < limit_mb
        return size_mb > limit_mb

    def _is_duration_filtered(self, duration_minutes: float, limit_minutes: float, mode: CompareMode) -> bool:
        if mode == CompareMode.GREATER:
            return duration_minutes < limit_minutes
        return duration_minutes > limit_minutes

    def _detect_media_type(self, message):
        # Telethon 中 video/audio/voice 本质都是 document，需要按具体类型优先判定，避免误判为 document
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

        return None

    def _get_media_duration_seconds(self, message):
        document = getattr(message, "document", None)
        if not document or not getattr(document, "attributes", None):
            return None
        for attr in document.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                return getattr(attr, "duration", None)
            if isinstance(attr, DocumentAttributeAudio):
                return getattr(attr, "duration", None)
        return None

    def _get_backfill_max_media_size_mb(self):
        value = os.getenv("BACKFILL_MAX_MEDIA_SIZE_MB")
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            logger.warning("BACKFILL_MAX_MEDIA_SIZE_MB 配置无效，忽略")
            return None
    
    async def _is_media_extension_allowed(self, rule, media):
        """
        检查媒体扩展名是否被允许
        
        Args:
            rule: 转发规则
            media: 媒体对象
            
        Returns:
            bool: 如果扩展名被允许返回True，否则返回False
        """
        # 如果没有启用扩展名过滤，默认允许
        if not rule.enable_extension_filter:
            return True
            
        # 获取文件名
        file_name = None
     
        for attr in media.document.attributes:
            if hasattr(attr, 'file_name'):
                file_name = attr.file_name
                break

            
        # 如果没有文件名，则无法判断扩展名，默认允许
        if not file_name:
            logger.info("无法获取文件名，无法判断扩展名")
            return True
            
        # 提取扩展名
        _, extension = os.path.splitext(file_name)
        extension = extension.lstrip('.').lower()  # 移除点号并转为小写
        
        # 特殊处理：如果文件没有扩展名，将extension设为特殊值"无扩展名"
        if not extension:
            logger.info(f"文件 {file_name} 没有扩展名")
            extension = "无扩展名"
        else:
            logger.info(f"文件 {file_name} 的扩展名: {extension}")
        
        # 获取规则中保存的扩展名列表
        db_ops = await get_db_ops()
        session = get_session()
        allowed = True
        try:
            # 使用db_operations中的函数获取扩展名列表
            extensions = await db_ops.get_media_extensions(session, rule.id)
            extension_list = [ext["extension"].lower() for ext in extensions]
            
            # 判断是否允许该扩展名
            if rule.extension_filter_mode == AddMode.BLACKLIST:
                # 黑名单模式：如果扩展名在列表中，则不允许
                if extension in extension_list:
                    logger.info(f"扩展名 {extension} 在黑名单中，不允许")
                    allowed = False
                else:
                    logger.info(f"扩展名 {extension} 不在黑名单中，允许")
                    allowed = True
            else:
                # 白名单模式：如果扩展名不在列表中，则不允许
                if extension in extension_list:
                    logger.info(f"扩展名 {extension} 在白名单中，允许")
                    allowed = True
                else:
                    logger.info(f"扩展名 {extension} 不在白名单中，不允许")
                    allowed = False
        except Exception as e:
            logger.error(f"检查媒体扩展名时出错: {str(e)}")
            allowed = True  # 出错时默认允许
        finally:
            session.close()
            
        return allowed
