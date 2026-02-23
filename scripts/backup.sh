#!/usr/bin/env bash
set -euo pipefail

backup_dir="./backups"
mkdir -p "${backup_dir}"

timestamp="$(date +%Y%m%d)"
archive="${backup_dir}/backup_${timestamp}.tar.gz"

items=()

if [ -f "config.json" ]; then
  items+=("config.json")
else
  echo "warn: config.json not found"
fi

if [ -d "sessions" ]; then
  items+=("sessions")
else
  echo "warn: sessions/ not found"
fi

if [ -f ".env" ]; then
  items+=(".env")
else
  echo "warn: .env not found"
fi

if [ -f "telegram_forwarder.log" ]; then
  items+=("telegram_forwarder.log")
elif [ -f "logs/telegram_forwarder.log" ]; then
  items+=("logs/telegram_forwarder.log")
else
  echo "warn: telegram_forwarder.log not found"
fi

if [ "${#items[@]}" -eq 0 ]; then
  echo "no backup items found"
  tar -czf "${archive}" --files-from /dev/null
else
  tar -czf "${archive}" "${items[@]}"
fi

echo "backup created: ${archive}"
