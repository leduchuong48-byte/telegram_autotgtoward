from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from rss.app.routes.auth import router as auth_router
from rss.app.routes.rss import router as rss_router, rule_api_router, rule_domain_router
from rss.app.routes.system import router as system_router
from rss.app.routes.config import router as config_router
from rss.app.routes.bot_control import router as bot_control_router
from rss.app.routes.telegram_auth import router as telegram_auth_router
from rss.app.routes.ai import router as ai_router
from rss.app.api.endpoints import feed
import uvicorn
import logging
import sys
import os
from pathlib import Path
from utils.log_config import setup_logging



root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))


# 获取日志记录器
logger = logging.getLogger(__name__)

app = FastAPI(title="Telegram AutoFoward")

# 静态资源
static_dir = root_dir / "rss" / "app" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/sw.js")
async def service_worker():
    sw_path = static_dir / "sw.js"
    return FileResponse(
        sw_path,
        media_type="application/javascript",
        headers={
            "Service-Worker-Allowed": "/",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )

# 注册路由
app.include_router(auth_router)
app.include_router(rule_domain_router)
app.include_router(rss_router)
app.include_router(rule_api_router)
app.include_router(feed.router)
app.include_router(system_router)
app.include_router(config_router)
app.include_router(bot_control_router)
app.include_router(telegram_auth_router)
app.include_router(ai_router)

# 模板配置
templates = Jinja2Templates(directory="rss/app/templates")

def run_server(host: str = "0.0.0.0", port: int = 8000):
    """运行 RSS 服务器"""
    uvicorn.run(app, host=host, port=port)

# 添加直接运行支持
if __name__ == "__main__":
    # 只有在直接运行时才设置日志（而不是被导入时）
    setup_logging()
    run_server() 
