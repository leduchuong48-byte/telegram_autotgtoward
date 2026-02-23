import asyncio
from datetime import datetime, timedelta
import pytz
from models.models import get_session, ForwardRule
import logging
import os
from dotenv import load_dotenv
from telethon import TelegramClient, errors
from ai import get_ai_provider
import traceback
from utils.constants import DEFAULT_TIMEZONE,DEFAULT_AI_MODEL,DEFAULT_SUMMARY_PROMPT

logger = logging.getLogger(__name__)

# Telegram's maximum message size limit (4096 characters)
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
# Maximum length for each summary message part, leaving headroom for metadata or formatting
MAX_MESSAGE_PART_LENGTH = TELEGRAM_MAX_MESSAGE_LENGTH - 300
# Maximum number of attempts for sending messages
MAX_SEND_ATTEMPTS = 2

class SummaryScheduler:
    def __init__(self, user_client: TelegramClient, bot_client: TelegramClient):
        self.tasks = {}  # 存储所有定时任务 {rule_id: task}
        self.timezone = pytz.timezone(DEFAULT_TIMEZONE)
        self.user_client = user_client
        self.bot_client = bot_client
        # 添加信号量来限制并发请求
        self.request_semaphore = asyncio.Semaphore(2)  # 最多同时执行2个请求
        # 从环境变量获取配置
        self.batch_size = int(os.getenv('SUMMARY_BATCH_SIZE', 20))
        self.batch_delay = int(os.getenv('SUMMARY_BATCH_DELAY', 2))

    async def schedule_rule(self, rule):
        """为规则创建或更新定时任务"""
        try:
            # 如果规则已有任务，先取消
            if rule.id in self.tasks:
                old_task = self.tasks[rule.id]
                old_task.cancel()
                logger.info(f"已取消规则 {rule.id} 的旧任务")
                del self.tasks[rule.id]

            # 如果启用了AI总结，创建新任务
            if rule.is_summary:
                # 计算下一次执行时间
                now = datetime.now(self.timezone)
                next_time = self._get_next_run_time(now, rule.summary_time)
                wait_seconds = (next_time - now).total_seconds()

                logger.info(f"规则 {rule.id} 的下一次执行时间: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"等待时间: {wait_seconds:.2f} 秒")

                task = asyncio.create_task(self._run_summary_task(rule))
                self.tasks[rule.id] = task
                logger.info(f"已为规则 {rule.id} 创建新的总结任务，时间: {rule.summary_time}")
            else:
                logger.info(f"规则 {rule.id} 的总结功能已关闭，不创建新任务")

        except Exception as e:
            logger.error(f"调度规则 {rule.id} 时出错: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")

    async def _run_summary_task(self, rule):
        """运行单个规则的总结任务"""
        while True:
            try:
                # 计算下一次执行时间
                now = datetime.now(self.timezone)
                target_time = self._get_next_run_time(now, rule.summary_time)

                # 等待到执行时间
                wait_seconds = (target_time - now).total_seconds()
                await asyncio.sleep(wait_seconds)

                # 执行总结任务
                await self._execute_summary(rule.id)

            except asyncio.CancelledError:
                logger.info(f"规则 {rule.id} 的旧任务已取消")
                break
            except Exception as e:
                logger.error(f"规则 {rule.id} 的总结任务出错: {str(e)}")
                await asyncio.sleep(60)  # 出错后等待一分钟再重试

    def _split_message(self, text: str, max_length: int = MAX_MESSAGE_PART_LENGTH):
        if not text:
            return []

        parts = []
        while len(text) > 0:
            # Strip any leading whitespace from the remaining text to prevent empty parts.
            text = text.lstrip()
            if not text:
                break

            if len(text) <= max_length:
                parts.append(text)
                break

            # Find the best split position, searching backwards from max_length.
            split_pos = -1
            for sep in ('\n\n', '\n', ' '):
                pos = text.rfind(sep, 0, max_length)
                if pos > 0:
                    split_pos = pos
                    break
            if split_pos == -1:
                split_pos = max_length

            parts.append(text[:split_pos])
            text = text[split_pos:]

        return parts

    def _get_next_run_time(self, now, target_time):
        """计算下一次运行时间"""
        hour, minute = map(int, target_time.split(':'))
        next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if next_time <= now:
            next_time += timedelta(days=1)

        return next_time

    async def _execute_summary(self, rule_id, is_now=False):
        """执行单个规则的总结任务"""
        session = get_session()
        try:
            rule = session.query(ForwardRule).get(rule_id)
            if not is_now:
                if not rule or not rule.is_summary:
                    return

            try:
                source_chat_id = int(rule.source_chat.telegram_chat_id)
                target_chat_id = int(rule.target_chat.telegram_chat_id)

                messages = []

                # 计算时间范围
                now = datetime.now(self.timezone)
                summary_hour, summary_minute = map(int, rule.summary_time.split(':'))

                # 设置结束时间为当前时间
                end_time = now

                # 设置开始时间为前一天的总结时间
                start_time = now.replace(
                    hour=summary_hour,
                    minute=summary_minute,
                    second=0,
                    microsecond=0
                ) - timedelta(days=1)

                logger.info(f'规则 {rule_id} 获取消息时间范围: {start_time} 到 {end_time}')

                async with self.request_semaphore:
                    messages = []
                    current_offset = 0

                    while True:
                        batch = []  # 移到循环外部
                        messages_batch = await self.user_client.get_messages(
                            source_chat_id,
                            limit=self.batch_size,
                            offset_date=end_time,
                            offset_id=current_offset,
                            reverse=False
                        )

                        if not messages_batch:
                            logger.info(f'规则 {rule_id} 没有获取到新消息，退出循环')
                            break

                        logger.info(f'规则 {rule_id} 获取到批次消息数量: {len(messages_batch)}')

                        should_break = False
                        for message in messages_batch:
                            msg_time = message.date.astimezone(self.timezone)
                            preview = message.text[:20] + '...' if message.text else 'None'
                            logger.info(f'规则 {rule_id} 处理消息 - 时间: {msg_time}, 预览: {preview}, 长度: {len(message.text) if message.text else 0}')

                            # 跳过未来时间的消息
                            if msg_time > end_time:
                                continue

                            # 如果消息在有效时间范围内，添加到批次
                            if start_time <= msg_time <= end_time and message.text:
                                batch.append(message.text)

                            # 如果遇到早于开始时间的消息，标记退出
                            if msg_time < start_time:
                                logger.info(f'规则 {rule_id} 消息时间 {msg_time} 早于开始时间 {start_time}，停止获取')
                                should_break = True
                                break

                        # 如果当前批次有消息，添加到总消息列表
                        if batch:
                            messages.extend(batch)
                            logger.info(f'规则 {rule_id} 当前批次添加了 {len(batch)} 条消息，总消息数: {len(messages)}')

                        # 更新offset为最后一条消息的ID
                        current_offset = messages_batch[-1].id

                        # 如果需要退出循环
                        if should_break:
                            break

                        # 在批次之间等待
                        await asyncio.sleep(self.batch_delay)

                if not messages:
                    logger.info(f'规则 {rule_id} 没有需要总结的消息')
                    return

                all_messages = '\n'.join(messages)

                # 检查AI模型设置，如未设置则使用默认模型
                if not rule.ai_model:
                    rule.ai_model = DEFAULT_AI_MODEL
                    logger.info(f"使用默认AI模型进行总结: {rule.ai_model}")
                else:
                    logger.info(f"使用规则配置的AI模型进行总结: {rule.ai_model}")

                # 获取AI提供者并处理总结
                provider = await get_ai_provider(rule.ai_model)
                summary = await provider.process_message(
                    all_messages,
                    prompt=rule.summary_prompt or DEFAULT_SUMMARY_PROMPT,
                    model=rule.ai_model
                )


                if summary:
                    duration_hours = round((end_time - start_time).total_seconds() / 3600)
                    header = f"📋 {rule.source_chat.name} - {duration_hours}小时消息总结\n"
                    header += f"🕐 时间范围: {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%Y-%m-%d %H:%M')}\n"
                    header += f"📊 消息数量: {len(messages)} 条\n\n"

                    summary_parts = self._split_message(summary, MAX_MESSAGE_PART_LENGTH)

                    summary_message = None
                    for i, part in enumerate(summary_parts):
                        if i == 0:
                            message_to_send = header + part
                        else:
                            message_to_send = f"📋 {rule.source_chat.name} - 总结报告 (续 {i+1}/{len(summary_parts)})\n\n" + part

                        # 发送消息，支持重试机制
                        current_message = None
                        use_markdown = True
                        attempt = 0

                        while attempt < MAX_SEND_ATTEMPTS:
                            logger.info(f"Retry attempt {attempt + 1}/{MAX_SEND_ATTEMPTS} for sending message to chat ID {target_chat_id}.")
                            try:
                                if use_markdown:
                                    current_message = await self.bot_client.send_message(
                                        target_chat_id,
                                        message_to_send,
                                        parse_mode='markdown'
                                    )
                                else:
                                    # Fallback to plain text
                                    current_message = await self.bot_client.send_message(
                                        target_chat_id,
                                        message_to_send
                                    )
                                break  # Success, exit retry loop

                            except errors.MarkupInvalidError as e:
                                if use_markdown:
                                    logger.warning(f"Markdown解析失败: {e}. 降级为纯文本后重试。")
                                    use_markdown = False
                                    continue  # 立即重试，使用纯文本格式
                                else:
                                    # This should not happen, but if it does, it's a bug.
                                    logger.error(f"纯文本发送时出现意外的 MarkupInvalidError : {e}")
                                    raise # Fail fast

                            except errors.FloodWaitError as fwe:
                                if attempt < MAX_SEND_ATTEMPTS - 1:
                                    logger.warning(f"触发Telegram发送频率限制，等待 {fwe.seconds} 秒后重试...")
                                    await asyncio.sleep(fwe.seconds)
                                    attempt += 1
                                else:
                                    logger.error("重试次数已达上限，发送失败。")
                                    raise

                            except Exception as send_error:
                                logger.error(f"发送总结第 {i+1} 部分时出错: {str(send_error)}")
                                if attempt >= MAX_SEND_ATTEMPTS - 1:
                                    raise # Re-raise on last attempt
                                await asyncio.sleep(1) # Wait a bit before retrying on other errors
                                attempt += 1

                        # 统一处理第一条消息的赋值
                        if i == 0:
                            summary_message = current_message

                    if rule.is_top_summary and summary_message:
                        try:
                            await self.bot_client.pin_message(target_chat_id, summary_message)
                        except Exception as pin_error:
                            logger.warning(f"置顶总结消息失败: {str(pin_error)}")

                    logger.info(f'规则 {rule_id} 总结完成，共处理 {len(messages)} 条消息，分为 {len(summary_parts)} 部分发送')

            except Exception as e:
                logger.error(f'执行规则 {rule_id} 的总结任务时出错: {str(e)}')
                logger.error(f'错误详情: {traceback.format_exc()}')

        finally:
            session.close()

    async def start(self):
        """启动调度器"""
        logger.info("开始启动调度器...")
        session = get_session()
        try:
            # 获取所有启用了总结功能的规则
            rules = session.query(ForwardRule).filter_by(is_summary=True).all()
            logger.info(f"找到 {len(rules)} 个启用了总结功能的规则")

            for rule in rules:
                logger.info(f"正在为规则 {rule.id} ({rule.source_chat.name} -> {rule.target_chat.name}) 创建调度任务")
                logger.info(f"总结时间: {rule.summary_time}")

                # 计算下一次执行时间
                now = datetime.now(self.timezone)
                next_time = self._get_next_run_time(now, rule.summary_time)
                wait_seconds = (next_time - now).total_seconds()

                logger.info(f"下一次执行时间: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"等待时间: {wait_seconds:.2f} 秒")

                await self.schedule_rule(rule)

            if not rules:
                logger.info("没有找到启用了总结功能的规则")

            logger.info("调度器启动完成")
        except Exception as e:
            logger.error(f"启动调度器时出错: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
        finally:
            session.close()

    def stop(self):
        """停止所有任务"""
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()

    async def execute_all_summaries(self):
        """立即执行所有启用了总结功能的规则"""
        session = get_session()
        try:
            rules = session.query(ForwardRule).filter_by(is_summary=True).all()
            # 使用 gather 但限制并发数
            tasks = [self._execute_summary(rule.id, is_now=True) for rule in rules]
            for i in range(0, len(tasks), 2):  # 每次执行2个任务
                batch = tasks[i:i+2]
                await asyncio.gather(*batch)
                await asyncio.sleep(1)  # 每批次之间稍微暂停

        finally:
            session.close()
