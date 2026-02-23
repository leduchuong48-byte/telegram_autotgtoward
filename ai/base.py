from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

class BaseAIProvider(ABC):
    """AI提供者的基类"""
    
    @abstractmethod
    async def process_message(self, 
                            message: str, 
                            prompt: Optional[str] = None,
                            images: Optional[List[Dict[str, str]]] = None,
                            **kwargs) -> str:
        """
        处理消息的抽象方法
        
        Args:
            message: 要处理的消息内容
            prompt: 可选的提示词
            images: 可选的图片列表，每个图片是一个字典，包含data和mime_type
            **kwargs: 其他参数
            
        Returns:
            str: 处理后的消息
        """
        pass
    
    @abstractmethod
    async def initialize(self, **kwargs) -> None:
        """初始化AI提供者"""
        pass