from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class Media(BaseModel):
    """媒体文件信息"""
    url: str
    type: str
    size: int = 0
    filename: str
    original_name: Optional[str] = None

    def get(self, key: str, default: Any = None) -> Any:
        """获取属性值，如果不存在返回默认值"""
        return getattr(self, key, default)

class Entry(BaseModel):
    """RSS条目数据模型"""
    id: Optional[str] = None
    rule_id: int
    message_id: str
    title: str
    content: str
    published: str  # ISO格式的日期时间字符串
    author: str = ""
    link: str = ""
    media: List[Media] = []
    created_at: Optional[str] = None  # 添加到系统的时间 
    original_link: Optional[str] = None
    sender_info: Optional[str] = None

    
    def __init__(self, **data):
        # 处理媒体数据，确保它是Media对象列表
        if "media" in data and isinstance(data["media"], list):
            media_list = []
            for item in data["media"]:
                try:
                    if isinstance(item, dict):
                        media_list.append(Media(**item))
                    elif not isinstance(item, Media):
                        # 尝试转换为字典
                        if hasattr(item, '__dict__'):
                            media_list.append(Media(**item.__dict__))
                    else:
                        media_list.append(item)
                except Exception as e:
                    # 忽略无法转换的媒体项
                    pass
            data["media"] = media_list
            
        # 确保必要字段有默认值
        if "message_id" not in data and "id" in data:
            data["message_id"] = data["id"]
            
        # 调用父类初始化
        super().__init__(**data) 