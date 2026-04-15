"""
Telegram AutoFoward Application
"""

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from .routes.auth import router as auth_router

app = FastAPI(title="Telegram AutoFoward")


# 注册路由
app.include_router(auth_router)

# 模板配置
templates = Jinja2Templates(directory="rss/app/templates") 