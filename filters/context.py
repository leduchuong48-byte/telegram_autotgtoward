import copy

class MessageContext:
    """
    消息上下文类，包含处理消息所需的所有信息
    """
    
    def __init__(self, client, event, chat_id, rule):
        """
        初始化消息上下文
        
        Args:
            client: 机器人客户端
            event: 消息事件
            chat_id: 聊天ID
            rule: 转发规则
        """
        self.client = client
        self.event = event
        self.chat_id = chat_id
        self.rule = rule
        
        # 初始消息文本，保持不变用于引用
        self.original_message_text = event.message.text or ''
        
        # 当前处理的消息文本
        self.message_text = event.message.text or ''
        
        # 用于检查的消息文本（可能包含发送者信息等）
        self.check_message_text = event.message.text or ''
        
        # 记录处理过程中的媒体文件
        self.media_files = []
        
        # 记录发送者信息
        self.sender_info = ''
        
        # 记录时间信息
        self.time_info = ''
        
        # 原始链接
        self.original_link = ''
        
        # 按钮
        self.buttons = event.message.buttons if hasattr(event.message, 'buttons') else None
        
        # 是否继续处理
        self.should_forward = True

        # 是否直接转发原消息（避免下载）
        self.forward_via_forward_messages = False
        
        # 用于记录媒体组消息
        self.is_media_group = event.message.grouped_id is not None
        self.media_group_id = event.message.grouped_id
        self.media_group_messages = []
        
        # 用于跟踪被跳过的超大媒体
        self.skipped_media = []
        
        # 记录任何可能的错误
        self.errors = []
        
        # 记录已转发的消息
        self.forwarded_messages = []
        
        # 评论区链接
        self.comment_link = None
        
    def clone(self):
        """创建上下文的副本"""
        return copy.deepcopy(self) 
