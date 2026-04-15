# Telegram AutoTG Toward

![UI Preview](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_dashboard_real.png)

[![Docker Pulls](https://img.shields.io/docker/pulls/leduchuong/telegram_chanel_autotoward?logo=docker&label=Docker%20Pulls&style=flat-square)](https://hub.docker.com/r/leduchuong/telegram_chanel_autotoward)
[![GitHub Stars](https://img.shields.io/github/stars/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/network/members)
[![GitHub Issues](https://img.shields.io/github/issues/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/issues)
[![License](https://img.shields.io/github/license/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/blob/main/LICENSE)
[![Build: Passing](https://img.shields.io/badge/Build-Passing-brightgreen.svg)](#)
[![Platform: ARM64/AMD64](https://img.shields.io/badge/Platform-ARM64%2FAMD64-blue.svg)](#)

[中文](README.md)

> Better alternative to Fluent Reader for E-ink devices.

Telegram AutoTG Toward is a self-hosted Telegram forwarding control center that combines WebUI rule management, filtering, Bot/Web coordination, and optional RSS workflows into one stable operating stack.

## Why this tool?

Many Telegram forwarding tools work for short demos but become fragile in long-running deployments with complex filters, multi-target routing, and media constraints. Version `3.2` focuses on strengthening the overall stability of the project so it is safer to run continuously on NAS and homelab environments.

## Why This Project Is Useful (Pain Points)

- Older setups often become unstable after running for a long time, causing forwarding drift or broken rules.
- Messages that do not match filters could still be forwarded in user mode, making behavior hard to trust.
- Bot-only administration is not enough for complex operations, and troubleshooting becomes slow.

## What the Project Does (Features)

- Create, edit, enable, disable, and test Telegram forwarding rules from a WebUI.
- Apply keyword, regex, media size, replacement template, and delay-based processing.
- Coordinate Bot and Web operations while keeping optional RSS and AI integrations available.
- Ship a more stable Docker image for self-hosted, NAS, and homelab deployments.

## Current Release Highlights

- `v3.2` improves the overall stability of the entire project and is recommended for upgrade.
- Fixes unstable forwarding behavior in long-running workloads.
- Fixes the issue where messages missing filter conditions could still be forwarded in user mode; strict filtering is now the default.

## UI Preview

![Dashboard](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_dashboard_real.png)
![New Rule](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_new_rule_forward_real.png)
![Login](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_login_real.png)

## ⚡️ Quick Start (Run in 3 seconds)

```bash
docker run -d --name telegram_autotgtoward --restart unless-stopped -p 1008:8000 --env-file .env -v $(pwd)/db:/app/db -v $(pwd)/sessions:/app/sessions -v $(pwd)/logs:/app/logs -v $(pwd)/config:/app/config -v $(pwd)/rss/data:/app/rss/data -v $(pwd)/rss/media:/app/rss/media leduchuong/telegram_chanel_autotoward:latest
```

## Docker Compose (Portainer / NAS ready)

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

## GitHub Topics (pick at least 5)

`#nas` `#homelab` `#selfhosted` `#synology` `#unraid` `#telegram` `#automation`

## Image Overview

`leduchuong/telegram_chanel_autotoward` is the official Docker Hub image for Telegram AutoTG Toward. It ships `latest` and `3.2` tags for self-hosted users who want a quick, stable Telegram forwarding deployment.

## Configuration

Before startup, prepare `.env` and set at least `API_ID`, `API_HASH`, `BOT_TOKEN`, `USER_ID`, `INVITE_CODE`, and `JWT_SECRET_KEY`. If you enable RSS, AI providers, or UFB integration, keep the related configuration mounted and persist `db/`, `sessions/`, `logs/`, `config/`, `rss/data/`, and `rss/media/`.

## Getting Started

### Requirements

- Docker 24+ or another compatible container runtime
- Network access to Telegram APIs
- A correctly prepared `.env` file

### Install

```bash
git clone https://github.com/leduchuong48-byte/telegram_autotgtoward.git
cd telegram_autotgtoward
cp .env.example .env
```

### Run

```bash
docker compose up -d --build
```

## Usage Example

```bash
docker run -d   --name telegram_autotgtoward   --restart unless-stopped   -p 1008:8000   --env-file .env   -v $(pwd)/db:/app/db   -v $(pwd)/sessions:/app/sessions   -v $(pwd)/logs:/app/logs   -v $(pwd)/config:/app/config   -v $(pwd)/rss/data:/app/rss/data   -v $(pwd)/rss/media:/app/rss/media   leduchuong/telegram_chanel_autotoward:3.2
```

## Supported Tags and Dockerfile Links

The recommended tags are `latest` and `3.2`. `latest` tracks the current stable release and `3.2` pins this stability-focused release. The build recipe lives in the repository root `Dockerfile`.

## Where to Get Help

- Issues: https://github.com/leduchuong48-byte/telegram_autotgtoward/issues
- Discussions: https://github.com/leduchuong48-byte/telegram_autotgtoward/discussions

## Maintainers and Contributors

- Maintainer: [@leduchuong48-byte](https://github.com/leduchuong48-byte)

## License

This project is licensed under GPL-3.0. See `LICENSE` for details.

## Disclaimer

By using this project, you agree to the terms in [DISCLAIMER.md](DISCLAIMER.md).

## UI Preview

![UI Screenshot](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_dashboard_real.png)

✅ Perfect for Raspberry Pi & Oracle Cloud Free Tier (ARM)
