# Telegram AutoTG Toward

[![Docker Pulls](https://img.shields.io/docker/pulls/leduchuong/telegram_chanel_autotoward?logo=docker&style=flat-square)](https://hub.docker.com/r/leduchuong/telegram_chanel_autotoward)
[![GitHub Stars](https://img.shields.io/github/stars/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/stargazers)
[![License](https://img.shields.io/github/license/leduchuong48-byte/telegram_autotgtoward?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/blob/main/LICENSE)

[中文](README.md)

Telegram AutoTG Toward is a WebUI-first Telegram forwarding control center focused on fast group-to-group forwarding operations, not just RSS subscription.

## Why This Is Not a Generic RSS Tool

- Instant rule creation from UI: open the "New Rule" modal and set `source link / source_chat_id / target_chat_id` directly.
- Visual forwarding workflow: create, edit, enable/disable, filter, and test rules on one page.
- Cluster-style rule orchestration: multi-rule parallel management with rule sync (`enable_sync`) for multi-group scenarios.
- Bot + Web linkage: send test messages to specific `chat_id` from WebUI while keeping Bot-side quick controls.

## UI Highlights (Real Screenshots)

> Screenshots below are rendered from this repository templates and reflect the real WebUI.

### 1) New rule forwarding window (link/chat_id supported)

![New rule forwarding window](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_new_rule_forward_real.png)

### 2) Bot + Web linkage (send test message to specific chat_id)

![Bot and Web linkage](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_bot_web_linkage_real.png)

### 3) Rule dashboard for cluster-style management

![Rule dashboard](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_dashboard_real.png)

### 4) First-time onboarding (login/register/setup wizard)

![WebUI Login](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_login_real.png)

![WebUI Register](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_register_real.png)

![Setup Wizard](https://raw.githubusercontent.com/leduchuong48-byte/telegram_autotgtoward/main/images/ui_real/ui_setup_wizard_real.png)

## Ownership and Maintenance

- Official repository: `https://github.com/leduchuong48-byte/telegram_autotgtoward`
- Official image: `https://hub.docker.com/r/leduchuong/telegram_chanel_autotoward`
- Maintainer: `@leduchuong48-byte`

## Core Features

- WebUI operations: config editor, rules dashboard, logs, and runtime status.
- Telegram setup wizard: complete auth and session initialization in browser.
- Rule-driven forwarding: keyword/regex/media filters, replacement templates, delayed processing.
- Bot + Web dual channel: linked operations from Bot commands and Web console.
- AI pipeline: optional providers such as OpenAI, Gemini, DeepSeek, Qwen, Grok, and Claude.
- RSS subsystem: optional feed ingestion/output that does not replace forwarding core.

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

- `main.py`: bootstrap (Telegram clients + Web runtime).
- `rss/main.py`: FastAPI app bootstrap and route mounting.
- `rss/app/routes/`: auth, config, system status, Telegram auth, and bot control APIs.
- `filters/`: message filtering pipeline.
- `handlers/`: interaction and command orchestration.
- `models/`: database models and migration logic.

## Troubleshooting

- UI is up but forwarding does nothing: verify Telegram credentials in `.env`.
- Changes saved but not applied: trigger config reload in WebUI and inspect logs.
- Auth issues: verify invite code, cookies, and `JWT_SECRET_KEY`.

## Support

- Issues: `https://github.com/leduchuong48-byte/telegram_autotgtoward/issues`

## License

GPL-3.0. See [LICENSE](LICENSE).

## Disclaimer

By using this project, you acknowledge and agree to the [Disclaimer](DISCLAIMER.md).
