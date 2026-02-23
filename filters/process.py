import logging
from filters.filter_chain import FilterChain
from filters.keyword_filter import KeywordFilter
from filters.replace_filter import ReplaceFilter
from filters.ai_filter import AIFilter
from filters.info_filter import InfoFilter
from filters.media_filter import MediaFilter
from filters.sender_filter import SenderFilter
from filters.delete_original_filter import DeleteOriginalFilter
from filters.delay_filter import DelayFilter
from filters.edit_filter import EditFilter
from filters.comment_button_filter import CommentButtonFilter
from filters.init_filter import InitFilter
from filters.reply_filter import ReplyFilter
from filters.rss_filter import RSSFilter
from filters.push_filter import PushFilter
logger = logging.getLogger(__name__)

async def process_forward_rule(client, event, chat_id, rule):
    """
    处理转发规则
    
    Args:
        client: 机器人客户端
        event: 消息事件
        chat_id: 聊天ID
        rule: 转发规则
        
    Returns:
        bool: 处理是否成功
    """
    logger.info(f'使用过滤器链处理规则 ID: {rule.id}')
    
    # 创建过滤器链
    filter_chain = FilterChain()

    # 添加初始化过滤器
    filter_chain.add_filter(InitFilter())

    # 延迟处理过滤器（如果启用了延迟处理）
    filter_chain.add_filter(DelayFilter())
    
    # 添加关键字过滤器（如果消息不匹配关键字，会中断处理链）
    filter_chain.add_filter(KeywordFilter())
    
    # 添加替换过滤器
    filter_chain.add_filter(ReplaceFilter())

    # 添加媒体过滤器（处理媒体内容）
    filter_chain.add_filter(MediaFilter())
    
    # 添加AI处理过滤器（如果启用了AI处理后的关键字检查，可能会中断处理链）
    filter_chain.add_filter(AIFilter())
    
    # 添加信息过滤器（处理原始链接和发送者信息）
    filter_chain.add_filter(InfoFilter())
    
    # 添加评论区按钮过滤器
    filter_chain.add_filter(CommentButtonFilter())

    # 添加RSS过滤器
    filter_chain.add_filter(RSSFilter())
    
    # 添加编辑过滤器（编辑原始消息）
    filter_chain.add_filter(EditFilter())

    # 添加发送过滤器（发送消息）
    filter_chain.add_filter(SenderFilter())
    
    # 添加回复过滤器（处理媒体组消息的评论区按钮）
    filter_chain.add_filter(ReplyFilter())

    # 添加推送过滤器
    filter_chain.add_filter(PushFilter())
    
    # 添加删除原始消息过滤器（最后执行）
    filter_chain.add_filter(DeleteOriginalFilter())
    
    # 执行过滤器链
    result = await filter_chain.process(client, event, chat_id, rule)
    
    return result 
