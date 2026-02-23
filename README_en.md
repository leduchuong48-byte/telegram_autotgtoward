# Telegram AutoTG Toward

[中文](README.md)

Telegram AutoTG Toward is a `Telethon + FastAPI` automation project for Telegram forwarding and RSS aggregation, with rule-based filtering, AI-assisted processing, multi-channel pushing, and a web management panel.

## Why This Project Is Useful (Pain Points)

When monitoring many channels/groups, manual triage and forwarding is inefficient and error-prone. Message formats are inconsistent, making cleanup costly. Long-running operations also become fragmented across multiple tools. This project unifies listening, filtering, rewriting, forwarding, RSS management, and operations into one maintainable workflow.

## What the Project Does (Features)

- Multi-source forwarding to target chats
- Rule engine: keyword, regex, and media filters
- Content transformation with replacement and AI processing
- External push delivery via Apprise
- RSS subsystem with web dashboard and config APIs
- Deployment via Docker or local Python runtime

## Getting Started

### Prerequisites

- Docker and Docker Compose (recommended)
- Or Python 3.11+
- Telegram credentials (`API_ID`, `API_HASH`, `BOT_TOKEN`, `USER_ID`)

### Run with Docker

```bash
cp .env.example .env
# edit .env with required values

docker compose up -d --build
```

Open: `http://localhost:1008`

### Run Locally

```bash
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## Where to Get Help

- Issues: `https://github.com/leduchuong48-byte/telegram_autotgtoward/issues`
- Include reproduction steps and sanitized logs when reporting problems

## Maintainers and Contributors

- Maintainer: `@leduchuong48-byte`

## Disclaimer

By using this project, you acknowledge and agree to the [Disclaimer](DISCLAIMER.md).
