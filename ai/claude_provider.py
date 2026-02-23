from typing import Optional, List, Dict
import anthropic
from .base import BaseAIProvider
import os
import logging
from rss.app.core.config_manager import config_manager

logger = logging.getLogger(__name__)

class ClaudeProvider(BaseAIProvider):
    def __init__(self):
        self.client = None
        self.model = None
        self.default_model = 'claude-3-5-sonnet-latest'
        
    async def initialize(self, **kwargs):
        """初始化Claude客户端"""
        config = config_manager.get_config()
        ai_config = config.get("ai_service", {}) if isinstance(config, dict) else {}

        api_key = (ai_config.get("api_key") or "").strip() or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise ValueError("未设置CLAUDE_API_KEY 或 AI API Key")
            
        # 检查是否配置了自定义API基础URL
        api_base = (ai_config.get("base_url") or "").strip() or os.getenv('CLAUDE_API_BASE', '').strip()
        if api_base:
            logger.info(f"使用自定义Claude API基础URL: {api_base}")
            self.client = anthropic.Anthropic(
                api_key=api_key,
                base_url=api_base
            )
        else:
            # 使用默认URL
            self.client = anthropic.Anthropic(api_key=api_key)
            
        self.model = kwargs.get('model', self.default_model)
        
    async def process_message(self, 
                            message: str, 
                            prompt: Optional[str] = None,
                            images: Optional[List[Dict[str, str]]] = None,
                            **kwargs) -> str:
        """处理消息"""
        try:
            await self.initialize(**kwargs)
                
            # 构建消息列表
            messages = []
            if prompt:
                messages.append({"role": "system", "content": prompt})
            
            # 如果有图片，需要添加到消息中
            if images and len(images) > 0:
                # 构建包含图片的内容列表
                content = []
                
                # 添加文本
                content.append({
                    "type": "text",
                    "text": message
                })
                
                # 添加每张图片
                for img in images:
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img["mime_type"],
                            "data": img["data"]
                        }
                    })
                    logger.info(f"已添加一张类型为 {img['mime_type']} 的图片，大小约 {len(img['data']) // 1000} KB")
                
                # 添加用户消息
                messages.append({"role": "user", "content": content})
            else:
                # 没有图片，只添加文本
                messages.append({"role": "user", "content": message})
            
            # 使用流式输出 - 按照官方文档正确实现
            with self.client.messages.stream(
                model=self.model,
                max_tokens=4096,
                messages=messages
            ) as stream:
                # 使用专用的text_stream迭代器直接获取文本
                full_response = ""
                for text in stream.text_stream:
                    full_response += text
        
            return full_response
            
        except Exception as e:
            logger.error(f"Claude API 调用失败: {str(e)}")
            return f"AI处理失败: {str(e)}" 
