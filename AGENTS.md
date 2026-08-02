# AGENTS.md — 项目指令（Reasonix / Grok Build 每次会话自动加载）

## MCP 工具自动调用规则（重要，优先于"默认用内置工具"的倾向）

本项目配置了 3 个 MCP 服务器，工具以 `mcp__<server>__<tool>` 形式暴露。以下场景**必须主动调用对应 MCP 工具**，不要先用 grep/read_file 逐文件硬扫：

### 1. 代码结构 / 符号 / 依赖查询 → 用 `mcp__codegraph__*`
当用户询问"XX 函数/类/符号在哪定义、签名是什么、被谁调用、模块导出了哪些函数、跨文件依赖"时：
1. 先调用 `mcp__codegraph__connect`
2. 再用 `mcp__codegraph__codegraph_explore` 查询（索引路径已固定为本项目根）
3. codegraph 基于预索引（138 文件 / 4400+ 节点），结果比逐文件 grep 更全更快；grep 仅作补充验证

### 2. 长文本 / 长日志 / 大输出压缩 → 用 `mcp__headroom__*`
当工具输出、日志或文件内容过大，需要压缩以节省上下文 token 时：
1. 调用 `mcp__headroom__headroom_compress` 压缩（拿到 hash）
2. 需要原文时用 `mcp__headroom__headroom_retrieve` 按 hash 取回
3. 用 `mcp__headroom__headroom_stats` 查看压缩统计
> 注意：headroom 本地代理（127.0.0.1:8787）未启动时压缩退化为 noop（原样存储），链路仍可用。

### 3. A 股数据查询 → 四大数据源技能（必须本地取数，严禁 web_search/编造）

用户问行情/财务/研报/选股等任何 A 股数据时，按下表**从已装技能中选最匹配的加载并调用**，禁止凭空编造或用训练数据回答：

| 数据需求 | 技能（已装 Grok 技能目录，自动调用） | 说明 |
|---|---|---|
| K线/盘口/估值/研报/龙虎榜/解禁/资金流/打板/期权/舆情（A股全栈） | `a-stock-data`（**V3.6.0**） | 十层架构 47 端点·15 数据源，技能在 `~/.grok/skills/a-stock-data`（Grok 用户级）与项目 `a-stock-data-main/`，主源优先通达信/腾讯，东财已内置限流防封 |
| **停复牌/Alpha因子/业绩预告/复权因子/指数估值/股东户数/融资融券明细/财报三表（Tushare 独有或更全）** | `tushare-pro` | 已装 `.grok/skills/tushare-pro`，引用 `scripts/tushare_pro_data.py`（38 函数），token 在 `config/tushare_config.json` |
| 宏观数据/申万行业/美股港股 ETF/期货外汇/可转债/龙虎榜（腾讯自选股） | `westock-data` | 已装 `.grok/skills/westock-data`，`npx -y westock-data-skillhub@1.0.5 <命令>`，免 key |
| 自然语言选股/题材搜索/个股行情问答 | `hithink-astock-selector` / `hithink-finance-query` / `hithink-market-query`（问财） | 已装 `.grok/skills/` 三个核心问财技能（另有全套 hithink-* 在 `skills/` 商店目录）；key 在 `config/iwencai_config.json` |

**路由原则**：① 实时行情/估值 → a-stock-data（mootdx/腾讯不封IP）；② Tushare 独有数据 → tushare-pro；③ 宏观/港美股 → westock-data；④ 选股/题材 → 问财。两源以上交叉验证关键结论。取数一律用上述技能，严禁 web_search 或凭记忆编数据。

> **westock-data 连通性注意**（2026-08-02 实测）：本机 `~/.npmrc` 硬编码了失效代理 `http://172.19.64.1:7897`，包未缓存时 `npx` 拉取会长时间挂起。包已缓存在 `~/.npm/_npx`，正常情况下 `npx -y westock-data-skillhub@1.0.5 <命令>` 可直接用；若再次遇到 npx 卡死，改用 `env npm_config_proxy= npm_config_https_proxy= NO_PROXY='*' npx -y westock-data-skillhub@1.0.5 <命令>` 绕过失效代理（直连 registry 与 westock 接口均可达）。

## 数据源版本保证（强制）

1. **a-stock-data 必须用 V3.6.0**：47 端点·15 数据源（含 3 官方备胎）。版本以技能 frontmatter `version: 3.6.0` 为准（`~/.grok/skills/a-stock-data/SKILL.md` 与项目 `a-stock-data-main/SKILL.md` 双份一致）。禁止降级到旧版本代码或混用 V3.5 及更早的接口写法。
2. **四大数据源技能已全部装进 Grok 技能目录**（`~/.grok/skills/` 用户级 + `.grok/skills/` 项目级），AI agent 直接对话即可被自动激活，无需手动加载；命中描述即调用，不得以"没加载技能"为由改用 web_search 或训练数据。
3. **V3.6.0 已知行为**（2026-07-31 实测）：北交所老号段（43/83/87）返回僵尸数据且不报错，一律先用 `norm_ticker()` 归一化、用 920 新码；`tencent_quote()` 带 `is_stale` 标志；东财研报遇老码抛 ValueError 而非静默返回空。
4. **验证手段**：`grok inspect` 可查技能清单；跑 `python tests/test_a_stock.py` 或连通性测试确认数据链路；关键结论两源以上交叉验证。

## 项目约定摘要
- 项目：A股数据分析工具集（Python），根目录 scripts/ 含数据总线 `scripts/market_api.py`（`from scripts.market_api import api`）、数据守门员 `scripts/data_gate.py`
- 报告产物输出到 `reports/`，临时分析脚本用完删除
- 编码规范：`Session().trust_env = False`、禁止裸 `except:`、`if __name__ == '__main__':` 必加、禁止硬编码路径
