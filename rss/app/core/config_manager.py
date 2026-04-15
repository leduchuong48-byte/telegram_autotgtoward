import copy
import json
import logging
import os
import shutil
import threading
import secrets
from datetime import datetime
from pathlib import Path
from typing import Callable


class ConfigManager:
    def __init__(self, config_path: str | None = None):
        self._lock = threading.RLock()
        self._logger = logging.getLogger(__name__)
        self._handlers: list[Callable[[dict], None]] = []
        default_path = os.getenv("CONFIG_FILE_PATH") or "./config/config.json"
        self._config_path = Path(config_path or default_path).resolve()
        self._legacy_path = Path("./config.json").resolve()
        self.settings: dict = {}
        self._ensure_parent_dir()
        self._load_from_disk()

    @property
    def config_path(self) -> Path:
        return self._config_path

    def _ensure_parent_dir(self) -> None:
        parent = self._config_path.parent
        if parent:
            parent.mkdir(parents=True, exist_ok=True)

    def _load_from_disk(self) -> dict:
        should_persist = False
        if not self._config_path.exists():
            if self._legacy_path.exists() and self._legacy_path != self._config_path:
                shutil.copy2(self._legacy_path, self._config_path)
                self._logger.info("Migrated legacy config from %s to %s", self._legacy_path, self._config_path)
            else:
                should_persist = True

        if self._config_path.exists():
            with self._config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        else:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("Config file must contain a JSON object")
        data, defaults_persist = self._apply_defaults(data)
        data, invite_persist = self._ensure_invite_code(data)
        should_persist = should_persist or defaults_persist or invite_persist
        if should_persist:
            with self._config_path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=True)
            if invite_persist:
                self._logger.info("Generated INVITE_CODE: %s", data.get("INVITE_CODE"))
        self.settings = data
        return data

    def get_config(self) -> dict:
        with self._lock:
            return self._load_from_disk()

    def _ensure_invite_code(self, data: dict) -> tuple[dict, bool]:
        invite = (data.get("INVITE_CODE") or "").strip()
        if invite:
            return data, False

        env_invite = (os.getenv("INVITE_CODE") or "").strip()
        if env_invite:
            data["INVITE_CODE"] = env_invite
            return data, True

        data["INVITE_CODE"] = secrets.token_urlsafe(24)
        return data, True

    def _apply_defaults(self, data: dict) -> tuple[dict, bool]:
        defaults = {
            "telegram": {
                "api_id": "",
                "api_hash": "",
                "bot_token": "",
                "phone": "",
                "user_id": "",
            },
            "ai_service": {
                "enabled": False,
                "provider": "openai",
                "api_key": "",
                "model": "gpt-3.5-turbo",
                "base_url": "",
                "key_strategy": "sequence",
            },
        }

        changed = False
        for key, value in defaults.items():
            if key not in data or not isinstance(data.get(key), dict):
                data[key] = copy.deepcopy(value)
                changed = True
                continue
            for sub_key, sub_value in value.items():
                if sub_key not in data[key]:
                    data[key][sub_key] = copy.deepcopy(sub_value)
                    changed = True
        return data, changed

    def get_invite_code(self) -> str:
        with self._lock:
            data = self._load_from_disk()
            return data.get("INVITE_CODE", "")


    def set_invite_code(self, invite_code: str) -> str:
        cleaned = (invite_code or "").strip()
        if not cleaned:
            raise ValueError("Invite code cannot be empty")

        with self._lock:
            config = self._load_from_disk()
            config["INVITE_CODE"] = cleaned
            self._apply_defaults(config)
            self._backup_config()
            with self._config_path.open("w", encoding="utf-8") as handle:
                json.dump(config, handle, indent=2, ensure_ascii=True)
            self.settings = config
            self._logger.info("Invite code updated at %s", self._config_path)
            return cleaned

    def rotate_invite_code(self) -> str:
        new_code = secrets.token_urlsafe(24)
        self.set_invite_code(new_code)
        return new_code

    def _backup_config(self) -> None:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        backup_name = f"{self._config_path.name}.bak.{timestamp}"
        backup_path = self._config_path.with_name(backup_name)
        if not self._config_path.exists():
            with backup_path.open("w", encoding="utf-8") as handle:
                json.dump({}, handle, indent=2, ensure_ascii=True)
            return
        shutil.copy2(self._config_path, backup_path)

    def update_config(self, new_config: dict) -> dict:
        if not isinstance(new_config, dict):
            raise ValueError("Config payload must be a JSON object")
        try:
            json.dumps(new_config)
        except (TypeError, ValueError) as exc:
            raise ValueError("Config payload is not JSON serializable") from exc

        with self._lock:
            self._ensure_parent_dir()
            current = self._load_from_disk()
            if not (new_config.get("INVITE_CODE") or "").strip():
                fallback_invite = (current.get("INVITE_CODE") or "").strip()
                new_config["INVITE_CODE"] = fallback_invite or secrets.token_urlsafe(24)
            new_config, _ = self._apply_defaults(new_config)
            self._backup_config()
            with self._config_path.open("w", encoding="utf-8") as handle:
                json.dump(new_config, handle, indent=2, ensure_ascii=True)
            self.settings = new_config
            self._logger.info("Config updated at %s", self._config_path)
            return self.settings

    def register_reload_handler(self, handler: Callable[[dict], None]) -> None:
        if handler not in self._handlers:
            self._handlers.append(handler)

    def reload_config(self) -> dict:
        with self._lock:
            data = self._load_from_disk()
            for handler in list(self._handlers):
                try:
                    handler(data)
                except Exception as exc:
                    self._logger.warning("Reload handler failed: %s", exc)
            self._logger.info("Config reloaded from %s", self._config_path)
            return data


config_manager = ConfigManager()
