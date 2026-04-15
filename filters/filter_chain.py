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

    @staticmethod
    def _reason_from_filter_name(name: str) -> str:
        mapping = {
            'KeywordFilter': 'keyword',
            'MediaFilter': 'media_type',
            'AIFilter': 'ai_blocked',
            'RSSFilter': 'filter_chain_blocked',
            'SenderFilter': 'forward_failed',
            'ReplyFilter': 'reply_failed',
            'PushFilter': 'push_failed',
            'EditFilter': 'edit_failed',
            'DelayFilter': 'delayed',
            'DeleteOriginalFilter': 'delete_original',
        }
        return mapping.get(name, 'filter_chain_blocked')
        
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
            dict: {ok, stop_reason, stop_reason_detail}
        """
        # 创建消息上下文
        context = MessageContext(client, event, chat_id, rule)
        
        logger.info(f"开始过滤器链处理，共 {len(self.filters)} 个过滤器")
        
        # 依次执行每个过滤器
        for filter_obj in self.filters:
            try:
                should_continue = await filter_obj.process(context)
                if getattr(context, 'should_forward', True) is False:
                    if not getattr(context, 'stop_reason', None):
                        context.stop_reason = self._reason_from_filter_name(filter_obj.name)
                        context.stop_reason_detail = f'{filter_obj.name} set should_forward=false'
                    if not getattr(context, 'stop_stage', None):
                        context.stop_stage = filter_obj.name
                if not should_continue:
                    if not getattr(context, 'stop_reason', None):
                        context.stop_reason = self._reason_from_filter_name(filter_obj.name)
                    if not getattr(context, 'stop_reason_detail', None):
                        context.stop_reason_detail = f'{filter_obj.name} stopped processing chain'
                    if not getattr(context, 'stop_stage', None):
                        context.stop_stage = filter_obj.name
                    logger.info(f"过滤器 {filter_obj.name} 中断了处理链")
                    return {
                        "ok": False,
                        "stop_reason": getattr(context, 'stop_reason', None),
                        "stop_reason_detail": getattr(context, 'stop_reason_detail', ''),
                        "stop_stage": getattr(context, 'stop_stage', ''),
                    }
            except Exception as e:
                logger.error(f"过滤器 {filter_obj.name} 处理出错: {str(e)}")
                context.errors.append(f"过滤器 {filter_obj.name} 错误: {str(e)}")
                context.stop_reason = 'exception'
                context.stop_reason_detail = f'{filter_obj.name} exception: {str(e)}'
                context.stop_stage = filter_obj.name
                return {
                    "ok": False,
                    "stop_reason": context.stop_reason,
                    "stop_reason_detail": context.stop_reason_detail,
                    "stop_stage": context.stop_stage,
                }
        
        logger.info("过滤器链处理完成")
        return {
            "ok": True,
            "stop_reason": None,
            "stop_reason_detail": '',
            "stop_stage": None,
        }
