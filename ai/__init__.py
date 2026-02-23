from .base import BaseAIProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .deepseek_provider import DeepSeekProvider
from .qwen_provider import QwenProvider
from .grok_provider import GrokProvider
from .claude_provider import ClaudeProvider
import logging
from utils.constants import DEFAULT_AI_MODEL
from rss.app.core.config_manager import config_manager

# 获取日志记录器
logger = logging.getLogger(__name__)

async def get_ai_provider(model=None):
    """获取AI提供者实例（移除模型白名单校验）"""
    config = config_manager.get_config()
    ai_config = config.get("ai_service", {}) if isinstance(config, dict) else {}
    provider_type = (ai_config.get("provider") or "").strip().lower()

    if not model:
        model = (ai_config.get("model") or "").strip() or DEFAULT_AI_MODEL

    if provider_type in ("", "openai", "custom"):
        provider = OpenAIProvider()
    elif provider_type == "gemini":
        provider = GeminiProvider()
    elif provider_type == "deepseek":
        provider = DeepSeekProvider()
    elif provider_type == "qwen":
        provider = QwenProvider()
    elif provider_type == "grok":
        provider = GrokProvider()
    elif provider_type == "claude":
        provider = ClaudeProvider()
    else:
        logger.warning("未知的 AI Provider 类型: %s，回退为 OpenAIProvider", provider_type)
        provider = OpenAIProvider()

    logger.info("AI Provider 选择: %s，模型: %s", provider.__class__.__name__, model)
    return provider


__all__ = [
    'BaseAIProvider',
    'OpenAIProvider',
    'GeminiProvider',
    'DeepSeekProvider',
    'QwenProvider',
    'GrokProvider',
    'ClaudeProvider',
    'get_ai_provider'
]
