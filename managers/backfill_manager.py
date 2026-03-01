import asyncio
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Dict, Optional

import pytz
from sqlalchemy.orm import joinedload, selectinload
from telethon.errors import FloodWaitError
from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeVideo

from filters.process import process_forward_rule
from handlers import user_handler
from models.models import ForwardRule, get_session
from utils.common import check_keywords
from utils.media import get_media_size
from enums.enums import CompareMode
from utils.dedup import build_dedup_key, claim_processed, is_processed


def _get_env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _get_env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class BackfillThrottle:
    def __init__(
        self,
        min_delay: float,
        max_delay: float,
        increase_step: float,
        decrease_step: float,
        cooldown_threshold: int,
    ):
        self.min_delay = max(0.0, min_delay)
        self.max_delay = max(self.min_delay, max_delay)
        self.increase_step = max(0.0, increase_step)
        self.decrease_step = max(0.0, decrease_step)
        self.cooldown_threshold = max(1, cooldown_threshold)
        self._delay = self.min_delay
        self._stable_count = 0

    @property
    def delay(self) -> float:
        return self._delay

    def on_success(self) -> None:
        if self._delay <= self.min_delay:
            return
        self._stable_count += 1
        if self._stable_count >= self.cooldown_threshold:
            self._delay = max(self.min_delay, self._delay - self.decrease_step)
            self._stable_count = 0

    def on_flood_wait(self, wait_seconds: Optional[int]) -> None:
        self._stable_count = 0
        if wait_seconds is None:
            return
        wait_seconds = max(0, int(wait_seconds))
        next_delay = max(self._delay, wait_seconds + 1)
        next_delay = max(next_delay, self._delay + self.increase_step)
        self._delay = min(self.max_delay, next_delay)

    def on_failure(self) -> None:
        self._stable_count = 0
        if self.increase_step > 0:
            self._delay = min(self.max_delay, self._delay + self.increase_step)

logger = logging.getLogger(__name__)

_BACKFILL_TASKS_LOCK = asyncio.Lock()
_BACKFILL_TASKS: Dict[int, "BackfillTaskInfo"] = {}


class BackfillEvent:
    """
    将历史 Message 包装成与 Telethon NewMessage event 足够兼容的对象，
    以便复用现有过滤器链（filters/process.py）。
    """

    def __init__(self, message, user_client):
        self.message = message
        self.client = user_client
        self.is_backfill = True

    @property
    def chat_id(self):
        return getattr(self.message, "chat_id", None)

    @property
    def id(self):
        return getattr(self.message, "id", None)

    @property
    def sender_id(self):
        return getattr(self.message, "sender_id", None)

    @property
    def sender(self):
        return getattr(self.message, "sender", None)

    async def get_chat(self):
        if hasattr(self.message, "get_chat"):
            return await self.message.get_chat()
        return None


@dataclass(frozen=True)
class BackfillParams:
    mode: str  # last | range | all
    limit: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    batch_size: int = 20
    batch_delay_seconds: float = 0.0
    message_delay_seconds: float = 0.0
    adaptive_throttle: bool = True
    throttle_min_delay: float = 0.2
    throttle_max_delay: float = 6.0
    throttle_increase_step: float = 0.5
    throttle_decrease_step: float = 0.2
    throttle_cooldown_threshold: int = 10


@dataclass(frozen=True)
class BackfillTaskInfo:
    """
    回填任务控制信息（按 notify_chat_id 管理，确保同一聊天窗口只跑一个回填）。
    """

    task: asyncio.Task
    stop_event: asyncio.Event
    rule_id: int
    params: BackfillParams
    started_at: datetime


def _get_message_text(message) -> str:
    if not message:
        return ""
    return message.message or message.text or ""


def _is_video_message(message) -> bool:
    if getattr(message, "video", None):
        return True

    document = getattr(message, "document", None)
    if document and getattr(document, "attributes", None):
        for attr in document.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                return True

    return False


async def _collect_media_group_messages(client, message):
    grouped_id = getattr(message, "grouped_id", None)
    if not grouped_id:
        return [message]

    messages = []
    try:
        async for item in client.iter_messages(
            message.chat_id,
            limit=20,
            min_id=message.id - 10,
            max_id=message.id + 10,
        ):
            if item.grouped_id == grouped_id:
                messages.append(item)
    except Exception as e:
        logger.warning(f"收集媒体组消息失败: {str(e)}")

    if not messages:
        return [message]

    messages.sort(key=lambda item: item.id)
    return messages


def _extract_group_text(messages) -> str:
    texts = []
    for message in messages:
        text = _get_message_text(message)
        if text:
            texts.append(text)
    return "\n".join(texts)


async def _forward_with_flood_wait(
    client, target_chat_id: int, message_ids, source_chat_id: int, rule_id: int
) -> tuple[bool, Optional[int]]:
    max_attempts = 2
    last_wait_seconds = None
    for attempt in range(1, max_attempts + 1):
        try:
            await client.forward_messages(target_chat_id, message_ids, source_chat_id)
            return True, last_wait_seconds
        except FloodWaitError as e:
            wait_seconds = e.seconds
            last_wait_seconds = wait_seconds
            logger.warning(
                f"规则 {rule_id} 转发视频触发限流，需要等待 {wait_seconds} 秒 (尝试 {attempt}/{max_attempts})"
            )
            if attempt >= max_attempts:
                return False, last_wait_seconds
            await asyncio.sleep(wait_seconds + 1)
        except Exception as e:
            logger.error(f"规则 {rule_id} 转发视频失败: {str(e)}")
            return False, last_wait_seconds
    return False, last_wait_seconds


async def _forward_messages_with_flood_wait(
    client, target_chat_id: int, message_ids, source_chat_id: int, rule_id: int
) -> tuple[bool, Optional[int], Optional[object]]:
    max_attempts = 2
    last_wait_seconds = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await client.forward_messages(target_chat_id, message_ids, source_chat_id)
            return True, last_wait_seconds, result
        except FloodWaitError as e:
            wait_seconds = e.seconds
            last_wait_seconds = wait_seconds
            logger.warning(
                f"规则 {rule_id} 转发视频触发限流，需要等待 {wait_seconds} 秒 (尝试 {attempt}/{max_attempts})"
            )
            if attempt >= max_attempts:
                return False, last_wait_seconds, None
            await asyncio.sleep(wait_seconds + 1)
        except Exception as e:
            logger.error(f"规则 {rule_id} 转发视频失败: {str(e)}")
            return False, last_wait_seconds, None
    return False, last_wait_seconds, None


async def _forward_messages_with_flood_wait_custom_caption(
    client,
    target_chat_id: int,
    message_ids,
    source_chat_id: int,
    rule_id: int,
    caption: str,
) -> tuple[bool, Optional[int]]:
    max_attempts = 2
    last_wait_seconds = None
    for attempt in range(1, max_attempts + 1):
        try:
            ids = message_ids if isinstance(message_ids, list) else [message_ids]
            if not ids:
                return True, last_wait_seconds

            messages = await client.get_messages(source_chat_id, ids=ids)
            if isinstance(messages, list):
                items = [msg for msg in messages if msg and msg.media]
                items.sort(key=lambda msg: msg.id)
            else:
                items = [messages] if messages and messages.media else []

            if not items:
                logger.warning(f"规则 {rule_id} 合并转发失败: 未找到可发送的媒体")
                return False, last_wait_seconds

            if len(items) == 1:
                await client.send_file(
                    target_chat_id,
                    items[0],
                    caption=caption or None,
                )
            else:
                captions = None
                if caption:
                    captions = [caption] + [""] * (len(items) - 1)
                await client.send_file(
                    target_chat_id,
                    items,
                    caption=captions,
                )
            return True, last_wait_seconds
        except FloodWaitError as e:
            wait_seconds = e.seconds
            last_wait_seconds = wait_seconds
            logger.warning(
                f"规则 {rule_id} 合并转发触发限流，需要等待 {wait_seconds} 秒 (尝试 {attempt}/{max_attempts})"
            )
            if attempt >= max_attempts:
                return False, last_wait_seconds
            await asyncio.sleep(wait_seconds + 1)
        except Exception as e:
            logger.warning(f"规则 {rule_id} 合并转发失败: {str(e)}")
            return False, last_wait_seconds
    return False, last_wait_seconds


async def _edit_caption_with_flood_wait(
    client, target_chat_id: int, message, caption: str, rule_id: int
) -> tuple[bool, Optional[int]]:
    max_attempts = 2
    last_wait_seconds = None
    for attempt in range(1, max_attempts + 1):
        try:
            await client.edit_message(target_chat_id, message, text=caption)
            return True, last_wait_seconds
        except FloodWaitError as e:
            wait_seconds = e.seconds
            last_wait_seconds = wait_seconds
            logger.warning(
                f"规则 {rule_id} 编辑说明触发限流，需要等待 {wait_seconds} 秒 (尝试 {attempt}/{max_attempts})"
            )
            if attempt >= max_attempts:
                return False, last_wait_seconds
            await asyncio.sleep(wait_seconds + 1)
        except Exception as e:
            logger.warning(f"规则 {rule_id} 编辑说明失败: {str(e)}")
            return False, last_wait_seconds
    return False, last_wait_seconds


def _get_compare_mode(value):
    if isinstance(value, CompareMode):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == "greater":
            return CompareMode.GREATER
        if lowered == "less":
            return CompareMode.LESS
    return CompareMode.LESS


def _is_size_filtered(size_mb: float, limit_mb: float, mode: CompareMode) -> bool:
    if mode == CompareMode.GREATER:
        return size_mb < limit_mb
    return size_mb > limit_mb


def _is_duration_filtered(duration_minutes: float, limit_minutes: float, mode: CompareMode) -> bool:
    if mode == CompareMode.GREATER:
        return duration_minutes < limit_minutes
    return duration_minutes > limit_minutes


def _get_media_duration_seconds(message):
    document = getattr(message, "document", None)
    if not document or not getattr(document, "attributes", None):
        return None
    for attr in document.attributes:
        if isinstance(attr, DocumentAttributeVideo):
            return getattr(attr, "duration", None)
        if isinstance(attr, DocumentAttributeAudio):
            return getattr(attr, "duration", None)
    return None


async def _passes_media_filters(rule, message) -> bool:
    if not message or not getattr(message, "media", None):
        return True

    if rule.enable_media_size_filter:
        size_bytes = await get_media_size(message.media)
        size_mb = size_bytes / 1024 / 1024
        size_mb_display = round(size_mb, 4)
        limit_mb = rule.max_media_size
        mode = _get_compare_mode(getattr(rule, "media_size_filter_mode", CompareMode.LESS))
        if limit_mb is not None and _is_size_filtered(size_mb, limit_mb, mode):
            logger.info(f"视频大小 {size_mb_display}MB 未通过筛选 (阈值 {limit_mb}MB)")
            return False

    if rule.enable_media_duration_filter:
        duration_seconds = _get_media_duration_seconds(message)
        if duration_seconds is not None:
            duration_minutes = round(duration_seconds / 60, 2)
            limit_minutes = rule.media_duration_minutes
            mode = _get_compare_mode(getattr(rule, "media_duration_filter_mode", CompareMode.LESS))
            if limit_minutes and _is_duration_filtered(duration_minutes, limit_minutes, mode):
                logger.info(f"视频时长 {duration_minutes} 分钟未通过筛选 (阈值 {limit_minutes} 分钟)")
                return False

    return True

async def start_backfill_task(
    *,
    bot_client,
    user_client,
    rule_id: int,
    params: BackfillParams,
    notify_chat_id: int,
) -> tuple[bool, str, Optional[BackfillTaskInfo]]:
    """
    启动回填任务并登记，以便 /backfill_stop 中断。

    - 同一 notify_chat_id 同时只允许一个回填任务运行。
    """
    async with _BACKFILL_TASKS_LOCK:
        existing = _BACKFILL_TASKS.get(notify_chat_id)
        if existing and not existing.task.done():
            return False, f"已有回填任务在运行（规则 {existing.rule_id}），请先 /backfill_stop", existing

        stop_event = asyncio.Event()

        async def _runner():
            try:
                await run_backfill(
                    bot_client=bot_client,
                    user_client=user_client,
                    rule_id=rule_id,
                    params=params,
                    notify_chat_id=notify_chat_id,
                    stop_event=stop_event,
                )
            finally:
                async with _BACKFILL_TASKS_LOCK:
                    current = _BACKFILL_TASKS.get(notify_chat_id)
                    if current and current.task is asyncio.current_task():
                        _BACKFILL_TASKS.pop(notify_chat_id, None)

        task = asyncio.create_task(_runner())
        info = BackfillTaskInfo(
            task=task,
            stop_event=stop_event,
            rule_id=rule_id,
            params=params,
            started_at=datetime.now(_get_timezone()),
        )
        _BACKFILL_TASKS[notify_chat_id] = info
        return True, "已启动回填任务", info


async def start_video_forward_task(
    *,
    bot_client,
    user_client,
    forward_client,
    rule_id: int,
    params: BackfillParams,
    notify_chat_id: int,
) -> tuple[bool, str, Optional[BackfillTaskInfo]]:
    """
    启动“转发全部视频”任务并登记，以便 /backfill_stop 中断。
    """
    async with _BACKFILL_TASKS_LOCK:
        existing = _BACKFILL_TASKS.get(notify_chat_id)
        if existing and not existing.task.done():
            return False, f"已有任务在运行（规则 {existing.rule_id}），请先 /backfill_stop", existing

        stop_event = asyncio.Event()

        async def _runner():
            try:
                await run_video_forward(
                    bot_client=bot_client,
                    user_client=user_client,
                    forward_client=forward_client,
                    rule_id=rule_id,
                    params=params,
                    notify_chat_id=notify_chat_id,
                    stop_event=stop_event,
                )
            finally:
                async with _BACKFILL_TASKS_LOCK:
                    current = _BACKFILL_TASKS.get(notify_chat_id)
                    if current and current.task is asyncio.current_task():
                        _BACKFILL_TASKS.pop(notify_chat_id, None)

        task = asyncio.create_task(_runner())
        info = BackfillTaskInfo(
            task=task,
            stop_event=stop_event,
            rule_id=rule_id,
            params=params,
            started_at=datetime.now(_get_timezone()),
        )
        _BACKFILL_TASKS[notify_chat_id] = info
        return True, "已启动视频转发任务", info


async def stop_backfill_task(*, notify_chat_id: int) -> tuple[bool, str, Optional[BackfillTaskInfo]]:
    """
    请求停止当前聊天窗口的回填任务。

    采用“先通知 stop_event + 再 cancel task”以便尽快中断等待中的 I/O。
    """
    async with _BACKFILL_TASKS_LOCK:
        info = _BACKFILL_TASKS.get(notify_chat_id)
        if not info or info.task.done():
            if info and info.task.done():
                _BACKFILL_TASKS.pop(notify_chat_id, None)
            return False, "当前没有正在运行的回填任务", None

        info.stop_event.set()
        info.task.cancel()
        return True, f"已请求停止回填任务（规则 {info.rule_id}），请稍候…", info


def _get_timezone():
    timezone_name = os.getenv("DEFAULT_TIMEZONE", "Asia/Shanghai")
    return pytz.timezone(timezone_name)


def _load_rule_for_processing(rule_id: int) -> Optional[ForwardRule]:
    session = get_session()
    try:
        rule = (
            session.query(ForwardRule)
            .options(
                joinedload(ForwardRule.source_chat),
                joinedload(ForwardRule.target_chat),
                selectinload(ForwardRule.keywords),
                selectinload(ForwardRule.replace_rules),
            )
            .get(rule_id)
        )
        if not rule:
            return None

        _ = rule.source_chat, rule.target_chat, rule.keywords, rule.replace_rules

        session.expunge_all()
        return rule
    finally:
        session.close()


async def _iter_last_messages(
    user_client, source_chat_id: int, limit: int, stop_event: Optional[asyncio.Event] = None
) -> AsyncIterator:
    async for message in user_client.iter_messages(source_chat_id, limit=limit):
        if stop_event and stop_event.is_set():
            break
        yield message


async def _iter_messages_by_time_range(
    user_client,
    source_chat_id: int,
    start_time: datetime,
    end_time: datetime,
    batch_size: int,
    batch_delay_seconds: float,
    stop_event: Optional[asyncio.Event] = None,
) -> AsyncIterator:
    timezone = _get_timezone()
    current_offset = 0

    while True:
        if stop_event and stop_event.is_set():
            break

        messages_batch = await user_client.get_messages(
            source_chat_id,
            limit=batch_size,
            offset_date=end_time,
            offset_id=current_offset,
            reverse=False,
        )

        if not messages_batch:
            break

        should_break = False
        for message in messages_batch:
            if stop_event and stop_event.is_set():
                should_break = True
                break

            msg_time = message.date.astimezone(timezone) if getattr(message, "date", None) else None
            if msg_time is None:
                continue
            if msg_time > end_time:
                continue
            if msg_time < start_time:
                should_break = True
                break
            yield message

        current_offset = messages_batch[-1].id

        if should_break:
            break

        if batch_delay_seconds > 0:
            await asyncio.sleep(batch_delay_seconds)


async def run_backfill(
    *,
    bot_client,
    user_client,
    rule_id: int,
    params: BackfillParams,
    notify_chat_id: Optional[int] = None,
    stop_event: Optional[asyncio.Event] = None,
):
    rule = _load_rule_for_processing(rule_id)
    if not rule:
        raise ValueError(f"找不到规则: {rule_id}")

    if not rule.enable_rule:
        raise ValueError(f"规则未启用: {rule_id}")

    source_chat_id = int(rule.source_chat.telegram_chat_id)

    timezone = _get_timezone()
    now = datetime.now(timezone)

    if params.mode == "last":
        if not params.limit or params.limit <= 0:
            raise ValueError("last 模式需要提供正整数 limit")
        iterator = _iter_last_messages(user_client, source_chat_id, params.limit, stop_event)
        mode_desc = f"最近 {params.limit} 条"
    elif params.mode == "range":
        if not params.start_time or not params.end_time:
            raise ValueError("range 模式需要提供 start_time/end_time")
        iterator = _iter_messages_by_time_range(
            user_client,
            source_chat_id,
            params.start_time,
            params.end_time,
            params.batch_size,
            params.batch_delay_seconds,
            stop_event,
        )
        mode_desc = f"{params.start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ {params.end_time.strftime('%Y-%m-%d %H:%M:%S')}"
    elif params.mode == "all":
        start_time = timezone.localize(datetime(1970, 1, 1, 0, 0, 0))
        end_time = now
        iterator = _iter_messages_by_time_range(
            user_client,
            source_chat_id,
            start_time,
            end_time,
            params.batch_size,
            params.batch_delay_seconds,
            stop_event,
        )
        mode_desc = "全部历史"
    else:
        raise ValueError(f"未知回填模式: {params.mode}")

    scanned = 0
    skipped_dup = 0
    processed = 0
    not_forwarded = 0

    if notify_chat_id:
        try:
            await bot_client.send_message(
                notify_chat_id,
                f"开始回填：规则 {rule.id}，来源 {rule.source_chat.name} -> 目标 {rule.target_chat.name}\n范围：{mode_desc}",
            )
        except Exception:
            pass
    logger.info(
        f"回填开始：规则 {rule.id}，来源 {rule.source_chat.name} -> 目标 {rule.target_chat.name}，范围：{mode_desc}"
    )

    last_report_time = datetime.now(timezone)
    stopped = False
    throttle = None
    if params.adaptive_throttle:
        throttle = BackfillThrottle(
            min_delay=params.throttle_min_delay,
            max_delay=params.throttle_max_delay,
            increase_step=params.throttle_increase_step,
            decrease_step=params.throttle_decrease_step,
            cooldown_threshold=params.throttle_cooldown_threshold,
        )

    try:
        async for message in iterator:
            if stop_event and stop_event.is_set():
                stopped = True
                break

            scanned += 1

            event = BackfillEvent(message, user_client)
            try:
                dedup_key = build_dedup_key(event)
                if not dedup_key:
                    continue

                if is_processed(rule.id, dedup_key):
                    skipped_dup += 1
                    continue

                flood_wait_seconds = None
                if rule.use_bot:
                    ok = await process_forward_rule(bot_client, event, str(source_chat_id), rule)
                else:
                    ok, flood_wait_seconds = await user_handler.process_forward_rule(
                        user_client, event, str(source_chat_id), rule
                    )

                if ok is None:
                    ok = True

                if ok:
                    processed += 1
                    if not claim_processed(rule.id, dedup_key):
                        logger.warning(f"回填去重写入失败或已存在: rule={rule.id}, key={dedup_key}")
                    if throttle:
                        if flood_wait_seconds:
                            throttle.on_flood_wait(flood_wait_seconds)
                        else:
                            throttle.on_success()
                else:
                    not_forwarded += 1
                    if throttle:
                        if flood_wait_seconds:
                            throttle.on_flood_wait(flood_wait_seconds)
                        else:
                            throttle.on_failure()
            except asyncio.CancelledError:
                stopped = True
                raise
            except Exception as e:
                logger.error(f"回填处理消息失败: rule={rule.id}, key={dedup_key}, err={str(e)}")
                not_forwarded += 1
                if throttle:
                    throttle.on_failure()

            delay_seconds = 0.0
            if params.message_delay_seconds > 0:
                delay_seconds = params.message_delay_seconds
            if throttle:
                delay_seconds = max(delay_seconds, throttle.delay)
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

            if notify_chat_id and (datetime.now(timezone) - last_report_time).total_seconds() >= 30:
                last_report_time = datetime.now(timezone)
                try:
                    await bot_client.send_message(
                        notify_chat_id,
                        f"回填进度：已扫描 {scanned}，已处理 {processed}，已跳过 {skipped_dup}，未转发 {not_forwarded}",
                    )
                except Exception:
                    pass
                logger.info(
                    f"回填进度：已扫描 {scanned}，已处理 {processed}，已跳过 {skipped_dup}，未转发 {not_forwarded}"
                )
    except asyncio.CancelledError:
        stopped = True

    if notify_chat_id:
        try:
            if stopped:
                await bot_client.send_message(
                    notify_chat_id,
                    f"回填已停止：已扫描 {scanned}，已处理 {processed}，已跳过 {skipped_dup}，未转发 {not_forwarded}",
                )
            else:
                await bot_client.send_message(
                    notify_chat_id,
                    f"回填完成：已扫描 {scanned}，已处理 {processed}，已跳过 {skipped_dup}，未转发 {not_forwarded}",
                )
        except Exception:
            pass
    if stopped:
        logger.info(
            f"回填已停止：已扫描 {scanned}，已处理 {processed}，已跳过 {skipped_dup}，未转发 {not_forwarded}"
        )
    else:
        logger.info(
            f"回填完成：已扫描 {scanned}，已处理 {processed}，已跳过 {skipped_dup}，未转发 {not_forwarded}"
        )


async def run_video_forward(
    *,
    bot_client,
    user_client,
    forward_client,
    rule_id: int,
    params: BackfillParams,
    notify_chat_id: Optional[int] = None,
    stop_event: Optional[asyncio.Event] = None,
):
    rule = _load_rule_for_processing(rule_id)
    if not rule:
        raise ValueError(f"找不到规则: {rule_id}")

    if not rule.enable_rule:
        raise ValueError(f"规则未启用: {rule_id}")

    source_chat_id = int(rule.source_chat.telegram_chat_id)
    target_chat_id = int(rule.target_chat.telegram_chat_id)

    timezone = _get_timezone()
    now = datetime.now(timezone)

    if params.mode == "last":
        if not params.limit or params.limit <= 0:
            raise ValueError("last 模式需要提供正整数 limit")
        iterator = _iter_last_messages(user_client, source_chat_id, params.limit, stop_event)
        mode_desc = f"最近 {params.limit} 条"
    elif params.mode == "range":
        if not params.start_time or not params.end_time:
            raise ValueError("range 模式需要提供 start_time/end_time")
        iterator = _iter_messages_by_time_range(
            user_client,
            source_chat_id,
            params.start_time,
            params.end_time,
            params.batch_size,
            params.batch_delay_seconds,
            stop_event,
        )
        mode_desc = f"{params.start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ {params.end_time.strftime('%Y-%m-%d %H:%M:%S')}"
    elif params.mode == "all":
        start_time = timezone.localize(datetime(1970, 1, 1, 0, 0, 0))
        end_time = now
        iterator = _iter_messages_by_time_range(
            user_client,
            source_chat_id,
            start_time,
            end_time,
            params.batch_size,
            params.batch_delay_seconds,
            stop_event,
        )
        mode_desc = "全部历史"
    else:
        raise ValueError(f"未知回填模式: {params.mode}")

    scanned = 0
    skipped_dup = 0
    skipped_non_video = 0
    skipped_media_filter = 0
    fallback_user_forwarded = 0
    skipped_keyword = 0
    processed = 0
    not_forwarded = 0
    allow_over_limit_fallback_to_user = _get_env_bool(
        "VIDEO_FORWARD_OVER_LIMIT_FALLBACK_TO_USER",
        False,
    )

    if notify_chat_id:
        try:
            await bot_client.send_message(
                notify_chat_id,
                (
                    f"开始转发视频：规则 {rule.id}，来源 {rule.source_chat.name} -> 目标 {rule.target_chat.name}\n"
                    f"范围：{mode_desc}（仅保留关键字筛选）"
                ),
            )
        except Exception:
            pass
    logger.info(
        f"视频转发开始：规则 {rule.id}，来源 {rule.source_chat.name} -> 目标 {rule.target_chat.name}，范围：{mode_desc}"
    )

    last_report_time = datetime.now(timezone)
    stopped = False
    throttle = None
    if params.adaptive_throttle:
        throttle = BackfillThrottle(
            min_delay=params.throttle_min_delay,
            max_delay=params.throttle_max_delay,
            increase_step=params.throttle_increase_step,
            decrease_step=params.throttle_decrease_step,
            cooldown_threshold=params.throttle_cooldown_threshold,
        )

    try:
        async for message in iterator:
            if stop_event and stop_event.is_set():
                stopped = True
                break

            scanned += 1

            event = BackfillEvent(message, user_client)
            try:
                dedup_key = build_dedup_key(event)
                if not dedup_key:
                    continue

                if is_processed(rule.id, dedup_key):
                    skipped_dup += 1
                    continue

                grouped_id = getattr(message, "grouped_id", None)
                pass_message_ids = []
                over_message_ids = []
                message_text = ""
                use_merge_caption = False
                video_messages = None

                if grouped_id:
                    group_messages = await _collect_media_group_messages(user_client, message)
                    video_messages = [item for item in group_messages if _is_video_message(item)]
                    if not video_messages:
                        skipped_non_video += 1
                        continue

                    passed_videos = []
                    over_limit_videos = []
                    for item in video_messages:
                        if await _passes_media_filters(rule, item):
                            passed_videos.append(item)
                        else:
                            over_limit_videos.append(item)
                    if not passed_videos and not over_limit_videos:
                        continue
                    message_text = _extract_group_text(group_messages)
                    use_merge_caption = bool(message_text)
                    pass_message_ids = [item.id for item in passed_videos]
                    over_message_ids = [item.id for item in over_limit_videos]
                else:
                    if not _is_video_message(message):
                        skipped_non_video += 1
                        continue
                    if await _passes_media_filters(rule, message):
                        pass_message_ids = [message.id]
                    else:
                        over_message_ids = [message.id]
                    message_text = _get_message_text(message)

                should_forward = await check_keywords(rule, message_text, event)
                if not should_forward:
                    skipped_keyword += 1
                    continue

                if over_message_ids:
                    if allow_over_limit_fallback_to_user:
                        logger.info(
                            f"规则 {rule.id} 媒体超限 {len(over_message_ids)} 条，兼容模式下改用用户账号转发"
                        )
                    else:
                        skipped_media_filter += len(over_message_ids)
                        logger.info(
                            f"规则 {rule.id} 媒体超限 {len(over_message_ids)} 条，严格模式下跳过，不降级到用户账号转发"
                        )
                        over_message_ids = []

                if not pass_message_ids and not over_message_ids:
                    continue

                if use_merge_caption and (pass_message_ids or over_message_ids):
                    caption = message_text or ""
                    ok = False
                    flood_wait_seconds = None
                    caption_for_pass = caption if pass_message_ids else ""
                    caption_for_over = caption if over_message_ids else ""
                    ok = True

                    if pass_message_ids:
                        ok_pass, wait_pass = await _forward_messages_with_flood_wait_custom_caption(
                            forward_client,
                            target_chat_id,
                            pass_message_ids,
                            source_chat_id,
                            rule.id,
                            caption_for_pass,
                        )
                        ok = ok and ok_pass
                        if wait_pass:
                            flood_wait_seconds = max(flood_wait_seconds or 0, wait_pass)

                    if over_message_ids:
                        ok_over, wait_over = await _forward_messages_with_flood_wait_custom_caption(
                            user_client,
                            target_chat_id,
                            over_message_ids,
                            source_chat_id,
                            rule.id,
                            caption_for_over,
                        )
                        ok = ok and ok_over
                        if wait_over:
                            flood_wait_seconds = max(flood_wait_seconds or 0, wait_over)
                        if ok_over:
                            fallback_user_forwarded += len(over_message_ids)
                else:
                    ok = True
                    flood_wait_seconds = None

                    if pass_message_ids:
                        ok_pass, wait_pass = await _forward_with_flood_wait(
                            forward_client, target_chat_id, pass_message_ids, source_chat_id, rule.id
                        )
                        ok = ok and ok_pass
                        if wait_pass:
                            flood_wait_seconds = max(flood_wait_seconds or 0, wait_pass)

                    if over_message_ids:
                        ok_over, wait_over = await _forward_with_flood_wait(
                            user_client, target_chat_id, over_message_ids, source_chat_id, rule.id
                        )
                        ok = ok and ok_over
                        if wait_over:
                            flood_wait_seconds = max(flood_wait_seconds or 0, wait_over)
                        if ok_over:
                            fallback_user_forwarded += len(over_message_ids)

                if ok:
                    processed += 1
                    if not claim_processed(rule.id, dedup_key):
                        logger.warning(f"视频转发去重写入失败或已存在: rule={rule.id}, key={dedup_key}")
                    if throttle:
                        if flood_wait_seconds:
                            throttle.on_flood_wait(flood_wait_seconds)
                        else:
                            throttle.on_success()
                else:
                    not_forwarded += 1
                    if throttle:
                        if flood_wait_seconds:
                            throttle.on_flood_wait(flood_wait_seconds)
                        else:
                            throttle.on_failure()
            except asyncio.CancelledError:
                stopped = True
                raise
            except Exception as e:
                logger.error(f"视频转发处理消息失败: rule={rule.id}, err={str(e)}")
                not_forwarded += 1
                if throttle:
                    throttle.on_failure()

            delay_seconds = 0.0
            if params.message_delay_seconds > 0:
                delay_seconds = params.message_delay_seconds
            if throttle:
                delay_seconds = max(delay_seconds, throttle.delay)
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

            if notify_chat_id and (datetime.now(timezone) - last_report_time).total_seconds() >= 30:
                last_report_time = datetime.now(timezone)
                try:
                    await bot_client.send_message(
                        notify_chat_id,
                        (
                            f"视频转发进度：已扫描 {scanned}，已处理 {processed}，"
                            f"跳过非视频 {skipped_non_video}，跳过筛选 {skipped_media_filter}，"
                            f"兼容降级转发 {fallback_user_forwarded}，"
                            f"跳过关键字 {skipped_keyword}，"
                            f"已跳过 {skipped_dup}，未转发 {not_forwarded}"
                        ),
                    )
                except Exception:
                    pass
                logger.info(
                    "视频转发进度：已扫描 %s，已处理 %s，跳过非视频 %s，跳过筛选 %s，兼容降级转发 %s，跳过关键字 %s，已跳过 %s，未转发 %s",
                    scanned,
                    processed,
                    skipped_non_video,
                    skipped_media_filter,
                    fallback_user_forwarded,
                    skipped_keyword,
                    skipped_dup,
                    not_forwarded,
                )
    except asyncio.CancelledError:
        stopped = True

    if notify_chat_id:
        try:
            if stopped:
                await bot_client.send_message(
                    notify_chat_id,
                    (
                        f"视频转发已停止：已扫描 {scanned}，已处理 {processed}，"
                        f"跳过非视频 {skipped_non_video}，跳过筛选 {skipped_media_filter}，"
                        f"兼容降级转发 {fallback_user_forwarded}，"
                        f"跳过关键字 {skipped_keyword}，"
                        f"已跳过 {skipped_dup}，未转发 {not_forwarded}"
                    ),
                )
            else:
                await bot_client.send_message(
                    notify_chat_id,
                    (
                        f"视频转发完成：已扫描 {scanned}，已处理 {processed}，"
                        f"跳过非视频 {skipped_non_video}，跳过筛选 {skipped_media_filter}，"
                        f"兼容降级转发 {fallback_user_forwarded}，"
                        f"跳过关键字 {skipped_keyword}，"
                        f"已跳过 {skipped_dup}，未转发 {not_forwarded}"
                    ),
                )
        except Exception:
            pass

    if stopped:
        logger.info(
            "视频转发已停止：已扫描 %s，已处理 %s，跳过非视频 %s，跳过筛选 %s，兼容降级转发 %s，跳过关键字 %s，已跳过 %s，未转发 %s",
            scanned,
            processed,
            skipped_non_video,
            skipped_media_filter,
            fallback_user_forwarded,
            skipped_keyword,
            skipped_dup,
            not_forwarded,
        )
    else:
        logger.info(
            "视频转发完成：已扫描 %s，已处理 %s，跳过非视频 %s，跳过筛选 %s，兼容降级转发 %s，跳过关键字 %s，已跳过 %s，未转发 %s",
            scanned,
            processed,
            skipped_non_video,
            skipped_media_filter,
            fallback_user_forwarded,
            skipped_keyword,
            skipped_dup,
            not_forwarded,
        )
