# Telegram AutoTG Toward

[中文](README.md)

Telegram AutoTG Toward is a **WebUI-first** Telegram automation platform built with `Telethon + FastAPI + Jinja2`, providing visual configuration, setup wizard login, rule-driven forwarding, live logs, and RSS operations in one place.

## Why This Project Is Useful (Pain Points)

In long-running multi-channel operations, rules often become scattered across commands and scripts, changes are hard to track, and runtime visibility is limited. This project consolidates listening, filtering, rewriting, forwarding, RSS management, and operations into a single maintainable workflow.

## What the Project Does (Features)

- **WebUI**: login page, dashboard, config editor, logs, and system status
- **Setup Wizard**: guided Telegram authorization from the web interface
- **Rule-driven forwarding**: keyword/regex/media filters, replacement, delay, and routing
- **AI integration**: OpenAI / Gemini / DeepSeek / Qwen / Grok / Claude (config-based)
- **RSS subsystem**: feed handling, rule management, and media/title templates
- **Observability**: health/status APIs and runtime log endpoints

## Architecture Overview

- `main.py`: starts Telegram clients and FastAPI runtime
- `rss/main.py`: web app bootstrap and static mounts
- `rss/app/routes/*`: auth, config, system, Telegram auth, and bot control APIs
- `filters/`: message processing and filter chain
- `handlers/`: command and interaction orchestration
- `models/`: persistence and data access

## Getting Started

### Prerequisites

- Docker and Docker Compose (recommended)
- Or Python 3.11+
- Telegram credentials: `API_ID`, `API_HASH`, `BOT_TOKEN`, `USER_ID`

### Run with Docker

```bash
cp .env.example .env
# fill required fields in .env

docker compose up -d --build
```

Default URL: `http://localhost:1008`

### Run Locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## Where to Get Help

- Issues: `https://github.com/leduchuong48-byte/telegram_autotgtoward/issues`
- Please include sanitized logs and reproducible steps

## Maintainers and Contributors

- Maintainer: `@leduchuong48-byte`

## Disclaimer

By using this project, you acknowledge and agree to the [Disclaimer](DISCLAIMER.md).
