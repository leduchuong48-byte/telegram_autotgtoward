from typing import Optional, List, Dict
import logging
from .openai_base_provider import OpenAIBaseProvider

logger = logging.getLogger(__name__)

class OpenAIProvider(OpenAIBaseProvider):
    def __init__(self):
        super().__init__(
            env_prefix='OPENAI',
            default_model='gpt-4o-mini',
            default_api_base='https://api.openai.com/v1'
        )

    async def process_message(self, 
                            message: str, 
                            prompt: Optional[str] = None,
                            images: Optional[List[Dict[str, str]]] = None,
                            **kwargs) -> str:
        """处理消息"""
        return await super().process_message(message, prompt, images, **kwargs)
