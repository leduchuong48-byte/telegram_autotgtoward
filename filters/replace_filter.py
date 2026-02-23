import logging
import re
from filters.base_filter import BaseFilter

logger = logging.getLogger(__name__)

class ReplaceFilter(BaseFilter):
    """
    替换过滤器，根据规则替换消息文本
    """
    
    async def _process(self, context):
        """
        处理消息文本替换
        
        Args:
            context: 消息上下文
            
        Returns:
            bool: 是否继续处理
        """
        rule = context.rule
        message_text = context.message_text

        #打印context的所有属性
        # logger.info(f"ReplaceFilter处理消息前，context: {context.__dict__}")
        # 如果不需要替换，直接返回
        if not rule.is_replace or not message_text:
            return True
        
        try:
            # 应用所有替换规则
            for replace_rule in rule.replace_rules:
                if replace_rule.pattern == '.*':
                    # 全文替换
                    logger.info(f'执行全文替换:\n原文: "{message_text}"\n替换为: "{replace_rule.content or ""}"')
                    message_text = replace_rule.content or ''
                    break  # 如果是全文替换，就不继续处理其他规则
                else:
                    try:
                        # 正则替换
                        old_text = message_text
                        matches = re.finditer(replace_rule.pattern, message_text)
                        message_text = re.sub(
                            replace_rule.pattern,
                            replace_rule.content or '',
                            message_text
                        )
                        if old_text != message_text:
                            matched_texts = [m.group(0) for m in matches]
                            logger.info(f'执行部分替换:\n原文: "{old_text}"\n匹配内容: {matched_texts}\n替换规则: "{replace_rule.pattern}" -> "{replace_rule.content}"\n替换后: "{message_text}"')
                    except re.error as e:
                        logger.error(f'替换规则格式错误: {replace_rule.pattern}, 错误: {str(e)}')
            
            # 更新上下文中的消息文本
            context.message_text = message_text
            context.check_message_text = message_text
            
            return True
        except Exception as e:
            logger.error(f'应用替换规则时出错: {str(e)}')
            context.errors.append(f"替换规则错误: {str(e)}")
            return True  # 即使替换出错，仍然继续处理 
        finally:
            # logger.info(f"ReplaceFilter处理消息后，context: {context.__dict__}")
            pass