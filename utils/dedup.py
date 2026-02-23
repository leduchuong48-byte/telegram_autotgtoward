import logging

from sqlalchemy.exc import IntegrityError

from models.models import ProcessedMessage, get_session

logger = logging.getLogger(__name__)


def build_dedup_key(event) -> str | None:
    """
    生成幂等去重键（同一规则内唯一）。

    - 媒体组：按 grouped_id 去重（整个 album 视为一次处理）
    - 普通消息：按 message.id 去重
    """
    try:
        message = getattr(event, "message", None)
        if not message:
            return None

        grouped_id = getattr(message, "grouped_id", None)
        if grouped_id:
            return f"g:{grouped_id}"

        message_id = getattr(message, "id", None)
        if message_id is None:
            return None

        return f"m:{message_id}"
    except Exception as e:
        logger.error(f"生成去重键失败: {str(e)}")
        return None


def claim_processed(rule_id: int, dedup_key: str) -> bool:
    """
    先占位再处理：确保“绝不重复”。

    返回 True 表示本次获得处理权；False 表示已处理/已占位，应跳过。
    """
    session = get_session()
    try:
        session.add(ProcessedMessage(rule_id=rule_id, dedup_key=dedup_key))
        session.commit()
        return True
    except IntegrityError:
        session.rollback()
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"写入去重记录失败: {str(e)}")
        return False
    finally:
        session.close()


def is_processed(rule_id: int, dedup_key: str) -> bool:
    """检查是否已处理过（不写入）。"""
    session = get_session()
    try:
        exists = (
            session.query(ProcessedMessage)
            .filter(ProcessedMessage.rule_id == rule_id, ProcessedMessage.dedup_key == dedup_key)
            .first()
            is not None
        )
        return exists
    except Exception as e:
        logger.error(f"查询去重记录失败: {str(e)}")
        return False
    finally:
        session.close()
