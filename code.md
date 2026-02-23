# TelegramForwarder 代码与规则说明书（开发者版）

> 文档范围：基于当前仓库源码（目录名 `Autotgtoward-1.0`）整理。  
> 数据来源：本文所有结论均来自仓库内对应源码文件（在每节均标注“来源：`文件路径`”）。  
> 目标读者：需要二次开发/排障/审计该项目的维护者。

---

## 1. 项目总体目标与术语

**项目目标**
- 使用 Telethon 登录“用户账号 + 机器人账号”，监听用户账号可见的频道/群组/私聊消息，并按“转发规则”处理后发送到目标聊天（来源：`main.py`、`message_listener.py`）。
- 支持关键字过滤、替换、媒体过滤/下载、AI改写、AI总结、RSS落库、Apprise 推送、评论区按钮、延迟处理等（来源：`filters/process.py`、`filters/*.py`、`scheduler/*.py`、`rss/*`）。

**核心术语**
- **user_client**：Telethon 用户客户端，用于监听源聊天/拉取历史/获取实体信息（来源：`main.py`、`message_listener.py`）。
- **bot_client**：Telethon 机器人客户端，用于接收管理员命令、发送消息（来源：`main.py`、`handlers/bot_handler.py`）。
- **Rule / ForwardRule**：一条转发规则，源聊天→目标聊天 + 各种开关/策略（来源：`models/models.py`）。
- **过滤器链（Filter Chain）**：机器人模式下的统一处理管线（来源：`filters/process.py`、`filters/filter_chain.py`）。
- **幂等（绝不重复）**：通过数据库唯一约束保证同一规则内同一条消息只会处理一次（来源：`models/models.py`、`utils/dedup.py`、`message_listener.py`、`managers/backfill_manager.py`）。

---

## 2. 启动与运行架构

### 2.1 进程与入口
- 主进程入口：`main.py`（来源：`main.py`）。
- 可选 RSS Web：FastAPI（`rss/main.py`），由 `main.py` 在独立进程启动（来源：`main.py`、`rss/main.py`）。

### 2.2 主流程（启动顺序）
1. 读取环境变量、创建 `user_client` 与 `bot_client`（来源：`main.py`）。
2. 初始化数据库（`models/models.py:init_db()` -> `Base.metadata.create_all` + `migrate_db`）（来源：`main.py`、`models/models.py`）。
3. 启动 Telethon 两个客户端并注册监听器（来源：`main.py`、`message_listener.py`）。
4. 注册机器人命令列表（来源：`main.py`）。
5. 启动调度器：AI总结 `SummaryScheduler`、聊天信息更新 `ChatUpdater`（来源：`main.py`、`scheduler/summary_scheduler.py`、`scheduler/chat_updater.py`）。
6. 如 `RSS_ENABLED=true` 则启动 RSS Web 服务进程（来源：`main.py`、`.env.example`）。

---

## 3. 配置说明（.env）

### 3.1 必填项
来源：`.env.example`
- `API_ID` / `API_HASH`：Telegram API 凭据（Telethon 登录必需）。
- `PHONE_NUMBER`：用户账号手机号（用户客户端登录）。
- `BOT_TOKEN`：机器人 Token（机器人客户端登录）。
- `USER_ID`：你的用户 ID（用于识别管理员/管理入口）。

### 3.2 常用可选项（与行为直接相关）
来源：`.env.example`、`utils/constants.py`
- `ADMINS`：管理员列表（逗号分隔），为空默认使用 `USER_ID`（来源：`utils/common.py:get_admin_list`）。
- `DEFAULT_MAX_MEDIA_SIZE`：默认媒体大小上限（MB）（来源：`.env.example`、`models/models.py`）。
- `DEFAULT_TIMEZONE`：默认时区（来源：`.env.example`、`utils/constants.py`）。
- `CHAT_UPDATE_TIME`：聊天名称更新任务执行时间（来源：`.env.example`、`scheduler/chat_updater.py`）。
- `BACKFILL_ADAPTIVE_THROTTLE` / `BACKFILL_THROTTLE_*`：回填自适应节流参数（来源：`.env.example`、`handlers/command_handlers.py`、`managers/backfill_manager.py`）。
- `SUMMARY_BATCH_SIZE` / `SUMMARY_BATCH_DELAY`：总结任务抓取消息的分页大小/间隔（来源：`.env.example`、`scheduler/summary_scheduler.py`）。
- `RSS_ENABLED` / `RSS_BASE_URL` / `RSS_MEDIA_BASE_URL`：RSS 功能开关与 URL 配置（来源：`.env.example`、`utils/constants.py`、`filters/rss_filter.py`、`rss/app/api/endpoints/feed.py`）。
- `UFB_ENABLED` / `UFB_SERVER_URL` / `UFB_TOKEN`：UFB 联动（来源：`.env.example`、`utils/constants.py`、`ufb/ufb_client.py`）。

### 3.3 UI 相关分页/布局参数
来源：`.env.example`、`utils/constants.py`
- `AI_MODELS_PER_PAGE`、`KEYWORDS_PER_PAGE`、`PUSH_CHANNEL_PER_PAGE`
- `SUMMARY_TIME_ROWS/COLS`、`DELAY_TIME_ROWS/COLS`、`MEDIA_SIZE_ROWS/COLS`、`MEDIA_EXTENSIONS_ROWS/COLS`
- `RULES_PER_PAGE`

---

## 4. 数据库（SQLite）与数据模型（规则的“真相来源”）

### 4.1 数据库位置
来源：`models/models.py:init_db`、`.env.example`
- 默认 SQLite 文件：`./db/forward.db`
- 项目会在启动时创建 `./db` 目录（来源：`models/models.py:init_db`）。

### 4.2 核心表：`forward_rules`（转发规则）
来源：`models/models.py:ForwardRule`

**唯一性**
- `(source_chat_id, target_chat_id)` 唯一（同一源→目标只能存在一条规则）（来源：`models/models.py`）。

**字段分组说明（产品视角）**
- 基础绑定：
  - `source_chat_id` / `target_chat_id`：外键到 `chats`。
- 过滤模式（关键字规则）：
  - `forward_mode`：黑/白/先后组合模式（来源：`enums/enums.py`、`utils/common.py:check_keywords`）。
- 转发执行方式：
  - `use_bot`：是否走机器人模式（过滤器链 + 发送），否则走用户模式（仅关键字 + forward_messages）（来源：`message_listener.py`、`handlers/user_handler.py`）。
  - `handle_mode`：编辑/转发（编辑模式会尝试修改源消息）（来源：`enums/enums.py`、`filters/edit_filter.py`）。
- 文本替换：
  - `is_replace`：是否启用替换规则（来源：`filters/replace_filter.py`）。
- 消息格式与预览：
  - `message_mode`：Markdown/HTML（来源：`enums/enums.py`、`filters/sender_filter.py`）。
  - `is_preview`：链接预览开关/跟随原消息（来源：`enums/enums.py`、`filters/sender_filter.py`）。
- 原始信息附加：
  - `is_original_link` / `original_link_template`
  - `is_original_sender` / `userinfo_template`
  - `is_original_time` / `time_template`
  - 实际拼接发生在 `filters/info_filter.py`、`filters/sender_filter.py`。
- 延迟处理：
  - `enable_delay` / `delay_seconds`：延迟后重新获取消息内容（来源：`filters/delay_filter.py`）。
- 评论区按钮：
  - `enable_comment_button`：为频道消息生成评论区直达按钮；媒体组会由 ReplyFilter 追加回复消息实现（来源：`filters/comment_button_filter.py`、`filters/reply_filter.py`）。
- 媒体过滤：
  - `enable_media_type_filter`（配合 `media_types`）
  - `enable_media_size_filter` / `max_media_size` / `is_send_over_media_size_message`
  - `enable_extension_filter` / `extension_filter_mode`（配合 `media_extensions`）
  - `media_allow_text`：媒体被屏蔽时是否仍允许文本通过（来源：`filters/media_filter.py`）。
- 推送（Apprise）：
  - `enable_push`：启用推送
  - `enable_only_push`：只推送不发送到目标聊天（来源：`filters/push_filter.py`、`filters/sender_filter.py`）。
- AI：
  - `is_ai` / `ai_model` / `ai_prompt` / `enable_ai_upload_image`
  - `is_keyword_after_ai`：AI处理后再次关键字过滤（来源：`filters/ai_filter.py`）。
- AI总结：
  - `is_summary` / `summary_time` / `summary_prompt` / `is_top_summary`（来源：`scheduler/summary_scheduler.py`）。
- RSS：
  - `only_rss`：只写入 RSS，不执行后续发送/编辑（来源：`filters/rss_filter.py`）。
- 同步：
  - `enable_sync`：将关键字/替换等操作同步到其他规则（来源：`models/db_operations.py`、`models/models.py:RuleSync`）。
- UFB：
  - `is_ufb` / `ufb_domain` / `ufb_item`（来源：`models/models.py`、`models/db_operations.py`、`ufb/ufb_client.py`）。

### 4.3 幂等表：`processed_messages`
来源：`models/models.py:ProcessedMessage`、`utils/dedup.py`
- 作用：同一规则（`rule_id`）内，通过唯一约束保证 `dedup_key` 只出现一次，从而实现“绝不重复”。
- `dedup_key` 规则（来源：`utils/dedup.py`）：
  - 普通消息：`m:<message_id>`
  - 媒体组：`g:<grouped_id>`（整个媒体组只处理一次）

### 4.4 其他表（与规则相关）
来源：`models/models.py`
- `chats`：存储聊天实体信息 + `current_add_id`（用于 `/switch` 当前规则选择）。
- `keywords`：关键字（正则/普通、黑名单/白名单），唯一约束包含 `is_regex/is_blacklist`。
- `replace_rules`：替换规则（正则 pattern + content）。
- `media_types`：媒体类型开关（photo/document/video/audio/voice/text）。
- `media_extensions`：扩展名列表（黑/白名单模式由 `forward_rules.extension_filter_mode` 控制）。
- `push_configs`：推送通道配置（Apprise URL 等）。
- `rss_configs` / `rss_patterns`：RSS 的 per-rule 配置与正则提取规则。
- `rule_syncs`：规则同步映射。
- `users`：RSS 仪表盘登录用户（来源：`rss/app/routes/auth.py`、`models/models.py:User`）。

---

## 5. 实时消息转发（只能转发“未来消息”的原始原因）

### 5.1 原因
来源：`message_listener.py`
- 监听仅注册 `events.NewMessage`（新消息事件），因此默认只会处理启动后的新消息。

### 5.2 实时处理流程（用户客户端监听）
来源：`message_listener.py`
1. `setup_listeners()` 注册 user/bot 两个 NewMessage handler，并过滤 bot 自己的消息（BOT_ID）（来源：`message_listener.py`）。
2. `handle_user_message()`：
   - 解析 `chat_id`（频道场景有额外处理逻辑）（来源：`message_listener.py`）。
   - 媒体组去重：`PROCESSED_GROUPS`（进程内缓存，避免同一媒体组多次触发）（来源：`message_listener.py`）。
   - 从 DB 找到源聊天、再找所有以此为源的规则（来源：`message_listener.py`、`models/models.py`）。
   - 对每条规则执行：
     - `enable_rule` 开关；
     - 幂等占位：`build_dedup_key()` + `claim_processed()`（来源：`message_listener.py`、`utils/dedup.py`）；
     - `use_bot=True`：走过滤器链 `filters/process.py:process_forward_rule`；
     - `use_bot=False`：走用户模式 `handlers/user_handler.py:process_forward_rule`（仅关键字过滤 + forward_messages）。

---

## 6. 过滤器链（机器人模式）的“产品规则”

### 6.1 链顺序
来源：`filters/process.py`
顺序固定如下：
1. `InitFilter`
2. `DelayFilter`
3. `KeywordFilter`
4. `ReplaceFilter`
5. `MediaFilter`
6. `AIFilter`
7. `InfoFilter`
8. `CommentButtonFilter`
9. `RSSFilter`
10. `EditFilter`
11. `SenderFilter`
12. `ReplyFilter`
13. `PushFilter`
14. `DeleteOriginalFilter`

### 6.2 上下文对象（MessageContext）
来源：`filters/context.py`
- `original_message_text` / `message_text` / `check_message_text`
- `media_files` / `media_group_messages` / `skipped_media` / `is_media_group` / `media_group_id`
- `sender_info` / `time_info` / `original_link`
- `buttons` / `comment_link`
- `should_forward` / `errors` / `forwarded_messages`

### 6.3 各过滤器规则要点（按触发开关）
来源：`filters/*.py`
- `DelayFilter`：`rule.enable_delay && rule.delay_seconds>0` 时 sleep 后 `get_messages` 刷新消息内容（来源：`filters/delay_filter.py`）。
- `KeywordFilter`：调用 `utils/common.py:check_keywords` 按 `forward_mode` + `keywords` 决策是否继续（来源：`filters/keyword_filter.py`、`utils/common.py`）。
- `ReplaceFilter`：`rule.is_replace` 时按 `replace_rules` 做正则替换（来源：`filters/replace_filter.py`）。
- `MediaFilter`：媒体类型/大小/扩展名过滤 + 下载到 `./temp`（来源：`filters/media_filter.py`、`utils/constants.py:TEMP_DIR`）。
- `AIFilter`：`rule.is_ai` 时调用 AI provider；可选上传图片（来源：`filters/ai_filter.py`、`ai/__init__.py`）。
- `InfoFilter`：按开关拼接原始链接/发送者/时间（来源：`filters/info_filter.py`）。
- `CommentButtonFilter`：为频道消息生成评论区按钮；媒体组不直接加按钮（来源：`filters/comment_button_filter.py`）。
- `RSSFilter`：`RSS_ENABLED && rss_config.enable_rss` 时写入 RSS；若 `rule.only_rss` 则返回 False 终止后续发送/编辑（来源：`filters/rss_filter.py`、`utils/constants.py:RSS_ENABLED`）。
- `EditFilter`：`rule.handle_mode==EDIT` 时尝试编辑源消息；并通过返回 False 终止链路（来源：`filters/edit_filter.py`）。
- `SenderFilter`：将最终内容/媒体发送到目标聊天；若 `rule.enable_only_push` 则跳过发送（来源：`filters/sender_filter.py`）。
- `ReplyFilter`：媒体组场景下，为已发送的媒体组消息追加“评论区按钮”回复（来源：`filters/reply_filter.py`）。
- `PushFilter`：`rule.enable_push` 时通过 Apprise 推送（来源：`filters/push_filter.py`）。
- `DeleteOriginalFilter`：`rule.is_delete_original` 时删除源消息（来源：`filters/delete_original_filter.py`）。

---

## 7. 历史消息回填（Backfill）功能说明书

### 7.1 功能目标
来源：`handlers/command_handlers.py`、`managers/backfill_manager.py`
- 支持对当前选中的规则执行历史回填：
  - 最近 N 条
  - 指定时间段
  - 全部历史
- 回填遵循规则的转发方式：
  - `use_bot=true`：执行完整过滤器链（关键字/替换/媒体/AI/推送/RSS 等）
  - `use_bot=false`：走用户模式（仅关键字过滤 + forward_messages）
- 回填在**成功转发后**写入 `processed_messages`，避免失败/过滤导致永远跳过。

### 7.2 用户操作（命令）
来源：`handlers/command_handlers.py`、`handlers/bot_handler.py`、`main.py`
1. 在“目标聊天窗口”选择规则（已有逻辑）：`/switch`
2. 启动回填：
   - `/backfill 100` 或 `/backfill last 100`
   - `/backfill range "2025-01-01 00:00" "2025-01-02 23:59"`
   - `/backfill all`
3. 清理回填去重记录：
   - `/backfill_reset`

### 7.3 参数规则
来源：`handlers/command_handlers.py`
- `range` 时间格式支持：`YYYY-MM-DD`、`YYYY-MM-DD HH:MM`、`YYYY-MM-DD HH:MM:SS`
- 时区来自 `DEFAULT_TIMEZONE`（来源：`.env.example`、`handlers/command_handlers.py`）。

### 7.4 执行流程（内部）
来源：`managers/backfill_manager.py`
- 通过 `user_client` 拉取历史消息（last 用 `iter_messages`；range/all 用 `get_messages` 分页 + `offset_id`）。
- 将 Telethon Message 包装为 `BackfillEvent` 以复用过滤器链所需字段（`event.message`、`event.chat_id`、`event.get_chat()` 等）。
- 对每条消息先检查是否已处理（`is_processed`），成功转发后再写入去重（`claim_processed`）。
- 回填在后台 `asyncio.create_task` 执行，并每 30 秒向当前聊天报告一次统计（扫描/处理/跳过/未转发）。

### 7.5 “绝不重复”的代价与运维建议
来源：`utils/dedup.py`、`managers/backfill_manager.py`
- 采用“成功转发后写入去重”，因此：
  - ✅ 避免处理失败导致永久跳过。
  - ⚠️ 若需要重复回填历史消息，需要先清理去重记录。
- 清理手段：
  - `/backfill_reset`（当前规则）
  - 或删除 `processed_messages` 中对应 `rule_id + dedup_key` 的记录后再次回填。

---

## 8. RSS 子系统（概览）

### 8.1 写入入口（过滤器）
来源：`filters/rss_filter.py`
- `RSSFilter` 在过滤器链中负责把消息落到 RSS 服务的数据源中。
- 若规则开启 `only_rss`，会在 RSS 处理后终止链路，后续不再发送/编辑（来源：`filters/rss_filter.py`）。

### 8.2 Web 服务入口
来源：`rss/main.py`
- FastAPI 应用：`rss/main.py:app`
- 路由聚合：
  - 登录/账号：`rss/app/routes/auth.py`
  - 仪表盘/配置：`rss/app/routes/rss.py`
  - API：`rss/app/api/endpoints/feed.py`

### 8.3 Feed API（示例）
来源：`rss/app/api/endpoints/feed.py`
- `GET /rss/feed/{rule_id}`：返回 rule 对应的 RSS XML（会检查 RSSConfig.enable_rss）。
- 生成 feed 依赖 `FeedService`（来源：`rss/app/services/feed_generator.py`）。

---

## 9. AI 子系统（概览）

### 9.1 AI Provider 选择
来源：`ai/__init__.py`
- `get_ai_provider(model_name)` 根据模型名选择 Provider（OpenAI/Claude/Gemini/DeepSeek/Qwen/Grok 等）。

### 9.2 AI 处理入口（过滤器）
来源：`filters/ai_filter.py`
- `AIFilter` 在 `rule.is_ai=True` 时生效。
- 支持 `enable_ai_upload_image`：对媒体文件/图片进行 base64 后随请求上传（来源：`filters/ai_filter.py`）。

### 9.3 AI 总结（定时任务）
来源：`scheduler/summary_scheduler.py`
- `SummaryScheduler` 按 `rule.is_summary` 与 `rule.summary_time` 执行。
- 通过 `user_client.get_messages` 分页抓取时间窗口内消息（来源：`scheduler/summary_scheduler.py`）。

---

## 10. 推送（Apprise）子系统（概览）

来源：`filters/push_filter.py`、`models/models.py:PushConfig`
- `PushFilter` 在 `rule.enable_push=True` 时生效。
- 推送通道配置来自 `push_configs` 表（Apprise URL、是否启用、媒体发送方式等）。

---

## 11. UFB 联动（概览）

来源：`ufb/ufb_client.py`、`models/db_operations.py`
- UFB 用于与通用论坛屏蔽插件服务端同步关键字/配置。
- 是否启用由 `UFB_ENABLED` 控制（来源：`utils/constants.py`、`.env.example`）。

---

## 12. 代码索引（按目录）

> 目的：覆盖“所有代码文件”的可检索清单。  
> 来源：仓库目录结构（见 `find . -name "*.py"` 输出）。

### 12.1 入口与核心
- `main.py`：启动双客户端、注册监听与调度器、启动 RSS 进程（来源：`main.py`）
- `message_listener.py`：实时 NewMessage 监听、路由到过滤器链/用户模式、幂等占位（来源：`message_listener.py`）
- `version.py`：版本与欢迎文案（来源：`version.py`）

### 12.2 managers/
- `managers/state_manager.py`：会话状态机（用于交互式设置等）（来源：`managers/state_manager.py`）
- `managers/backfill_manager.py`：历史回填执行器（来源：`managers/backfill_manager.py`）

### 12.3 models/
- `models/models.py`：SQLAlchemy 模型 + DB 迁移（来源：`models/models.py`）
- `models/db_operations.py`：对规则/关键字/替换/RSS/推送/用户等提供 CRUD 与同步封装（来源：`models/db_operations.py`）

### 12.4 filters/
- `filters/process.py`：过滤器链编排入口（来源：`filters/process.py`）
- `filters/filter_chain.py` / `filters/context.py`：过滤器链框架与上下文（来源：对应文件）
- 具体过滤器：`filters/*.py`（AI/媒体/替换/推送/RSS/删除等，详见第 6 节）（来源：对应文件）

### 12.5 handlers/
- `handlers/bot_handler.py`：命令路由入口、回调入口、欢迎消息（来源：`handlers/bot_handler.py`）
- `handlers/command_handlers.py`：命令实现（含 `/backfill`）（来源：`handlers/command_handlers.py`）
- `handlers/user_handler.py`：用户模式转发实现（来源：`handlers/user_handler.py`）
- `handlers/link_handlers.py`：消息链接转发（来源：`handlers/link_handlers.py`）
- `handlers/prompt_handlers.py`：交互式 prompt 设置等（来源：`handlers/prompt_handlers.py`）
- `handlers/button/*`：设置菜单/按钮生成与回调处理（来源：`handlers/button/...`）

### 12.6 scheduler/
- `scheduler/summary_scheduler.py`：AI总结调度（来源：`scheduler/summary_scheduler.py`）
- `scheduler/chat_updater.py`：聊天名称更新（来源：`scheduler/chat_updater.py`）

### 12.7 ai/
- `ai/base.py` + 各 Provider：AI 适配层（来源：`ai/*.py`）

### 12.8 rss/
- `rss/main.py`：FastAPI app（来源：`rss/main.py`）
- `rss/app/...`：仪表盘、feed API、条目存储与 feed 生成（来源：`rss/app/...`）

### 12.9 utils/
- `utils/common.py`：管理员校验、关键字判断、DBOps 获取等通用逻辑（来源：`utils/common.py`）
- `utils/dedup.py`：幂等占位实现（来源：`utils/dedup.py`）
- `utils/constants.py`：常量与目录（来源：`utils/constants.py`）
- `utils/settings.py` / `utils/file_creator.py`：config 目录默认文件生成与加载（来源：对应文件）
- `utils/auto_delete.py`：自动删除消息辅助（来源：`utils/auto_delete.py`）
- `utils/media.py`：媒体大小读取（来源：`utils/media.py`）
- `utils/log_config.py`：日志配置（来源：`utils/log_config.py`）

### 12.10 全量源码文件清单（.py）
来源：仓库文件列表（`find . -name "*.py"`）
- `ai/__init__.py`
- `ai/base.py`
- `ai/claude_provider.py`
- `ai/deepseek_provider.py`
- `ai/gemini_provider.py`
- `ai/grok_provider.py`
- `ai/openai_base_provider.py`
- `ai/openai_provider.py`
- `ai/qwen_provider.py`
- `enums/enums.py`
- `filters/ai_filter.py`
- `filters/base_filter.py`
- `filters/comment_button_filter.py`
- `filters/context.py`
- `filters/delay_filter.py`
- `filters/delete_original_filter.py`
- `filters/edit_filter.py`
- `filters/filter_chain.py`
- `filters/info_filter.py`
- `filters/init_filter.py`
- `filters/keyword_filter.py`
- `filters/media_filter.py`
- `filters/process.py`
- `filters/push_filter.py`
- `filters/replace_filter.py`
- `filters/reply_filter.py`
- `filters/rss_filter.py`
- `filters/sender_filter.py`
- `handlers/bot_handler.py`
- `handlers/button/button_helpers.py`
- `handlers/button/callback/ai_callback.py`
- `handlers/button/callback/callback_handlers.py`
- `handlers/button/callback/media_callback.py`
- `handlers/button/callback/other_callback.py`
- `handlers/button/callback/push_callback.py`
- `handlers/button/settings_manager.py`
- `handlers/command_handlers.py`
- `handlers/link_handlers.py`
- `handlers/list_handlers.py`
- `handlers/prompt_handlers.py`
- `handlers/user_handler.py`
- `main.py`
- `managers/backfill_manager.py`
- `managers/state_manager.py`
- `message_listener.py`
- `models/db_operations.py`
- `models/models.py`
- `rss/app/api/endpoints/feed.py`
- `rss/app/api/endpoints/__init__.py`
- `rss/app/api/__init__.py`
- `rss/app/core/config.py`
- `rss/app/core/__init__.py`
- `rss/app/crud/entry.py`
- `rss/app/__init__.py`
- `rss/app/models/entry.py`
- `rss/app/routes/auth.py`
- `rss/app/routes/rss.py`
- `rss/app/services/feed_generator.py`
- `rss/app/services/__init__.py`
- `rss/main.py`
- `scheduler/chat_updater.py`
- `scheduler/summary_scheduler.py`
- `ufb/ufb_client.py`
- `utils/auto_delete.py`
- `utils/common.py`
- `utils/constants.py`
- `utils/dedup.py`
- `utils/file_creator.py`
- `utils/log_config.py`
- `utils/media.py`
- `utils/settings.py`
- `version.py`

---

## 13. 枚举值（关键规则枚举）

来源：`enums/enums.py`

### 13.1 ForwardMode（关键字过滤模式）
- `WHITELIST`：仅白名单
- `BLACKLIST`：仅黑名单
- `BLACKLIST_THEN_WHITELIST`：先黑后白
- `WHITELIST_THEN_BLACKLIST`：先白后黑

### 13.2 PreviewMode（链接预览）
- `ON`：强制开
- `OFF`：强制关
- `FOLLOW`：跟随原消息（在 SenderFilter 中以 `event.message.media is not None` 判断）

### 13.3 MessageMode（发送解析格式）
- `MARKDOWN`：`Markdown`
- `HTML`：`HTML`

### 13.4 AddMode（关键字/扩展名的黑白名单语义）
- `WHITELIST`：白名单
- `BLACKLIST`：黑名单

### 13.5 HandleMode（处理模式）
- `FORWARD`：转发（默认）
- `EDIT`：编辑（会尝试改写源消息）

---

## 14. 关键字过滤规则引擎（check_keywords）详解

来源：`utils/common.py`、`filters/keyword_filter.py`、`handlers/user_handler.py`

### 14.1 关键字数据结构
来源：`models/models.py:Keyword`
- `keyword.keyword`：关键字内容
- `keyword.is_regex`：是否正则
- `keyword.is_blacklist`：是否黑名单（`True`=黑名单，`False`=白名单）

### 14.2 过滤输入文本
来源：`utils/common.py:check_keywords`
- 默认：使用消息文本（机器人模式下来自 `context.message_text`，用户模式下来自 `event.message.text`）。
- 当 `rule.is_filter_user_info=True` 且传入 `event` 时：会把发送者信息拼接到文本前用于匹配（不会影响最终发送内容）（来源：`utils/common.py:process_user_info`）。

### 14.3 ForwardMode 与判定逻辑（核心规则）
来源：`utils/common.py`

> 记号约定：  
> - “命中”= `check_keyword_match` 返回 True（普通关键字为包含关系；正则为 `re.search`）。  
> - `reverse_blacklist`= `rule.enable_reverse_blacklist`  
> - `reverse_whitelist`= `rule.enable_reverse_whitelist`

#### A) `WHITELIST`（仅白名单）
来源：`utils/common.py:process_whitelist_mode`
- 必须命中任意一个白名单关键字，否则不转发。
- 若 `reverse_blacklist=True`：黑名单关键字被“反转”为第二重白名单，必须再命中任意一个黑名单关键字才转发。

#### B) `BLACKLIST`（仅黑名单）
来源：`utils/common.py:process_blacklist_mode`
- 命中任意黑名单关键字则不转发。
- 若 `reverse_whitelist=True`：白名单关键字被“反转”为额外黑名单，命中任意白名单关键字也不转发。

#### C) `WHITELIST_THEN_BLACKLIST`（先白后黑）
来源：`utils/common.py:process_whitelist_then_blacklist_mode`
- 第一步：必须命中任意白名单关键字，否则不转发。
- 第二步（黑名单处理）：
  - 若 `reverse_blacklist=False`：命中任意黑名单关键字则不转发。
  - 若 `reverse_blacklist=True`：黑名单被反转为第二重白名单，必须命中任意黑名单关键字才转发。

#### D) `BLACKLIST_THEN_WHITELIST`（先黑后白）
来源：`utils/common.py:process_blacklist_then_whitelist_mode`
- 第一步：命中任意黑名单关键字则不转发。
- 第二步（白名单处理）：
  - 若 `reverse_whitelist=False`：必须命中任意白名单关键字才转发。
  - 若 `reverse_whitelist=True`：白名单被反转为第二重黑名单，命中任意白名单关键字则不转发（且无需额外白名单命中条件）。

---

## 15. config/ 配置文件（自动生成与用途）

来源：`utils/file_creator.py`、`utils/settings.py`、`handlers/button/button_helpers.py`

### 15.1 自动生成逻辑
来源：`utils/file_creator.py:create_default_configs`
- 程序会在需要时创建 `./config/` 目录，并生成以下文件：
  - `config/summary_times.txt`
  - `config/delay_times.txt`
  - `config/max_media_size.txt`
  - `config/media_extensions.txt`
  - `config/ai_models.json`

### 15.2 读取入口
来源：`utils/settings.py`
- `load_ai_models()`：读取 `config/ai_models.json`（不存在会先生成默认）
- `load_summary_times()`：读取 `config/summary_times.txt`
- `load_delay_times()`：读取 `config/delay_times.txt`
- `load_max_media_size()`：读取 `config/max_media_size.txt`
- `load_media_extensions()`：读取 `config/media_extensions.txt`

### 15.3 UI 使用方式
来源：`handlers/button/button_helpers.py`、`handlers/button/settings_manager.py`
- UI 按钮/分页会在模块加载时读取这些配置，生成可选项按钮（例如总结时间、延迟时间、媒体大小、扩展名、AI模型列表等）。

---

## 16. 权限与安全边界（重要规则）

### 16.1 机器人命令与回调权限
来源：`handlers/bot_handler.py`、`utils/common.py:is_admin`
- 所有命令/回调入口在执行前都会调用 `is_admin(event)` 校验（来源：`handlers/bot_handler.py`）。
- 管理员来源：
  - `ADMINS` 环境变量（逗号分隔）
  - 为空则使用 `USER_ID`（来源：`utils/common.py:get_admin_list`）。
- 频道场景：还会校验“机器人管理员”是否在频道管理员列表内（来源：`utils/common.py:is_admin`、`utils/common.py:get_channel_admins`）。

### 16.2 RSS API 的本地访问限制
来源：`rss/app/api/endpoints/feed.py`
- `verify_local_access` 用于限制部分写入/删除类 API 只能本地/内网访问：
  - `POST /api/entries/{rule_id}/add`
  - `DELETE /api/entries/{rule_id}/{entry_id}`
  - `DELETE /api/rule/{rule_id}`
- `GET /rss/feed/{rule_id}` 不在该依赖保护范围内（用于公开订阅）。

---

## 17. 命令与交互（产品说明书版）

### 17.1 命令入口与权限
来源：`handlers/bot_handler.py`、`utils/common.py:is_admin`
- 命令入口：`handlers/bot_handler.py:handle_command`。
- 权限：所有命令与回调在执行前都会校验 `is_admin(event)`（管理员列表来自 `ADMINS` 或 `USER_ID`）。
- 触发条件：仅处理以 `/` 开头的消息文本；否则直接返回（但见“链接转发特例”）。
- 链接转发特例：在与 bot 的私聊中（`chat_id == USER_ID`），发送非 `/` 开头且包含 `t.me/` 的消息，会进入 `handlers/link_handlers.py:handle_message_link`（来源：`handlers/bot_handler.py`、`handlers/link_handlers.py`）。

### 17.2 命令别名与路由表（索引）
来源：`handlers/bot_handler.py`、`handlers/command_handlers.py`

> 说明：以下为“命令触发词 -> 处理函数”的索引，用于你快速定位代码入口（不展开每个按钮回调）。

- `/bind` `/b` -> `handlers/command_handlers.py:handle_bind_command`
- `/settings` `/s` -> `handlers/command_handlers.py:handle_settings_command`
- `/switch` `/sw` -> `handlers/command_handlers.py:handle_switch_command`（按钮回调：`handlers/button/callback/callback_handlers.py:callback_switch`）
- `/backfill` `/bf` -> `handlers/command_handlers.py:handle_backfill_command`（详细见第 7 节）
- `/backfill_reset` -> `handlers/command_handlers.py:handle_backfill_reset_command`（清理回填去重记录）
- `/add` `/a`、`/add_regex` `/ar` -> `handlers/command_handlers.py:handle_add_command`
- `/replace` `/r` -> `handlers/command_handlers.py:handle_replace_command`
- `/list_keyword` `/lk` -> `handlers/command_handlers.py:handle_list_keyword_command`
- `/list_replace` `/lrp` -> `handlers/command_handlers.py:handle_list_replace_command`
- `/remove_keyword` `/rk`、`/remove_keyword_by_id` `/rkbi`、`/remove_replace` `/rr` -> `handlers/command_handlers.py:handle_remove_command`
- `/remove_all_keyword` `/rak` -> `handlers/command_handlers.py:handle_remove_all_keyword_command`
- `/add_all` `/aa`、`/add_regex_all` `/ara` -> `handlers/command_handlers.py:handle_add_all_command`
- `/replace_all` `/ra` -> `handlers/command_handlers.py:handle_replace_all_command`
- `/clear_all_keywords` `/cak` -> `handlers/command_handlers.py:handle_clear_all_keywords_command`
- `/clear_all_keywords_regex` `/cakr` -> `handlers/command_handlers.py:handle_clear_all_keywords_regex_command`
- `/clear_all_replace` `/car` -> `handlers/command_handlers.py:handle_clear_all_replace_command`
- `/copy_keywords` `/ck`、`/copy_keywords_regex` `/ckr`、`/copy_replace` `/crp`、`/copy_rule` `/cr` -> `handlers/command_handlers.py:handle_copy_*`
- `/export_keyword` `/ek`、`/export_replace` `/er` -> `handlers/command_handlers.py:handle_export_*`
- `/import_keyword` `/ik`、`/import_regex_keyword` `/irk`、`/import_replace` `/ir` -> `handlers/command_handlers.py:handle_import_command`
- `/list_rule` `/lr` -> `handlers/command_handlers.py:handle_list_rule_command`（按钮回调：`page_rule:<page>`，来源：`handlers/command_handlers.py`）
- `/delete_rule` `/dr` -> `handlers/command_handlers.py:handle_delete_rule_command`（按钮回调删除也存在，来源：`handlers/button/callback/callback_handlers.py`、`handlers/button/callback/other_callback.py`）
- `/clear_all` `/ca` -> `handlers/command_handlers.py:handle_clear_all_command`（危险：清空全库，来源：`handlers/command_handlers.py`）
- `/delete_rss_user` `/dru` -> `handlers/command_handlers.py:handle_delete_rss_user_command`
- `/ufb_bind` `/ub`、`/ufb_unbind` `/uu`、`/ufb_item_change` `/uic` -> `handlers/command_handlers.py:handle_ufb_*`
- `/start` -> `handlers/command_handlers.py:handle_start_command`
- `/help` `/h` -> `handlers/command_handlers.py:handle_help_command`
- `/changelog` `/cl` -> `handlers/command_handlers.py:handle_changelog_command`

### 17.3 /bind（绑定规则）
来源：`handlers/command_handlers.py:handle_bind_command`、`models/models.py:Chat/ForwardRule`
- 用法：`/bind <源聊天链接或名称> [目标聊天链接或名称]`
- 行为要点：
  - 用 `user_client.get_entity()` 或遍历对话列表按名称模糊匹配聊天实体（来源：`handlers/command_handlers.py`）。
  - 在 DB 中写入/复用 `chats` 记录，并创建一条 `forward_rules`（来源：`handlers/command_handlers.py`、`models/models.py`）。
  - 若目标聊天的 `current_add_id` 为空，会默认把本次源聊天设为“当前选中源”（用于后续 `/add`、`/replace`、`/backfill` 等命令）（来源：`handlers/command_handlers.py`、`models/models.py:Chat.current_add_id`）。

### 17.4 /settings（规则设置面板）
来源：`handlers/command_handlers.py:handle_settings_command`、`handlers/button/settings_manager.py`
- 用法：
  - `/settings`：列出当前聊天作为“目标聊天”的所有规则，并提供按钮进入对应规则设置。
  - `/settings <rule_id>`：直接打开指定规则的设置面板。
- 输出：通过 `Button.inline` 渲染设置按钮（来源：`handlers/command_handlers.py`、`handlers/button/settings_manager.py`）。

### 17.5 /switch（选择“当前规则”）
来源：`handlers/command_handlers.py:handle_switch_command`、`handlers/button/callback/callback_handlers.py:callback_switch`
- 用法：`/switch`
- 行为：点击按钮后把当前聊天对应 `chats.current_add_id` 更新为所选源聊天的 `telegram_chat_id`（影响后续所有“针对当前规则”的命令：关键字/替换/导入导出/回填等）。

### 17.6 关键字与替换（文本规则）
来源：`handlers/command_handlers.py`、`models/db_operations.py`
- 关键字新增：`/add`、`/add_regex`（会按 `rule.add_mode` 决定写入黑/白名单，来源：`handlers/command_handlers.py`、`models/models.py`）。
- 关键字查询/删除：`/list_keyword`、`/remove_keyword`、`/remove_keyword_by_id`（删除会走 `db_ops.delete_keywords`，包含同步逻辑，来源：`handlers/command_handlers.py`、`models/db_operations.py`）。
- 替换新增：`/replace`（内部走 `db_ops.add_replace_rules`，来源：`handlers/command_handlers.py`、`models/db_operations.py`）。
- 替换查询/删除：`/list_replace`、`/remove_replace`。

### 17.7 批量/复制/导入导出
来源：`handlers/command_handlers.py`
- 批量新增：`/add_all`、`/add_regex_all`、`/replace_all`（对当前目标聊天下的全部规则批量操作）。
- 复制：`/copy_keywords`、`/copy_keywords_regex`、`/copy_replace`、`/copy_rule`（`/copy_rule` 会复制关键字/替换/媒体设置/同步表与大部分规则字段，来源：`handlers/command_handlers.py:handle_copy_rule_command`）。
- 导出：`/export_keyword`、`/export_replace`（生成文件并发送，临时文件位于 `TEMP_DIR`，来源：`handlers/command_handlers.py`、`utils/constants.py`）。
- 导入：`/import_keyword`、`/import_regex_keyword`、`/import_replace`（需要把命令与文件一起发送；文件会下载到 `TEMP_DIR` 后读取，来源：`handlers/command_handlers.py`）。

### 17.8 规则列表与删除（运维）
来源：`handlers/command_handlers.py`、`handlers/button/callback/*`
- 列出规则：`/list_rule [page]`（每页 30 条；使用按钮 `page_rule:<page>` 翻页，来源：`handlers/command_handlers.py:handle_list_rule_command`）。
- 删除规则：`/delete_rule <id...>` 或按钮删除（会尝试调用 RSS 服务删除 `/api/rule/{rule_id}`，来源：`handlers/command_handlers.py:handle_delete_rule_command`、`handlers/button/callback/callback_handlers.py`、`handlers/button/callback/other_callback.py`）。
- 清空全库：`/clear_all`（会删除 `processed_messages/chats/forward_rules/keywords/replace_rules` 等，属于高危操作，来源：`handlers/command_handlers.py:handle_clear_all_command`）。

### 17.9 RSS 用户管理
来源：`handlers/command_handlers.py:handle_delete_rss_user_command`、`models/models.py:User`
- `/delete_rss_user [username]`：删除 RSS 仪表盘用户（默认单用户场景会直接删除唯一用户；多用户场景会提示指定用户名）。

### 17.10 UFB 联动命令
来源：`handlers/command_handlers.py:handle_ufb_*`、`ufb/ufb_client.py`
- `/ufb_bind <domain>`：绑定域名。
- `/ufb_unbind`：解绑域名。
- `/ufb_item_change`：切换同步配置类型。
