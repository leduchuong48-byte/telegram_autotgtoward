import logging
import re
from utils.common import get_sender_info,check_keywords
from filters.base_filter import BaseFilter
from enums.enums import ForwardMode

logger = logging.getLogger(__name__)

class KeywordFilter(BaseFilter):
    """
    关键字过滤器，检查消息是否包含指定关键字
    """
    
    async def _process(self, context):
        """
        检查消息是否包含规则中的关键字
        
        Args:
            context: 消息上下文
            
        Returns:
            bool: 若消息应继续处理则返回True，否则返回False
        """
        rule = context.rule
        message_text = context.message_text
        event = context.event

        
        should_forward = await check_keywords(rule, message_text, event)
        
        return should_forward
    
