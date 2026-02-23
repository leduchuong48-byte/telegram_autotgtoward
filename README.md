# Telegram AutoTG Toward

[English](README_en.md)

Telegram AutoTG Toward 是一个以 **WebUI 为核心** 的 Telegram 自动化转发与 RSS 聚合系统，基于 `Telethon + FastAPI + Jinja2` 构建，支持可视化配置、Setup Wizard 登录、规则编排、实时日志与系统状态监控。

## 为什么有用（痛点）

多频道/群组长期监控时，常见问题是规则分散在命令与脚本里、配置变更不透明、运行状态不可观测、接手维护成本高。这个项目把消息监听、过滤改写、分发推送、RSS 管理与运维入口集中到一个 Web 面板中，把原本碎片化操作变成可持续的工作流。

## 项目做什么（功能概览）

- **可视化 WebUI**：登录页、仪表盘、配置编辑器、日志页、系统状态页
- **Setup Wizard**：Web 端引导完成 Telegram 登录授权
- **规则化转发**：多源消息转发、关键词/正则/媒体过滤、替换与延迟处理
- **AI 处理能力**：支持 OpenAI / Gemini / DeepSeek / Qwen / Grok / Claude（按配置启用）
- **RSS 子系统**：RSS 规则管理、订阅处理、媒体与标题模板配置
- **运行可观测性**：`/api/system/status`、`/api/logs`、转发状态接口与健康检查

## 架构概览

- `main.py`：启动入口，同时拉起 Telegram 客户端与 FastAPI 服务
- `rss/main.py`：Web 应用与静态资源挂载（`/static`、`/sw.js`）
- `rss/app/routes/*`：认证、配置、系统状态、Telegram 授权、Bot 控制等 API
- `filters/`：过滤链与消息处理策略
- `handlers/`：Bot 命令、按钮交互与业务编排
- `models/`：数据库模型与数据访问逻辑

## 如何快速开始（Getting Started）

### 环境要求

- Docker 与 Docker Compose（推荐）
- 或 Python 3.11+
- Telegram 凭据：`API_ID`、`API_HASH`、`BOT_TOKEN`、`USER_ID`

### Docker 启动

```bash
cp .env.example .env
# 编辑 .env，填写必要参数

docker compose up -d --build
```

默认访问：`http://localhost:1008`

### 本地运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

### 首次进入 WebUI

1. 打开 `http://localhost:1008`
2. 按页面提示完成 Setup Wizard
3. 在配置页补全 Telegram 与 AI 相关参数
4. 保存后执行配置重载（页面内操作）

## 关键配置说明

- `.env`：运行时环境变量（生产建议只在服务器保留）
- `config.sample.json`：配置结构示例（初始化参考）
- `db/`：数据库目录（运行时生成）
- `sessions/`：Telegram 会话目录（运行时生成）
- `logs/`：日志目录（运行时生成）

## 常见问题（FAQ）

- 页面可打开但功能不可用：优先检查 `.env` 是否已填必要 Telegram 参数。
- WebUI 登录失败：检查邀请码/用户初始化流程，以及浏览器 Cookie 是否被禁用。
- 配置已保存但行为未更新：执行配置重载，并检查日志是否出现 reload 错误。
- 无法处理历史消息：确认 Telethon 会话有效并已完成用户授权。

## 在哪里获得帮助

- Issue：`https://github.com/leduchuong48-byte/telegram_autotgtoward/issues`
- 建议附带：复现步骤、脱敏日志、关键配置截图

## 维护者与贡献者

- Maintainer: `@leduchuong48-byte`

## 免责声明

使用本项目即表示你已阅读并同意 [免责声明](DISCLAIMER.md)。
