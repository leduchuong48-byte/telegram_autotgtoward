import logging

from fastapi import APIRouter, Body
from openai import AsyncOpenAI
from pydantic import BaseModel

from ..core.config_manager import config_manager
from ai.openai_base_provider import OpenAIBaseProvider


router = APIRouter(prefix="/api/ai", tags=["ai"])
logger = logging.getLogger(__name__)


class FetchModelsRequest(BaseModel):
    api_key: str
    base_url: str = ""
    provider: str = "openai"


@router.post("/fetch_models")
async def fetch_available_models(request: FetchModelsRequest = Body(...)):
    """连接 AI 服务商并拉取可用模型列表"""
    api_key = (request.api_key or "").strip()
    base_url = (request.base_url or "").strip()

    current_config = config_manager.get_config()
    ai_config = current_config.get("ai_service", {}) if isinstance(current_config, dict) else {}
    stored_key = ai_config.get("api_key", "")

    if not api_key or api_key.startswith("******"):
        if stored_key:
            api_key = stored_key
        else:
            return {"success": False, "message": "请先输入 API Key"}

    if not base_url:
        if request.provider == "openai":
            base_url = "https://api.openai.com/v1"
        elif request.provider == "deepseek":
            base_url = "https://api.deepseek.com"
        elif request.provider == "gemini":
            base_url = ""

    if base_url and not base_url.endswith("/v1") and not base_url.endswith("/v1/"):
        if "api.openai.com" in base_url or "deepseek" in base_url:
            base_url = f"{base_url}/v1"

    logger.info("正在从 %s 拉取模型...", base_url or "默认地址")

    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url if base_url else None,
            timeout=10.0,
            max_retries=1
        )

        models_response = await client.models.list()
        model_list = sorted([model.id for model in models_response.data])

        return {
            "success": True,
            "count": len(model_list),
            "models": model_list
        }
    except Exception as exc:
        logger.error("拉取模型失败: %s", exc)
        error_str = str(exc)
        if "401" in error_str:
            return {"success": False, "message": "认证失败 (401): API Key 无效"}
        if "404" in error_str:
            return {"success": False, "message": "路径错误 (404): 请检查 Base URL"}
        return {"success": False, "message": f"请求失败: {error_str}"}


@router.get("/models")
async def get_models():
    """基于当前配置拉取模型列表（支持多 Key / 多线路）"""
    provider = OpenAIBaseProvider()
    models = await provider.get_models()
    if not models:
        return {"status": "error", "data": [], "message": "未获取到模型列表"}
    return {"status": "success", "data": models, "count": len(models)}
