# TelegramForwarder Bot 命令说明书（产品版）

> 文档范围：仅覆盖“通过 Telegram Bot 发送的命令/入口”（不展开过滤器链与各子系统实现细节）。  
> 数据来源：  
> - 命令路由：`handlers/bot_handler.py:handle_command`  
> - 命令实现：`handlers/command_handlers.py`（各 `handle_*`）  
> - 权限与“当前规则”：`utils/common.py:is_admin`、`utils/common.py:get_current_rule`、`utils/common.py:get_all_rules`  
> - 自动删除：`utils/auto_delete.py`、`utils/constants.py`  
> - 链接转发入口（非命令）：`handlers/link_handlers.py`  

---

## 0. 总览（你在用的到底是什么）

### 0.1 Bot 命令的入口与前置条件
来源：`handlers/bot_handler.py`、`utils/common.py:is_admin`、`main.py`
- Bot 只处理以 `/` 开头的消息；命令支持 `@botusername` 后缀（会被自动去掉）。  
  - 实现：`command = parts[0].split('@')[0][1:]`（来源：`handlers/bot_handler.py`）
- 所有命令执行前都要通过管理员校验 `is_admin(event)`（来源：`handlers/bot_handler.py`、`utils/common.py:is_admin`）。
- 监听/拉取源聊天消息靠“用户账号”（Telethon user_client）完成：用户账号需要对源聊天具备访问权限（否则可能出现 `get_entity/iter_dialogs/get_messages` 等失败）（来源：`handlers/command_handlers.py:handle_bind_command`、`managers/backfill_manager.py`、`message_listener.py`）。

### 0.2 管理员是谁（ADMINS / USER_ID）
来源：`utils/common.py:get_admin_list`、`utils/common.py:is_admin`
- 管理员列表来自环境变量 `ADMINS`（逗号分隔）；若为空则使用 `USER_ID`（来源：`utils/common.py:get_admin_list`）。
- 在频道（`message.is_channel and not message.is_group`）场景，`is_admin` 还会拉取频道管理员列表，并要求 **bot_admins 中至少一个 ID** 在频道管理员列表内（来源：`utils/common.py:is_admin`、`utils/common.py:get_channel_admins`）。

### 0.3 自动删除机制（常见“怎么消息自己没了”）
来源：`utils/auto_delete.py`、`utils/constants.py`
- 机器人回复（`reply_and_delete/respond_and_delete`）默认会在 `BOT_MESSAGE_DELETE_TIMEOUT` 秒后删除，默认值 300 秒（来源：`utils/constants.py:BOT_MESSAGE_DELETE_TIMEOUT`）。
- 用户发送的命令消息是否自动删除由 `USER_MESSAGE_DELETE_ENABLE` 控制，默认 `false`（来源：`utils/constants.py:USER_MESSAGE_DELETE_ENABLE`、`utils/auto_delete.py:async_delete_user_message`）。
- 注意：部分功能（例如 `/settings <rule_id>` 打开的设置面板）使用 `event.respond` 发送，不走自动删除（来源：`handlers/command_handlers.py:handle_settings_command`）。

---

## 1. “当前规则”机制（几乎所有操作都依赖它）

### 1.1 什么是“目标聊天窗口 / 当前规则”
来源：`models/models.py:Chat`、`utils/common.py:get_current_rule`、`handlers/command_handlers.py`
- 你在某个聊天窗口里对 Bot 发命令时，这个聊天窗口被视为“目标聊天”（target chat）。
- 数据库表 `chats` 有字段 `current_add_id`，用于记录“该目标聊天当前选中的源聊天 telegram_chat_id”（来源：`models/models.py:Chat`）。
- `get_current_rule(session, event)` 会：
  1) 以当前聊天 `current_chat.id` 去 `chats.telegram_chat_id` 查找目标聊天记录；  
  2) 读取该记录的 `current_add_id`；  
  3) 再用 `current_add_id` 找到源聊天记录；  
  4) 最后在 `forward_rules` 中查 `(source_chat_id, target_chat_id)` 对应规则（来源：`utils/common.py:get_current_rule`）。

### 1.2 如何设置“当前规则”
来源：`handlers/command_handlers.py:handle_switch_command`、`handlers/button/callback/callback_handlers.py:callback_switch`
- 使用 `/switch`（或 `/sw`）在当前聊天窗口弹出规则列表，点击按钮后会更新 `chats.current_add_id`（来源：`handlers/command_handlers.py`、`handlers/button/callback/callback_handlers.py`）。
- 若未选择当前规则，很多命令会提示：`请先使用 /switch 选择一个源聊天`（来源：`utils/common.py:get_current_rule`）。

---

## 2. 参数解析规则（哪些命令支持引号/空格）

> 这是“产品说明书级”的坑点：同样是“支持引号”，不同命令实现不一致。

### 2.1 解析器类型
来源：`handlers/command_handlers.py`
- **shlex.split（支持引号）**：会正确处理 `"带 空 格"`、`'带 空 格'` 参数。
- **str.split（不识别引号）**：引号只是普通字符；遇到空格会直接拆分。

### 2.2 各命令解析方式速查
来源：`handlers/command_handlers.py`
- 使用 `shlex.split`：`/bind`、`/add`、`/remove_keyword`、`/remove_all_keyword`、`/add_all`、`/backfill`
- 使用普通 split（不识别引号）：
  - 规则/运维类：`/settings`（仅 `rule_id`）、`/switch`、`/list_rule`、`/delete_rule`、`/clear_all`
  - 复制类：`/copy_keywords`、`/copy_keywords_regex`、`/copy_replace`、`/copy_rule`
  - 替换类：`/replace`、`/replace_all`（`pattern` 为第一个 token；`content` 为剩余整段文本）
  - 批量正则关键字：`/add_regex_all`（按空格拆分为多个表达式）
  - 正则关键字：`/add_regex`（按空格拆分为多个表达式）
  - UFB：`/ufb_bind`（domain 与 item 以空格分隔）

---

## 3. ID/序号到底指什么（避免“删错东西”）

来源：`handlers/command_handlers.py`、`models/models.py`

|操作|你输入的“ID/序号”含义|来源|
|---|---|---|
|`/settings <rule_id>`、`/delete_rule <id...>`、`/copy_rule <src> [dst]`、`/copy_* <rule_id>`|数据库里的规则主键 `forward_rules.id`|`handlers/command_handlers.py`、`models/models.py:ForwardRule`|
|`/remove_replace <ID>`|替换规则列表的**序号（1-based）**，不是 `replace_rules.id`|`handlers/command_handlers.py:handle_remove_command`|
|`/remove_keyword_by_id <ID>`|关键字列表的**序号（1-based）**（且只针对当前 add_mode 列表）|`handlers/command_handlers.py:handle_remove_command`|
|`/list_rule [page]`|分页页码（默认 1）|`handlers/command_handlers.py:handle_list_rule_command`|

---

## 4. 命令清单（完整）

来源：`handlers/bot_handler.py:handle_command`、`handlers/command_handlers.py`

> 说明：以下以“主命令”为主，括号内给出别名。

### 4.1 基础
- `/start`
- `/help`（`/h`）
- `/changelog`（`/cl`）

### 4.2 规则绑定/选择/设置
- `/bind`（`/b`）
- `/settings`（`/s`）
- `/switch`（`/sw`）
- `/backfill`（`/bf`）
- `/backfill_stop`

### 4.3 关键字
- `/add`（`/a`）
- `/add_regex`（`/ar`）
- `/list_keyword`（`/lk`）
- `/remove_keyword`（`/rk`）
- `/remove_keyword_by_id`（`/rkbi`）
- `/remove_all_keyword`（`/rak`）
- `/clear_all_keywords`（`/cak`）
- `/clear_all_keywords_regex`（`/cakr`）
- `/copy_keywords`（`/ck`）
- `/copy_keywords_regex`（`/ckr`）
- `/add_all`（`/aa`）
- `/add_regex_all`（`/ara`）
- `/export_keyword`（`/ek`）
- `/import_keyword`（`/ik`）
- `/import_regex_keyword`（`/irk`）

### 4.4 替换规则
- `/replace`（`/r`）
- `/replace_all`（`/ra`）
- `/list_replace`（`/lrp`）
- `/remove_replace`（`/rr`）
- `/clear_all_replace`（`/car`）
- `/copy_replace`（`/crp`）
- `/export_replace`（`/er`）
- `/import_replace`（`/ir`）

### 4.5 规则运维
- `/list_rule`（`/lr`）
- `/delete_rule`（`/dr`）
- `/clear_all`（`/ca`）
- `/copy_rule`（`/cr`）

### 4.6 RSS / UFB
- `/delete_rss_user`（`/dru`）
- `/ufb_bind`（`/ub`）
- `/ufb_unbind`（`/uu`）
- `/ufb_item_change`（`/uic`）

---

## 5. 命令说明书（逐条）

### 5.1 /start
来源：`handlers/command_handlers.py:handle_start_command`
- 作用：显示欢迎语与版本号。
- 用法：`/start`

### 5.2 /help（/h）
来源：`handlers/command_handlers.py:handle_help_command`
- 作用：输出命令帮助文本（注意：帮助文本是“维护者手写”，以实际实现为准）。
- 用法：`/help` 或 `/h`

### 5.3 /changelog（/cl）
来源：`handlers/command_handlers.py:handle_changelog_command`、`version.py`
- 作用：输出更新日志文本 `UPDATE_INFO`。
- 用法：`/changelog` 或 `/cl`

---

## 6. 规则绑定/选择/设置

### 6.1 /bind（/b）绑定源->目标规则
来源：`handlers/command_handlers.py:handle_bind_command`、`models/models.py:Chat/ForwardRule`

**作用**
- 创建一条转发规则：源聊天 -> 目标聊天，并把两端聊天写入 `chats` 表（若不存在）。

**用法**
- `/bind <源聊天链接或名称> [目标聊天链接或名称]`
  - 不填目标：默认以“当前聊天窗口”作为目标（来源：`handle_bind_command`）。

**参数**
- 源聊天：
  - 允许 `https://t.me/...` 或 `t.me/...`（直接 `user_client.get_entity`）
  - 允许名称（遍历 `user_client.iter_dialogs` 做子串匹配，取第一个匹配项）
- 目标聊天（可选）：同上；不填则使用当前聊天。

**典型示例**
- `/bind https://t.me/tgnews`
- `/bind "TG 新闻"`
- `/bind https://t.me/source https://t.me/target`

**副作用（落库）**
- `chats`：写入/复用 `telegram_chat_id`、`name`
- `forward_rules`：写入 `source_chat_id`、`target_chat_id`  
（来源：`handle_bind_command`、`models/models.py`）

**额外行为**
- 若目标聊天对应 `chats.current_add_id` 为空，会自动设为本次源聊天（用于后续“当前规则”命令）（来源：`handle_bind_command`）。
- 若绑定“自己”（源实体 id == 目标实体 id），会把该规则默认设为白名单模式（`rule.forward_mode=WHITELIST` 且 `rule.add_mode=WHITELIST`）（来源：`handle_bind_command`）。

**常见报错/提示**
- 参数不足：会回复用法提示（来源：`handle_bind_command`）。
- 未加入源/目标聊天：`未找到匹配...请确保账号已加入该群组/频道`（来源：`handle_bind_command`）。
- 规则已存在：`已存在相同的转发规则`（来源：`handle_bind_command`，唯一约束来自 `models/models.py:ForwardRule.__table_args__`）。

---

### 6.2 /settings（/s）打开规则设置面板
来源：`handlers/command_handlers.py:handle_settings_command`、`handlers/button/settings_manager.py`

**用法**
- `/settings`：列出“当前聊天作为目标聊天”的全部规则，点按钮进入。
- `/settings <rule_id>`：直接打开指定规则设置（`rule_id` 为 `forward_rules.id`）。

**输出**
- 使用 Inline Button 展示配置项（来源：`handlers/button/settings_manager.py`）。

---

### 6.3 /switch（/sw）选择当前规则
来源：`handlers/command_handlers.py:handle_switch_command`、`handlers/button/callback/callback_handlers.py:callback_switch`

**作用**
- 在当前聊天窗口选择“当前源聊天”，从而确定后续命令操作哪条规则（见第 1 节）。

**用法**
- `/switch` 或 `/sw`

**副作用（落库）**
- 更新 `chats.current_add_id`（来源：`callback_switch`）。

---

### 6.4 /backfill（/bf）回填历史消息
来源：`handlers/command_handlers.py:handle_backfill_command`、`managers/backfill_manager.py`、`utils/dedup.py`、`models/models.py:ProcessedMessage`

**作用**
- 对“当前规则”的源聊天执行历史消息回填，并复用完整过滤链（关键字/替换/媒体下载/AI/推送等）。

**前置条件**
- 必须先在当前聊天窗口选中规则：`/switch`（来源：`get_current_rule`）。

**用法（4 种）**
- `/backfill <N>`：最近 N 条（等价 `/backfill last <N>`）
- `/backfill last <N>` 或 `/backfill l <N>`
- `/backfill range "<start>" "<end>"` 或 `/backfill r "<start>" "<end>"`
- `/backfill all` 或 `/backfill a`

**停止**
- `/backfill_stop`：停止当前聊天窗口正在运行的回填任务（来源：`handlers/command_handlers.py:handle_backfill_stop_command`、`managers/backfill_manager.py:stop_backfill_task`）。

**时间格式**
- 支持：`YYYY-MM-DD`、`YYYY-MM-DD HH:MM`、`YYYY-MM-DD HH:MM:SS`
- 时区来自 `DEFAULT_TIMEZONE`（来源：`handlers/command_handlers.py:_parse_datetime`）。

**幂等（绝不重复）**
- 每条规则内按 `processed_messages(rule_id, dedup_key)` 唯一；先占位再处理（来源：`utils/dedup.py:claim_processed`、`models/models.py:ProcessedMessage`）。
- 代价：占位成功后若处理崩溃/异常，可能漏发（需要人工清理去重记录后再回填）（来源：`utils/dedup.py`、`managers/backfill_manager.py`）。

---

### 6.5 /backfill_stop 停止回填任务
来源：`handlers/command_handlers.py:handle_backfill_stop_command`、`managers/backfill_manager.py:stop_backfill_task`

**作用**
- 停止“当前聊天窗口”里正在执行的回填任务。

**用法**
- `/backfill_stop`

**行为**
- 回填任务采用“协作停止 + cancel I/O”的方式：先设置停止标记，再 `task.cancel()` 尽快中断等待中的网络/休眠（来源：`managers/backfill_manager.py:stop_backfill_task`、`managers/backfill_manager.py:run_backfill`）。

**返回**
- 若当前窗口无回填任务：返回 `当前没有正在运行的回填任务`（来源：`stop_backfill_task`）。
- 若停止成功：返回 `已请求停止回填任务...请稍候`，随后回填线程会输出最终统计 `回填已停止：已扫描/已处理/已跳过/未转发`（来源：`run_backfill`）。

---

## 7. 关键字管理

### 7.1 /add（/a）添加普通关键字
来源：`handlers/command_handlers.py:handle_add_command`、`models/db_operations.py:add_keywords`

**前置条件**
- 必须已选中“当前规则”：`/switch`（来源：`get_current_rule`）。

**用法**
- `/add <关键字1> [关键字2] ...`
- 支持引号包含空格：`/add "关 键 字"`

**黑/白名单归属**
- 实际写入黑/白名单由当前规则 `rule.add_mode` 决定：`is_blacklist=(rule.add_mode==AddMode.BLACKLIST)`（来源：`handle_add_command`）。

---

### 7.2 /add_regex（/ar）添加正则关键字
来源：`handlers/command_handlers.py:handle_add_command`

**用法**
- `/add_regex <regex1> [regex2] ...`

**重要限制**
- 该命令不使用 `shlex`，参数按空格拆分；正则表达式本身不应包含空格（来源：`handle_add_command`）。

---

### 7.3 /list_keyword（/lk）列出关键字
来源：`handlers/command_handlers.py:handle_list_keyword_command`、`models/db_operations.py:get_keywords`

**行为**
- 只列出当前规则 `add_mode` 对应的关键字集合（黑名单或白名单）（来源：`handle_list_keyword_command`）。

---

### 7.4 /remove_keyword（/rk）按关键字文本删除
来源：`handlers/command_handlers.py:handle_remove_command`

**用法**
- `/remove_keyword <关键字1> [关键字2] ...`
- 支持引号：`/remove_keyword "关 键 字"`

**删除范围**
- 只会在“当前规则 + 当前 add_mode（黑/白名单）”对应的列表中查找并删除（来源：`handle_remove_command`）。

---

### 7.5 /remove_keyword_by_id（/rkbi）按序号删除
来源：`handlers/command_handlers.py:handle_remove_command`

**用法**
- `/remove_keyword_by_id <ID1> [ID2] ...`

**注意**
- ID 是 `/list_keyword` 展示的序号（1-based），不是数据库主键（来源：`handle_remove_command`）。

---

### 7.6 /remove_all_keyword（/rak）在当前聊天绑定的所有规则中删除关键字
来源：`handlers/command_handlers.py:handle_remove_all_keyword_command`、`utils/common.py:get_all_rules`

**用法**
- `/remove_all_keyword <关键字1> [关键字2] ...`

**范围**
- 以“当前聊天窗口”为目标，遍历该目标聊天下的所有规则（`get_all_rules`），在每条规则的当前 `add_mode` 列表中删除匹配关键字（来源：`handle_remove_all_keyword_command`）。

---

### 7.7 /clear_all_keywords（/cak）清空当前规则全部关键字
来源：`handlers/command_handlers.py:handle_clear_all_keywords_command`

**用法**
- `/clear_all_keywords`

---

### 7.8 /clear_all_keywords_regex（/cakr）清空当前规则全部正则关键字
来源：`handlers/command_handlers.py:handle_clear_all_keywords_regex_command`

**用法**
- `/clear_all_keywords_regex`

---

### 7.9 /copy_keywords（/ck）从另一条规则复制普通关键字到当前规则
来源：`handlers/command_handlers.py:handle_copy_keywords_command`

**用法**
- `/copy_keywords <源规则ID>`

---

### 7.10 /copy_keywords_regex（/ckr）复制正则关键字
来源：`handlers/command_handlers.py:handle_copy_keywords_regex_command`

**用法**
- `/copy_keywords_regex <源规则ID>`

---

### 7.11 /add_all（/aa）批量添加关键字到当前聊天绑定的所有规则
来源：`handlers/command_handlers.py:handle_add_all_command`、`utils/common.py:get_all_rules`

**用法**
- `/add_all <关键字1> [关键字2] ...`

**黑/白名单归属（实现细节）**
- 批量写入时 `is_blacklist` 取自“当前规则”的 `add_mode`，并用于所有规则（来源：`handle_add_all_command`）。

---

### 7.12 /add_regex_all（/ara）批量添加正则关键字
来源：`handlers/command_handlers.py:handle_add_all_command`

**用法**
- `/add_regex_all <regex1> [regex2] ...`

**限制**
- 参数按空格拆分，不识别引号（来源：`handle_add_all_command`）。

---

### 7.13 /export_keyword（/ek）导出关键字
来源：`handlers/command_handlers.py:handle_export_keyword_command`

**作用**
- 导出两个文件（若有内容）：  
  - `keywords.txt`（普通关键字）  
  - `regex_keywords.txt`（正则关键字）

**文件格式（每行）**
- `<关键字> <flag>`  
  - `flag=1` 表示黑名单  
  - `flag=0` 表示白名单  
（来源：`handle_export_keyword_command`）

---

### 7.14 /import_keyword（/ik）与 /import_regex_keyword（/irk）导入关键字
来源：`handlers/command_handlers.py:handle_import_command`

**用法**
- 需要把“文件 + 命令”一起发送（同一条消息）：`/import_keyword` 或 `/import_regex_keyword`

**文件格式（每行）**
- `<关键字> <flag>`（flag 必须为 0 或 1；关键字允许包含空格，因为实现会把最后一个 token 当 flag，其余拼回关键字）（来源：`handle_import_command`）。

---

## 8. 替换规则管理

### 8.1 /replace（/r）添加替换规则
来源：`handlers/command_handlers.py:handle_replace_command`、`filters/replace_filter.py`

**用法**
- `/replace <pattern> [content]`
  - `content` 为空表示“删除匹配内容”

**重要限制**
- `pattern` 以“第一个空格”分隔获取，因此 `pattern` 不能包含空格（即使写引号也不参与解析）（来源：`handle_replace_command`）。

**特殊规则**
- 当 `pattern == ".*"` 时，过滤器会执行“全文替换”（来源：`filters/replace_filter.py`）。

---

### 8.2 /list_replace（/lrp）列出替换规则
来源：`handlers/command_handlers.py:handle_list_replace_command`

---

### 8.3 /remove_replace（/rr）删除替换规则（按序号）
来源：`handlers/command_handlers.py:handle_remove_command`

**用法**
- `/remove_replace <ID1> [ID2] ...`

**注意**
- ID 是 `/list_replace` 展示的序号（1-based），不是数据库主键（来源：`handle_remove_command`）。

---

### 8.4 /clear_all_replace（/car）清空当前规则替换规则
来源：`handlers/command_handlers.py:handle_clear_all_replace_command`

**额外行为**
- 清空后会把 `rule.is_replace` 自动置为 `False`（来源：`handle_clear_all_replace_command`）。

---

### 8.5 /copy_replace（/crp）复制替换规则
来源：`handlers/command_handlers.py:handle_copy_replace_command`

**用法**
- `/copy_replace <源规则ID>`

---

### 8.6 /replace_all（/ra）批量添加替换规则到当前聊天绑定的所有规则
来源：`handlers/command_handlers.py:handle_replace_all_command`、`utils/common.py:get_all_rules`

**用法**
- `/replace_all <pattern> [content]`

**限制**
- 与 `/replace` 相同：`pattern` 为第一个 token，不支持空格（来源：`handle_replace_all_command`）。

---

### 8.7 /export_replace（/er）导出替换规则
来源：`handlers/command_handlers.py:handle_export_replace_command`

**文件格式（每行）**
- `<pattern>\\t<content>`
  - `content` 可为空

---

### 8.8 /import_replace（/ir）导入替换规则
来源：`handlers/command_handlers.py:handle_import_command`

**用法**
- 需要把“文件 + 命令”一起发送：`/import_replace`

**文件格式（每行）**
- 按第一个制表符 `\\t` 分割为 `pattern` 与 `content`（content 可省略）（来源：`handle_import_command`）。

---

## 9. 规则运维与复制

### 9.1 /list_rule（/lr）列出所有规则
来源：`handlers/command_handlers.py:handle_list_rule_command`
- 用法：`/list_rule [page]`
- 行为：分页列出全库 `ForwardRule`（不限定某个目标聊天），每页 30 条（来源：`handle_list_rule_command`）。

### 9.2 /delete_rule（/dr）删除规则
来源：`handlers/command_handlers.py:handle_delete_rule_command`
- 用法：`/delete_rule <ID1> [ID2] ...`
- 副作用：
  - 删除 `forward_rules` 记录；
  - 并清理该规则的去重记录 `processed_messages`（来源：`handle_delete_rule_command`、`models/models.py:ProcessedMessage`）；
  - 结束后会调用 `check_and_clean_chats` 清理无引用聊天（来源：`utils/common.py:check_and_clean_chats`）。
- 额外行为：会尝试调用 RSS 服务 `DELETE /api/rule/{rule_id}`（来源：`handle_delete_rule_command`）。

### 9.3 /copy_rule（/cr）复制整条规则配置
来源：`handlers/command_handlers.py:handle_copy_rule_command`
- 用法：
  - `/copy_rule <源规则ID>`：复制到“当前规则”
  - `/copy_rule <源规则ID> <目标规则ID>`：复制到指定规则
- 行为：复制关键字/替换/媒体扩展名/媒体类型/同步表与大部分规则字段（来源：`handle_copy_rule_command`）。

### 9.4 /clear_all（/ca）清空数据库（高危）
来源：`handlers/command_handlers.py:handle_clear_all_command`
- 用法：`/clear_all`
- 行为：清空 `processed_messages/replace_rules/keywords/forward_rules/chats` 等（来源：`handle_clear_all_command`、`models/models.py`）。

---

## 10. RSS / UFB

### 10.1 /delete_rss_user（/dru）删除 RSS 用户
来源：`handlers/command_handlers.py:handle_delete_rss_user_command`、`models/models.py:User`
- 用法：`/delete_rss_user [username]`
- 行为：
  - 若只存在 1 个用户且不指定用户名：直接删除该用户；
  - 若存在多个用户且不指定用户名：列出用户名并提示指定；
  - 指定用户名：删除匹配的用户（来源：`handle_delete_rss_user_command`）。

### 10.2 /ufb_bind（/ub）绑定 UFB 域名与类型
来源：`handlers/command_handlers.py:handle_ufb_bind_command`、`models/models.py:ForwardRule`
- 用法：`/ufb_bind <domain> [item]`
- `item` 可选值：`main|content|main_username|content_username`（来源：`handle_ufb_bind_command`）。
- 副作用：更新当前规则 `ufb_domain`、`ufb_item`（来源：`handle_ufb_bind_command`）。

### 10.3 /ufb_unbind（/uu）解绑 UFB
来源：`handlers/command_handlers.py:handle_ufb_unbind_command`
- 用法：`/ufb_unbind`
- 副作用：把当前规则 `ufb_domain` 置空（来源：`handle_ufb_unbind_command`）。

### 10.4 /ufb_item_change（/uic）切换 UFB 配置类型（按钮交互）
来源：`handlers/command_handlers.py:handle_ufb_item_change_command`
- 用法：`/ufb_item_change`
- 行为：发送带按钮的选择菜单（实际切换逻辑在回调里，来源：`handlers/button/callback/*`）。

---

## 11. 附录：非命令入口（链接转发）

来源：`handlers/bot_handler.py`、`handlers/link_handlers.py`
- 在与 bot 的私聊中（`chat_id == USER_ID`），发送包含 `t.me/` 的消息链接（且不是以 `/` 开头）会触发“链接转发”（来源：`handlers/bot_handler.py`）。
- 链接格式匹配：`https://t.me/c/<id>/<msg_id>` 或 `https://t.me/<username>/<msg_id>`（来源：`handlers/link_handlers.py`）。
- 注意：`handlers/link_handlers.py` 中调用了 `reply_and_delete`，但文件顶部未显式导入该函数（来源：`handlers/link_handlers.py`），这条路径可能存在运行时报错风险（NameError）。
