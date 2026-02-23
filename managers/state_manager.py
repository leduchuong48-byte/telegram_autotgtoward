import logging
from typing import Dict, Tuple, Optional, Union
from telethon.tl.custom import Message

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self):
        self._states: Dict[Tuple[int, int], Tuple[str, Optional[Message], Optional[str]]] = {}
        logger.info("StateManager 初始化")
    
    def set_state(self, user_id: int, chat_id: int, state: str, message: Optional[Message] = None, state_type: Optional[str] = None) -> None:
        """设置用户状态"""
        key = (user_id, chat_id)
        self._states[key] = (state, message, state_type)
        logger.info(f"设置状态 - key: {key}, state: {state}, type: {state_type}")
        logger.debug(f"当前所有状态: {self._states}")  # 改为 debug 级别
    
    def get_state(self, user_id: int, chat_id: int) -> Union[Tuple[str, Optional[Message], Optional[str]], Tuple[None, None, None]]:
        """获取用户状态"""
        key = (user_id, chat_id)
        state_data = self._states.get(key)
        if state_data:  # 只在状态存在时记录日志
            if len(state_data) == 3:  # 兼容新格式
                state, message, state_type = state_data
                logger.info(f"获取状态 - key: {key}, state: {state}, type: {state_type}")
            else:  # 兼容旧格式
                state, message = state_data
                state_type = None
                logger.info(f"获取状态 - key: {key}, state: {state}, type: None (旧格式)")
            return state, message, state_type
        return None, None, None
    
    def clear_state(self, user_id: int, chat_id: int) -> None:
        """清除用户状态"""
        key = (user_id, chat_id)
        if key in self._states:
            del self._states[key]
            logger.info(f"清除状态 - key: {key}")
        logger.debug(f"当前所有状态: {self._states}")  # 改为 debug 级别
    
    def check_state(self) -> bool:
        """检查是否存在状态"""
        return bool(self._states)

# 创建全局实例
state_manager = StateManager()
logger.info("StateManager 全局实例已创建")