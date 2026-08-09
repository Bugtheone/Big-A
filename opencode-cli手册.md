# opencode CLI 使用说明书手册

> 版本：1.18.15（本机实测 `opencode -v`）
> 生成时间：2026-08-09 · 内容基于 `opencode --help` 及各子命令 `--help` 输出整理

---

## 目录

1. [简介](#1-简介)
2. [安装与升级](#2-安装与升级)
3. [全局选项](#3-全局选项)
4. [命令总览](#4-命令总览)
5. [命令详解](#5-命令详解)
   - [opencode（启动 TUI）](#51-opencode-启动-tui)
   - [opencode run（无头执行）](#52-opencode-run-无头执行)
   - [opencode attach（连接远程服务器）](#53-opencode-attach-连接远程服务器)
   - [opencode serve / web（服务器模式）](#54-opencode-serve--web-服务器模式)
   - [opencode mcp（MCP 服务器管理）](#55-opencode-mcp-mcp-服务器管理)
   - [opencode providers / auth（提供商与凭证）](#56-opencode-providers--auth-提供商与凭证)
   - [opencode models（模型列表）](#57-opencode-models-模型列表)
   - [opencode agent（Agent 管理）](#58-opencode-agent-agent-管理)
   - [opencode session（会话管理）](#59-opencode-session-会话管理)
   - [opencode export / import（数据迁移）](#510-opencode-export--import-数据迁移)
   - [opencode stats（用量统计）](#511-opencode-stats-用量统计)
   - [opencode github / pr（GitHub 集成）](#512-opencode-github--pr-github-集成)
   - [opencode plugin（插件安装）](#513-opencode-plugin-插件安装)
   - [opencode db（数据库工具）](#514-opencode-db-数据库工具)
   - [opencode debug（调试工具）](#515-opencode-debug-调试工具)
   - [opencode acp（ACP 协议服务器）](#516-opencode-acp-acp-协议服务器)
   - [opencode completion（Shell 补全）](#517-opencode-completion-shell-补全)
   - [opencode upgrade / uninstall（升级与卸载）](#518-opencode-upgrade--uninstall-升级与卸载)
6. [常用环境变量](#6-常用环境变量)
7. [常见用法速查](#7-常见用法速查)

---

## 1. 简介

opencode 是一个运行在终端（TUI）中的 AI 编码助手。它可以直接在命令行里与 AI 对话，帮助完成代码编写、调试、重构等任务。支持：

- **交互式 TUI**：默认启动模式，带完整界面（`.opencode/bin/opencode`）
- **无头执行**：`opencode run "任务描述"` 一行命令完成任务
- **服务器模式**：`serve` / `web` 启动本地服务，供 `attach` 或 Web 界面连接
- **多模型支持**：通过 `-m provider/model` 切换任意提供商模型
- **Agent / MCP / 插件**：扩展生态完整

---

## 2. 安装与升级

| 命令 | 说明 |
|---|---|
| `curl -fsSL https://opencode.ai/install \| bash` | 官方脚本安装 |
| `opencode upgrade` | 升级到最新版本 |
| `opencode upgrade <target>` | 升级到指定版本 |
| `opencode upgrade --method <m>` | 指定安装方式：`curl` / `npm` / `pnpm` / `bun` / `brew` / `choco` / `scoop` |
| `opencode uninstall` | 卸载并删除所有相关文件 |

卸载选项：

| 选项 | 说明 |
|---|---|
| `-c, --keep-config` | 保留配置文件 |
| `-d, --keep-data` | 保留会话数据和快照 |
| `--dry-run` | 只显示会删除什么，不实际删除 |
| `-f, --force` | 跳过确认提示 |

---

## 3. 全局选项

以下选项对所有命令通用：

| 选项 | 说明 |
|---|---|
| `-h, --help` | 显示帮助 |
| `-v, --version` | 显示版本号 |
| `--print-logs` | 打印日志到 stderr |
| `--log-level <级别>` | 日志级别：`DEBUG` / `INFO` / `WARN` / `ERROR` |
| `--pure` | 不加载外部插件运行 |
| `--port <端口>` | 监听端口（默认 0 = 随机） |
| `--hostname <主机>` | 监听主机（默认 `127.0.0.1`） |
| `--mdns` | 启用 mDNS 服务发现（hostname 默认为 `0.0.0.0`） |
| `--mdns-domain <域名>` | mDNS 自定义域名（默认 `opencode.local`） |
| `--cors <域>` | 额外允许的 CORS 域（可多个） |
| `-m, --model <provider/model>` | 指定模型，格式如 `anthropic/claude-sonnet-4` |
| `-c, --continue` | 继续上一个会话 |
| `-s, --session <id>` | 继续指定会话 |
| `--fork` | 继续会话时 fork 出新会话（需配合 `--continue` / `--session`） |
| `--prompt <文本>` | 指定提示词 |
| `--agent <名称>` | 指定使用的 Agent |
| `--auto` | 自动批准未被显式拒绝的权限（**危险！**） |
| `--mini` | 启动极简交互界面 |
| `--no-replay` | 禁用 mini 模式恢复/缩放时的历史回放 |
| `--replay-limit <N>` | 限制 mini 回放显示最近 N 条消息 |

---

## 4. 命令总览

```
Commands:
  opencode completion          generate shell completion script
  opencode acp                 start ACP (Agent Client Protocol) server
  opencode mcp                 manage MCP (Model Context Protocol) servers
  opencode [project]           start opencode tui                          [default]
  opencode attach <url>        attach to a running opencode server
  opencode run [message..]     run opencode with a message
  opencode debug               debugging and troubleshooting tools
  opencode providers           manage AI providers and credentials        [aliases: auth]
  opencode agent               manage agents
  opencode upgrade [target]    upgrade opencode to the latest or a specific version
  opencode uninstall           uninstall opencode and remove all related files
  opencode serve               starts a headless opencode server
  opencode web                 start opencode server and open web interface
  opencode models [provider]   list all available models
  opencode stats               show token usage and cost statistics
  opencode export [sessionID]  export session data as JSON
  opencode import <file>       import session data from JSON file or URL
  opencode github              manage GitHub agent
  opencode pr <number>         fetch and checkout a GitHub PR branch, then run opencode
  opencode session             manage sessions
  opencode plugin <module>     install plugin and update config            [aliases: plug]
  opencode db                  database tools
```

位置参数：`project` —— 启动 opencode 的项目路径。

---

## 5. 命令详解

### 5.1 opencode（启动 TUI）

默认命令，启动交互式终端界面：

```bash
opencode                 # 在当前目录启动
opencode /path/to/proj   # 在指定项目启动
opencode -m deepseek/deepseek-chat   # 指定模型
opencode -c              # 继续上一次会话
opencode -s <sessionID>  # 继续指定会话
opencode --fork          # fork 出分支会话
opencode --mini          # 极简界面模式
```

### 5.2 opencode run（无头执行）

不带交互界面直接运行，适合脚本/CI 场景：

```bash
opencode run "修复这个 bug"
opencode run -m anthropic/claude-sonnet-4 "重构 xxx 模块"
opencode run --continue "继续上次任务"
opencode run -f file1.py -f file2.py "审查这两个文件"
opencode run --format json "输出 JSON 事件流"
opencode run --thinking "显示思考过程"
opencode run --share "分享会话"
```

| 选项 | 说明 |
|---|---|
| `message` | 要发送的消息（可多个，位置参数） |
| `--command <cmd>` | 要执行的命令（message 作为参数） |
| `-c, --continue` | 继续上一次会话 |
| `-s, --session <id>` | 继续指定会话 |
| `--fork` | fork 会话后继续（需配合 `--continue`/`--session`） |
| `--share` | 分享会话 |
| `-m, --model <p/m>` | 指定模型 |
| `--agent <名称>` | 指定 Agent |
| `--format <default\|json>` | 输出格式，`json` 输出原始 JSON 事件 |
| `-f, --file <文件>` | 附加文件到消息（可多次） |
| `--title <标题>` | 会话标题（默认截断提示词） |
| `--attach <url>` | 附加到运行中的 opencode 服务器（如 `http://localhost:4096`） |
| `-p, --password <pw>` | 基本认证密码（默认读 `OPENCODE_SERVER_PASSWORD`） |
| `-u, --username <user>` | 基本认证用户名（默认读 `OPENCODE_SERVER_USERNAME` 或 `opencode`） |
| `--dir <目录>` | 运行目录（attach 远程时指远程路径） |
| `--port <端口>` | 本地服务器端口（默认随机） |
| `--variant <变体>` | 模型变体（如 `high` / `max` / `minimal` 推理强度） |
| `--thinking` | 显示思考块 |
| `-i, --interactive` | 直接进入交互式 split-footer 模式 |
| `--auto` | 自动批准权限（危险！） |

### 5.3 opencode attach（连接远程服务器）

连接到正在运行的 opencode 服务器：

```bash
opencode attach http://localhost:4096
opencode attach ws://192.168.1.10:4096 --dir /remote/path
```

| 选项 | 说明 |
|---|---|
| `--dir <目录>` | 运行目录 |
| `-c, --continue` | 继续上一次会话 |
| `-s, --session <id>` | 继续指定会话 |
| `--fork` | fork 会话 |
| `-p, --password <pw>` | 认证密码（默认 `OPENCODE_SERVER_PASSWORD`） |
| `-u, --username <user>` | 认证用户名（默认 `OPENCODE_SERVER_USERNAME` 或 `opencode`） |
| `--mini` | 极简界面 |
| `--no-replay` / `--replay-limit <N>` | mini 回放控制 |

### 5.4 opencode serve / web（服务器模式）

无头服务器（供 attach 或其它客户端连接）与 Web 界面：

```bash
opencode serve                # 启动无头服务器（随机端口）
opencode serve --port 4096    # 指定端口
opencode web                  # 启动服务器并打开 Web 界面
```

选项：`--port` / `--hostname` / `--mdns` / `--mdns-domain` / `--cors` / `--pure` 等全局选项。

### 5.5 opencode mcp（MCP 服务器管理）

管理 Model Context Protocol 服务器：

```bash
opencode mcp list              # 列出 MCP 服务器及状态（别名：ls）
opencode mcp auth <name>       # 与支持 OAuth 的 MCP 服务器认证
opencode mcp logout <name>     # 移除 MCP 服务器的 OAuth 凭证
opencode mcp debug <name>      # 调试 MCP 服务器的 OAuth 连接
```

### 5.6 opencode providers / auth（提供商与凭证）

管理 AI 提供商与凭证：

```bash
opencode providers login              # 登录提供商
opencode providers login <url>        # 登录到指定 URL 的提供商
opencode providers logout <provider>  # 登出已配置的提供商
```

> `auth` 是该命令的别名。

### 5.7 opencode models（模型列表）

```bash
opencode models              # 列出所有可用模型
opencode models <provider>   # 列出指定提供商的模型
opencode models --verbose    # 详细输出（含成本等元数据）
opencode models --refresh    # 从 models.dev 刷新模型缓存
```

### 5.8 opencode agent（Agent 管理）

```bash
opencode agent list            # 列出所有可用 Agent
opencode agent create <name>   # 创建新 Agent
```

`agent create` 选项：

| 选项 | 说明 |
|---|---|
| `--path <目录>` | 生成 agent 文件的目录路径 |
| `--description <文本>` | Agent 的职责描述 |
| `--mode <all\|primary\|subagent>` | Agent 模式 |
| `--permissions, --tools <列表>` | 允许的权限（逗号分隔，默认全部）。可选值：`bash, read, edit, glob, grep, webfetch, task, todowrite, websearch, lsp, skill` |
| `-m, --model <p/m>` | 指定模型 |

### 5.9 opencode session（会话管理）

```bash
opencode session delete <sessionID>   # 删除会话
```

### 5.10 opencode export / import（数据迁移）

```bash
opencode export                     # 导出当前会话为 JSON
opencode export <sessionID>         # 导出指定会话
opencode export --sanitize          # 脱敏导出（打码敏感内容/文件数据）
opencode import <file>              # 从 JSON 文件导入会话
opencode import <url>               # 从 URL 导入会话
```

### 5.11 opencode stats（用量统计）

```bash
opencode stats                   # 查看 token 用量与成本统计
opencode stats --days 7          # 最近 7 天
opencode stats --tools 10        # 显示工具使用 Top 10
opencode stats --models 5        # 显示模型统计 Top 5（默认隐藏，传数字显示 Top N）
opencode stats --project "xxx"   # 按项目过滤（空字符串 = 当前项目）
```

### 5.12 opencode github / pr（GitHub 集成）

```bash
opencode github run      # 运行 GitHub agent
opencode pr <number>     # 拉取并检出 GitHub PR 分支，然后运行 opencode
```

### 5.13 opencode plugin（插件安装）

```bash
opencode plugin <module>      # 安装插件并更新配置（别名：plug）
opencode plugin <module> -g   # 安装到全局配置
opencode plugin <module> -f   # 强制替换已有插件版本
```

### 5.14 opencode db（数据库工具）

```bash
opencode db path              # 打印数据库路径
opencode db <sql查询>          # 对本地数据库执行 SQL 查询
opencode db <sql> --format json   # 输出格式：json / tsv（默认 tsv）
```

### 5.15 opencode debug（调试工具）

```bash
opencode debug lsp           # LSP 调试工具
opencode debug rg            # ripgrep 调试工具
opencode debug file          # 文件系统调试工具
opencode debug scrap         # 列出所有已知项目
opencode debug skill         # 列出所有可用技能
opencode debug snapshot      # 快照调试工具
opencode debug startup       # 打印启动耗时
opencode debug agent <name>  # 查看 Agent 配置详情
opencode debug v2            # 调试 v2 目录与内置插件
opencode debug info          # 显示调试信息
opencode debug paths         # 显示全局路径（data/config/cache/state）
opencode debug wait          # 无限等待（用于调试）
```

### 5.16 opencode acp（ACP 协议服务器）

启动 Agent Client Protocol 服务器：

```bash
opencode acp --cwd /path/to/proj   # 指定工作目录
```

### 5.17 opencode completion（Shell 补全）

生成 Shell 补全脚本：

```bash
opencode completion bash > /etc/bash_completion.d/opencode
opencode completion zsh > "${fpath[1]}/_opencode"
```

### 5.18 opencode upgrade / uninstall（升级与卸载）

见[第 2 节](#2-安装与升级)。

---

## 6. 常用环境变量

| 变量 | 说明 |
|---|---|
| `OPENCODE_SERVER_PASSWORD` | 服务器基本认证密码（`attach` / `run --attach` 默认读取） |
| `OPENCODE_SERVER_USERNAME` | 服务器认证用户名（默认 `opencode`） |
| `OPENCODE_PROVIDERS` | 提供商配置（具体格式见官方文档 https://opencode.ai/docs/providers） |

> 各提供商 API Key 通过 `opencode auth login` 或配置文件管理，密钥存放在 `~/.local/share/opencode/auth.json`（Linux）。

---

## 7. 常见用法速查

```bash
# 启动
opencode                        # TUI 启动
opencode --mini                 # 极简界面
opencode -c                     # 继续上次会话

# 无头执行
opencode run "解释这段代码"
opencode run --thinking "分析这个 bug"
opencode run -f main.py "审查 main.py"
opencode run --format json "输出结构化事件"

# 模型切换
opencode -m anthropic/claude-sonnet-4
opencode models --verbose       # 查看可用模型及价格

# 服务器模式
opencode serve --port 4096 &
opencode attach http://localhost:4096

# 会话管理
opencode session delete <id>
opencode export --sanitize      # 脱敏导出备份
opencode import backup.json     # 恢复会话

# 运维
opencode upgrade
opencode stats --days 7 --models 5
opencode debug paths            # 查看所有数据目录
opencode db "SELECT * FROM session LIMIT 10;"   # 直接查库
```

---

*手册内容基于 `opencode --help` 实时输出整理；子命令选项以各命令 `-h` 为准。官方文档：https://opencode.ai/docs*
