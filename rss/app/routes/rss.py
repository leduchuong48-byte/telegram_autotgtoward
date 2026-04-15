from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from models.models import (
    get_session,
    User,
    RSSConfig,
    ForwardRule,
    RSSPattern,
    Keyword,
    MediaTypes,
    MediaExtensions,
    RuleSync,
    Chat,
    ReplaceRule,
    PushConfig,
    ProcessedMessage,
)
from models.db_operations import DBOperations
from typing import Optional, List
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from .auth import get_current_user
from feedgen.feed import FeedGenerator
from datetime import datetime
import logging
import base64
import re
from enum import Enum
from utils.common import get_db_ops, get_user_client, get_bot_client, get_user_id
import os
import aiohttp
import pytz
from utils.constants import RSS_HOST, RSS_PORT, RSS_BASE_URL
from utils.settings import load_ai_models, load_summary_times, load_delay_times
from utils.chat_id import normalize_chat_peer_key, build_chat_id_aliases
from rss.app.core.app_state import build_app_state
from managers.backfill_manager import (
    BackfillParams,
    start_backfill_task,
    start_video_forward_task,
    get_backfill_status,
    stop_backfill_task_by_rule,
    _get_env_bool,
    _get_env_float,
    _get_env_int,
)
from enums.enums import ForwardMode, AddMode, CompareMode, HandleMode, MessageMode, PreviewMode

# 配置日志
logger = logging.getLogger(__name__)

def _enum_value(value, default=None):
    if value is None:
        return default
    if isinstance(value, Enum):
        return value.value
    return value


def _parse_forward_mode(value, fallback: ForwardMode) -> ForwardMode:
    if isinstance(value, ForwardMode):
        return value
    if isinstance(value, str):
        for mode in ForwardMode:
            if mode.value == value:
                return mode
    return fallback


def _parse_add_mode(value, fallback: AddMode) -> AddMode:
    if isinstance(value, AddMode):
        return value
    if isinstance(value, str):
        for mode in AddMode:
            if mode.value == value:
                return mode
    return fallback


def _parse_compare_mode(value, fallback: CompareMode) -> CompareMode:
    if isinstance(value, CompareMode):
        return value
    if isinstance(value, str):
        for mode in CompareMode:
            if mode.value == value:
                return mode
    return fallback


def _normalize_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = re.split(r"[\n,]+", value)
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = list(value)

    seen = set()
    items = []
    for item in raw_items:
        if item is None:
            continue
        text = str(item).strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def _parse_handle_mode(value, fallback: HandleMode) -> HandleMode:
    if isinstance(value, HandleMode):
        return value
    if isinstance(value, str):
        for mode in HandleMode:
            if mode.value == value or mode.name == value:
                return mode
    return fallback


def _parse_message_mode(value, fallback: MessageMode) -> MessageMode:
    if isinstance(value, MessageMode):
        return value
    if isinstance(value, str):
        for mode in MessageMode:
            if mode.value == value or mode.name == value:
                return mode
    return fallback


def _parse_preview_mode(value, fallback: PreviewMode) -> PreviewMode:
    if isinstance(value, PreviewMode):
        return value
    if isinstance(value, str):
        for mode in PreviewMode:
            if mode.value == value or mode.name == value:
                return mode
    return fallback


def _parse_datetime(text: str, timezone) -> datetime:
    formats = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=0, minute=0, second=0)
            return timezone.localize(dt)
        except ValueError:
            continue
    raise ValueError("时间格式错误，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM[:SS]")


def _serialize_rule_filters(rule: ForwardRule) -> dict:
    keywords = rule.keywords or []
    blacklist = [k.keyword for k in keywords if k.is_blacklist and not k.is_regex]
    blacklist_regex = [k.keyword for k in keywords if k.is_blacklist and k.is_regex]
    whitelist = [k.keyword for k in keywords if not k.is_blacklist and not k.is_regex]
    whitelist_regex = [k.keyword for k in keywords if not k.is_blacklist and k.is_regex]

    media_types = rule.media_types
    media_types_data = {
        "photo": bool(getattr(media_types, "photo", False)),
        "document": bool(getattr(media_types, "document", False)),
        "video": bool(getattr(media_types, "video", False)),
        "audio": bool(getattr(media_types, "audio", False)),
        "voice": bool(getattr(media_types, "voice", False)),
        "text": bool(getattr(media_types, "text", False))
    }

    media_extensions = [item.extension for item in (rule.media_extensions or [])]

    return {
        "forward_mode": _enum_value(rule.forward_mode, ForwardMode.BLACKLIST.value),
        "enable_reverse_blacklist": bool(rule.enable_reverse_blacklist),
        "enable_reverse_whitelist": bool(rule.enable_reverse_whitelist),
        "keyword_blacklist": blacklist,
        "keyword_blacklist_regex": blacklist_regex,
        "keyword_whitelist": whitelist,
        "keyword_whitelist_regex": whitelist_regex,
        "enable_media_type_filter": bool(rule.enable_media_type_filter),
        "media_type_filter_mode": _enum_value(rule.media_type_filter_mode, AddMode.BLACKLIST.value),
        "media_types": media_types_data,
        "enable_media_size_filter": bool(rule.enable_media_size_filter),
        "max_media_size": rule.max_media_size,
        "media_size_filter_mode": _enum_value(rule.media_size_filter_mode, CompareMode.LESS.value),
        "is_send_over_media_size_message": bool(rule.is_send_over_media_size_message),
        "enable_media_duration_filter": bool(rule.enable_media_duration_filter),
        "media_duration_minutes": rule.media_duration_minutes,
        "media_duration_filter_mode": _enum_value(rule.media_duration_filter_mode, CompareMode.LESS.value),
        "enable_extension_filter": bool(rule.enable_extension_filter),
        "extension_filter_mode": _enum_value(rule.extension_filter_mode, AddMode.BLACKLIST.value),
        "media_extensions": media_extensions,
        "media_allow_text": bool(rule.media_allow_text)
    }


def _apply_rule_filters_to_rule(target_rule: ForwardRule, db_session, payload: dict) -> None:
    forward_mode = _parse_forward_mode(payload.get("forward_mode"), target_rule.forward_mode)
    media_type_mode = _parse_add_mode(payload.get("media_type_filter_mode"), target_rule.media_type_filter_mode)
    extension_mode = _parse_add_mode(payload.get("extension_filter_mode"), target_rule.extension_filter_mode)
    media_size_mode = _parse_compare_mode(payload.get("media_size_filter_mode"), target_rule.media_size_filter_mode)
    media_duration_mode = _parse_compare_mode(payload.get("media_duration_filter_mode"), target_rule.media_duration_filter_mode)

    keyword_blacklist = _normalize_list(payload.get("keyword_blacklist", []))
    keyword_blacklist_regex = _normalize_list(payload.get("keyword_blacklist_regex", []))
    keyword_whitelist = _normalize_list(payload.get("keyword_whitelist", []))
    keyword_whitelist_regex = _normalize_list(payload.get("keyword_whitelist_regex", []))
    update_keywords = any(
        key in payload for key in [
            "keyword_blacklist", "keyword_blacklist_regex",
            "keyword_whitelist", "keyword_whitelist_regex"
        ]
    )

    media_types_payload = payload.get("media_types")
    update_media_types = isinstance(media_types_payload, dict)
    media_types_data = {
        "photo": bool(media_types_payload.get("photo")) if update_media_types else False,
        "document": bool(media_types_payload.get("document")) if update_media_types else False,
        "video": bool(media_types_payload.get("video")) if update_media_types else False,
        "audio": bool(media_types_payload.get("audio")) if update_media_types else False,
        "voice": bool(media_types_payload.get("voice")) if update_media_types else False,
        "text": bool(media_types_payload.get("text")) if update_media_types else False
    }

    media_extensions = _normalize_list(payload.get("media_extensions", []))
    media_extensions = [ext.lstrip('.').lower() for ext in media_extensions if ext]
    update_media_extensions = "media_extensions" in payload

    target_rule.forward_mode = forward_mode
    if "enable_reverse_blacklist" in payload:
        target_rule.enable_reverse_blacklist = bool(payload.get("enable_reverse_blacklist"))
    if "enable_reverse_whitelist" in payload:
        target_rule.enable_reverse_whitelist = bool(payload.get("enable_reverse_whitelist"))
    if "add_mode" in payload:
        target_rule.add_mode = _parse_add_mode(payload.get("add_mode"), target_rule.add_mode)
    if "is_filter_user_info" in payload:
        target_rule.is_filter_user_info = bool(payload.get("is_filter_user_info"))

    if "enable_media_type_filter" in payload:
        target_rule.enable_media_type_filter = bool(payload.get("enable_media_type_filter"))
    target_rule.media_type_filter_mode = media_type_mode

    if "enable_media_size_filter" in payload:
        target_rule.enable_media_size_filter = bool(payload.get("enable_media_size_filter"))
    if "max_media_size" in payload:
        target_rule.max_media_size = int(payload.get("max_media_size") or 0)
    target_rule.media_size_filter_mode = media_size_mode
    if "is_send_over_media_size_message" in payload:
        target_rule.is_send_over_media_size_message = bool(payload.get("is_send_over_media_size_message"))

    if "enable_media_duration_filter" in payload:
        target_rule.enable_media_duration_filter = bool(payload.get("enable_media_duration_filter"))
    if "media_duration_minutes" in payload:
        target_rule.media_duration_minutes = int(payload.get("media_duration_minutes") or 0)
    target_rule.media_duration_filter_mode = media_duration_mode

    if "enable_extension_filter" in payload:
        target_rule.enable_extension_filter = bool(payload.get("enable_extension_filter"))
    target_rule.extension_filter_mode = extension_mode
    if "media_allow_text" in payload:
        target_rule.media_allow_text = bool(payload.get("media_allow_text"))

    if update_media_types:
        media_types = db_session.query(MediaTypes).filter_by(rule_id=target_rule.id).first()
        if not media_types:
            media_types = MediaTypes(rule_id=target_rule.id)
            db_session.add(media_types)
        for field, value in media_types_data.items():
            setattr(media_types, field, value)

    if update_media_extensions:
        db_session.query(MediaExtensions).filter(MediaExtensions.rule_id == target_rule.id).delete()
        for ext in media_extensions:
            if not ext:
                continue
            db_session.add(MediaExtensions(rule_id=target_rule.id, extension=ext))

    if update_keywords:
        db_session.query(Keyword).filter(Keyword.rule_id == target_rule.id).delete()
        for keyword in keyword_blacklist:
            db_session.add(Keyword(
                rule_id=target_rule.id,
                keyword=keyword,
                is_regex=False,
                is_blacklist=True
            ))
        for keyword in keyword_blacklist_regex:
            db_session.add(Keyword(
                rule_id=target_rule.id,
                keyword=keyword,
                is_regex=True,
                is_blacklist=True
            ))
        for keyword in keyword_whitelist:
            db_session.add(Keyword(
                rule_id=target_rule.id,
                keyword=keyword,
                is_regex=False,
                is_blacklist=False
            ))
        for keyword in keyword_whitelist_regex:
            db_session.add(Keyword(
                rule_id=target_rule.id,
                keyword=keyword,
                is_regex=True,
                is_blacklist=False
            ))


async def _apply_rule_filters(rule_id: int, payload: dict) -> tuple[bool, str, int]:
    db_session = get_session()
    try:
        db_ops_instance = await init_db_ops()

        rule = db_session.query(ForwardRule).filter(ForwardRule.id == rule_id).first()
        if not rule:
            return False, "规则不存在", status.HTTP_404_NOT_FOUND

        updated_rule_ids = []
        _apply_rule_filters_to_rule(rule, db_session, payload)
        updated_rule_ids.append(rule.id)

        if rule.enable_sync:
            sync_rules = db_session.query(RuleSync).filter(RuleSync.rule_id == rule.id).all()
            for sync_rule in sync_rules:
                target_rule = db_session.query(ForwardRule).get(sync_rule.sync_rule_id)
                if not target_rule:
                    continue
                _apply_rule_filters_to_rule(target_rule, db_session, payload)
                updated_rule_ids.append(target_rule.id)

        db_session.commit()

        if db_ops_instance:
            for updated_id in updated_rule_ids:
                await db_ops_instance.sync_to_server(db_session, updated_id)

        return True, "筛选设置已更新", status.HTTP_200_OK
    except Exception as e:
        db_session.rollback()
        logger.error(f"更新筛选设置失败: {str(e)}")
        return False, f"更新筛选设置失败: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR
    finally:
        db_session.close()


def _serialize_rule_detail(rule: ForwardRule, db_session) -> dict:
    filters = _serialize_rule_filters(rule)
    keywords = {
        "forward_mode": filters.get("forward_mode"),
        "add_mode": _enum_value(rule.add_mode, AddMode.BLACKLIST.value),
        "enable_reverse_blacklist": filters.get("enable_reverse_blacklist"),
        "enable_reverse_whitelist": filters.get("enable_reverse_whitelist"),
        "is_filter_user_info": bool(rule.is_filter_user_info),
        "blacklist": filters.get("keyword_blacklist", []),
        "blacklist_regex": filters.get("keyword_blacklist_regex", []),
        "whitelist": filters.get("keyword_whitelist", []),
        "whitelist_regex": filters.get("keyword_whitelist_regex", []),
        "is_replace": bool(rule.is_replace),
    }
    media_filters = {
        "enable_media_type_filter": filters.get("enable_media_type_filter"),
        "media_type_filter_mode": filters.get("media_type_filter_mode"),
        "media_types": filters.get("media_types", {}),
        "enable_media_size_filter": filters.get("enable_media_size_filter"),
        "max_media_size": filters.get("max_media_size"),
        "media_size_filter_mode": filters.get("media_size_filter_mode"),
        "is_send_over_media_size_message": filters.get("is_send_over_media_size_message"),
        "enable_media_duration_filter": filters.get("enable_media_duration_filter"),
        "media_duration_minutes": filters.get("media_duration_minutes"),
        "media_duration_filter_mode": filters.get("media_duration_filter_mode"),
        "enable_extension_filter": filters.get("enable_extension_filter"),
        "extension_filter_mode": filters.get("extension_filter_mode"),
        "media_extensions": filters.get("media_extensions", []),
        "media_allow_text": filters.get("media_allow_text"),
    }
    replace_rules = db_session.query(ReplaceRule).filter(ReplaceRule.rule_id == rule.id).all()
    replace_rules_data = [
        {
            "id": item.id,
            "pattern": item.pattern,
            "content": item.content or "",
        }
        for item in replace_rules
    ]
    push_configs = db_session.query(PushConfig).filter(PushConfig.rule_id == rule.id).all()
    push_configs_data = [
        {
            "id": item.id,
            "push_channel": item.push_channel,
            "enable_push_channel": bool(item.enable_push_channel),
            "media_send_mode": item.media_send_mode,
        }
        for item in push_configs
    ]

    basic = {
        "enable_rule": bool(rule.enable_rule),
        "use_bot": bool(rule.use_bot),
        "handle_mode": _enum_value(rule.handle_mode, HandleMode.FORWARD.value),
        "message_mode": _enum_value(rule.message_mode, MessageMode.MARKDOWN.value),
        "is_preview": _enum_value(rule.is_preview, PreviewMode.FOLLOW.value),
        "only_rss": bool(rule.only_rss),
        "enable_push": bool(rule.enable_push),
        "enable_only_push": bool(rule.enable_only_push),
        "enable_sync": bool(rule.enable_sync),
        "source_chat_id": rule.source_chat.telegram_chat_id if rule.source_chat else "",
        "target_chat_id": rule.target_chat.telegram_chat_id if rule.target_chat else "",
        "source_chat_name": rule.source_chat.name if rule.source_chat else "",
        "target_chat_name": rule.target_chat.name if rule.target_chat else "",
    }

    style = {
        "is_original_sender": bool(rule.is_original_sender),
        "is_original_time": bool(rule.is_original_time),
        "is_original_link": bool(rule.is_original_link),
        "userinfo_template": rule.userinfo_template or "",
        "time_template": rule.time_template or "",
        "original_link_template": rule.original_link_template or "",
        "enable_comment_button": bool(rule.enable_comment_button),
        "is_delete_original": bool(rule.is_delete_original),
    }

    ai = {
        "is_ai": bool(rule.is_ai),
        "ai_model": rule.ai_model or "",
        "ai_prompt": rule.ai_prompt or "",
        "enable_ai_upload_image": bool(rule.enable_ai_upload_image),
        "is_keyword_after_ai": bool(rule.is_keyword_after_ai),
        "is_summary": bool(rule.is_summary),
        "summary_time": rule.summary_time or "",
        "summary_prompt": rule.summary_prompt or "",
        "is_top_summary": bool(rule.is_top_summary),
    }

    advanced = {
        "is_ufb": bool(rule.is_ufb),
        "ufb_domain": rule.ufb_domain or "",
        "ufb_item": rule.ufb_item or "",
        "enable_delay": bool(rule.enable_delay),
        "delay_seconds": rule.delay_seconds,
    }

    return {
        "rule_id": rule.id,
        "basic": basic,
        "keywords": keywords,
        "media_filters": media_filters,
        "replace_rules": replace_rules_data,
        "push_configs": push_configs_data,
        "ai": ai,
        "style": style,
        "advanced": advanced,
    }


def _parse_bool(value, fallback=None):
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return fallback
        return cleaned.lower() in ("1", "true", "yes", "on")
    return bool(value)


def _get_or_create_chat(db_session, telegram_chat_id: str) -> Chat:
    canonical_id = normalize_chat_peer_key(telegram_chat_id)
    aliases = build_chat_id_aliases(canonical_id)
    candidates = list(aliases) if aliases else [str(telegram_chat_id).strip()]

    chats = db_session.query(Chat).filter(Chat.telegram_chat_id.in_(candidates)).all()
    if chats:
        preferred = None
        for item in chats:
            if item.telegram_chat_id == canonical_id:
                preferred = item
                break
        if preferred is None:
            preferred = chats[0]

        for item in chats:
            if item.id == preferred.id:
                continue
            db_session.query(ForwardRule).filter(ForwardRule.source_chat_id == item.id).update(
                {ForwardRule.source_chat_id: preferred.id},
                synchronize_session=False,
            )
            db_session.query(ForwardRule).filter(ForwardRule.target_chat_id == item.id).update(
                {ForwardRule.target_chat_id: preferred.id},
                synchronize_session=False,
            )
            if not preferred.name and item.name:
                preferred.name = item.name
            if not preferred.current_add_id and item.current_add_id:
                preferred.current_add_id = normalize_chat_peer_key(item.current_add_id) or item.current_add_id
            db_session.delete(item)

        if canonical_id and preferred.telegram_chat_id != canonical_id:
            preferred.telegram_chat_id = canonical_id
        return preferred

    chat = Chat(telegram_chat_id=canonical_id or str(telegram_chat_id).strip(), name=None)
    db_session.add(chat)
    db_session.flush()
    return chat


async def _apply_rule_settings(rule_id: int, payload: dict) -> tuple[bool, str, int]:
    db_session = get_session()
    try:
        db_ops_instance = await init_db_ops()

        rule = db_session.query(ForwardRule).filter(ForwardRule.id == rule_id).first()
        if not rule:
            return False, "规则不存在", status.HTTP_404_NOT_FOUND

        sync_enabled = bool(rule.enable_sync)
        basic = payload.get("basic", {}) if isinstance(payload.get("basic"), dict) else {}
        keywords = payload.get("keywords", {}) if isinstance(payload.get("keywords"), dict) else {}
        media_filters = payload.get("media_filters", {}) if isinstance(payload.get("media_filters"), dict) else {}
        ai = payload.get("ai", {}) if isinstance(payload.get("ai"), dict) else {}
        style = payload.get("style", {}) if isinstance(payload.get("style"), dict) else {}
        advanced = payload.get("advanced", {}) if isinstance(payload.get("advanced"), dict) else {}
        replace_rules = payload.get("replace_rules") if isinstance(payload.get("replace_rules"), list) else None
        push_configs = payload.get("push_configs") if isinstance(payload.get("push_configs"), list) else None

        filter_payload = {}
        if keywords:
            filter_payload.update({
                "forward_mode": keywords.get("forward_mode"),
                "add_mode": keywords.get("add_mode"),
                "enable_reverse_blacklist": keywords.get("enable_reverse_blacklist"),
                "enable_reverse_whitelist": keywords.get("enable_reverse_whitelist"),
                "is_filter_user_info": keywords.get("is_filter_user_info"),
                "keyword_blacklist": keywords.get("blacklist", []),
                "keyword_blacklist_regex": keywords.get("blacklist_regex", []),
                "keyword_whitelist": keywords.get("whitelist", []),
                "keyword_whitelist_regex": keywords.get("whitelist_regex", []),
            })
            if "is_replace" in keywords:
                rule.is_replace = _parse_bool(keywords.get("is_replace"), rule.is_replace)
        if media_filters:
            filter_payload.update({
                "enable_media_type_filter": media_filters.get("enable_media_type_filter"),
                "media_type_filter_mode": media_filters.get("media_type_filter_mode"),
                "media_types": media_filters.get("media_types", {}),
                "enable_media_size_filter": media_filters.get("enable_media_size_filter"),
                "max_media_size": media_filters.get("max_media_size"),
                "media_size_filter_mode": media_filters.get("media_size_filter_mode"),
                "is_send_over_media_size_message": media_filters.get("is_send_over_media_size_message"),
                "enable_media_duration_filter": media_filters.get("enable_media_duration_filter"),
                "media_duration_minutes": media_filters.get("media_duration_minutes"),
                "media_duration_filter_mode": media_filters.get("media_duration_filter_mode"),
                "enable_extension_filter": media_filters.get("enable_extension_filter"),
                "extension_filter_mode": media_filters.get("extension_filter_mode"),
                "media_extensions": media_filters.get("media_extensions", []),
                "media_allow_text": media_filters.get("media_allow_text"),
            })

        if not filter_payload:
            for key in [
                "forward_mode", "add_mode", "enable_reverse_blacklist", "enable_reverse_whitelist",
                "keyword_blacklist", "keyword_blacklist_regex", "keyword_whitelist", "keyword_whitelist_regex",
                "enable_media_type_filter", "media_type_filter_mode", "media_types",
                "enable_media_size_filter", "max_media_size", "media_size_filter_mode",
                "is_send_over_media_size_message", "enable_media_duration_filter",
                "media_duration_minutes", "media_duration_filter_mode", "enable_extension_filter",
                "extension_filter_mode", "media_extensions", "media_allow_text"
            ]:
                if key in payload:
                    filter_payload[key] = payload.get(key)

        def apply_basic_fields(target_rule: ForwardRule, allow_enable_rule: bool, allow_enable_sync: bool, allow_chat_update: bool):
            if "enable_rule" in basic and allow_enable_rule:
                target_rule.enable_rule = _parse_bool(basic.get("enable_rule"), target_rule.enable_rule)
            if "use_bot" in basic:
                target_rule.use_bot = _parse_bool(basic.get("use_bot"), target_rule.use_bot)
            if "handle_mode" in basic:
                target_rule.handle_mode = _parse_handle_mode(basic.get("handle_mode"), target_rule.handle_mode)
            if "message_mode" in basic:
                target_rule.message_mode = _parse_message_mode(basic.get("message_mode"), target_rule.message_mode)
            if "is_preview" in basic:
                target_rule.is_preview = _parse_preview_mode(basic.get("is_preview"), target_rule.is_preview)
            if "only_rss" in basic:
                target_rule.only_rss = _parse_bool(basic.get("only_rss"), target_rule.only_rss)
            if "enable_push" in basic:
                target_rule.enable_push = _parse_bool(basic.get("enable_push"), target_rule.enable_push)
            if "enable_only_push" in basic:
                target_rule.enable_only_push = _parse_bool(basic.get("enable_only_push"), target_rule.enable_only_push)
            if "enable_sync" in basic and allow_enable_sync:
                target_rule.enable_sync = _parse_bool(basic.get("enable_sync"), target_rule.enable_sync)
            if allow_chat_update:
                if "source_chat_id" in basic and basic.get("source_chat_id"):
                    source_chat = _get_or_create_chat(db_session, str(basic.get("source_chat_id")).strip())
                    target_rule.source_chat_id = source_chat.id
                if "target_chat_id" in basic and basic.get("target_chat_id"):
                    target_chat = _get_or_create_chat(db_session, str(basic.get("target_chat_id")).strip())
                    target_rule.target_chat_id = target_chat.id

        def apply_ai_fields(target_rule: ForwardRule):
            if "is_ai" in ai:
                target_rule.is_ai = _parse_bool(ai.get("is_ai"), target_rule.is_ai)
            if "ai_model" in ai:
                target_rule.ai_model = ai.get("ai_model") or ""
            if "ai_prompt" in ai:
                target_rule.ai_prompt = ai.get("ai_prompt") or ""
            if "enable_ai_upload_image" in ai:
                target_rule.enable_ai_upload_image = _parse_bool(
                    ai.get("enable_ai_upload_image"), target_rule.enable_ai_upload_image
                )
            if "is_keyword_after_ai" in ai:
                target_rule.is_keyword_after_ai = _parse_bool(
                    ai.get("is_keyword_after_ai"), target_rule.is_keyword_after_ai
                )
            if "is_summary" in ai:
                target_rule.is_summary = _parse_bool(ai.get("is_summary"), target_rule.is_summary)
            if "summary_time" in ai:
                target_rule.summary_time = ai.get("summary_time") or ""
            if "summary_prompt" in ai:
                target_rule.summary_prompt = ai.get("summary_prompt") or ""
            if "is_top_summary" in ai:
                target_rule.is_top_summary = _parse_bool(ai.get("is_top_summary"), target_rule.is_top_summary)

        def apply_style_fields(target_rule: ForwardRule, allow_templates: bool):
            if "is_original_sender" in style:
                target_rule.is_original_sender = _parse_bool(style.get("is_original_sender"), target_rule.is_original_sender)
            if "is_original_time" in style:
                target_rule.is_original_time = _parse_bool(style.get("is_original_time"), target_rule.is_original_time)
            if "is_original_link" in style:
                target_rule.is_original_link = _parse_bool(style.get("is_original_link"), target_rule.is_original_link)
            if "enable_comment_button" in style:
                target_rule.enable_comment_button = _parse_bool(
                    style.get("enable_comment_button"), target_rule.enable_comment_button
                )
            if "is_delete_original" in style:
                target_rule.is_delete_original = _parse_bool(style.get("is_delete_original"), target_rule.is_delete_original)
            if allow_templates:
                if "userinfo_template" in style:
                    target_rule.userinfo_template = style.get("userinfo_template") or ""
                if "time_template" in style:
                    target_rule.time_template = style.get("time_template") or ""
                if "original_link_template" in style:
                    target_rule.original_link_template = style.get("original_link_template") or ""

        def apply_advanced_fields(target_rule: ForwardRule, allow_ufb_meta: bool):
            if "is_ufb" in advanced:
                target_rule.is_ufb = _parse_bool(advanced.get("is_ufb"), target_rule.is_ufb)
            if "enable_delay" in advanced:
                target_rule.enable_delay = _parse_bool(advanced.get("enable_delay"), target_rule.enable_delay)
            if "delay_seconds" in advanced:
                try:
                    target_rule.delay_seconds = int(advanced.get("delay_seconds") or 0)
                except (TypeError, ValueError):
                    pass
            if allow_ufb_meta:
                if "ufb_domain" in advanced:
                    target_rule.ufb_domain = advanced.get("ufb_domain") or None
                if "ufb_item" in advanced:
                    target_rule.ufb_item = advanced.get("ufb_item") or None

        def apply_replace_rules(target_rule: ForwardRule):
            if replace_rules is None:
                return
            db_session.query(ReplaceRule).filter(ReplaceRule.rule_id == target_rule.id).delete()
            for item in replace_rules:
                pattern = (item.get("pattern") if isinstance(item, dict) else "") or ""
                if not pattern:
                    continue
                content = item.get("content") if isinstance(item, dict) else ""
                db_session.add(ReplaceRule(
                    rule_id=target_rule.id,
                    pattern=pattern,
                    content=content or ""
                ))
            if replace_rules and "is_replace" not in keywords:
                target_rule.is_replace = True

        def apply_push_configs(target_rule: ForwardRule):
            if push_configs is None:
                return
            db_session.query(PushConfig).filter(PushConfig.rule_id == target_rule.id).delete()
            for item in push_configs:
                if not isinstance(item, dict):
                    continue
                push_channel = (item.get("push_channel") or "").strip()
                if not push_channel:
                    continue
                enable_push_channel = _parse_bool(item.get("enable_push_channel"), True)
                media_send_mode = item.get("media_send_mode") or "Single"
                db_session.add(PushConfig(
                    rule_id=target_rule.id,
                    push_channel=push_channel,
                    enable_push_channel=enable_push_channel,
                    media_send_mode=media_send_mode
                ))

        apply_basic_fields(rule, allow_enable_rule=True, allow_enable_sync=True, allow_chat_update=True)
        apply_ai_fields(rule)
        apply_style_fields(rule, allow_templates=True)
        apply_advanced_fields(rule, allow_ufb_meta=True)
        if filter_payload:
            _apply_rule_filters_to_rule(rule, db_session, filter_payload)
        apply_replace_rules(rule)
        apply_push_configs(rule)

        updated_rule_ids = [rule.id]
        if sync_enabled:
            sync_rules = db_session.query(RuleSync).filter(RuleSync.rule_id == rule.id).all()
            for sync_rule in sync_rules:
                target_rule = db_session.query(ForwardRule).get(sync_rule.sync_rule_id)
                if not target_rule:
                    continue
                apply_basic_fields(target_rule, allow_enable_rule=False, allow_enable_sync=False, allow_chat_update=False)
                apply_ai_fields(target_rule)
                apply_style_fields(target_rule, allow_templates=False)
                apply_advanced_fields(target_rule, allow_ufb_meta=False)
                if filter_payload:
                    _apply_rule_filters_to_rule(target_rule, db_session, filter_payload)
                apply_replace_rules(target_rule)
                apply_push_configs(target_rule)
                updated_rule_ids.append(target_rule.id)

        db_session.commit()

        if db_ops_instance and filter_payload:
            for updated_id in updated_rule_ids:
                await db_ops_instance.sync_to_server(db_session, updated_id)

        return True, "规则配置已更新", status.HTTP_200_OK
    except Exception as e:
        db_session.rollback()
        logger.error(f"更新规则配置失败: {str(e)}")
        return False, f"更新规则配置失败: {str(e)}", status.HTTP_500_INTERNAL_SERVER_ERROR
    finally:
        db_session.close()

router = APIRouter(prefix="/rss")
rule_api_router = APIRouter()
rule_domain_router = APIRouter()
templates = Jinja2Templates(directory="rss/app/templates")
db_ops = None

async def init_db_ops():
    global db_ops
    if db_ops is None:
        db_ops = await get_db_ops()
    return db_ops

@router.get("/dashboard", response_class=HTMLResponse)
async def rss_dashboard(request: Request, user = Depends(get_current_user)):
    state = build_app_state(bool(user))
    if not state["auth"]["authenticated"]:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    if not state["routing"]["allow_dashboard"]:
        return RedirectResponse(url=state["routing"]["default_route"], status_code=status.HTTP_302_FOUND)

    db_session = get_session()
    try:
        # 初始化数据库操作对象
        await init_db_ops()
        
        # 获取所有RSS配置
        rss_configs = db_session.query(RSSConfig).options(
            joinedload(RSSConfig.rule)
        ).all()
        
        # 将 RSSConfig 对象转换为字典列表
        configs_list = []
        for config in rss_configs:
            # 处理AI提取提示词，使用Base64编码避免JSON解析问题
            ai_prompt = config.ai_extract_prompt
            ai_prompt_encoded = None
            if ai_prompt:
                # 使用Base64编码处理提示词
                ai_prompt_encoded = base64.b64encode(ai_prompt.encode('utf-8')).decode('utf-8')
                # 添加标记，表示这是Base64编码的内容
                ai_prompt_encoded = "BASE64:" + ai_prompt_encoded
            
            configs_list.append({
                "id": config.id,
                "rule_id": config.rule_id,
                "enable_rss": config.enable_rss,
                "rule_title": config.rule_title,
                "rule_description": config.rule_description,
                "language": config.language,
                "max_items": config.max_items,
                "is_auto_title": config.is_auto_title,
                "is_auto_content": config.is_auto_content,
                "is_ai_extract": config.is_ai_extract,
                "ai_extract_prompt": ai_prompt_encoded,
                "is_auto_markdown_to_html": config.is_auto_markdown_to_html,
                "enable_custom_title_pattern": config.enable_custom_title_pattern,
                "enable_custom_content_pattern": config.enable_custom_content_pattern
            })
        
        # 获取所有转发规则（用于创建新的RSS配置）
        rules = db_session.query(ForwardRule).options(
            joinedload(ForwardRule.source_chat),
            joinedload(ForwardRule.target_chat)
        ).all()
        
        # 将 ForwardRule 对象转换为字典列表
        rules_list = []
        for rule in rules:
            rules_list.append({
                "id": rule.id,
                "source_chat": {
                    "id": rule.source_chat.id,
                    "name": rule.source_chat.name
                } if rule.source_chat else None,
                "target_chat": {
                    "id": rule.target_chat.id,
                    "name": rule.target_chat.name
                } if rule.target_chat else None
            })
        
        ai_models = load_ai_models("list")
        summary_times = load_summary_times()
        delay_times = load_delay_times()
        return templates.TemplateResponse(
            "rss_dashboard.html", 
            {
                "request": request,
                "user": user,
                "rss_configs": configs_list,
                "rules": rules_list,
                "rss_base_url": RSS_BASE_URL or "",
                "ai_models": ai_models,
                "summary_times": summary_times,
                "delay_times": delay_times,
            }
        )
    finally:
        db_session.close()

@router.post("/config", response_class=JSONResponse)
async def rss_config_save(
    request: Request,
    user = Depends(get_current_user),
    config_id: Optional[str] = Form(None),
    rule_id: int = Form(...),
    enable_rss: bool = Form(True),
    rule_title: str = Form(""),
    rule_description: str = Form(""),
    language: str = Form("zh-CN"),
    max_items: int = Form(50),
    is_auto_title: bool = Form(False),
    is_auto_content: bool = Form(False),
    is_ai_extract: bool = Form(False),
    ai_extract_prompt: str = Form(""),
    is_auto_markdown_to_html: bool = Form(False),
    enable_custom_title_pattern: bool = Form(False),
    enable_custom_content_pattern: bool = Form(False)
):
    if not user:
        return JSONResponse(content={"success": False, "message": "未登录"})
    
    # 记录接收到的AI提取提示词内容，帮助调试
    logger.info(f"接收到的AI提取提示词字符数: {len(ai_extract_prompt)}")
    
    # 初始化数据库操作
    await init_db_ops()
    
    db_session = get_session()
    try:
        # 创建或更新RSS配置
        # 如果有config_id，表示更新
        if config_id and config_id.strip():
            config_id = int(config_id)
            # 检查配置是否存在
            rss_config = db_session.query(RSSConfig).filter(RSSConfig.id == config_id).first()
            if not rss_config:
                return JSONResponse(content={"success": False, "message": "配置不存在"})
            
            # 更新配置
            rss_config.rule_id = rule_id
            rss_config.enable_rss = enable_rss
            rss_config.rule_title = rule_title
            rss_config.rule_description = rule_description
            rss_config.language = language
            rss_config.max_items = max_items
            rss_config.is_auto_title = is_auto_title
            rss_config.is_auto_content = is_auto_content
            rss_config.is_ai_extract = is_ai_extract
            rss_config.ai_extract_prompt = ai_extract_prompt
            rss_config.is_auto_markdown_to_html = is_auto_markdown_to_html
            rss_config.enable_custom_title_pattern = enable_custom_title_pattern
            rss_config.enable_custom_content_pattern = enable_custom_content_pattern
        else:
            # 检查是否已经存在该规则的配置
            existing_config = db_session.query(RSSConfig).filter(RSSConfig.rule_id == rule_id).first()
            if existing_config:
                return JSONResponse(content={"success": False, "message": "该规则已经存在RSS配置"})
            
            # 创建新配置
            rss_config = RSSConfig(
                rule_id=rule_id,
                enable_rss=enable_rss,
                rule_title=rule_title,
                rule_description=rule_description,
                language=language,
                max_items=max_items,
                is_auto_title=is_auto_title,
                is_auto_content=is_auto_content,
                is_ai_extract=is_ai_extract,
                ai_extract_prompt=ai_extract_prompt,
                is_auto_markdown_to_html=is_auto_markdown_to_html,
                enable_custom_title_pattern=enable_custom_title_pattern,
                enable_custom_content_pattern=enable_custom_content_pattern
            )
        
        # 保存配置
        db_session.add(rss_config)
        db_session.commit()
        
        return JSONResponse({
            "success": True, 
            "message": "RSS 配置已保存",
            "config_id": rss_config.id,
            "rule_id": rss_config.rule_id
        })
    except Exception as e:
        return JSONResponse({"success": False, "message": f"保存配置失败: {str(e)}"})
    finally:
        db_session.close()

@router.get("/toggle/{rule_id}")
async def toggle_rss(rule_id: int, user = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    db_session = get_session()
    try:
        # 初始化数据库操作对象
        db_ops_instance = await init_db_ops()
        
        # 获取配置
        config = await db_ops_instance.get_rss_config(db_session, rule_id)
        if not config:
            return RedirectResponse(
                url="/rss/dashboard?error=配置不存在", 
                status_code=status.HTTP_302_FOUND
            )
        
        # 切换启用/禁用状态
        await db_ops_instance.update_rss_config(
            db_session,
            rule_id,
            enable_rss=not config.enable_rss
        )
        
        return RedirectResponse(
            url="/rss/dashboard?success=RSS状态已切换", 
            status_code=status.HTTP_302_FOUND
        )
    finally:
        db_session.close()

@router.get("/delete/{rule_id}")
async def delete_rss(rule_id: int, user = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    db_session = get_session()
    try:
        target_rule = db_session.query(ForwardRule).filter(ForwardRule.id == rule_id).first()
        if not target_rule:
            return RedirectResponse(
                url="/rss/dashboard?error=规则不存在", 
                status_code=status.HTTP_302_FOUND
            )

        # 先删除依赖数据，再删除规则本体
        db_session.query(ProcessedMessage).filter(ProcessedMessage.rule_id == rule_id).delete(synchronize_session=False)
        db_session.query(MediaExtensions).filter(MediaExtensions.rule_id == rule_id).delete(synchronize_session=False)
        db_session.query(MediaTypes).filter(MediaTypes.rule_id == rule_id).delete(synchronize_session=False)
        db_session.query(Keyword).filter(Keyword.rule_id == rule_id).delete(synchronize_session=False)
        db_session.query(ReplaceRule).filter(ReplaceRule.rule_id == rule_id).delete(synchronize_session=False)
        db_session.query(PushConfig).filter(PushConfig.rule_id == rule_id).delete(synchronize_session=False)

        # 删除规则同步关系（双向）
        db_session.query(RuleSync).filter(RuleSync.rule_id == rule_id).delete(synchronize_session=False)
        db_session.query(RuleSync).filter(RuleSync.sync_rule_id == rule_id).delete(synchronize_session=False)

        # 删除 RSS 配置及其模式
        rss_config = db_session.query(RSSConfig).filter(RSSConfig.rule_id == rule_id).first()
        if rss_config:
            db_session.query(RSSPattern).filter(RSSPattern.rss_config_id == rss_config.id).delete(synchronize_session=False)
            db_session.delete(rss_config)

        db_session.delete(target_rule)
        db_session.commit()

        # 删除关联的媒体和数据文件（非阻塞主流程）
        try:
            logger.info(f"开始删除规则 {rule_id} 的媒体和数据文件")
            rss_url = f"http://{RSS_HOST}:{RSS_PORT}/api/rule/{rule_id}"
            async with aiohttp.ClientSession() as client_session:
                async with client_session.delete(rss_url) as response:
                    if response.status == 200:
                        logger.info(f"成功删除规则 {rule_id} 的媒体和数据文件")
                    else:
                        response_text = await response.text()
                        logger.warning(f"删除规则 {rule_id} 的媒体和数据文件失败, 状态码: {response.status}, 响应: {response_text}")
        except Exception as e:
            logger.error(f"调用删除媒体文件API时出错: {str(e)}")

        return RedirectResponse(
            url="/rss/dashboard?success=规则已删除", 
            status_code=status.HTTP_302_FOUND
        )
    except Exception as exc:
        db_session.rollback()
        logger.error(f"删除规则失败: rule={rule_id}, err={str(exc)}")
        return RedirectResponse(
            url="/rss/dashboard?error=删除规则失败", 
            status_code=status.HTTP_302_FOUND
        )
    finally:
        db_session.close()

@router.get("/patterns/{config_id}")
async def get_patterns(config_id: int, user = Depends(get_current_user)):
    """获取指定RSS配置的所有模式"""
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)
    
    db_session = get_session()
    try:
        # 初始化数据库操作对象
        db_ops_instance = await init_db_ops()
        
        # 获取所有正则表达式数据
        config = await db_ops_instance.get_rss_config_with_patterns(db_session, config_id)
        if not config:
            return JSONResponse({"success": False, "message": "配置不存在"}, status_code=status.HTTP_404_NOT_FOUND)
        
        # 将模式转换为JSON格式
        patterns = []
        for pattern in config.patterns:
            patterns.append({
                "id": pattern.id,
                "pattern": pattern.pattern,
                "pattern_type": pattern.pattern_type,
                "priority": pattern.priority
            })
        
        return JSONResponse({"success": True, "patterns": patterns})
    finally:
        db_session.close()

@router.post("/pattern")
async def save_pattern(
    request: Request,
    user = Depends(get_current_user),
    pattern_id: Optional[str] = Form(None),
    rss_config_id: int = Form(...),
    pattern: str = Form(...),
    pattern_type: str = Form(...),
    priority: int = Form(0)
):
    """保存模式"""
    logger.info(f"开始保存模式，参数：config_id={rss_config_id}, pattern={pattern}, type={pattern_type}, priority={priority}")
    
    if not user:
        logger.warning("未登录的访问尝试")
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)
    
    db_session = get_session()
    try:
        # 初始化数据库操作对象
        db_ops_instance = await init_db_ops()
        
        # 检查RSS配置是否存在
        config = await db_ops_instance.get_rss_config(db_session, rss_config_id)
        if not config:
            logger.error(f"RSS配置不存在：config_id={rss_config_id}")
            return JSONResponse({"success": False, "message": "RSS配置不存在"})
        
        logger.debug(f"找到RSS配置：{config}")
    
      
        logger.info("创建新模式")
        # 创建新模式
        try:
            pattern_obj = await db_ops_instance.create_rss_pattern(
                db_session,
                config.id,
                pattern=pattern,
                pattern_type=pattern_type,
                priority=priority
            )
            logger.info(f"新模式创建成功：{pattern_obj}")
            return JSONResponse({"success": True, "message": "模式已创建", "pattern_id": pattern_obj.id})
        except Exception as e:
            logger.error(f"创建模式失败：{str(e)}")
            raise
    except Exception as e:
        logger.error(f"保存模式时发生错误：{str(e)}", exc_info=True)
        return JSONResponse({"success": False, "message": f"保存模式失败: {str(e)}"})
    finally:
        db_session.close()

@router.delete("/pattern/{pattern_id}")
async def delete_pattern(pattern_id: int, user = Depends(get_current_user)):
    """删除模式"""
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)
    
    db_session = get_session()
    try:
        # 初始化数据库操作对象
        await init_db_ops()
        
        # 查询模式
        pattern = db_session.query(RSSPattern).filter(RSSPattern.id == pattern_id).first()
        if not pattern:
            return JSONResponse({"success": False, "message": "找不到该模式"})
        
        # 删除模式
        db_session.delete(pattern)
        db_session.commit()
        
        return JSONResponse({"success": True, "message": "模式删除成功"})
    except Exception as e:
        db_session.rollback()
        logger.error(f"删除模式时出错: {str(e)}")
        return JSONResponse({"success": False, "message": f"删除模式失败: {str(e)}"})
    finally:
        db_session.close()

@router.delete("/patterns/{config_id}")
async def delete_all_patterns(config_id: int, user = Depends(get_current_user)):
    """删除配置的所有模式，通常在更新前调用以便重建模式列表"""
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)
    
    db_session = get_session()
    try:
        # 初始化数据库操作对象
        await init_db_ops()
        
        # 查询并删除指定配置的所有模式
        patterns = db_session.query(RSSPattern).filter(RSSPattern.rss_config_id == config_id).all()
        count = len(patterns)
        for pattern in patterns:
            db_session.delete(pattern)
        
        db_session.commit()
        logger.info(f"已删除配置 {config_id} 的所有模式，共 {count} 个")
        
        return JSONResponse({"success": True, "message": f"已删除 {count} 个模式"})
    except Exception as e:
        db_session.rollback()
        logger.error(f"删除配置 {config_id} 的所有模式时出错: {str(e)}")
        return JSONResponse({"success": False, "message": f"删除所有模式失败: {str(e)}"})
    finally:
        db_session.close()

@router.post("/test-regex")
async def test_regex(user = Depends(get_current_user), 
                    pattern: str = Form(...), 
                    test_text: str = Form(...), 
                    pattern_type: str = Form(...)):
    """测试正则表达式匹配结果"""
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)
    
    try:
        
        
        # 记录测试信息
        logger.info(f"测试正则表达式: {pattern}")
        logger.info(f"测试类型: {pattern_type}")
        logger.info(f"测试文本长度: {len(test_text)} 字符")
        
        # 执行正则匹配
        match = re.search(pattern, test_text)
        
        # 检查是否有匹配
        if not match:
            return JSONResponse({
                "success": True,
                "matched": False,
                "message": "未找到匹配"
            })
            
        # 检查捕获组
        if not match.groups():
            return JSONResponse({
                "success": True,
                "matched": True,
                "has_groups": False,
                "message": "匹配成功，但没有捕获组。请使用括号 () 来创建捕获组。"
            })
            
        # 成功匹配且有捕获组
        extracted_content = match.group(1)
        
        # 返回匹配结果
        return JSONResponse({
            "success": True,
            "matched": True,
            "has_groups": True,
            "extracted": extracted_content,
            "message": "匹配成功！"
        })
        
    except Exception as e:
        logger.error(f"测试正则表达式时出错: {str(e)}")
        return JSONResponse({
            "success": False,
            "message": f"测试失败: {str(e)}"
        }) 


@router.get("/filters/{rule_id}")
async def get_rule_filters(rule_id: int, user = Depends(get_current_user)):
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)

    db_session = get_session()
    try:
        rule = db_session.query(ForwardRule).options(
            joinedload(ForwardRule.keywords),
            joinedload(ForwardRule.media_types),
            joinedload(ForwardRule.media_extensions)
        ).filter(ForwardRule.id == rule_id).first()

        if not rule:
            return JSONResponse({"success": False, "message": "规则不存在"}, status_code=status.HTTP_404_NOT_FOUND)

        filters = _serialize_rule_filters(rule)
        return JSONResponse({"success": True, "filters": filters})
    finally:
        db_session.close()


@router.get("/rules/{rule_id}")
async def get_rule_detail(rule_id: int, user = Depends(get_current_user)):
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)

    db_session = get_session()
    try:
        rule = db_session.query(ForwardRule).options(
            joinedload(ForwardRule.source_chat),
            joinedload(ForwardRule.target_chat),
            joinedload(ForwardRule.keywords),
            joinedload(ForwardRule.media_types),
            joinedload(ForwardRule.media_extensions)
        ).filter(ForwardRule.id == rule_id).first()

        if not rule:
            return JSONResponse({"success": False, "message": "规则不存在"}, status_code=status.HTTP_404_NOT_FOUND)

        detail = _serialize_rule_detail(rule, db_session)
        return JSONResponse({"success": True, "rule": detail})
    finally:
        db_session.close()


@router.post("/rules")
async def create_rule(request: Request, user = Depends(get_current_user)):
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = await request.json()
    except Exception:
        payload = None

    if not isinstance(payload, dict):
        return JSONResponse({"success": False, "message": "请求数据无效"}, status_code=status.HTTP_400_BAD_REQUEST)

    basic = payload.get("basic") if isinstance(payload.get("basic"), dict) else {}
    source_chat_id = str(basic.get("source_chat_id") or "").strip()
    target_chat_id = str(basic.get("target_chat_id") or "").strip()
    if not source_chat_id or not target_chat_id:
        return JSONResponse({"success": False, "message": "请填写源与目标频道 ID"}, status_code=status.HTTP_400_BAD_REQUEST)

    canonical_source_chat_id = normalize_chat_peer_key(source_chat_id)
    canonical_target_chat_id = normalize_chat_peer_key(target_chat_id)

    db_session = get_session()
    new_rule_id = None
    try:
        source_chat = _get_or_create_chat(db_session, source_chat_id)
        target_chat = _get_or_create_chat(db_session, target_chat_id)

        exists = db_session.query(ForwardRule).filter(
            ForwardRule.source_chat_id == source_chat.id,
            ForwardRule.target_chat_id == target_chat.id
        ).first()
        if exists:
            return JSONResponse(
                {"success": False, "message": "规则已存在", "rule_id": exists.id},
                status_code=status.HTTP_409_CONFLICT
            )

        max_id = db_session.query(func.max(ForwardRule.id)).scalar() or 0
        new_rule_id = int(max_id) + 1
        rule = ForwardRule(
            id=new_rule_id,
            source_chat_id=source_chat.id,
            target_chat_id=target_chat.id
        )
        if canonical_source_chat_id and canonical_source_chat_id == canonical_target_chat_id:
            rule.forward_mode = ForwardMode.WHITELIST
            rule.add_mode = AddMode.WHITELIST

        db_session.add(rule)
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        logger.error(f"创建规则失败: {str(e)}")
        return JSONResponse({"success": False, "message": "创建规则失败"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        db_session.close()

    success, message, status_code = await _apply_rule_settings(new_rule_id, payload)
    if not success:
        cleanup_session = get_session()
        try:
            stale_rule = cleanup_session.query(ForwardRule).get(new_rule_id)
            if stale_rule:
                cleanup_session.delete(stale_rule)
                cleanup_session.commit()
        finally:
            cleanup_session.close()
        return JSONResponse({"success": False, "message": message}, status_code=status_code)

    return JSONResponse({"success": True, "rule_id": new_rule_id, "message": "规则已创建"})


@router.put("/rules/{rule_id}")
async def update_rule_detail(rule_id: int, request: Request, user = Depends(get_current_user)):
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = await request.json()
    except Exception:
        payload = None

    if not isinstance(payload, dict):
        return JSONResponse({"success": False, "message": "请求数据无效"}, status_code=status.HTTP_400_BAD_REQUEST)

    success, message, status_code = await _apply_rule_settings(rule_id, payload)
    return JSONResponse({"success": success, "message": message}, status_code=status_code)


@rule_api_router.post("/api/rules/{rule_id}/backfill")
async def start_rule_backfill(rule_id: int, request: Request, user = Depends(get_current_user)):
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = await request.json()
    except Exception:
        payload = None

    if payload is None:
        payload = {}

    if not isinstance(payload, dict):
        return JSONResponse({"success": False, "message": "请求数据无效"}, status_code=status.HTTP_400_BAD_REQUEST)

    mode = str(payload.get("mode") or "last").strip().lower()
    limit_value = payload.get("limit")
    start_text = payload.get("start_time") or payload.get("start")
    end_text = payload.get("end_time") or payload.get("end")

    try:
        batch_size = int(payload.get("batch_size") or 20)
    except (TypeError, ValueError):
        batch_size = 20

    try:
        batch_delay_seconds = float(payload.get("batch_delay_seconds") or 0)
    except (TypeError, ValueError):
        batch_delay_seconds = 0.0

    try:
        message_delay_seconds = float(payload.get("message_delay_seconds") or 0)
    except (TypeError, ValueError):
        message_delay_seconds = 0.0

    timezone_name = os.getenv("DEFAULT_TIMEZONE", "Asia/Shanghai")
    timezone = pytz.timezone(timezone_name)

    try:
        adaptive_throttle = _parse_bool(payload.get("adaptive_throttle"), _get_env_bool("BACKFILL_ADAPTIVE_THROTTLE", True))
        throttle_min_delay = _get_env_float("BACKFILL_THROTTLE_MIN_DELAY", 0.2)
        throttle_max_delay = _get_env_float("BACKFILL_THROTTLE_MAX_DELAY", 6.0)
        throttle_increase_step = _get_env_float("BACKFILL_THROTTLE_INCREASE_STEP", 0.5)
        throttle_decrease_step = _get_env_float("BACKFILL_THROTTLE_DECREASE_STEP", 0.2)
        throttle_cooldown_threshold = _get_env_int("BACKFILL_THROTTLE_COOLDOWN_THRESHOLD", 10)

        throttle_kwargs = {
            "adaptive_throttle": adaptive_throttle,
            "throttle_min_delay": throttle_min_delay,
            "throttle_max_delay": throttle_max_delay,
            "throttle_increase_step": throttle_increase_step,
            "throttle_decrease_step": throttle_decrease_step,
            "throttle_cooldown_threshold": throttle_cooldown_threshold,
        }

        if mode.isdigit():
            params = BackfillParams(
                mode="last",
                limit=int(mode),
                batch_size=batch_size,
                batch_delay_seconds=batch_delay_seconds,
                message_delay_seconds=message_delay_seconds,
                **throttle_kwargs,
            )
        elif mode in ("last", "l"):
            if limit_value is None or str(limit_value).strip() == "":
                raise ValueError("last 模式需要提供 limit")
            params = BackfillParams(
                mode="last",
                limit=int(limit_value),
                batch_size=batch_size,
                batch_delay_seconds=batch_delay_seconds,
                message_delay_seconds=message_delay_seconds,
                **throttle_kwargs,
            )
        elif mode in ("range", "r"):
            if not start_text or not end_text:
                raise ValueError("range 模式需要提供 start_time/end_time")
            start_time = _parse_datetime(str(start_text), timezone)
            end_time = _parse_datetime(str(end_text), timezone)
            if end_time < start_time:
                raise ValueError("end_time 必须 >= start_time")
            params = BackfillParams(
                mode="range",
                start_time=start_time,
                end_time=end_time,
                batch_size=batch_size,
                batch_delay_seconds=batch_delay_seconds,
                message_delay_seconds=message_delay_seconds,
                **throttle_kwargs,
            )
        elif mode in ("all", "a"):
            params = BackfillParams(
                mode="all",
                batch_size=batch_size,
                batch_delay_seconds=batch_delay_seconds,
                message_delay_seconds=message_delay_seconds,
                **throttle_kwargs,
            )
        else:
            raise ValueError("未知回填模式")
    except ValueError as exc:
        return JSONResponse({"success": False, "message": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)

    try:
        bot_client = await get_bot_client()
        user_client = await get_user_client()
        notify_chat_id = await get_user_id()
    except Exception as exc:
        return JSONResponse({"success": False, "message": f"初始化客户端失败: {str(exc)}"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    ok, msg, _ = await start_backfill_task(
        bot_client=bot_client,
        user_client=user_client,
        rule_id=rule_id,
        params=params,
        notify_chat_id=notify_chat_id,
    )
    status_code = status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST
    return JSONResponse({"success": ok, "message": msg}, status_code=status_code)


@rule_api_router.post("/api/rules/{rule_id}/backfill/video-forward")
async def start_rule_video_forward(rule_id: int, request: Request, user = Depends(get_current_user)):
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = await request.json()
    except Exception:
        payload = None

    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return JSONResponse({"success": False, "message": "请求数据无效"}, status_code=status.HTTP_400_BAD_REQUEST)

    db_session = get_session()
    try:
        rule = db_session.query(ForwardRule).filter(ForwardRule.id == rule_id).first()
        if not rule:
            return JSONResponse({"success": False, "message": "规则不存在"}, status_code=status.HTTP_404_NOT_FOUND)
        use_bot = bool(rule.use_bot)
    finally:
        db_session.close()

    try:
        batch_size = int(payload.get("batch_size") or 20)
    except (TypeError, ValueError):
        batch_size = 20

    try:
        batch_delay_seconds = float(payload.get("batch_delay_seconds") or 0)
    except (TypeError, ValueError):
        batch_delay_seconds = 0.0

    try:
        message_delay_seconds = float(payload.get("message_delay_seconds") or 0)
    except (TypeError, ValueError):
        message_delay_seconds = 0.0

    adaptive_throttle = _parse_bool(payload.get("adaptive_throttle"), _get_env_bool("BACKFILL_ADAPTIVE_THROTTLE", True))
    throttle_min_delay = _get_env_float("BACKFILL_THROTTLE_MIN_DELAY", 0.2)
    throttle_max_delay = _get_env_float("BACKFILL_THROTTLE_MAX_DELAY", 6.0)
    throttle_increase_step = _get_env_float("BACKFILL_THROTTLE_INCREASE_STEP", 0.5)
    throttle_decrease_step = _get_env_float("BACKFILL_THROTTLE_DECREASE_STEP", 0.2)
    throttle_cooldown_threshold = _get_env_int("BACKFILL_THROTTLE_COOLDOWN_THRESHOLD", 10)

    params = BackfillParams(
        mode="all",
        batch_size=batch_size,
        batch_delay_seconds=batch_delay_seconds,
        message_delay_seconds=message_delay_seconds,
        adaptive_throttle=adaptive_throttle,
        throttle_min_delay=throttle_min_delay,
        throttle_max_delay=throttle_max_delay,
        throttle_increase_step=throttle_increase_step,
        throttle_decrease_step=throttle_decrease_step,
        throttle_cooldown_threshold=throttle_cooldown_threshold,
    )

    try:
        bot_client = await get_bot_client()
        user_client = await get_user_client()
        notify_chat_id = await get_user_id()
    except Exception as exc:
        return JSONResponse({"success": False, "message": f"初始化客户端失败: {str(exc)}"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    forward_client = bot_client if use_bot else user_client
    ok, msg, _ = await start_video_forward_task(
        bot_client=bot_client,
        user_client=user_client,
        forward_client=forward_client,
        rule_id=rule_id,
        params=params,
        notify_chat_id=notify_chat_id,
    )
    status_code = status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST
    return JSONResponse({"success": ok, "message": msg}, status_code=status_code)


@rule_api_router.get("/api/rules/{rule_id}/backfill/status")
async def get_rule_backfill_status(rule_id: int, user = Depends(get_current_user)):
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)

    db_session = get_session()
    try:
        dedup_count = db_session.query(ProcessedMessage).filter(ProcessedMessage.rule_id == rule_id).count()
    finally:
        db_session.close()

    status_payload = await get_backfill_status(rule_id=rule_id)
    task = status_payload.get("task")
    return JSONResponse({
        "success": True,
        "active": bool(status_payload.get("active")),
        "task": task,
        "dedup_count": dedup_count,
    })


@rule_api_router.post("/api/rules/{rule_id}/backfill/stop")
async def stop_rule_backfill(rule_id: int, user = Depends(get_current_user)):
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)

    ok, msg, info = await stop_backfill_task_by_rule(rule_id=rule_id)
    status_code = status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST
    return JSONResponse({
        "success": ok,
        "message": msg,
        "rule_id": info.rule_id if info else rule_id,
    }, status_code=status_code)


@rule_api_router.post("/api/rules/{rule_id}/backfill/reset")
async def reset_rule_backfill_dedup(rule_id: int, user = Depends(get_current_user)):
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)

    status_payload = await get_backfill_status(rule_id=rule_id)
    if status_payload.get("active"):
        return JSONResponse({
            "success": False,
            "message": "当前规则有回填任务运行中，请先停止后再重置",
        }, status_code=status.HTTP_409_CONFLICT)

    db_session = get_session()
    try:
        deleted = (
            db_session.query(ProcessedMessage)
            .filter(ProcessedMessage.rule_id == rule_id)
            .delete(synchronize_session=False)
        )
        db_session.commit()
    except Exception as exc:
        db_session.rollback()
        logger.error(f"重置回填去重记录失败: rule={rule_id}, err={str(exc)}")
        return JSONResponse({"success": False, "message": "重置失败，请检查日志"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        db_session.close()

    return JSONResponse({
        "success": True,
        "message": f"已清理回填去重记录 {deleted} 条",
        "deleted": deleted,
    })


@router.post("/filters/{rule_id}")
async def update_rule_filters(rule_id: int, request: Request, user = Depends(get_current_user)):
    if not user:
        return JSONResponse({"success": False, "message": "未登录"}, status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = await request.json()
    except Exception:
        payload = None

    if not isinstance(payload, dict):
        return JSONResponse({"success": False, "message": "请求数据无效"}, status_code=status.HTTP_400_BAD_REQUEST)

    success, message, status_code = await _apply_rule_filters(rule_id, payload)
    return JSONResponse({"success": success, "message": message}, status_code=status_code)


# 规则主域别名路由（兼容保留 /rss 前缀）
rule_domain_router.add_api_route("/dashboard", rss_dashboard, methods=["GET"], response_class=HTMLResponse)
rule_domain_router.add_api_route("/rules", create_rule, methods=["POST"], response_class=JSONResponse)
rule_domain_router.add_api_route("/rules/{rule_id}", get_rule_detail, methods=["GET"], response_class=JSONResponse)
rule_domain_router.add_api_route("/rules/{rule_id}", update_rule_detail, methods=["PUT"], response_class=JSONResponse)
rule_domain_router.add_api_route("/rules/{rule_id}/filters", get_rule_filters, methods=["GET"], response_class=JSONResponse)
rule_domain_router.add_api_route("/rules/{rule_id}/filters", update_rule_filters, methods=["POST"], response_class=JSONResponse)
rule_domain_router.add_api_route("/rules/{rule_id}/toggle", toggle_rss, methods=["GET"], response_class=RedirectResponse)
rule_domain_router.add_api_route("/rules/{rule_id}/delete", delete_rss, methods=["GET"], response_class=RedirectResponse)
