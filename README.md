![img](images/logo/png/logo-title.png)

<h3><div align="center">Telegram 转发器 | Telegram Forwarder</div>

---

<div align="center">

[![Docker](https://img.shields.io/badge/-Docker-2496ED?style=flat-square&logo=docker&logoColor=white)][docker-url] [![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-4CAF50?style=flat-square)](https://github.com/leduchuong48-byte/telegram_autotgtoward/blob/main/LICENSE)

[docker-url]: https://hub.docker.com/r/leduchuong/telegram_chanel_autotoward

</div>

## 📖 简介
Telegram 转发器是一个强大的消息转发工具，只需要你的账号加入频道/群聊即可以将指定聊天中的消息转发到其他聊天，不需要bot进入对应的频道/群组即可监听。可用于信息流整合过滤，消息提醒，内容收藏等多种场景, 不受转发/复制禁止的限制。此外，利用 Apprise 强大的推送功能，你可以轻松将消息分发至聊天软件、邮件、短信、Webhooks、APIs 等各种平台。

## ✨ 特性

- 🔄 **多源转发**：支持从多个来源转发到指定目标
- 🔍 **关键词过滤**：支持白名单和黑名单模式
- 📝 **正则匹配**：支持正则表达式匹配目标文本
- 📋 **内容修改**：支持多种方式修改消息内容
- 🤖 **AI 处理**：支持使用各大厂商的AI接口
- 📹 **媒体过滤**：支持过滤指定类型的媒体文件
- 📰 **RSS订阅**：支持RSS订阅
- 📢 **多平台推送**：支持通过Apprise推送到多个平台

## Project Overview

本项目是基于 FastAPI + Telethon + Vue3(Style) 的全栈 RSS Bot，前端采用服务端模板与原生 JS 实现管理面板与移动端体验。

## Features

- RSS 订阅管理与仪表盘
- JWT 鉴权与登录拦截
- Web-based Telegram Login（Setup Wizard）
- Apple 风格 UI 与毛玻璃组件
- PWA 支持（可添加到主屏幕）
- Bot 远程控制与测试消息
- 配置编辑器与热重载（Hot Reload Config）
- 日志查看器与系统状态面板（System Status Monitoring）

## Quick Start

1. `git clone <repo-url>`
2. `cp config.sample.json config.json`（无需手动编辑，推荐在 `.env` 中设置 `INVITE_CODE`）
3. `docker compose up -d --build`
4. 打开 `http://localhost:1008` 进入 Setup Wizard 完成 Telegram 登录

默认端口映射为 `1008:8000`。如需开启 RSS 服务，请确保容器内 `RSS_ENABLED=true`。

## Configuration

### Web UI Configuration

1. 登录 Web 仪表盘
2. 点击右上角 ⚙️ Settings 图标
3. 在 “Telegram” 标签页填写 API ID / API Hash / Bot Token
4. 在 “Intelligence” 标签页配置 AI 服务（OpenAI / Gemini / DeepSeek）
5. 点击“保存并重载”，等待服务生效

### RSS Filtering

- 支持关键词黑白名单与正则匹配
- 支持媒体类型白名单、大小阈值、时长阈值与扩展名过滤

环境变量优先级更高（推荐在生产环境使用）：
- `INVITE_CODE`：在 `.env` 中设置注册邀请码，必须匹配才允许创建用户
- `JWT_SECRET_KEY`：JWT 签名密钥，建议设置强随机字符串

## Screenshots

- Dashboard: TODO
- Login: TODO
- Config Editor: TODO

## 📋 目录

- [📖 简介](#-简介)
- [✨ 特性](#-特性)
- [🧾 开发者说明书](#-开发者说明书)
- [🚀 快速开始](#-快速开始)
  - [1️⃣ 准备工作](#1️⃣-准备工作)
  - [2️⃣ 配置环境](#2️⃣-配置环境)
  - [3️⃣ 启动服务](#3️⃣-启动服务)
  - [4️⃣ 更新](#4️⃣-更新)
- [📚 使用指南](#-使用指南)
  - [🌟 基础使用示例](#-基础使用示例)
  - [🔧 特殊使用场景示例](#-特殊使用场景示例)
- [🛠️ 功能详解](#️-功能详解)
  - [⚡ 过滤流程](#-过滤流程)
  - [⚙️ 设置说明](#️-设置说明)
    - [主设置说明](#主设置说明)
    - [媒体设置说明](#媒体设置说明)
  - [🤖 AI功能](#-ai功能)
    - [配置说明](#配置)
    - [自定义模型](#自定义模型)
    - [AI处理能力](#ai-处理)
    - [定时总结功能](#定时总结)
  - [📢 推送功能](#-推送功能)
    - [设置说明](#设置说明)
  - [📰 RSS订阅](#-RSS订阅)
    - [启用RSS功能](#启用rss功能)
    - [访问RSS仪表盘](#访问rss仪表盘) 
    - [Nginx配置](#nginx配置)
    - [RSS配置说明](#rss配置管理)
    - [特殊设置项](#特殊设置项)
    - [注意事项](#注意事项)
  
- [🎯 特殊功能](#-特殊功能)
  - [🔗 链接转发功能](#-链接转发功能)
  - [🕰️ 历史消息回填功能](#-历史消息回填功能)
- [📝 命令列表](#-命令列表)
- [💐 致谢](#-致谢)
- [☕ 捐赠](#-捐赠)
- [📄 开源协议](#-开源协议)



## 🧾 开发者说明书

- 全量“代码与规则说明书（开发者版）”：`code.md`（覆盖过滤器链、DB 模型、命令索引、历史回填与幂等等）
- Bot 命令说明书（产品版）：`bot_cod.md`（覆盖所有 bot 命令、别名、用法与注意事项）

## 🚀 快速开始

### 1️⃣ 准备工作

1. 获取 Telegram API 凭据：
   - 访问 https://my.telegram.org/apps
   - 创建一个应用获取 `API_ID` 和 `API_HASH`

2. 获取机器人 Token：
   - 与 @BotFather 对话创建机器人
   - 获取机器人的 `BOT_TOKEN`

3. 获取用户 ID：
   - 与 @userinfobot 对话获取你的 `USER_ID`

### 2️⃣ 配置环境

本仓库 `docker-compose.yml` 已配置为**本地构建镜像**（来源：`docker-compose.yml`、`Dockerfile`），请在**源码目录**内执行以下步骤。

复制仓库的 **[.env.example](./.env.example)** 文件，填入必填项，然后重命名为`.env`
```bash
cp .env.example .env
```
请在 `.env` 中设置 `INVITE_CODE`，用于首次注册与后续用户管理。



### 3️⃣ 启动服务

首次运行（推荐）：

> 说明：仅支持 Docker Compose v2（`docker compose`）。

```bash
docker compose up -d --build
```

服务启动后访问 `http://localhost:1008`，进入 Setup Wizard 完成 Telegram 登录，无需命令行交互。

### 4️⃣ 更新
注意：当前 `docker-compose.yml` 默认使用 `build:` 本地构建（来源：`docker-compose.yml`），更新代码后需要重新 build。
```bash
docker compose down
```
```bash
docker compose build
```
```bash
docker compose up -d
```

### 🧯 常见构建问题（Docker）

**现象：构建到最后一步报错 `parent snapshot ... does not exist`**

这属于 Docker/BuildKit 在“导出镜像并解包到本地镜像仓库”阶段的快照/缓存不一致问题（依据：Docker 输出 `failed to prepare extraction snapshot ... parent snapshot ... does not exist`），一般与项目代码无关。

按顺序尝试：

```bash
# 1) 清理 BuildKit/buildx 缓存
docker buildx prune -af
docker builder prune -af

# 2) 重启 Docker 服务（按你的系统选择其一）
sudo systemctl restart docker
# 或 sudo service docker restart

# 3) 重新构建
docker compose build autotgtoward

# 4) 仍失败：临时关闭 BuildKit
DOCKER_BUILDKIT=0 docker compose build autotgtoward
```

## 📚 使用指南

### 🌟 基础使用示例

假设订阅了频道 "TG 新闻" (https://t.me/tgnews) 和 "TG 阅读" (https://t.me/tgread) ，但想过滤掉一些不感兴趣的内容：

1. 创建一个 Telegram 群组/频道（例如："My TG Filter"）
2. 将机器人添加到群组/频道，并设置为管理员
3. 在**新创建**的群组/频道中发送命令：
   ```bash
   /bind https://t.me/tgnews 或者 /bind "TG 新闻"
   /bind https://t.me/tgread 或者 /bind "TG 阅读"
   ```
4. 设置消息处理模式：
   ```bash
   /settings
   ```
   选择要操作的对应频道的规则，根据喜好设置
   
   详细设置说明请查看 [🛠️ 功能详解](#️-功能详解)

5. 添加屏蔽关键词：
   ```bash
   /add 广告 推广 '这是 广告'
   ```

6. 如果发现转发的消息格式有问题（比如有多余的符号），可以使用正则表达式处理：
   ```bash
   /replace \*\*
   ```
   这会删除消息中的所有 `**` 符号

>注意：以上增删改查操作，只对第一个绑定的规则生效，示例里是TG 新闻。若想对TG 阅读进行操作，需要先使用`/settings(/s)`，选择TG 阅读，再点击"应用当前规则"，就可以对此进行增删改查操作了。也可以使用`/add_all(/aa)`，`/replace_all(/ra)`等指令同时对两条规则生效

这样，你就能收到经过过滤和格式化的频道消息了

### 🔧 特殊使用场景示例  

#### 1. TG 频道的部分消息由于文字嵌入链接，点击会让你确认再跳转，例如 NodeSeek 的官方通知频道  

频道的原始消息格式 
```markdown
[**贴子标题**](https://www.nodeseek.com/post-xxxx-1)
```  
可以对通知频道的转发规则 **依次** 使用以下指令：  
```plaintext
/replace \*\*
/replace \[(?:\[([^\]]+)\])?([^\]]+)\]\(([^)]+)\) [\1]\2\n(\3)
/replace \[\]\s*
```  
最终所有转发的消息都会变成以下格式，这样直接点击链接就无需确认跳转：  
```plaintext
贴子标题
(https://www.nodeseek.com/post-xxxx-1)
```  

---

#### 2. 监听用户消息格式不美观，可优化消息显示方式  

**依次** 使用以下指令：  
```plaintext
/r ^(?=.) <blockquote>
/r (?<=.)(?=$) </blockquote>
```  
然后设置消息格式为 **HTML**，这样监听用户消息时，消息格式就会美观很多：  

![示例图片](./images/user_spy.png)

---

#### 3. 同步规则操作  

在 **设置菜单** 中开启 **"同步规则"**，并选择 **目标规则**，当前规则的所有操作将同步到选定的规则。  

适用于以下场景：  
- 不想在当前窗口处理规则  
- 需要同时操作多个规则  

如果当前规则仅用于同步而不需实际生效，可将 **"是否启用规则"** 设置为 **"否"**。

---

#### 4. 如何转发到收藏夹 (Saved Messages)
> 不推荐，操作比较繁琐
1. 在你的 bot 管理的任意群组或频道中发送以下命令：  
   ```bash
   /bind https://t.me/tgnews 你的用户名（即展示的名称）
   ```  

2. 随意新建一个规则，并进行以下设置：  
   - **开启同步功能**，同步到 **转发收藏夹的规则**
   - **转发模式** 选择 **"用户模式"**  
   - **禁用规则**（将规则”是否启用规则“设置为关闭）  

这样，你就可以在其他规则中管理收藏夹的规则，所有操作都会同步到 **转发收藏夹** 规则中。


## 🛠️ 功能详解

### ⚡ 过滤流程
首先要清楚消息过滤顺序，括号里对应设置里的选项：

![img](./images/flow_chart.png)



### ⚙️ 设置说明
| 主设置界面 | AI设置界面 | 媒体设置界面 |
|---------|------|------|
| ![img](./images/settings_main.png) | ![img](./images/settings_ai.png) | ![img](./images/settings_media.png) |

#### 主设置说明
以下对设置选项进行说明
| 设置选项 | 说明 |
|---------|------|
| 应用当前规则 | 选择后，关键字指令(/add,/remove_keyword,/list_keyword等)和替换指令(/replace,/list_replace等)的增删改查导入导出将作用于当前规则 |
| 是否启用规则 | 选择后，当前规则将被启用，否则将被禁用 |
| 当前关键字添加模式 | 点击可切换黑/白名单模式，由于黑白名单是分开处理的，需要手动切换，注意，此时关键字的增删改查都和这里的模式有关，如果要使用指令对当前规则的白名单进行增删改查操作，请确保这里的模式是白名单 |
| 过滤关键字时是否附带发送者名称和ID | 启用后，过滤关键字时会包含发送者名称和ID信息(不会添加到实际消息中)，可用于针对特定用户进行过滤 |
| 处理模式 | 可切换编辑/转发模式。编辑模式下会直接修改原消息；转发模式下会将处理后的消息转发到目标聊天。注意:编辑模式仅适用于你是管理员的且原消息是频道消息或群组中自己发送的消息 |
| 过滤模式 | 可切换仅黑名单/仅白名单/先黑后白/先白后黑模式。由于黑白名单分开存储，可根据需要选择不同的过滤方式 |
| 转发模式 | 可切换用户/机器人模式。用户模式下使用用户账号转发消息；机器人模式下使用机器人账号发送消息 |
| 替换模式 | 启用后将根据已设置的替换规则对消息进行处理 |
| 消息格式 | 可切换Markdown/HTML格式，在最终发送阶段生效，一般使用默认的Markdown即可 |
| 预览模式 | 可切换开启/关闭/跟随原消息。开启后会预览消息中的第一个链接，默认跟随原消息的预览状态 |
| 原始发送者/原始链接/发送时间 | 启用后会在消息发送时添加这些信息，默认关闭，可在"其他设置"菜单中设置自定义模板 |
| 延时处理 | 启用后会按设定的延迟时间重新获取原消息内容，再开始处理流程，适用于频繁修改消息的频道/群组，可在 config/delay_time.txt 中添加自定义延迟时间 |
| 删除原始消息 | 启用后会删除原消息，使用前请确认是否有删除权限 |
| 评论区直达按钮 | 启用后在转发后的消息下发添加评论区直达按钮，前提是原消息有评论区 |
| 同步到其他规则 | 启用后会同步当前规则的操作到其他规则，除了"是否启用规则"和"开启同步"其他设置都会同步 |

#### 媒体设置说明
| 设置选项 | 说明 |
|---------|------|
| 媒体类型过滤 | 启用后按“媒体类型过滤模式”对媒体进行筛选 |
| 媒体类型过滤模式 | 黑名单=屏蔽选中的类型；白名单=仅放行选中的类型 |
| 选择的媒体类型 | 根据过滤模式选择要屏蔽/放行的媒体类型。支持：图片 (photo)、文档 (document)、视频 (video)、音频 (audio)、语音 (voice)、纯文本 (text，表示无媒体的消息)。注意：Telegram对媒体文件的分类是固定的，主要就是这几种，其中所有不属于图片、视频、音频、语音的文件都会被归类为"文档"类型。比如病毒文件(.exe)、压缩包(.zip)、文本文件(.txt)等，在 Telegram 中都属于"文档"类型。 |
| 媒体大小过滤 | 启用后会过滤掉超过设置大小的媒体 |
| 媒体大小限制 | 设置媒体大小限制，单位：MB，可在 config/media_size.txt 中添加自定义大小 |
| 媒体大小超限时发送提醒 | 启用后媒体超限会发送提醒消息 |
| 媒体扩展名过滤 | 启用后会过滤掉选中的媒体扩展名 |
| 媒体扩展名过滤模式 | 切换黑/白名单模式 |
| 选择的媒体扩展名 | 选择要过滤的的媒体扩展名，可在 config/media_extensions.txt 中添加自定义扩展名 |
| 放行文本 | 开启后过滤媒体时不会屏蔽整条消息，而是单独转发文本 |

#### 其他设置说明

其他设置菜单中整合了常用的几个指令，使其可以在界面直接交互，包括：
- 复制规则
- 复制关键字
- 复制替换规则
- 清除关键字
- 清除替换规则
- 删除规则

其中清除关键字、清除替换规则、删除规则可以对其他规则生效

同时你可以在这里设置自定义模板，包括：用户信息模板、时间模板、原始链接模板
| 设置选项 | 说明 |
|---------|------|
|反转黑名单| 启用后，将把黑名单当成白名单处理，若使用先白后黑模式，黑名单会作为第二重白名单处理|
|反转白名单| 启用后，将把白名单当成黑名单处理，若使用先白后黑模式，白名单会作为第二重黑名单处理|

结合“先 X 后 X”模式，可实现双层黑/白名单机制。例如，反转黑名单后，“先白后黑”中的黑名单将变为第二层级的白名单，适用于监听特定用户并筛选其特殊关键词等多种场景。



### 🤖 AI功能

项目内置了各大厂商的AI接口，可以帮你：
- 自动翻译外语内容
- 定时总结群组消息
- 智能过滤广告信息
- 自动为内容打标签
....
  
#### 配置

1. 在 `.env` 文件中配置你的 AI 接口：
```ini
# OpenAI API
OPENAI_API_KEY=your_key
OPENAI_API_BASE=  # 可选，默认官方接口

# Claude API
CLAUDE_API_KEY=your_key

# 其他支持的接口...
```

#### 自定义模型

没找到想要的模型名字？在 `config/ai_models.json` 中添加即可。

#### AI 处理

AI处理提示词中可以使用以下格式：
- `{source_message_context:数字}` - 获取源聊天窗口最新的指定数量消息
- `{target_message_context:数字}` - 获取目标聊天窗口最新的指定数量消息
- `{source_message_time:数字}` - 获取源聊天窗口最近指定分钟数的消息
- `{target_message_time:数字}` - 获取目标聊天窗口最近指定分钟数的消息

提示词示例：

前置：开启AI处理后再次执行关键词过滤，把“#不转发”添加到过滤关键字中
```
这是一个资讯整合频道，从多个源获取消息，现在你要判断新资讯是否和历史资讯内容重复了，若重复，则只需要回复“#不转发”，否则请返回新资讯的原文并保持格式。
记住，你只能返回“#不转发”或者新资讯的原文。
以下是历史资讯：{target_message_context:10}
以下是新资讯：
```

#### 定时总结

开启定时总结后，机器人会在指定时间（默认每天早上 7 点）自动总结过去 24 小时的消息。

- 可在 `config/summary_time.txt` 中添加多个总结时间点
- 在 `.env` 中设置默认时区
- 自定义总结的提示词

> 注意：总结功能会消耗较多的 API 额度，请根据需要开启。

### 📢 推送功能

除了telegram内部消息转发外，项目还集成了Apprise，利用其强大的推送功能，你可以轻松将消息分发至聊天软件、邮件、短信、Webhooks、APIs 等各种平台。

| 推送设置主界面 | 推送设置子界面 |
|---------|------|
| ![img](./images/settings_push.png) | ![img](./images/settings_push_sub1.png) |

#### 设置说明

| 设置选项 | 说明 |
|---------|------|
| 只转发到推送配置 | 开启后跳过转发过滤器,直接跳到推送过滤器 |
| 媒体发送方式 | 支持两种模式:<br>- 单个:每个媒体文件单独推送一条消息<br>- 全部:将所有媒体文件合并到一条消息中推送<br>具体使用哪种模式取决于目标平台是否支持一次推送多个附件 |

### 如何添加推送配置？
完整的推送平台列表和配置格式请参考 [Apprise Wiki](https://github.com/caronc/apprise/wiki)

**示例：使用 ntfy.sh 推送**

*   假设你想推送到 ntfy.sh 上的一个名为 `my_topic` 的主题。
*   根据 Apprise Wiki，其格式为 `ntfy://ntfy.sh/你的主题名`。
*   那么，你需要添加的配置 URL 就是：
    ```
    ntfy://ntfy.sh/my_topic
    ```



## 📰 RSS订阅

项目集成了将Telegram消息转换为RSS Feed的功能，可以轻松地将Telegram频道/群组内容转为标准RSS格式，方便通过RSS阅读器跟踪。

### 启用RSS功能

1. 在 `.env` 文件中配置RSS相关参数：
   ```ini
   # RSS配置
   # 是否启用RSS功能 (true/false)
   RSS_ENABLED=true
   # RSS基础访问URL，留空则使用默认的访问URL（例如：https://rss.example.com）
   RSS_BASE_URL=
   # RSS媒体文件基础URL，留空则使用默认的访问URL（例如：https://media.example.com）
   RSS_MEDIA_BASE_URL=
   ```
2. docker-compose.yml取消注释
   ```
    # 如果需要使用 RSS 功能，请取消以下注释
     ports:
       - 9804:8000
   ```
3. 重启服务以启用RSS功能：
   ```bash
   docker compose restart
   ```
> 注意：旧版本用户需要用新的docker-compose.yml文件重新部署：[docker-compose.yml](./docker-compose.yml)
### 访问RSS仪表盘

浏览器访问 `http://你的服务器地址:9804/`

### Nginx配置
```
 location / {
        proxy_pass http://127.0.0.1:9804;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
```

### RSS配置管理

相关界面

| 登录界面 | Dashboard界面 | 新建/编辑配置界面 |
|---------|------|------|
| ![img](./images/rss_login.png) | ![img](./images/rss_dashboard.png) | ![img](./images/rss_create_config.png) |


### 新建/编辑配置界面说明
| 设置选项 | 说明 |
|---------|------|
| 规则ID | 选择现有的一个转发规则，用于生成RSS订阅 |
| 复制已有配置 | 选择现有的一个RSS配置，复制它的配置到当前表单|
|订阅源标题| 设置订阅源标题 |
|自动填充| 点击后自动根据规则的源聊天窗口名字生成订阅源标题 |
|订阅源描述| 设置订阅源描述 |
|语言| 占位，暂无特殊功能 |
|最大条目数| 设置RSS订阅源的最大条目数，默认50，对于媒体比较多的聊天源，请根据硬盘实际硬盘大小设置 |
|使用 AI 提取标题和内容| 启用后，将使用AI服务自动分析消息，提取标题和内容和整理格式，AI模型请在bot中设置，不受bot中“是否开启 AI 处理”选项影响，此选项开启后和下面所有配置互斥 |
|AI 提取提示词| 设置AI提取标题和内容的提示词，如需自定义，请务必让AI返回以下json格式内容：`{ "title": "标题", "content": "正文内容" }` |
|自动提取标题| 启用后，由预设好的正则表达式自动提取标题 |
|自动提取内容| 启用后，由预设好的正则表达式自动提取内容 |
|自动将 Markdown 转换为 HTML| 启用后，将使用相关库自动将Telegram中的Markdown格式转换为标准HTML，如需自行处理，请在bot中使用 `/replace` 自行替换 |
|启用自定义标题提取正则表达式| 启用后，将使用自定义正则表达式提取标题 |
|启用自定义内容提取正则表达式| 启用后，将使用自定义正则表达式提取内容 |
|优先级| 设置正则表达式的执行顺序，数字越小优先级越高。系统会按优先级从高到低依次执行正则表达式，**前一个正则表达式提取的结果会作为下一个的输入**，直到完成所有提取 |
|正则表达式测试| 可用于测试当前正则表达式是否匹配目标文本 |

### 特殊说明
- 若只开启自动提取标题，而不开启自动提取内容，则内容会是包含提取了标题的完整的Telegram消息内容
- 若内容处理选项和正则表达式配置都为空，会自动匹配前20个字符作为标题，内容则为原始消息


### 特殊设置项
若在.env中开启`RSS_ENABLED=true`，则会在bot的设置中会新增一个`只转发到RSS`的选项，启用后，消息经过各种处理后会在RSS过滤器处理后中断，不会执行转发/编辑


### 注意事项

- 没有找回密码功能，请妥善保管你的账号密码

## 🎯 特殊功能

### 🔗 链接转发功能

向bot发送消息链接，即可把那条消息转发到当前聊天窗口，无视禁止转发和复制的限制（项目自身功能已无视转发和复制限制

### 🕰️ 历史消息回填功能

> 目标：把“已经存在的历史消息”按规则补发到目标聊天。

回填会遵循规则的转发方式：`use_bot=true` 时执行完整过滤链（关键字/替换/媒体下载/AI/推送等，见 `filters/process.py`），`use_bot=false` 时走用户模式（仅关键字过滤 + forward_messages）。回填在**成功转发后**写入去重记录，避免失败/过滤导致永远跳过。

#### 使用规则

1) 先在“目标聊天窗口”里选择要回填的源聊天（复用现有逻辑，未选择会提示先 `/switch`）
- `/switch`

2) 开始回填
- 最近 N 条：`/backfill 100` 或 `/backfill last 100`
- 指定时间段：`/backfill range "2025-01-01 00:00" "2025-01-02 23:59"`
- 全部：`/backfill all`
- 清理回填去重记录：`/backfill_reset`

回填任务会在后台异步执行，并在当前聊天窗口输出开始/进度/结束统计信息（实现见 `managers/backfill_manager.py`）。

回填自适应节流（建议开启，避免触发 Telegram 限流）：
- `BACKFILL_ADAPTIVE_THROTTLE`：是否启用自适应节流，默认 true
- `BACKFILL_THROTTLE_MIN_DELAY`：最小延迟（秒），默认 0.2
- `BACKFILL_THROTTLE_MAX_DELAY`：最大延迟（秒），默认 6.0
- `BACKFILL_THROTTLE_INCREASE_STEP`：触发限流/失败时增加步长（秒），默认 0.5
- `BACKFILL_THROTTLE_DECREASE_STEP`：稳定后降低步长（秒），默认 0.2
- `BACKFILL_THROTTLE_COOLDOWN_THRESHOLD`：连续成功多少次后降低延迟，默认 10

实时转发自适应节流（建议开启，避免触发 Telegram 限流）：
- `REALTIME_ADAPTIVE_THROTTLE`：是否启用自适应节流，默认 true
- `REALTIME_THROTTLE_MIN_DELAY`：最小延迟（秒），默认 0.2
- `REALTIME_THROTTLE_MAX_DELAY`：最大延迟（秒），默认 6.0
- `REALTIME_THROTTLE_INCREASE_STEP`：触发限流/失败时增加步长（秒），默认 0.5
- `REALTIME_THROTTLE_DECREASE_STEP`：稳定后降低步长（秒），默认 0.2
- `REALTIME_THROTTLE_COOLDOWN_THRESHOLD`：连续成功多少次后降低延迟，默认 10

实体预解析（解决 Bot 无法解析公开群/频道）：
- `PRE_RESOLVE_TARGETS`：Bot 启动时预解析目标实体（公开链接/用户名/ID），多个用分号分隔

#### 幂等规则（绝不重复）

去重表：SQLite `./db/forward.db` 的 `processed_messages` 表。

去重粒度：同一条规则内（`rule_id`），按 `dedup_key` 唯一。
- 普通消息：`dedup_key = m:<message_id>`
- 媒体组（album）：`dedup_key = g:<grouped_id>`（整个媒体组只会处理一次）

实现策略：**成功转发后写入去重记录**（避免失败/过滤导致永远跳过）
- 先处理消息，成功后再写入 `processed_messages`。
- 好处：不会因为处理失败而永久跳过。

#### 回填与幂等的关键代码

> 以下代码均来自仓库当前版本，方便你直接在 README 中检索与审计。

**1) 数据库表：`processed_messages`**

文件：`models/models.py`

```python
class ProcessedMessage(Base):
    __tablename__ = 'processed_messages'

    id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey('forward_rules.id'), nullable=False)
    dedup_key = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('rule_id', 'dedup_key', name='unique_rule_dedup_key'),
    )
```

**2) 幂等写入：实时预占位，回填成功后写入**

文件：`utils/dedup.py`

```python
import logging

from sqlalchemy.exc import IntegrityError

from models.models import ProcessedMessage, get_session

logger = logging.getLogger(__name__)


def build_dedup_key(event) -> str | None:
    """
    生成幂等去重键（同一规则内唯一）。

    - 媒体组：按 grouped_id 去重（整个 album 视为一次处理）
    - 普通消息：按 message.id 去重
    """
    try:
        message = getattr(event, "message", None)
        if not message:
            return None

        grouped_id = getattr(message, "grouped_id", None)
        if grouped_id:
            return f"g:{grouped_id}"

        message_id = getattr(message, "id", None)
        if message_id is None:
            return None

        return f"m:{message_id}"
    except Exception as e:
        logger.error(f"生成去重键失败: {str(e)}")
        return None


def claim_processed(rule_id: int, dedup_key: str) -> bool:
    """
    先占位再处理：确保“绝不重复”。

    返回 True 表示本次获得处理权；False 表示已处理/已占位，应跳过。
    """
    session = get_session()
    try:
        session.add(ProcessedMessage(rule_id=rule_id, dedup_key=dedup_key))
        session.commit()
        return True
    except IntegrityError:
        session.rollback()
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"写入去重记录失败: {str(e)}")
        return False
    finally:
        session.close()
```

**3) 实时消息也接入幂等（防止重复转发）**

文件：`message_listener.py`

```python
from utils.dedup import build_dedup_key, claim_processed

# ...
for rule in rules:
    if not rule.enable_rule:
        continue
    dedup_key = build_dedup_key(event)
    if dedup_key and not claim_processed(rule.id, dedup_key):
        logger.info(f'规则 {rule.id} 已处理过该消息，跳过: {dedup_key}')
        continue
    # 继续执行转发处理
```

**4) 回填执行器（按 last/range/all 拉取历史并遵循规则转发方式）**

文件：`managers/backfill_manager.py`

```python
import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Optional

import pytz
from sqlalchemy.orm import joinedload, selectinload

from filters.process import process_forward_rule
from models.models import ForwardRule, get_session
from utils.dedup import build_dedup_key, claim_processed

logger = logging.getLogger(__name__)


class BackfillEvent:
    """
    将历史 Message 包装成与 Telethon NewMessage event 足够兼容的对象，
    以便复用现有过滤器链（filters/process.py）。
    """

    def __init__(self, message, user_client):
        self.message = message
        self.client = user_client

    @property
    def chat_id(self):
        return getattr(self.message, "chat_id", None)

    @property
    def id(self):
        return getattr(self.message, "id", None)

    @property
    def sender_id(self):
        return getattr(self.message, "sender_id", None)

    @property
    def sender(self):
        return getattr(self.message, "sender", None)

    async def get_chat(self):
        if hasattr(self.message, "get_chat"):
            return await self.message.get_chat()
        return None


@dataclass(frozen=True)
class BackfillParams:
    mode: str  # last | range | all
    limit: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    batch_size: int = 20
    batch_delay_seconds: float = 0.0
    message_delay_seconds: float = 0.0


def _get_timezone():
    timezone_name = os.getenv("DEFAULT_TIMEZONE", "Asia/Shanghai")
    return pytz.timezone(timezone_name)


def _load_rule_for_processing(rule_id: int) -> Optional[ForwardRule]:
    session = get_session()
    try:
        rule = (
            session.query(ForwardRule)
            .options(
                joinedload(ForwardRule.source_chat),
                joinedload(ForwardRule.target_chat),
                selectinload(ForwardRule.keywords),
                selectinload(ForwardRule.replace_rules),
            )
            .get(rule_id)
        )
        if not rule:
            return None

        _ = rule.source_chat, rule.target_chat, rule.keywords, rule.replace_rules

        session.expunge_all()
        return rule
    finally:
        session.close()


async def _iter_last_messages(user_client, source_chat_id: int, limit: int) -> AsyncIterator:
    async for message in user_client.iter_messages(source_chat_id, limit=limit):
        yield message


async def _iter_messages_by_time_range(
    user_client,
    source_chat_id: int,
    start_time: datetime,
    end_time: datetime,
    batch_size: int,
    batch_delay_seconds: float,
) -> AsyncIterator:
    timezone = _get_timezone()
    current_offset = 0

    while True:
        messages_batch = await user_client.get_messages(
            source_chat_id,
            limit=batch_size,
            offset_date=end_time,
            offset_id=current_offset,
            reverse=False,
        )

        if not messages_batch:
            break

        should_break = False
        for message in messages_batch:
            msg_time = message.date.astimezone(timezone) if getattr(message, "date", None) else None
            if msg_time is None:
                continue
            if msg_time > end_time:
                continue
            if msg_time < start_time:
                should_break = True
                break
            yield message

        current_offset = messages_batch[-1].id

        if should_break:
            break

        if batch_delay_seconds > 0:
            await asyncio.sleep(batch_delay_seconds)


async def run_backfill(
    *,
    bot_client,
    user_client,
    rule_id: int,
    params: BackfillParams,
    notify_chat_id: Optional[int] = None,
):
    rule = _load_rule_for_processing(rule_id)
    if not rule:
        raise ValueError(f"找不到规则: {rule_id}")

    if not rule.enable_rule:
        raise ValueError(f"规则未启用: {rule_id}")

    source_chat_id = int(rule.source_chat.telegram_chat_id)

    timezone = _get_timezone()
    now = datetime.now(timezone)

    if params.mode == "last":
        if not params.limit or params.limit <= 0:
            raise ValueError("last 模式需要提供正整数 limit")
        iterator = _iter_last_messages(user_client, source_chat_id, params.limit)
        mode_desc = f"最近 {params.limit} 条"
    elif params.mode == "range":
        if not params.start_time or not params.end_time:
            raise ValueError("range 模式需要提供 start_time/end_time")
        iterator = _iter_messages_by_time_range(
            user_client,
            source_chat_id,
            params.start_time,
            params.end_time,
            params.batch_size,
            params.batch_delay_seconds,
        )
        mode_desc = f"{params.start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ {params.end_time.strftime('%Y-%m-%d %H:%M:%S')}"
    elif params.mode == "all":
        start_time = timezone.localize(datetime(1970, 1, 1, 0, 0, 0))
        end_time = now
        iterator = _iter_messages_by_time_range(
            user_client,
            source_chat_id,
            start_time,
            end_time,
            params.batch_size,
            params.batch_delay_seconds,
        )
        mode_desc = "全部历史"
    else:
        raise ValueError(f"未知回填模式: {params.mode}")

    scanned = 0
    skipped_dup = 0
    processed = 0
    not_forwarded = 0

    if notify_chat_id:
        try:
            await bot_client.send_message(
                notify_chat_id,
                f"开始回填：规则 {rule.id}，来源 {rule.source_chat.name} -> 目标 {rule.target_chat.name}\n范围：{mode_desc}",
            )
        except Exception:
            pass

    last_report_time = datetime.now(timezone)

    async for message in iterator:
        scanned += 1

        event = BackfillEvent(message, user_client)
        dedup_key = build_dedup_key(event)
        if not dedup_key:
            continue

        if not claim_processed(rule.id, dedup_key):
            skipped_dup += 1
            continue

        try:
            ok = await process_forward_rule(bot_client, event, str(source_chat_id), rule)
            if ok:
                processed += 1
            else:
                not_forwarded += 1
        except Exception as e:
            logger.error(f"回填处理消息失败: rule={rule.id}, key={dedup_key}, err={str(e)}")
            not_forwarded += 1

        if params.message_delay_seconds > 0:
            await asyncio.sleep(params.message_delay_seconds)

        if notify_chat_id and (datetime.now(timezone) - last_report_time).total_seconds() >= 30:
            last_report_time = datetime.now(timezone)
            try:
                await bot_client.send_message(
                    notify_chat_id,
                    f"回填进度：已扫描 {scanned}，已处理 {processed}，已跳过 {skipped_dup}，未转发 {not_forwarded}",
                )
            except Exception:
                pass

    if notify_chat_id:
        try:
            await bot_client.send_message(
                notify_chat_id,
                f"回填完成：已扫描 {scanned}，已处理 {processed}，已跳过 {skipped_dup}，未转发 {not_forwarded}",
            )
        except Exception:
            pass
```

**5) 命令入口（解析参数并启动后台回填）**

文件：`handlers/command_handlers.py`

```python
def _parse_datetime(text: str, timezone) -> datetime:
    formats = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=0, minute=0, second=0)
            return timezone.localize(dt)
        except ValueError:
            continue
    raise ValueError("时间格式错误，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM[:SS]")


async def handle_backfill_command(event, client, parts):
    """
    回填历史消息（按规则转发方式执行）

    用法：
    /backfill last <N>
    /backfill <N>
    /backfill range "<start>" "<end>"
    /backfill all
    """
    message_text = event.message.text or ""
    try:
        if " " in message_text:
            _, args_str = message_text.split(" ", 1)
            args = shlex.split(args_str)
        else:
            args = []
    except Exception:
        args = []

    if not args:
        await async_delete_user_message(event.client, event.message.chat_id, event.message.id, 0)
        await reply_and_delete(
            event,
            "用法:\n"
            "/backfill last <N>\n"
            "/backfill <N>\n"
            "/backfill range \"2025-01-01 00:00\" \"2025-01-02 23:59\"\n"
            "/backfill all",
        )
        return

    session = get_session()
    try:
        current = await get_current_rule(session, event)
        if not current:
            return
        rule, source_chat = current
    finally:
        session.close()

    main = await get_main_module()
    user_client = main.user_client

    timezone_name = os.getenv("DEFAULT_TIMEZONE", "Asia/Shanghai")
    timezone = pytz.timezone(timezone_name)

    mode = args[0].lower()

    try:
        if mode.isdigit():
            params = BackfillParams(mode="last", limit=int(mode))
        elif mode in ("last", "l"):
            if len(args) < 2 or not args[1].isdigit():
                raise ValueError("last 模式需要提供正整数 N")
            params = BackfillParams(mode="last", limit=int(args[1]))
        elif mode in ("range", "r"):
            if len(args) < 3:
                raise ValueError("range 模式需要提供 start/end")
            start_time = _parse_datetime(args[1], timezone)
            end_time = _parse_datetime(args[2], timezone)
            if end_time < start_time:
                raise ValueError("end 必须 >= start")
            params = BackfillParams(mode="range", start_time=start_time, end_time=end_time)
        elif mode in ("all", "a"):
            params = BackfillParams(mode="all")
        else:
            raise ValueError("未知模式")
    except ValueError as e:
        await async_delete_user_message(event.client, event.message.chat_id, event.message.id, 0)
        await reply_and_delete(event, f"参数错误: {str(e)}\n用法: /backfill last <N> | /backfill range <start> <end> | /backfill all")
        return

    asyncio.create_task(
        run_backfill(
            bot_client=client,
            user_client=user_client,
            rule_id=rule.id,
            params=params,
            notify_chat_id=event.chat_id,
        )
    )

    await async_delete_user_message(event.client, event.message.chat_id, event.message.id, 0)
    await reply_and_delete(event, f"已开始回填：规则 {rule.id}（{source_chat.name} -> {rule.target_chat.name}）")
```

**6) 命令路由与命令注册**

文件：`handlers/bot_handler.py`

```python
        'backfill': lambda: handle_backfill_command(event, client, parts),
        'bf': lambda: handle_backfill_command(event, client, parts),
```

文件：`main.py`

```python
        BotCommand(
            command='backfill',
            description='回填历史消息'
        ),
```

### 🔄 与通用论坛屏蔽插件联动
> https://github.com/heavrnl/universalforumblock

确保.env文件中已配置相关参数，在已经绑定好的聊天窗口中使用`/ufb_bind <论坛域名>`，即可实现三端联动屏蔽，使用`/ufb_item_change`切换要同步当前域名的主页关键字/主页用户名/内容页关键字/内容页用户名

## 📝 命令列表

```bash
命令列表

基础命令
/start - 开始使用
/help(/h) - 显示此帮助信息

绑定和设置
/bind(/b) <源聊天链接或名称> [目标聊天链接或名称] - 绑定源聊天
/settings(/s) [规则ID] - 管理转发规则
/switch(/sw) - 切换当前需要设置的聊天规则
/backfill(/bf) <last|range|all...> - 回填历史消息（最近N/时间段/全部，按规则转发方式）
/backfill_stop - 停止当前聊天窗口的回填任务
/backfill_reset - 清理当前规则的回填去重记录
/changelog(/cl) - 查看更新日志

转发规则管理
/copy_rule(/cr)  <源规则ID> [目标规则ID] - 复制指定规则的所有设置到当前规则或目标规则ID
/delete_rule(/dr) <规则ID> [规则ID] [规则ID] ... - 删除指定规则
/list_rule(/lr) - 列出所有转发规则

关键字管理
/add(/a) <关键字> [关键字] ["关 键 字"] ['关 键 字'] ... - 添加普通关键字
/add_regex(/ar) <正则表达式> [正则表达式] [正则表达式] ... - 添加正则表达式
/add_all(/aa) <关键字> [关键字] [关键字] ... - 添加普通关键字到当前频道绑定的所有规则
/add_regex_all(/ara) <正则表达式> [正则表达式] [正则表达式] ... - 添加正则关键字到所有规则
/list_keyword(/lk) - 列出所有关键字
/remove_keyword(/rk) <关键词> ["关 键 字"] ['关 键 字'] ... - 删除关键字
/remove_keyword_by_id(/rkbi) <ID> [ID] [ID] ... - 按ID删除关键字
/remove_all_keyword(/rak) <关键词> ["关 键 字"] ['关 键 字'] ... - 删除当前频道绑定的所有规则的指定关键字
/clear_all_keywords(/cak) - 清除当前规则的所有关键字
/clear_all_keywords_regex(/cakr) - 清除当前规则的所有正则关键字
/copy_keywords(/ck) <规则ID> - 复制指定规则的关键字到当前规则
/copy_keywords_regex(/ckr) <规则ID> - 复制指定规则的正则关键字到当前规则
/copy_replace(/crp) <规则ID> - 复制指定规则的替换规则到当前规则
/copy_rule(/cr) <规则ID> - 复制指定规则的所有设置到当前规则（包括关键字、正则、替换规则、媒体设置等）

替换规则管理
/replace(/r) <正则表达式> [替换内容] - 添加替换规则
/replace_all(/ra) <正则表达式> [替换内容] - 添加替换规则到所有规则
/list_replace(/lrp) - 列出所有替换规则
/remove_replace(/rr) <序号> - 删除替换规则
/clear_all_replace(/car) - 清除当前规则的所有替换规则
/copy_replace(/crp) <规则ID> - 复制指定规则的替换规则到当前规则

导入导出
/export_keyword(/ek) - 导出当前规则的关键字
/export_replace(/er) - 导出当前规则的替换规则
/import_keyword(/ik) <同时发送文件> - 导入普通关键字
/import_regex_keyword(/irk) <同时发送文件> - 导入正则关键字
/import_replace(/ir) <同时发送文件> - 导入替换规则

RSS相关
/delete_rss_user(/dru) [用户名] - 删除RSS用户

UFB相关
/ufb_bind(/ub) <域名> - 绑定UFB域名
/ufb_unbind(/uu) - 解绑UFB域名
/ufb_item_change(/uic) - 切换UFB同步配置类型

提示
• 括号内为命令的简写形式
• 尖括号 <> 表示必填参数
• 方括号 [] 表示可选参数
• 导入命令需要同时发送文件
```

## 💐 致谢

- [Apprise](https://github.com/caronc/apprise)
- [Telethon](https://github.com/LonamiWebs/Telethon)

## ☕ 捐赠

如果你觉得这个项目对你有帮助，欢迎通过以下方式请我喝杯咖啡：

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/0heavrnl)


## 📄 开源协议

本项目采用 [GPL-3.0](LICENSE) 开源协议，详细信息请参阅 [LICENSE](LICENSE) 文件。
