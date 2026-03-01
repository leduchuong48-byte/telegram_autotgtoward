# Telegram AutoTG Toward

[![Docker Pulls](https://img.shields.io/docker/pulls/leduchuong/telegram_chanel_autotoward?logo=docker&style=flat-square)](https://hub.docker.com/r/leduchuong/telegram_chanel_autotoward)
[![GitHub Stars](https://img.shields.io/github/stars/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/stargazers)
[![License](https://img.shields.io/github/license/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/blob/main/LICENSE)

[中文](README.md)

Telegram AutoTG Toward is a WebUI-first Telegram forwarding and RSS operations platform built with `Telethon + FastAPI + Jinja2`, designed for long-running multi-source monitoring and message distribution.

## Ownership and Maintenance

- Official repository: `https://github.com/leduchuong48-byte/telegram_autotgtoward`
- Official image: `https://hub.docker.com/r/leduchuong/telegram_chanel_autotoward`
- Maintainer: `@leduchuong48-byte`
- Project metadata and release notes are maintained for this repository only.

## Core Features

- WebUI management: auth, config editor, logs, and system status.
- Setup Wizard: complete Telegram authorization from the web page.
- Rule-driven forwarding: keyword/regex/media filters, replacement templates, delayed processing.
- AI processing: configurable providers including OpenAI, Gemini, DeepSeek, Qwen, Grok, and Claude.
- RSS subsystem: feed rules, dashboard, feed output, and media handling.
- Runtime stability: config hot reload, health checks, and status APIs.

## UI Preview

> The screenshots below are rendered from the current repository templates and reflect this project's WebUI pages.

### WebUI Login

![WebUI Login](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_login_real.png)

### WebUI Register

![WebUI Register](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_register_real.png)

### Telegram Setup Wizard

![Setup Wizard](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_setup_wizard_real.png)

### RSS Dashboard (Rule Management)

![RSS Dashboard](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_dashboard_real.png)

## Feature Highlights

- Full WebUI workflow for setup, configuration, monitoring, and troubleshooting.
- Bot-side quick operations for forwarding mode, AI/media/push strategies.
- NAS/HomeLab ready deployment with Docker/Compose for long-running use.

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

## Quick Start

### Run with Docker

```bash
cp .env.example .env
# edit .env and set at least API_ID/API_HASH/BOT_TOKEN/USER_ID/INVITE_CODE

docker compose up -d --build
```

Open: `http://localhost:1008`

### Run Locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## Key Paths

- `main.py`: bootstrap (Telegram clients + web runtime).
- `rss/main.py`: FastAPI app bootstrap and route mounting.
- `rss/app/routes/`: auth, config, system, Telegram auth, and bot control APIs.
- `filters/`: message filtering pipeline.
- `handlers/`: command/interaction orchestration.
- `models/`: database models and migration logic.

## Troubleshooting

- UI is up but tasks do nothing: check Telegram credentials in `.env`.
- Config saved but behavior unchanged: trigger config reload in WebUI and inspect logs.
- Auth issues: verify invite code, cookies, and `JWT_SECRET_KEY`.

## Support

- Issues: `https://github.com/leduchuong48-byte/telegram_autotgtoward/issues`

## License

GPL-3.0. See [LICENSE](LICENSE).

## Disclaimer

By using this project, you acknowledge and agree to the [Disclaimer](DISCLAIMER.md).
