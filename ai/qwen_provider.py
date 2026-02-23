from typing import Optional, List, Dict
from openai import AsyncOpenAI
from .openai_base_provider import OpenAIBaseProvider
import os
import logging

logger = logging.getLogger(__name__)

class QwenProvider(OpenAIBaseProvider):
    def __init__(self):
        super().__init__(
            env_prefix='QWEN',
            default_model='qwen-plus',
            default_api_base='https://dashscope.aliyuncs.com/compatible-mode/v1'
        )