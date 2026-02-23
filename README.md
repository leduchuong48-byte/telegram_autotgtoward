# Telegram AutoTG Toward

[English](README_en.md)

Telegram AutoTG Toward 是一个基于 `Telethon + FastAPI` 的 Telegram 自动转发与 RSS 聚合工具，支持多源消息转发、过滤规则、AI 处理、推送分发和 Web 管理面板。

## 为什么有用（痛点）

在多频道/群组场景中，手工筛选和二次分发消息非常耗时，且容易漏掉关键内容；不同来源内容格式不一致，人工清洗成本高；长期运行时，消息追踪、推送和订阅管理也容易碎片化。该项目把监听、过滤、改写、转发、RSS 订阅与运维入口整合在一个流程里，降低了持续维护成本。

## 项目做什么（功能概览）

- 多源转发：支持一个目标绑定多个来源聊天
- 过滤处理：关键词、正则、媒体类型/大小/时长过滤
- 内容改写：支持替换规则与 AI 文本处理
- 推送分发：通过 Apprise 推送到外部渠道
- RSS 子系统：Web 面板管理 RSS、配置与系统状态
- 运行方式：Docker 一键运行或本地 Python 启动

## 如何快速开始（Getting Started）

### 环境要求

- Docker 与 Docker Compose（推荐）
- 或 Python 3.11+
- Telegram API 凭据（`API_ID`、`API_HASH`、`BOT_TOKEN`、`USER_ID`）

### Docker 启动

```bash
cp .env.example .env
# 编辑 .env，填写必要参数

docker compose up -d --build
```

访问：`http://localhost:1008`

### 本地运行

```bash
pip install -r requirements.txt
cp .env.example .env
python main.py
```

### 目录说明

- `filters/`：消息过滤与处理链
- `handlers/`：命令和按钮交互处理
- `rss/`：RSS 子系统与 Web 管理端
- `db/`、`logs/`、`sessions/`：运行期数据目录（已默认忽略）

## 在哪里获得帮助

- Issue：`https://github.com/leduchuong48-byte/telegram_autotgtoward/issues`
- 建议附带：复现步骤、日志片段、配置截图（请打码敏感字段）

## 维护者与贡献者

- Maintainer: `@leduchuong48-byte`

## 免责声明

使用本项目即表示你已阅读并同意 [免责声明](DISCLAIMER.md)。
