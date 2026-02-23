import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseFilter(ABC):
    """
    基础过滤器类，定义过滤器接口
    """
    
    def __init__(self, name=None):
        """
        初始化过滤器
        
        Args:
            name: 过滤器名称，如果为None则使用类名
        """
        self.name = name or self.__class__.__name__
        
    async def process(self, context):
        """
        处理消息上下文
        
        Args:
            context: 包含消息处理所需所有信息的上下文对象
            
        Returns:
            bool: 表示是否应该继续处理消息
        """
        logger.debug(f"开始执行过滤器: {self.name}")
        result = await self._process(context)
        logger.debug(f"过滤器 {self.name} 处理结果: {'通过' if result else '不通过'}")
        return result
    
    @abstractmethod
    async def _process(self, context):
        """
        具体的处理逻辑，子类需要实现
        
        Args:
            context: 包含消息处理所需所有信息的上下文对象
            
        Returns:
            bool: 表示是否应该继续处理消息
        """
        pass 