# Telegram AutoTG Toward

[![Docker Pulls](https://img.shields.io/docker/pulls/leduchuong/telegram_chanel_autotoward?logo=docker&style=flat-square)](https://hub.docker.com/r/leduchuong/telegram_chanel_autotoward)
[![GitHub Stars](https://img.shields.io/github/stars/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/stargazers)
[![License](https://img.shields.io/github/license/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/blob/main/LICENSE)

[English](README_en.md)

Telegram AutoTG Toward 是一个以 WebUI 为核心的 Telegram 转发中控平台，重点是群组间转发的便捷操作，而不只是 RSS 订阅。

## 版本更新

- `v3.1`：修复转发不稳定问题，提升长时间运行场景下的稳定性。
- `v3.1`：修复“未命中筛选条件的内容在用户模式仍被转发”的问题，默认改为严格筛选。

## 为什么这不是普通 RSS 工具

- 新建规则即开即用：在 WebUI 打开“新建规则”弹窗后，直接填写 `source link / source_chat_id / target_chat_id` 即可落地转发规则。
- 转发操作可视化：规则创建、编辑、启停、过滤和测试全部在同一页面完成，不依赖命令行。
- 集群化规则管理：支持多规则并行和规则同步（`enable_sync`），适合多群组、多目标的集中管理。
- Bot + Web 联动：Web 端可直接下发测试消息到指定 `chat_id`，同时保留 Bot 侧快捷操作能力。

## UI 重点展示（真实页面截图）

> 以下截图由当前仓库模板实时渲染得到，展示的是本项目实际 WebUI。

### 1) 新建规则后可直接操作转发窗口（支持 link/chat_id）

![新建规则转发窗口](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_new_rule_forward_real.png)

### 2) Bot + Web 联动控制（Web 发测试消息到指定 chat_id）

![Bot 与 Web 联动](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_bot_web_linkage_real.png)

### 3) 规则集群管理看板（规则列表、状态、统计）

![规则集群管理看板](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_dashboard_real.png)

### 4) 首次接入流程（登录/注册/向导）

![WebUI 登录页](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_login_real.png)

![WebUI 注册页](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_register_real.png)

![Setup Wizard](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_setup_wizard_real.png)

## 项目归属与维护

- 官方仓库：`https://github.com/leduchuong48-byte/telegram_autotgtoward`
- 官方镜像：`https://hub.docker.com/r/leduchuong/telegram_chanel_autotoward`
- 维护者：`@leduchuong48-byte`

## 核心能力

- WebUI 管理：配置编辑、规则管理、日志查看、系统状态。
- Telegram 授权向导：页面内完成登录与会话初始化。
- 规则化转发：关键词/正则/媒体过滤、替换模板、延迟处理。
- Bot/Web 双通道：Bot 命令与 Web 控制台联动管理。
- AI 处理：可接入 OpenAI / Gemini / DeepSeek / Qwen / Grok / Claude。
- RSS 子系统：作为可选能力用于订阅与分发，不影响核心转发流程。

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
