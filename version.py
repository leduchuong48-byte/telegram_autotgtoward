VERSION = "3.1"
APP_NAME = "telegram_chanel_autotoward"
REPO_URL = "https://github.com/leduchuong48-byte/telegram_autotgtoward"

# 版本号说明
VERSION_INFO = {
    "major": 3,        # 主版本号：重大更新，可能不兼容旧版本
    "feature": 1,      # 功能版本号：添加重要新功能
    "minor": 0,        # 次要版本号：添加小功能或优化
    "patch": 0,        # 补丁版本号：Bug修复和小改动
}


UPDATE_INFO = f"""<blockquote><b>✨ 更新日志 v{VERSION}</b>

- 修复转发不稳定问题，提升长时运行稳定性
- 修复未命中筛选条件内容在用户模式仍被转发的问题
- 转发全部视频默认严格筛选：超限媒体不再降级到用户账号转发
- 新增环境开关：VIDEO_FORWARD_OVER_LIMIT_FALLBACK_TO_USER（默认 false）
- UI 名称统一为 {APP_NAME}

</blockquote>
"""


WELCOME_TEXT = (
    f"欢迎使用 {APP_NAME}!\n"
    f"当前版本 v{VERSION}\n"
    f"仓库地址：{REPO_URL}"
)
