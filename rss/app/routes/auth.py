from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from models.models import get_session, User, RSSConfig
from models.db_operations import DBOperations
import jwt
from datetime import datetime, timedelta
import pytz
from utils.constants import DEFAULT_TIMEZONE
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import joinedload
import models.models as models
import os
import secrets
from pathlib import Path
from rss.app.core.app_state import build_app_state

router = APIRouter()
templates = Jinja2Templates(directory="rss/app/templates")
db_ops = None

# JWT 配置
SECRET_KEY = os.getenv("JWT_SECRET_KEY") or secrets.token_hex(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24小时

def init_db_ops():
    global db_ops
    if db_ops is None:
        db_ops = DBOperations()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    tz = pytz.timezone(DEFAULT_TIMEZONE)
    if expires_delta:
        expire = datetime.now(tz) + expires_delta
    else:
        expire = datetime.now(tz) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def tail_lines(log_path: str, limit: int):
    path = Path(log_path)
    if not path.exists() or not path.is_file():
        return None

    block_size = 4096
    data = b""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        while position > 0 and data.count(b"\n") <= limit:
            read_size = min(block_size, position)
            position -= read_size
            handle.seek(position)
            data = handle.read(read_size) + data

    lines = data.splitlines()
    if limit > 0:
        lines = lines[-limit:]
    return [line.decode("utf-8", errors="replace") for line in lines]

def get_bearer_token(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]

async def get_current_user(request: Request):
    token = get_bearer_token(request) or request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except jwt.PyJWTError:
        return None
    
    db_session = get_session()
    try:
        init_db_ops()
        user = await db_ops.get_user(db_session, username)
        return user
    finally:
        db_session.close()

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    db_session = get_session()
    try:
        # 检查是否有任何用户存在
        users = db_session.query(User).all()
        if not users:
            return RedirectResponse(url="/register", status_code=status.HTTP_302_FOUND)
        return templates.TemplateResponse("login.html", {"request": request})
    finally:
        db_session.close()

@router.post("/api/token")
async def api_token(form_data: OAuth2PasswordRequestForm = Depends()):
    db_session = get_session()
    try:
        init_db_ops()
        user = await db_ops.verify_user(db_session, form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误"
            )

        access_token = create_access_token(
            data={"sub": user.username},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        return {"access_token": access_token, "token_type": "bearer"}
    finally:
        db_session.close()

@router.get("/api/logs")
async def api_logs(limit: int = 200, user = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    safe_limit = max(1, min(limit, 2000))
    log_path = os.getenv("LOG_FILE_PATH") or os.getenv("LOG_FILE") or "./logs/telegram_forwarder.log"
    log_path = os.path.abspath(log_path)
    try:
        lines = tail_lines(log_path, safe_limit)
        if lines is None:
            return {"lines": ["Waiting for logs to generate..."]}
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="读取日志失败")
    return {"lines": lines}

@router.post("/login")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    response: Response = None
):
    db_session = get_session()
    try:
        init_db_ops()
        user = await db_ops.verify_user(db_session, form_data.username, form_data.password)
        if not user:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "用户名或密码错误"},
                status_code=status.HTTP_401_UNAUTHORIZED
            )
        
        access_token = create_access_token(
            data={"sub": user.username},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        return response
    finally:
        db_session.close()

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    db_session = get_session()
    try:
        # 检查是否已有用户
        users = db_session.query(User).all()
        if users:
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        return templates.TemplateResponse("register.html", {"request": request})
    finally:
        db_session.close()

@router.post("/register")
async def register(request: Request):
    form_data = await request.form()
    username = form_data.get("username")
    password = form_data.get("password")
    confirm_password = form_data.get("confirm_password")
    invite_code = (form_data.get("invite_code") or "").strip()

    from rss.app.core.config_manager import config_manager
    expected_invite = config_manager.get_invite_code()

    db_session = get_session()
    try:
        has_users = db_session.query(User).first() is not None
    finally:
        db_session.close()

    if has_users and (not invite_code or invite_code != expected_invite):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "邀请码错误或未填写"},
            status_code=status.HTTP_403_FORBIDDEN
        )
    
    if password != confirm_password:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "两次输入的密码不一致"},
            status_code=status.HTTP_400_BAD_REQUEST
        )
    
    db_session = get_session()
    try:
        init_db_ops()
        user = await db_ops.create_user(db_session, username, password)
        if not user:
            return templates.TemplateResponse(
                "register.html",
                {"request": request, "error": "创建用户失败"},
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        access_token = create_access_token(
            data={"sub": user.username},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        return response
    finally:
        db_session.close()


class RegisterRequest(BaseModel):
    username: str
    password: str
    confirm_password: str
    invite_code: str = ""


@router.post("/api/register")
async def api_register(payload: RegisterRequest):
    invite_code = (payload.invite_code or "").strip()
    from rss.app.core.config_manager import config_manager
    expected_invite = config_manager.get_invite_code()

    db_session = get_session()
    try:
        has_users = db_session.query(User).first() is not None
    finally:
        db_session.close()

    if has_users and (not invite_code or invite_code != expected_invite):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="邀请码错误")

    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="两次输入的密码不一致")

    db_session = get_session()
    try:
        init_db_ops()
        user = await db_ops.create_user(db_session, payload.username, payload.password)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="创建用户失败")
        return {"success": True}
    finally:
        db_session.close()

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user = Depends(get_current_user)):
    state = build_app_state(bool(user))
    return RedirectResponse(url=state["routing"]["default_route"], status_code=status.HTTP_302_FOUND)


@router.get("/rss_dashboard")
async def rss_dashboard_alias():
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

@router.post("/rss/change_password")
async def change_password(
    request: Request,
    user = Depends(get_current_user),
):
    """修改用户密码"""
    if not user:
        return JSONResponse(
            {"success": False, "message": "未登录或会话已过期"}, 
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        form_data = await request.form()
        current_password = form_data.get("current_password")
        new_password = form_data.get("new_password")
        confirm_password = form_data.get("confirm_password")
        
        # 验证表单数据
        if not current_password:
            return JSONResponse({"success": False, "message": "请输入当前密码"})
        
        if not new_password:
            return JSONResponse({"success": False, "message": "请输入新密码"})
        
        if len(new_password) < 8:
            return JSONResponse({"success": False, "message": "新密码长度必须至少为8个字符"})
        
        if new_password != confirm_password:
            return JSONResponse({"success": False, "message": "新密码和确认密码不一致"})
        
        # 验证当前密码
        db_session = get_session()
        try:
            init_db_ops()
            is_valid = await db_ops.verify_user(db_session, user.username, current_password)
            if not is_valid:
                return JSONResponse({"success": False, "message": "当前密码不正确"})
            
            # 更新密码
            success = await db_ops.update_user_password(db_session, user.username, new_password)
            if not success:
                return JSONResponse({"success": False, "message": "修改密码失败，请重试"})
            
            return JSONResponse({"success": True, "message": "密码修改成功"})
        finally:
            db_session.close()
    except Exception as e:
        return JSONResponse({"success": False, "message": f"修改密码出错: {str(e)}"}) 
