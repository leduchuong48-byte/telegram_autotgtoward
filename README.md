# Telegram AutoTG Toward

![UI Preview](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_dashboard_real.png)

[![Docker Pulls](https://img.shields.io/docker/pulls/leduchuong/telegram_chanel_autotoward?logo=docker&label=Docker%20Pulls&style=flat-square)](https://hub.docker.com/r/leduchuong/telegram_chanel_autotoward)
[![GitHub Stars](https://img.shields.io/github/stars/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/network/members)
[![GitHub Issues](https://img.shields.io/github/issues/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/issues)
[![License](https://img.shields.io/github/license/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/blob/main/LICENSE)
[![Build: Passing](https://img.shields.io/badge/Build-Passing-brightgreen.svg)](#)
[![Platform: ARM64/AMD64](https://img.shields.io/badge/Platform-ARM64%2FAMD64-blue.svg)](#)

[English](README_en.md)

> Better alternative to Fluent Reader for E-ink devices.

Telegram AutoTG Toward 是一个面向自托管场景的 Telegram 转发中控平台，用 WebUI 把规则创建、过滤处理、Bot/Web 联动和可选 RSS 工作流整合到同一套稳定运行链路里。

## Why this tool?（为什么要做它）

很多 Telegram 转发工具能跑，但一旦进入长期运行、复杂过滤、多目标同步和媒体限制场景，就会频繁出现丢消息、误转发、规则难维护的问题。`v3.2` 这次重点补强的就是整套链路的稳定性，让它更适合长期开机、自托管和 NAS 场景持续使用。

## 为什么有用（痛点）

- 老方案经常在长时间运行后出现转发不稳定、规则失效或行为不一致。
- 用户模式下未命中筛选条件的消息仍可能被误转发，难以保证结果可控。
- 传统 Bot-only 管理方式不直观，复杂规则维护成本高，问题定位慢。

## 项目做什么（功能概览）

- 通过 WebUI 创建、编辑、启停和测试 Telegram 转发规则。
- 提供关键词、正则、媒体大小、替换模板、延迟等过滤处理能力。
- 支持 Bot + Web 双通道联动，并可按需启用 RSS 与 AI 处理扩展。
- 面向 NAS、HomeLab 与长期运行环境提供更稳定的发布镜像。

## 当前版本亮点

- `v3.2` 重点完善整个项目的稳定性，建议现有用户升级。
- 修复长时间运行场景中的转发不稳定问题。
- 修复“未命中筛选条件的内容在用户模式仍被转发”的问题，默认改为严格筛选。

## UI 预览

![Dashboard](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_dashboard_real.png)
![New Rule](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_new_rule_forward_real.png)
![Login](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_login_real.png)

## ⚡️ Quick Start (Run in 3 seconds)

```bash
docker run -d --name telegram_autotgtoward --restart unless-stopped -p 1008:8000 --env-file .env -v $(pwd)/db:/app/db -v $(pwd)/sessions:/app/sessions -v $(pwd)/logs:/app/logs -v $(pwd)/config:/app/config -v $(pwd)/rss/data:/app/rss/data -v $(pwd)/rss/media:/app/rss/media leduchuong/telegram_chanel_autotoward:latest
```

## Docker Compose（Portainer / NAS 可直接粘贴）

Copy this into Portainer stacks and hit Deploy. Done.

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
      - ./rss/media:/app/rss/media
```

## GitHub Topics（建议至少 5 个）

`#nas` `#homelab` `#selfhosted` `#synology` `#unraid` `#telegram` `#automation`

## 镜像说明

`leduchuong/telegram_chanel_autotoward` 是 Telegram AutoTG Toward 的官方 Docker Hub 镜像，默认提供 `latest` 和 `3.2` 两个标签，适合希望快速部署稳定版 Telegram 转发系统的自托管用户。

## 配置说明

启动前请准备 `.env`，至少配置 `API_ID`、`API_HASH`、`BOT_TOKEN`、`USER_ID`、`INVITE_CODE` 与 `JWT_SECRET_KEY`。如需启用 RSS、AI 或 UFB 能力，请继续补充相应配置，并持久化 `db/`、`sessions/`、`logs/`、`config/`、`rss/data/` 与 `rss/media/`。

## 如何快速开始（Getting Started）

### 环境要求

- Docker 24+ 或兼容的容器运行环境
- 可访问 Telegram API 的网络环境
- 一份已正确填写的 `.env`

### 安装

```bash
git clone https://github.com/leduchuong48-byte/telegram_autotgtoward.git
cd telegram_autotgtoward
cp .env.example .env
```

### 运行

```bash
docker compose up -d --build
```

## 使用示例

```bash
docker run -d   --name telegram_autotgtoward   --restart unless-stopped   -p 1008:8000   --env-file .env   -v $(pwd)/db:/app/db   -v $(pwd)/sessions:/app/sessions   -v $(pwd)/logs:/app/logs   -v $(pwd)/config:/app/config   -v $(pwd)/rss/data:/app/rss/data   -v $(pwd)/rss/media:/app/rss/media   leduchuong/telegram_chanel_autotoward:3.2
```

## 支持的标签与 Dockerfile

推荐标签为 `latest` 与 `3.2`。`latest` 跟随当前稳定发布，`3.2` 固定到本次稳定性增强版本。构建文件位于仓库根目录的 `Dockerfile`。

## 在哪里获得帮助

- Issues: https://github.com/leduchuong48-byte/telegram_autotgtoward/issues
- Discussions: https://github.com/leduchuong48-byte/telegram_autotgtoward/discussions

## 维护者与贡献者

- Maintainer: [@leduchuong48-byte](https://github.com/leduchuong48-byte)

## 许可证

本项目使用 GPL-3.0，详见 `LICENSE`。

## 免责声明

使用本项目即表示你已阅读并同意 [DISCLAIMER.md](DISCLAIMER.md)。

## UI 界面展示

![UI Screenshot](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_dashboard_real.png)

✅ Perfect for Raspberry Pi & Oracle Cloud Free Tier (ARM)
