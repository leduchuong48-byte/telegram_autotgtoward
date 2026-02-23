from fastapi import APIRouter, HTTPException, Depends, Body, Request
from fastapi.responses import Response, FileResponse
from typing import Dict, Any
import logging
import os
import json
from pathlib import Path
from ...services.feed_generator import FeedService
from ...models.entry import Entry
from ...core.config import settings
from ...crud.entry import get_entries, create_entry, delete_entry
import mimetypes
from models.models import get_session, RSSConfig
from datetime import datetime
from ai import get_ai_provider
from models.models import get_session, ForwardRule
import re
from models.models import RSSPattern
import shutil
import time
import os
import subprocess
import platform
from pydantic import ValidationError
from utils.constants import RSS_MEDIA_BASE_URL

logger = logging.getLogger(__name__)
router = APIRouter()

# 添加本地访问验证依赖
async def verify_local_access(request: Request):
    """验证请求是否来自本地或Docker内部网络"""
    client_host = request.client.host if request.client else None
    
    # 允许的本地IP地址列表
    local_addresses = ['127.0.0.1', '::1', 'localhost', '0.0.0.0']
    
    # 如果设置了 HOST 环境变量，也将其添加到允许列表中
    if hasattr(settings, 'HOST') and settings.HOST:
        local_addresses.append(settings.HOST)
    
    # 检查是否是Docker内部网络IP (常见的私有网络范围)
    docker_ip = False
    if client_host:
        docker_prefixes = ['172.', '192.168.', '10.']
        docker_ip = any(client_host.startswith(prefix) for prefix in docker_prefixes)
    
    # 如果是本地地址或Docker内部网络IP，允许访问
    if client_host in local_addresses or docker_ip:
        logger.debug(f"已验证访问权限: {client_host}")
        return True
    
    # 拒绝来自外部网络的访问
    logger.warning(f"拒绝来自外部网络的访问: {client_host}")
    raise HTTPException(
        status_code=403, 
        detail="此API端点仅允许本地或内部网络访问"
    )

@router.get("/")
async def root():
    """服务状态检查"""
    return {
        "status": "ok",
        "service": "TG Forwarder RSS"
    }

@router.get("/rss/feed/{rule_id}")
async def get_feed(rule_id: int, request: Request):
    """返回规则对应的RSS Feed"""
    session = None
    try:
        # 创建数据库会话
        session = get_session()
        
        # 查询规则配置
        rss_config = session.query(RSSConfig).filter(RSSConfig.rule_id == rule_id).first()
        if not rss_config or not rss_config.enable_rss:
            logger.warning(f"规则 {rule_id} 的RSS未启用或不存在")
            raise HTTPException(status_code=404, detail="RSS feed 未启用或不存在")
        
        # 获取请求URL的基础部分
        base_url = str(request.base_url).rstrip('/')
        logger.info(f"请求基础URL: {base_url}")
        logger.info(f"请求头: {request.headers}")
        logger.info(f"请求客户端: {request.client}")
        
        # 检查是否有环境变量中配置的基础URL
        if RSS_MEDIA_BASE_URL:
            logger.info(f"使用环境变量中配置的媒体基础URL: {RSS_MEDIA_BASE_URL}")
            base_url = RSS_MEDIA_BASE_URL.rstrip('/')
        else:
            # 检查是否有X-Forwarded-Host或Host头
            forwarded_host = request.headers.get("X-Forwarded-Host")
            host_header = request.headers.get("Host")
            if forwarded_host:
                logger.info(f"检测到X-Forwarded-Host: {forwarded_host}")
                # 构建基于forwarded_host的URL
                scheme = request.headers.get("X-Forwarded-Proto", "http")
                base_url = f"{scheme}://{forwarded_host}"
                logger.info(f"基于X-Forwarded-Host的媒体基础URL: {base_url}")
            elif host_header and host_header != f"{settings.HOST}:{settings.PORT}":
                logger.info(f"检测到自定义Host: {host_header}")
                # 构建基于Host的URL
                scheme = request.url.scheme
                base_url = f"{scheme}://{host_header}"
                logger.info(f"基于Host的媒体基础URL: {base_url}")
        
        logger.info(f"最终使用的媒体基础URL: {base_url}")
        
        # 获取规则对应的条目
        entries = await get_entries(rule_id)
        logger.info(f"获取到 {len(entries)} 个条目")
        
        # 如果没有条目，返回测试数据
        if not entries:
            logger.warning(f"规则 {rule_id} 没有条目数据，返回测试数据")
            try:
                fg = FeedService.generate_test_feed(rule_id, base_url)
                
                # 生成 RSS XML
                rss_xml = fg.rss_str(pretty=True)
                
                # 确保rss_xml是字符串类型
                if isinstance(rss_xml, bytes):
                    logger.info("将RSS XML从字节转换为字符串")
                    rss_xml = rss_xml.decode('utf-8')
                
                # 记录XML内容的一部分
                xml_sample = rss_xml[:500] + "..." if len(rss_xml) > 500 else rss_xml
                logger.info(f"生成的测试RSS XML (前500字符): {xml_sample}")
                
                # 检查XML中是否还有硬编码的localhost或127.0.0.1地址
                if "127.0.0.1" in rss_xml or "localhost" in rss_xml:
                    logger.warning(f"RSS XML中仍包含硬编码的本地地址")
                    
                    # 替换硬编码的地址
                    rss_xml = rss_xml.replace(f"http://127.0.0.1:{settings.PORT}", base_url)
                    rss_xml = rss_xml.replace(f"http://localhost:{settings.PORT}", base_url)
                    rss_xml = rss_xml.replace(f"http://{settings.HOST}:{settings.PORT}", base_url)
                    
                    logger.info(f"已替换硬编码的本地地址为: {base_url}")
                
                # 确保返回的是字节类型
                if isinstance(rss_xml, str):
                    rss_xml = rss_xml.encode('utf-8')
                
                return Response(
                    content=rss_xml,
                    media_type="application/xml; charset=utf-8"
                )
            except Exception as e:
                logger.error(f"生成测试Feed时出错: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"生成测试Feed失败: {str(e)}")
        else:
            # 根据真实数据生成 Feed，传入基础URL
            try:
                fg = await FeedService.generate_feed_from_entries(rule_id, entries, base_url)
                
                # 生成 RSS XML
                rss_xml = fg.rss_str(pretty=True)
                
                # 确保rss_xml是字符串类型
                if isinstance(rss_xml, bytes):
                    logger.info("将RSS XML从字节转换为字符串")
                    rss_xml = rss_xml.decode('utf-8')
                
                # 记录XML内容的一部分
                xml_sample = rss_xml[:500] + "..." if len(rss_xml) > 500 else rss_xml
                logger.info(f"生成的RSS XML (前500字符): {xml_sample}")
                
                # 检查XML中是否还有硬编码的localhost或127.0.0.1地址
                if "127.0.0.1" in rss_xml or "localhost" in rss_xml:
                    logger.warning(f"RSS XML中仍包含硬编码的本地地址")
                    
                    # 替换硬编码的地址
                    rss_xml = rss_xml.replace(f"http://127.0.0.1:{settings.PORT}", base_url)
                    rss_xml = rss_xml.replace(f"http://localhost:{settings.PORT}", base_url)
                    rss_xml = rss_xml.replace(f"http://{settings.HOST}:{settings.PORT}", base_url)
                    
                    logger.info(f"已替换硬编码的本地地址为: {base_url}")
                
                # 确保返回的是字节类型
                if isinstance(rss_xml, str):
                    rss_xml = rss_xml.encode('utf-8')
                
                return Response(
                    content=rss_xml,
                    media_type="application/xml; charset=utf-8"
                )
            except Exception as e:
                logger.error(f"生成真实条目Feed时出错: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"生成Feed失败: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成RSS feed时出错: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        # 确保会话被关闭
        if session:
            session.close()

@router.get("/media/{rule_id}/{filename}")
async def get_media(rule_id: int, filename: str, request: Request):
    """返回媒体文件"""
    # 记录请求信息
    logger.info(f"媒体请求 - 规则ID: {rule_id}, 文件名: {filename}")
    logger.info(f"请求URL: {request.url}")
    logger.info(f"请求头: {request.headers}")
    
    # 获取基础URL，用于日志记录
    base_url = str(request.base_url).rstrip('/')
    if RSS_MEDIA_BASE_URL:
        logger.info(f"环境变量中配置的媒体基础URL: {RSS_MEDIA_BASE_URL}")
        base_url = RSS_MEDIA_BASE_URL.rstrip('/')
    else:
        # 检查是否有X-Forwarded-Host或Host头
        forwarded_host = request.headers.get("X-Forwarded-Host")
        host_header = request.headers.get("Host")
        if forwarded_host:
            logger.info(f"检测到X-Forwarded-Host: {forwarded_host}")
            scheme = request.headers.get("X-Forwarded-Proto", "http")
            base_url = f"{scheme}://{forwarded_host}"
        elif host_header and host_header != f"{settings.HOST}:{settings.PORT}":
            logger.info(f"检测到自定义Host: {host_header}")
            scheme = request.url.scheme
            base_url = f"{scheme}://{host_header}"
    
    logger.info(f"最终使用的媒体基础URL: {base_url}")
    
    # 构建规则特定的媒体文件路径
    media_path = Path(settings.get_rule_media_path(rule_id)) / filename
    
    # 记录尝试访问的路径
    logger.info(f"尝试访问媒体文件: {media_path}")
    
    # 检查文件是否存在
    if not media_path.exists():
        # 文件不存在，返回404
        logger.error(f"媒体文件未找到: {filename}")
        raise HTTPException(status_code=404, detail=f"媒体文件未找到: {filename}")
    
    # 确定正确的MIME类型
    mime_type = mimetypes.guess_type(str(media_path))[0]
    if not mime_type:
        # 如果无法确定MIME类型，根据文件扩展名猜测
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        if ext in ['mp4', 'mov', 'avi', 'webm']:
            mime_type = f"video/{ext}"
        elif ext in ['mp3', 'wav', 'ogg', 'flac']:
            mime_type = f"audio/{ext}"
        elif ext in ['jpg', 'jpeg', 'png', 'gif']:
            mime_type = f"image/{ext}"
        else:
            mime_type = "application/octet-stream"
            
    logger.info(f"发送媒体文件: {filename}, MIME类型: {mime_type}, 大小: {os.path.getsize(media_path)} 字节")
    
    # 返回文件，并设置正确的Content-Type
    return FileResponse(
        path=media_path,
        media_type=mime_type,
        filename=filename
    )

@router.post("/api/entries/{rule_id}/add", dependencies=[Depends(verify_local_access)])
async def add_entry(rule_id: int, entry_data: Dict[str, Any] = Body(...)):
    """添加新的条目 (仅限本地访问)"""
    try:
        # 记录接收到的数据摘要
        media_count = len(entry_data.get("media", []))
        has_context = "context" in entry_data and entry_data["context"] is not None
        logger.info(f"接收到新条目数据: 规则ID={rule_id}, 标题='{entry_data.get('title', '无标题')}', 媒体数量={media_count}, 包含上下文={has_context}")
        
        # 获取 RSS 配置信息，确定最大条目数量
        session = get_session()
        max_items = None
        try:
            rss_config = session.query(RSSConfig).filter(RSSConfig.rule_id == rule_id).first()
            max_items = rss_config.max_items
        finally:
            session.close()
        
        # 验证媒体数据
        if media_count > 0:
            media_filenames = []
            for m in entry_data.get("media", []):
                if isinstance(m, dict):
                    media_filenames.append(m.get('filename', '未知'))
                else:
                    media_filenames.append(getattr(m, 'filename', '未知'))
            logger.info(f"媒体文件列表: {media_filenames}")
            
            # 确保媒体文件存在
            for media in entry_data.get("media", []):
                if isinstance(media, dict):
                    filename = media.get("filename", "")
                else:
                    filename = getattr(media, "filename", "")
                
                media_path = os.path.join(settings.MEDIA_PATH, filename)
                if not os.path.exists(media_path):
                    logger.warning(f"媒体文件不存在: {media_path}")
        
        # 记录上下文信息
        if has_context:
            logger.info(f"条目包含原始上下文对象，属性: {', '.join(entry_data['context'].keys()) if hasattr(entry_data['context'], 'keys') else '无法获取属性'}")
        
        # 确保必要的字段存在
        entry_data["rule_id"] = rule_id
        if not entry_data.get("message_id"):
            entry_data["message_id"] = entry_data.get("id", "")
        
        # 检查当前条目数量，如果接近限制则删除最旧的条目
        current_entries = await get_entries(rule_id)
        if len(current_entries) >= max_items - 1:
            # 计算需要删除的条目数量，确保添加新条目后总数不超过最大限制
            to_delete_count = len(current_entries) - (max_items - 1)
            if to_delete_count > 0:
                logger.info(f"当前条目数量({len(current_entries)})将超过限制({max_items})，需要删除 {to_delete_count} 个最早的条目")
                
                # 对条目按发布时间排序（从早到晚）
                sorted_entries = sorted(current_entries, key=lambda e: datetime.fromisoformat(e.published) if hasattr(e, 'published') else datetime.now())
                
                # 获取要删除的条目
                entries_to_delete = sorted_entries[:to_delete_count]
                
                # 删除多余条目
                for entry in entries_to_delete:
                    try:
                        # 删除条目前先处理其媒体文件
                        if hasattr(entry, 'media') and entry.media:
                            logger.info(f"条目 {entry.id} 包含 {len(entry.media)} 个媒体文件，将一并删除")
                            
                            # 删除媒体文件
                            media_dir = Path(settings.get_rule_media_path(rule_id))
                            for media in entry.media:
                                if hasattr(media, 'filename'):
                                    media_path = media_dir / media.filename
                                    if media_path.exists():
                                        try:
                                            os.remove(media_path)
                                            logger.info(f"已删除媒体文件: {media_path}")
                                        except Exception as e:
                                            logger.error(f"删除媒体文件失败: {media_path}, 错误: {str(e)}")
                        
                        # 删除条目
                        success = await delete_entry(rule_id, entry.id)
                        if success:
                            logger.info(f"已删除条目: {entry.id}")
                        else:
                            logger.warning(f"删除条目失败: {entry.id}")
                    except Exception as e:
                        logger.error(f"处理过期条目时出错: {str(e)}")
        
        # 转换为Entry对象
        entry = Entry(
            rule_id=rule_id,
            message_id=entry_data.get("message_id", entry_data.get("id", "")),
            title=entry_data.get("title", "新消息"),
            content=entry_data.get("content", ""),
            published=entry_data.get("published"),
            author=entry_data.get("author", ""),
            link=entry_data.get("link", ""),
            media=entry_data.get("media", []),
            original_link=entry_data.get("original_link"),
            sender_info=entry_data.get("sender_info")
        )

        

        # 使用AI提取内容
        if rss_config.is_ai_extract:
            try:
                rule = session.query(ForwardRule).filter(ForwardRule.id == rule_id).first()
                provider = await get_ai_provider(rule.ai_model)
                json_text = await provider.process_message(
                    message=entry.content or "",
                    prompt=rss_config.ai_extract_prompt,
                    model=rule.ai_model
                )
                logger.info(f"AI提取内容: {json_text}")
                
                # 去除代码块标记，如果有的话
                if "```" in json_text:
                    # 移除所有代码块标记，包括语言标识和结束标记
                    json_text = re.sub(r'```(\w+)?\n', '', json_text)  # 开始标记（带可选的语言标识）
                    json_text = re.sub(r'\n```', '', json_text)  # 结束标记
                    json_text = json_text.strip()
                    logger.info(f"去除代码块标记后的内容: {json_text}")
                
                # 解析JSON数据
                try:
                    json_data = json.loads(json_text)
                    logger.info(f"解析后的JSON数据: {json_data}")
                    
                    # 提取标题和内容
                    title = json_data.get("title", "")
                    content = json_data.get("content", "")
                    entry.title = title
                    entry.content = content
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析错误: {str(e)}, 原始文本: {json_text}")
                    # 尝试其他清理方式
                    try:
                        # 匹配大括号之间的JSON内容
                        json_match = re.search(r'\{.*\}', json_text, re.DOTALL)
                        if json_match:
                            clean_json = json_match.group(0)
                            logger.info(f"尝试提取JSON: {clean_json}")
                            json_data = json.loads(clean_json)
                            
                            # 提取标题和内容
                            title = json_data.get("title", "")
                            content = json_data.get("content", "")
                            entry.title = title
                            entry.content = content
                            logger.info(f"成功从文本中提取JSON数据")
                        else:
                            logger.error("无法从AI响应中提取有效JSON")
                    except Exception as inner_e:
                        logger.error(f"尝试二次解析JSON时出错: {str(inner_e)}")
                except Exception as e:
                    logger.error(f"处理JSON数据时出错: {str(e)}")
            except Exception as e:
                logger.error(f"AI提取内容时出错: {str(e)}")
            finally:
                if session:
                    session.close()
        
        logger.info(f"启用自定义标题模式: {rss_config.enable_custom_title_pattern}, 启用自定义内容模式: {rss_config.enable_custom_content_pattern}")
        if rss_config.enable_custom_title_pattern or rss_config.enable_custom_content_pattern:
            try:
                # 获取原始内容
                original_content = entry.content or ""
                original_title = entry.title
                
                # 如果启用了标题正则表达式提取
                if rss_config.enable_custom_title_pattern:
                    # 直接使用会话查询标题模式并按优先级排序
                    title_patterns = session.query(RSSPattern).filter_by(
                        rss_config_id=rss_config.id, 
                        pattern_type='title'
                    ).order_by(RSSPattern.priority).all()
                    
                    logger.info(f"找到 {len(title_patterns)} 个标题模式")
                    
                    # 设置初始处理文本
                    processing_content = original_content
                    logger.info(f"标题提取初始文本: {processing_content[:100]}..." if len(processing_content) > 100 else processing_content)
                    
                    # 依次应用每个模式，每次处理后的结果作为下一个模式的输入
                    for pattern in title_patterns:
                        logger.info(f"开始尝试标题模式: {pattern.pattern}")
                        try:
                            logger.info(f"对内容应用正则表达式: {pattern.pattern}")
                            match = re.search(pattern.pattern, processing_content)
                            if match:
                                logger.info(f"找到匹配: {match.groups()}")
                                if match.groups():
                                    entry.title = match.group(1)
                                    logger.info(f"使用标题模式 '{pattern.pattern}' 提取到标题: {entry.title}")
                                else:
                                    logger.warning(f"模式 '{pattern.pattern}' 匹配成功但没有捕获组")
                            else:
                                logger.info(f"模式 '{pattern.pattern}' 未找到匹配")
                        except Exception as e:
                            logger.error(f"应用标题正则表达式 '{pattern.pattern}' 时出错: {str(e)}")
                            logger.exception("详细错误信息:")
                
                # 如果启用了内容正则表达式提取
                if rss_config.enable_custom_content_pattern:
                    # 直接使用会话查询内容模式并按优先级排序
                    content_patterns = session.query(RSSPattern).filter_by(
                        rss_config_id=rss_config.id, 
                        pattern_type='content'
                    ).order_by(RSSPattern.priority).all()
                    
                    logger.info(f"找到 {len(content_patterns)} 个内容模式")
                    
                    # 设置初始处理文本
                    processing_content = original_content
                    logger.info(f"内容提取初始文本: {processing_content[:100]}..." if len(processing_content) > 100 else processing_content)
                    
                    # 依次应用每个模式，每次处理后的结果作为下一个模式的输入
                    for i, pattern in enumerate(content_patterns):
                        try:
                            logger.info(f"[步骤 {i+1}/{len(content_patterns)}] 对内容应用正则表达式: {pattern.pattern}")
                            logger.info(f"处理前的内容长度: {len(processing_content)}, 预览: {processing_content[:150]}..." if len(processing_content) > 150 else processing_content)
                            
                            match = re.search(pattern.pattern, processing_content)
                            if match and match.groups():
                                extracted_content = match.group(1)
                                processing_content = extracted_content  # 更新处理内容为提取结果
                                entry.content = extracted_content
                                
                                logger.info(f"使用内容模式 '{pattern.pattern}' 提取到内容，长度: {len(extracted_content)}")
                                logger.info(f"处理后的内容长度: {len(processing_content)}, 预览: {processing_content[:150]}..." if len(processing_content) > 150 else processing_content)
                            else:
                                logger.info(f"模式 '{pattern.pattern}' 未找到匹配或没有捕获组，内容保持不变")
                        except Exception as e:
                            logger.error(f"应用内容正则表达式 '{pattern.pattern}' 时出错: {str(e)}")
                
                
                # 如果执行到这里但没有提取到标题，则恢复原标题
                if not entry.title and original_title:
                    entry.title = original_title
                    logger.info(f"恢复原标题: {entry.title}")
                
            except Exception as e:
                logger.error(f"使用正则表达式提取标题和内容时出错: {str(e)}")


        if entry.sender_info:
            # 清楚空格和换行
            entry.sender_info = entry.sender_info.strip()
            entry.content = entry.sender_info +":" +"\n\n" + entry.content

        # 添加原始链接
        if entry.original_link:
            # 清理链接中的前缀、换行符和多余空格
            clean_link = entry.original_link.replace("原始消息:", "").strip()
            # 删除链接中的所有换行符
            clean_link = clean_link.replace("\n", "").replace("\r", "")
            # 处理链接中的多余空格
            clean_link = re.sub(r'\s+', ' ', clean_link).strip()
            
            # 确保链接是URL格式
            if clean_link.startswith("http"):
                if entry.author:
                    # 使用Markdown格式的链接
                    entry.content += f'\n\n[来源: {entry.author}]({clean_link})'
                else:
                    # 使用Markdown格式的链接
                    entry.content += f'\n\n[来源]({clean_link})'
                logger.info(f"已添加清理后的链接(Markdown格式): {clean_link}")
            else:
                logger.warning(f"链接格式不正确，跳过添加: {clean_link}")
        
        # 处理后的消息
        logger.info(f"处理后的消息: {entry.content}")

       

        
        # 添加条目
        success = await create_entry(entry)
        if success:
            return {"status": "success", "message": f"条目已添加，媒体文件数量: {media_count}"}
        else:
            logger.error("添加条目失败")
            raise HTTPException(status_code=500, detail="添加条目失败")
            
    except ValidationError as e:
        logger.error(f"验证错误: {str(e)}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"添加条目时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/entries/{rule_id}/{entry_id}", dependencies=[Depends(verify_local_access)])
async def delete_entry_api(rule_id: int, entry_id: str):
    """删除条目 (仅限本地访问)"""
    try:
        # 删除条目
        success = await delete_entry(rule_id, entry_id)
        if not success:
            raise HTTPException(status_code=404, detail="条目未找到")
        
        return {"status": "success", "message": "条目已删除"}
    except Exception as e:
        logger.error(f"删除条目时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/entries/{rule_id}")
async def list_entries(rule_id: int, limit: int = 20, offset: int = 0):
    """列出规则对应的所有条目"""
    try:
        entries = await get_entries(rule_id, limit, offset)
        return {"entries": entries, "total": len(entries), "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"获取条目列表时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/rule/{rule_id}", dependencies=[Depends(verify_local_access)])
async def delete_rule_data(rule_id: int):
    """删除规则相关的所有数据和媒体文件 (仅限本地访问)"""
    try:
        
        
        # 获取规则的数据目录和媒体目录
        data_path = Path(settings.get_rule_data_path(rule_id))
        media_path = Path(settings.get_rule_media_path(rule_id))
        
        deleted_files = 0
        deleted_dirs = 0
        failed_paths = []
        
        # 辅助函数：强制删除目录
        def force_delete_directory(dir_path):
            if not dir_path.exists():
                return True, "目录不存在"
                
            # 方法1: 使用 shutil.rmtree
            try:
                shutil.rmtree(dir_path, ignore_errors=True)
                if not dir_path.exists():
                    return True, "使用 shutil.rmtree 成功删除"
            except Exception as e:
                pass
                
            # 方法2: 使用系统命令
            try:
                system = platform.system()
                if system == "Windows":
                    # Windows: 使用 rd /s /q
                    subprocess.run(["rd", "/s", "/q", str(dir_path)], 
                                  shell=True, 
                                  stderr=subprocess.PIPE, 
                                  stdout=subprocess.PIPE)
                else:
                    # Linux/Mac: 使用 rm -rf
                    subprocess.run(["rm", "-rf", str(dir_path)], 
                                  stderr=subprocess.PIPE, 
                                  stdout=subprocess.PIPE)
                    
                if not dir_path.exists():
                    return True, "使用系统命令成功删除"
            except Exception as e:
                pass
                
            # 方法3: 重命名后删除
            try:
                temp_path = dir_path.parent / f"temp_delete_{time.time()}"
                os.rename(dir_path, temp_path)
                shutil.rmtree(temp_path, ignore_errors=True)
                if not dir_path.exists() and not temp_path.exists():
                    return True, "使用重命名后删除成功"
            except Exception as e:
                pass
            
            return False, "所有删除方法都失败"
        
        # 删除媒体目录
        if media_path.exists():
            logger.info(f"开始删除媒体目录: {media_path}")
            success, method = force_delete_directory(media_path)
            if success:
                deleted_dirs += 1
                logger.info(f"已删除媒体目录: {media_path} - {method}")
            else:
                logger.error(f"无法删除媒体目录: {media_path} - {method}")
                failed_paths.append(str(media_path))
        
        # 删除数据目录
        if data_path.exists():
            logger.info(f"开始删除数据目录: {data_path}")
            success, method = force_delete_directory(data_path)
            if success:
                deleted_dirs += 1
                logger.info(f"已删除数据目录: {data_path} - {method}")
            else:
                logger.error(f"无法删除数据目录: {data_path} - {method}")
                failed_paths.append(str(data_path))
        
        # 验证删除结果
        remaining_paths = []
        if media_path.exists():
            remaining_paths.append(str(media_path))
        if data_path.exists():
            remaining_paths.append(str(data_path))
        
        # 返回删除结果
        status = "success" if not remaining_paths else "failed"
        return {
            "status": status,
            "message": f"处理规则 {rule_id} 的数据{'失败，目录仍然存在' if remaining_paths else '成功，目录已删除'}",
            "details": {
                "data_path": str(data_path),
                "media_path": str(media_path),
                "deleted_files": deleted_files,
                "deleted_dirs": deleted_dirs,
                "failed_paths": failed_paths,
                "remaining_paths": remaining_paths,
                "data_dir_exists": data_path.exists(),
                "media_dir_exists": media_path.exists()
            }
        }
    except Exception as e:
        logger.error(f"删除规则数据时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除规则数据时出错: {str(e)}") 