from rss.app.core.config_manager import config_manager
from utils.common import is_admin


def _get_dashboard_url() -> str:
    config = config_manager.get_config()
    if isinstance(config, dict):
        url = (config.get("dashboard_url") or "").strip()
        if url:
            return url
    return "http://localhost:1008"


async def start_handler(event):
    """响应 /start 命令"""
    if not await is_admin(event):
        return
    sender = await event.get_sender()
    first_name = getattr(sender, "first_name", "用户")
    dashboard_url = _get_dashboard_url()

    welcome_text = (
        f"👋 **您好，{first_name}！**\n\n"
        "我是您的 **RSS 转发机器人** (RSS Bot)。\n"
        "我可以帮助您自动转发频道消息、订阅 RSS 源并进行 AI 智能处理。\n\n"
        "🔧 **快速上手：**\n"
        "1. 发送 `/help` 查看命令列表。\n"
        f"2. 访问 [Web 仪表盘]({dashboard_url}) 进行可视化配置（推荐）。\n"
        "3. 在仪表盘中添加转发规则和 RSS 订阅。\n\n"
        "🚀 **状态：** 系统运行正常。"
    )
    await event.respond(welcome_text, link_preview=False)


async def help_handler(event):
    """响应 /help 命令"""
    if not await is_admin(event):
        return
    help_text = (
        "🤖 **RSS Bot 命令帮助**\n\n"
        "**基础命令**\n"
        "• `/start` - 唤醒机器人并查看状态\n"
        "• `/help` - 显示此帮助信息\n"
        "• `/changelog` - 查看版本更新日志\n\n"
        "**配置与管理**\n"
        "• `/settings` - 获取 Web 仪表盘链接\n"
        "• `/bind` - (交互式) 绑定源频道与目标频道\n"
        "• `/switch` - 快速切换当前规则的启用/停用\n\n"
        "**RSS & 高级**\n"
        "• 推荐使用 **Web 仪表盘** 管理所有 RSS 订阅、AI 提示词和高级过滤规则。\n\n"
        "💡 *提示：遇到问题请检查 Web 端日志面板。*"
    )
    await event.respond(help_text)


async def dashboard_command_handler(event):
    """响应 /web 或 /dashboard 命令（仅入口提示）"""
    if not await is_admin(event):
        return
    dashboard_url = _get_dashboard_url()
    await event.respond(
        "🌐 **Web 仪表盘入口**\n\n"
        "请访问以下地址进行完整配置：\n"
        f"{dashboard_url}\n\n"
        "在仪表盘中，您可以：\n"
        "- 管理转发规则\n"
        "- 配置 AI API Key\n"
        "- 查看系统日志\n"
        "- 管理 RSS 订阅",
        link_preview=False
    )
