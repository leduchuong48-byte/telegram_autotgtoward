from typing import Optional, List, Dict
from openai import AsyncOpenAI, APIConnectionError, RateLimitError
from .base import BaseAIProvider
import itertools
import logging
import os
import random
import re
from rss.app.core.config_manager import config_manager

logger = logging.getLogger(__name__)

class OpenAIBaseProvider(BaseAIProvider):
    def __init__(self, env_prefix: str = 'OPENAI', default_model: str = 'gpt-4o-mini',
                 default_api_base: str = 'https://api.openai.com/v1'):
        """
        初始化基础OpenAI格式提供者

        Args:
            env_prefix: 环境变量前缀，如 'OPENAI', 'GROK', 'DEEPSEEK', 'QWEN'
            default_model: 默认模型名称
            default_api_base: 默认API基础URL
        """
        super().__init__()
        self.env_prefix = env_prefix
        self.default_model = default_model
        self.default_api_base = default_api_base
        self.client = None
        self.model = None
        self._last_api_key = None
        self._last_api_base = None

    def _parse_list(self, config_str: str) -> list:
        if not config_str:
            return []
        return [item.strip() for item in re.split(r"[,;\n]", str(config_str)) if item.strip()]

    def _generate_candidates(self, key_pool: list, url_pool: list, strategy: str) -> list:
        candidates = list(itertools.product(key_pool, url_pool))
        if strategy == "random":
            random.shuffle(candidates)
        return candidates

    def _get_runtime_config(self, **kwargs):
        config = config_manager.get_config()
        ai_config = config.get("ai_service", {}) if isinstance(config, dict) else {}
        api_key = (ai_config.get("api_key") or "").strip()
        if not api_key:
            api_key = os.getenv(f"{self.env_prefix}_API_KEY", "")
        api_base = (ai_config.get("base_url") or "").strip()
        if not api_base:
            api_base = os.getenv(f"{self.env_prefix}_API_BASE", "").strip()
        api_base = api_base or self.default_api_base or ""
        model = (kwargs.get("model") or "").strip()
        if not model:
            model = (ai_config.get("model") or "").strip() or self.default_model
        key_strategy = (ai_config.get("key_strategy") or "").strip().lower()
        if key_strategy not in ("sequence", "random"):
            key_strategy = "sequence"
        return api_key, api_base, model, key_strategy

    async def initialize(self, **kwargs) -> None:
        """初始化OpenAI客户端（动态读取配置）"""
        try:
            api_key, api_base, model, key_strategy = self._get_runtime_config(**kwargs)
            key_pool = self._parse_list(api_key)
            if not key_pool:
                raise ValueError(f"未设置 {self.env_prefix}_API_KEY 或 AI API Key")
            url_pool = self._parse_list(api_base)
            if not url_pool:
                url_pool = [self.default_api_base] if self.default_api_base else [""]
            candidates = self._generate_candidates(key_pool, url_pool, key_strategy)
            selected_key, selected_url = candidates[0]

            if self.client is None or selected_key != self._last_api_key or selected_url != self._last_api_base:
                base_url = selected_url if selected_url else None
                self.client = AsyncOpenAI(
                    api_key=selected_key,
                    base_url=base_url
                )
                self._last_api_key = selected_key
                self._last_api_base = selected_url

            self.model = model
            logger.info(f"初始化OpenAI模型: {self.model}")

        except Exception as e:
            error_msg = f"初始化 {self.env_prefix} 客户端时出错: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise

    async def process_message(self,
                            message: str,
                            prompt: Optional[str] = None,
                            images: Optional[List[Dict[str, str]]] = None,
                            **kwargs) -> str:
        """处理消息"""
        try:
            api_key, api_base, model, key_strategy = self._get_runtime_config(**kwargs)
            key_pool = self._parse_list(api_key)
            if not key_pool:
                raise ValueError(f"未设置 {self.env_prefix}_API_KEY 或 AI API Key")
            url_pool = self._parse_list(api_base)
            if not url_pool:
                url_pool = [self.default_api_base] if self.default_api_base else [""]
            candidates = self._generate_candidates(key_pool, url_pool, key_strategy)
            logger.info("已生成 %d 条候选线路", len(candidates))

            messages = []
            if prompt:
                messages.append({"role": "system", "content": prompt})

            # 如果有图片，需要添加到消息中
            if images and len(images) > 0:
                # 创建包含文本和图片的内容数组
                content = []

                # 添加文本
                content.append({
                    "type": "text",
                    "text": message
                })

                # 添加每张图片
                for img in images:
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img['mime_type']};base64,{img['data']}"
                        }
                    })
                    logger.info(f"已添加一张类型为 {img['mime_type']} 的图片，大小约 {len(img['data']) // 1000} KB")

                messages.append({"role": "user", "content": content})
            else:
                # 没有图片，只添加文本
                messages.append({"role": "user", "content": message})

            last_error = None
            for idx, (key, base_url) in enumerate(candidates):
                try:
                    base_url_value = base_url if base_url else None
                    client = AsyncOpenAI(
                        api_key=key,
                        base_url=base_url_value,
                        timeout=30.0
                    )
                    self.client = client
                    self.model = model

                    logger.info(f"实际使用的OpenAI模型: {self.model}")

                    # 所有模型统一使用流式调用
                    completion = await client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        stream=True
                    )

                    # 收集所有内容
                    collected_content = ""
                    collected_reasoning = ""

                    async for chunk in completion:
                        if not chunk.choices:
                            continue

                        delta = chunk.choices[0].delta

                        # 处理思考内容（如果存在）
                        if hasattr(delta, 'reasoning_content') and delta.reasoning_content is not None:
                            collected_reasoning += delta.reasoning_content

                        # 处理回答内容
                        if hasattr(delta, 'content') and delta.content is not None:
                            collected_content += delta.content

                    # 如果没有内容但有思考过程，可能是思考模型只返回了思考过程
                    if not collected_content and collected_reasoning:
                        logger.warning("模型只返回了思考过程，没有最终回答")
                        return "模型未能生成有效回答"

                    return collected_content
                except (RateLimitError, APIConnectionError) as exc:
                    key_suffix = key[-4:] if len(key) >= 4 else "****"
                    display_url = base_url or "默认地址"
                    logger.warning(
                        f"线路 {display_url} (Key尾号{key_suffix}) 请求失败: {exc}. 正在尝试第 {idx + 2} 个候选..."
                    )
                    last_error = exc
                    continue
                except Exception as exc:
                    key_suffix = key[-4:] if len(key) >= 4 else "****"
                    display_url = base_url or "默认地址"
                    logger.error(
                        f"线路 {display_url} (Key尾号{key_suffix}) 发生异常: {exc}. 切换下一候选..."
                    )
                    last_error = exc
                    continue

            raise RuntimeError(f"所有 {len(candidates)} 条候选线路均尝试失败。最后错误: {last_error}")

        except Exception as e:
            logger.error(f"{self.env_prefix} API 调用失败: {str(e)}", exc_info=True)
            return f"AI处理失败: {str(e)}"

    async def get_models(self) -> list:
        """轮询所有候选线路，成功拉取一次即返回模型列表"""
        api_key, api_base, _, key_strategy = self._get_runtime_config()
        key_pool = self._parse_list(api_key)
        if not key_pool:
            return []
        url_pool = self._parse_list(api_base)
        if not url_pool:
            url_pool = [self.default_api_base] if self.default_api_base else [""]

        candidates = self._generate_candidates(key_pool, url_pool, key_strategy)
        logger.info("拉取模型候选线路数: %d", len(candidates))

        for api_key_value, base_url in candidates:
            try:
                client = AsyncOpenAI(
                    api_key=api_key_value,
                    base_url=base_url if base_url else None,
                    timeout=10.0,
                    max_retries=1
                )
                resp = await client.models.list()
                return [model.id for model in resp.data]
            except Exception as exc:
                key_suffix = api_key_value[-4:] if len(api_key_value) >= 4 else "****"
                display_url = base_url or "默认地址"
                logger.warning("模型拉取失败: %s (Key尾号%s): %s", display_url, key_suffix, exc)
                continue

        return []
