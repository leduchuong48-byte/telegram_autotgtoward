from typing import Optional, List, Dict
from openai import AsyncOpenAI
from .openai_base_provider import OpenAIBaseProvider
import os
import logging

logger = logging.getLogger(__name__)

class DeepSeekProvider(OpenAIBaseProvider):
    def __init__(self):
        super().__init__(
            env_prefix='DEEPSEEK',
            default_model='deepseek-chat',
            default_api_base='https://api.deepseek.com/v1'
        )
