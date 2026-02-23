from typing import Optional, List, Dict
import google.generativeai as genai
# 移除对不存在的模块的导入
# from google.genai import types
from .base import BaseAIProvider
from .openai_base_provider import OpenAIBaseProvider
import os
import logging
import base64
from rss.app.core.config_manager import config_manager

logger = logging.getLogger(__name__)

class GeminiOpenAIProvider(OpenAIBaseProvider):
    """使用OpenAI兼容接口的Gemini提供者"""
    def __init__(self):
        super().__init__(
            env_prefix='GEMINI',
            default_model='gemini-pro',
            default_api_base=''  # API_BASE必须在环境变量中提供
        )

class GeminiProvider(BaseAIProvider):
    def __init__(self):
        self.model = None
        self.model_name = None  # 添加model_name属性
        self.provider = None
        
    async def initialize(self, **kwargs):
        """初始化Gemini客户端"""
        config = config_manager.get_config()
        ai_config = config.get("ai_service", {}) if isinstance(config, dict) else {}

        # 检查是否配置了 API Base，如果有则使用兼容OpenAI的接口
        api_base = (ai_config.get("base_url") or "").strip() or os.getenv('GEMINI_API_BASE', '').strip()
        
        if api_base:
            logger.info(f"检测到GEMINI_API_BASE环境变量: {api_base}，使用兼容OpenAI的接口")
            self.provider = GeminiOpenAIProvider()
            await self.provider.initialize(**kwargs)
            return
            
        # 原来的Gemini API初始化代码
        api_key = (ai_config.get("api_key") or "").strip() or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("未设置GEMINI_API_KEY 或 AI API Key")

        # 使用传入的model参数，如果没有才使用默认值
        if not self.model_name:  # 如果model_name还没设置
            self.model_name = kwargs.get('model') or ai_config.get("model")
        
        if not self.model_name:  # 如果kwargs中也没有model
            self.model_name = 'gemini-pro'  # 最后才使用默认值
            
        logger.info(f"初始化Gemini模型: {self.model_name}")
        
        # 配置安全设置 - 只使用基本类别
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE"
            }
        ]
            
        genai.configure(api_key=api_key)
        # 使用self.model_name初始化模型
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            safety_settings=safety_settings
        )
        
    async def process_message(self, 
                            message: str, 
                            prompt: Optional[str] = None,
                            images: Optional[List[Dict[str, str]]] = None,
                            **kwargs) -> str:
        """处理消息"""
        try:
            await self.initialize(**kwargs)
            
            # 如果使用的是OpenAI兼容接口，则调用该接口的处理方法
            if self.provider:
                return await self.provider.process_message(message, prompt, images, **kwargs)
                
            # 使用Gemini API的流式处理
            logger.info(f"实际使用的Gemini模型: {self.model_name}")

            # 组合提示词和消息
            if prompt:
                user_message = f"{prompt}\n\n{message}"
            else:
                user_message = message
            
            # 检查是否有图片
            if images and len(images) > 0:
                try:
                    # 使用MultimodalContent添加图片
                    contents = []
                    # 添加文本
                    contents.append({"role": "user", "parts": [{"text": user_message}]})
                    
                    # 对每张图片进行处理
                    for img in images:
                        try:
                            # 直接添加图片字节到模型的输入
                            image_part = {
                                "inline_data": {
                                    "mime_type": img["mime_type"],
                                    "data": img["data"]  # 使用原始base64数据
                                }
                            }
                            contents[0]["parts"].append(image_part)
                            logger.info(f"已添加一张类型为 {img['mime_type']} 的图片，大小约 {len(img['data']) // 1000} KB")
                        except Exception as img_error:
                            logger.error(f"处理单张图片时出错: {str(img_error)}")
                    
                    # 使用流式输出 - 不设置额外参数，使用默认值
                    response_stream = self.model.generate_content(
                        contents,
                        stream=True
                    )
                except Exception as e:
                    logger.error(f"Gemini处理带图片消息时出错: {str(e)}")
                    # 如果处理图片失败，尝试只用文本
                    response_stream = self.model.generate_content(
                        [{"role": "user", "parts": [{"text": user_message}]}],
                        stream=True
                    )
            else:
                # 无图片，使用流式输出
                response_stream = self.model.generate_content(
                    [{"role": "user", "parts": [{"text": user_message}]}],
                    stream=True
                )
            
            # 收集完整响应
            full_response = ""
            for chunk in response_stream:
                if hasattr(chunk, 'text'):
                    full_response += chunk.text
            
            return full_response
            
        except Exception as e:
            logger.error(f"Gemini处理消息时出错: {str(e)}")
            return f"AI处理失败: {str(e)}" 
