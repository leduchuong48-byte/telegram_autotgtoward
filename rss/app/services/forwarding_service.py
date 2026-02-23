import logging
from typing import Any, Dict, List, Tuple, Optional

from telethon import events

from rss.app.core.config_manager import config_manager


class ForwardingService:
    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._handlers: List[Tuple[Any, Any]] = []
        self._rules_by_source: Dict[Any, List[Dict[str, Any]]] = {}

    async def reload_rules(self, client) -> None:
        if client is None:
            self._logger.warning("ForwardingService: client 未就绪，跳过重载")
            return

        self._clear_handlers(client)

        config = config_manager.get_config()
        rules = config.get("forwarding_rules", [])
        if not isinstance(rules, list):
            self._logger.warning("forwarding_rules 不是列表，已忽略")
            self._rules_by_source = {}
            return

        self._rules_by_source = self._build_rule_map(rules)
        if not self._rules_by_source:
            self._logger.info("ForwardingService: 无可用规则")
            return

        for source_id in self._rules_by_source.keys():
            handler = self._make_handler(source_id)
            event_filter = events.NewMessage(chats=source_id)
            client.add_event_handler(handler, event_filter)
            self._handlers.append((handler, event_filter))

        self._logger.info("ForwardingService: 已加载 %s 个来源规则", len(self._rules_by_source))

    def _clear_handlers(self, client) -> None:
        for handler, event_filter in list(self._handlers):
            try:
                client.remove_event_handler(handler, event_filter)
            except Exception as exc:
                self._logger.debug("移除转发监听器失败: %s", exc)
        self._handlers = []

    def _build_rule_map(self, rules: List[dict]) -> Dict[Any, List[Dict[str, Any]]]:
        mapping: Dict[Any, List[Dict[str, Any]]] = {}
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            source_id = self._parse_chat_id(rule.get("source_id"))
            target_id = self._parse_chat_id(rule.get("target_id"))
            enabled = rule.get("enabled", True)
            if not enabled:
                continue
            if source_id is None or target_id is None:
                self._logger.warning("forwarding_rules 缺少 source_id/target_id: %s", rule)
                continue
            mapping.setdefault(source_id, []).append({
                "target_id": target_id
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


forwarding_service = ForwardingService()
