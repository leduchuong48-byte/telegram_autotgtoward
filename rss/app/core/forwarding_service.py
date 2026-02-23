import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from telethon import events
from sqlalchemy.orm import joinedload

from models.models import ForwardRule, get_session


class ForwardingService:
    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._handlers: List[Tuple[Any, Any]] = []
        self._rules_by_source: Dict[Any, List[Dict[str, Any]]] = {}
        self._total_processed: int = 0
        self._last_reload_at: Optional[str] = None

    async def reload_rules(self, client) -> None:
        if client is None:
            self._logger.warning("ForwardingService: client 未就绪，跳过重载")
            return

        self._clear_handlers(client)
        session = get_session()
        try:
            rules = (
                session.query(ForwardRule)
                .options(joinedload(ForwardRule.source_chat), joinedload(ForwardRule.target_chat))
                .filter(ForwardRule.enable_rule.is_(True))
                .all()
            )
            self._rules_by_source = self._build_rule_map(rules)
            if not self._rules_by_source:
                self._logger.info("ForwardingService: 无可用规则")
                self._last_reload_at = self._now_iso()
                return

            for source_id in self._rules_by_source.keys():
                handler = self._make_handler(source_id)
                event_filter = events.NewMessage(chats=source_id)
                client.add_event_handler(handler, event_filter)
                self._handlers.append((handler, event_filter))

            self._last_reload_at = self._now_iso()
            active_rules_count = sum(len(items) for items in self._rules_by_source.values())
            self._logger.info("ForwardingService: 已加载 %s 条规则", active_rules_count)
        except Exception as exc:
            self._logger.error("ForwardingService: 加载规则失败: %s", exc)
            self._rules_by_source = {}
            self._last_reload_at = self._now_iso()
        finally:
            session.close()

    def get_status(self) -> dict:
        active_rules_count = sum(len(items) for items in self._rules_by_source.values())
        return {
            "is_running": len(self._handlers) > 0,
            "active_rules_count": active_rules_count,
            "total_processed": self._total_processed,
            "last_reload": self._last_reload_at or ""
        }

    def _clear_handlers(self, client) -> None:
        for handler, event_filter in list(self._handlers):
            try:
                client.remove_event_handler(handler, event_filter)
            except Exception as exc:
                self._logger.debug("移除转发监听器失败: %s", exc)
        self._handlers = []

    def _build_rule_map(self, rules: List[ForwardRule]) -> Dict[Any, List[Dict[str, Any]]]:
        mapping: Dict[Any, List[Dict[str, Any]]] = {}
        for rule in rules:
            source_chat = getattr(rule, "source_chat", None)
            target_chat = getattr(rule, "target_chat", None)
            if not source_chat or not target_chat:
                self._logger.warning("ForwardingService: 规则 %s 缺少聊天关联", getattr(rule, "id", None))
                continue
            source_id = self._parse_chat_id(getattr(source_chat, "telegram_chat_id", None))
            target_id = self._parse_chat_id(getattr(target_chat, "telegram_chat_id", None))
            if source_id is None or target_id is None:
                self._logger.warning("ForwardingService: 规则 %s 缺少 source/target", getattr(rule, "id", None))
                continue
            mapping.setdefault(source_id, []).append({
                "target_id": target_id,
                "rule_id": getattr(rule, "id", None),
            })
        return mapping

    def _make_handler(self, source_id):
        async def _handler(event):
            await self._handle_new_message(event, source_id)
        return _handler

    async def _handle_new_message(self, event, source_id) -> None:
        targets = self._rules_by_source.get(source_id, [])
        if not targets:
            return

        for rule in targets:
            target_id = rule.get("target_id")
            try:
                await event.client.forward_messages(target_id, event.message)
                self._total_processed += 1
            except Exception as exc:
                self._logger.error("转发失败: source=%s target=%s err=%s", source_id, target_id, exc)

    def _parse_chat_id(self, value) -> Optional[Any]:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            try:
                return int(cleaned)
            except ValueError:
                return cleaned
        return value

    def _now_iso(self) -> str:
        return datetime.utcnow().isoformat() + "Z"


forwarding_service = ForwardingService()
