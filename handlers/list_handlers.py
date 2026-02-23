from handlers.button.button_helpers import *
from utils.auto_delete import reply_and_delete

async def show_list(event, command, items, formatter, title, page=1):
    """显示分页列表"""

    # KEYWORDS_PER_PAGE
    PAGE_SIZE = KEYWORDS_PER_PAGE
    total_items = len(items)
    total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE

    if not items:
        try:
            return await event.edit(f'没有找到任何{title}')
        except:
            return await reply_and_delete(event,f'没有找到任何{title}')

    # 获取当前页的项目
    start = (page - 1) * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_items)
    current_items = items[start:end]

    # 格式化列表项
    item_list = []
    for i, item in enumerate(current_items):
        formatted_item = formatter(i + start + 1, item)
        # 如果是关键字列表，给关键字添加反引号
        if command == 'keyword':
            # 分割序号和关键字内容
            parts = formatted_item.split('. ', 1)
            if len(parts) == 2:
                number = parts[0]
                content = parts[1]
                # 如果是正则表达式，在关键字部分添加反引号
                if ' (正则)' in content:
                    keyword, regex_mark = content.split(' (正则)')
                    formatted_item = f'{number}. `{keyword}` (正则)'
                else:
                    formatted_item = f'{number}. `{content}`'
        item_list.append(formatted_item)

    # 创建分页按钮
    buttons = await create_list_buttons(total_pages, page, command)

    # 构建消息文本
    text = f'{title}\n{chr(10).join(item_list)}'
    if len(text) > 4096:  # Telegram消息长度限制
        text = text[:4093] + '...'

    try:
        return await event.edit(text, buttons=buttons, parse_mode='markdown')
    except:
        return await reply_and_delete(event,text, buttons=buttons, parse_mode='markdown')

