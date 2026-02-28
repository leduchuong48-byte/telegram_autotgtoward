# Telegram AutoTG Toward

[![Docker Pulls](https://img.shields.io/docker/pulls/leduchuong/telegram_chanel_autotoward?logo=docker&style=flat-square)](https://hub.docker.com/r/leduchuong/telegram_chanel_autotoward)
[![GitHub Stars](https://img.shields.io/github/stars/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/stargazers)
[![License](https://img.shields.io/github/license/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/blob/main/LICENSE)

[English](README_en.md)

Telegram AutoTG Toward 是一个 WebUI 优先的 Telegram 自动化转发与 RSS 运营平台，基于 `Telethon + FastAPI + Jinja2`，用于长期监控、过滤与分发多来源消息。

## 项目归属与维护

- 官方仓库：`https://github.com/leduchuong48-byte/telegram_autotgtoward`
- 官方镜像：`https://hub.docker.com/r/leduchuong/telegram_chanel_autotoward`
- 维护者：`@leduchuong48-byte`
- 本仓库的元数据、说明文档与发布信息均以本项目为准，不继承第三方模板文案。

## 核心能力

- WebUI 管理：登录、配置编辑、日志查看、系统状态监控。
- Setup Wizard：在页面内完成 Telegram 授权，不依赖命令行登录。
- 规则化转发：关键词/正则/媒体过滤、替换模板、延迟处理。
- AI 处理：按配置接入 OpenAI / Gemini / DeepSeek / Qwen / Grok / Claude。
- RSS 子系统：订阅规则、仪表盘、Feed 输出与媒体处理。
- 运行稳定性：支持配置热重载、接口健康检查和状态查询。

## UI 界面展示

> 本项目核心特点：全流程 WebUI 操作 + Bot 侧快捷控制。

### WebUI 登录页

![WebUI 登录页](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/rss_login.png)

### WebUI 仪表盘（规则列表）

![WebUI 仪表盘](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/rss_dashboard.png)

### WebUI 新建配置页

![WebUI 新建配置](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/rss_create_config.png)

### Bot 规则控制面板

![Bot 规则控制](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/settings_main.png)

## 特色功能

- 全流程 WebUI：初始化、配置、状态监控、日志排查一站式完成。
- Bot 快捷操作：可在 Bot 内快速调整转发模式、AI/媒体/推送策略。
- NAS/HomeLab 友好：适配长期运行场景，支持 Docker/Compose 一键部署。

## For Portainer/Synology Users

Copy this into Portainer stacks and hit Deploy. Done.

## Docker Compose

```yaml
services:
  autotgtoward:
    image: leduchuong/telegram_chanel_autotoward:latest
    container_name: telegram_autotgtoward
    restart: unless-stopped
    ports:
      - "1008:8000"
    env_file:
      - .env
    volumes:
      - ./db:/app/db
      - ./sessions:/app/sessions
      - ./logs:/app/logs
      - ./config:/app/config
      - ./rss/data:/app/rss/data
```

## 快速开始

### Docker 运行

```bash
cp .env.example .env
# 编辑 .env，至少填写 API_ID/API_HASH/BOT_TOKEN/USER_ID/INVITE_CODE

docker compose up -d --build
```

访问：`http://localhost:1008`

### 本地运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## 关键目录

- `main.py`：启动入口（Telegram 客户端 + Web 服务）。
- `rss/main.py`：FastAPI 应用与路由挂载。
- `rss/app/routes/`：认证、配置、系统状态、Telegram 授权、Bot 控制 API。
- `filters/`：消息过滤与处理链。
- `handlers/`：Bot 交互与业务编排。
- `models/`：数据库模型与迁移逻辑。

## 常用排查

- 页面可访问但任务不工作：优先检查 `.env` 中 Telegram 参数是否完整。
- 保存配置后未生效：在 WebUI 中执行配置重载，并查看日志页。
- 鉴权失败：检查邀请码、Cookie 与 `JWT_SECRET_KEY` 配置。

## 支持与反馈

- Issues：`https://github.com/leduchuong48-byte/telegram_autotgtoward/issues`

## License

GPL-3.0，详见 [LICENSE](LICENSE)。

## Disclaimer

使用本项目即表示你已阅读并同意 [免责声明](DISCLAIMER.md)。
