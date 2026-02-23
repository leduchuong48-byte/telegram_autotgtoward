import logging
from filters.base_filter import BaseFilter
from filters.context import MessageContext

logger = logging.getLogger(__name__)

class FilterChain:
    """
    过滤器链，用于组织和执行多个过滤器
    """
    
    def __init__(self):
        """初始化过滤器链"""
        self.filters = []
        
    def add_filter(self, filter_obj):
        """
        添加过滤器到链中
        
        Args:
            filter_obj: 要添加的过滤器对象，必须是BaseFilter的子类
        """
        if not isinstance(filter_obj, BaseFilter):
            raise TypeError("过滤器必须是BaseFilter的子类")
        self.filters.append(filter_obj)
        return self
        
    async def process(self, client, event, chat_id, rule):
        """
        处理消息
        
        Args:
            client: 机器人客户端
            event: 消息事件
            chat_id: 聊天ID
            rule: 转发规则
            
        Returns:
            bool: 表示处理是否成功
        """
        # 创建消息上下文
        context = MessageContext(client, event, chat_id, rule)
        
        logger.info(f"开始过滤器链处理，共 {len(self.filters)} 个过滤器")
        
        # 依次执行每个过滤器
        for filter_obj in self.filters:
            try:
                should_continue = await filter_obj.process(context)
                if not should_continue:
                    logger.info(f"过滤器 {filter_obj.name} 中断了处理链")
                    return False
            except Exception as e:
                logger.error(f"过滤器 {filter_obj.name} 处理出错: {str(e)}")
                context.errors.append(f"过滤器 {filter_obj.name} 错误: {str(e)}")
                return False
        
        logger.info("过滤器链处理完成")
        return True 