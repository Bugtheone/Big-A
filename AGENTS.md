# AGENTS.md — 项目指令（Reasonix / Grok Build 每次会话自动加载）

## MCP 工具自动调用规则（重要，优先于"默认用内置工具"的倾向）

本项目配置了 4 个 MCP 服务器（codegraph / headroom / ftshare / 按需扩展），工具以 `mcp__<server>__<tool>` 形式暴露。以下场景**必须主动调用对应 MCP 工具**，不要先用 grep/read_file 逐文件硬扫：

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

| 数据需求 | 技能/源（自动调用） | 说明 |
|---|---|---|
| K线/盘口/估值/研报/龙虎榜/解禁/资金流/打板/期权/舆情（A股全栈） | `a-stock-data`（**V3.6.0**） | 十层架构 47 端点·15 数据源，技能在 `~/.grok/skills/a-stock-data`（Grok 用户级）与项目 `a-stock-data-main/`，主源优先通达信/腾讯，东财已内置限流防封 |
| **停复牌/Alpha因子/业绩预告/复权因子/指数估值/股东户数/融资融券明细/财报三表（Tushare 独有或更全）** | `tushare-pro` | 已装 `.grok/skills/tushare-pro`，引用 `scripts/tushare_pro_data.py`（38 函数），token 在 `config/tushare_config.json` |
| 宏观数据/申万行业/美股港股 ETF/期货外汇/可转债/龙虎榜（腾讯自选股） | `westock-data` | 已装 `.grok/skills/westock-data`，`npx -y westock-data-skillhub@1.0.5 <命令>`，免 key |
| 自然语言选股/题材搜索/个股行情问答 | `hithink-astock-selector` / `hithink-finance-query` / `hithink-market-query`（问财） | 已装 `.grok/skills/` 三个核心问财技能（另有全套 hithink-* 在 `skills/` 商店目录）；key 在 `config/iwencai_config.json` |
| **补充验证源（仅交叉验证，不作主源）**：A股/港股/美股行情 K线、涨跌停/资金流/龙虎榜/财务、ETF/指数/基金、期货债券、宏观/公告/研报/新闻 | `ftshare`（FTShare-MCP，远程 Streamable HTTP） | opencode 已配置 `mcp__ftshare__ft_*`（199 工具：194 个 `ft_*` 数据工具 + 5 个便捷查询入口），公共地址 `https://market.ft.tech/gateway/mcp`（server 0.1.1），免 key 免安装、只读；首次调用先 `initialize` 取 `Mcp-Session-Id` |
| **补充验证源（与 FTShare-MCP 同源同层，仅交叉验证）**：A股/港股/美股/ETF/基金/指数/板块/宏观/可转债/新闻等 153 个子技能 | `ftshare-market-data`（FTShare-skills，数据级 Skill） | 已装 `~/.config/opencode/skills/ftshare-market-data/`（1 主 skill 路由 + `run.py` 统一调度 + 153 子 skill，2026-08-09 接入），调用 `python <run.py> <子技能名> [参数]`，走 `market.ft.tech` `/api/v1` 公共 API 免 key 只读；对话命中描述（行情/估值/K线/指数权重/宏观）自动加载 |

**路由原则**：① 实时行情/估值 → a-stock-data（mootdx/腾讯不封IP）；② Tushare 独有数据 → tushare-pro；③ 宏观/港美股 → westock-data；④ 选股/题材 → 问财；⑤ **关键结论交叉验证 → 四源技能 + FTShare-MCP / FTShare-skills 互验，FTShare 系仅作补充验证源（A股/港美股/宏观覆盖广），实时行情仍以 a-stock-data 主源为准，禁止以 FTShare 为唯一数据源**。两源以上交叉验证关键结论。取数一律用上述技能/MCP，严禁 web_search 或凭记忆编数据。

**自动激活保证**：a-stock-data V3.6.0 已注册为 Grok 用户级技能（`~/.grok/skills/a-stock-data`）并在项目 `a-stock-data-main/` 双份备份（md5 一致），AI agent 对话中命中描述即自动加载；命中 A 股取数需求**必须先走 a-stock-data 主源**（mootdx/腾讯不封 IP），Tushare 独有数据 → tushare-pro，宏观/港美股 → westock-data，选股/题材 → 问财 SkillHub，交叉验证 → FTShare-MCP（`mcp__ftshare__*`）/ FTShare-skills（`ftshare-market-data`）——四源能力 + FTShare 共同构成完整取数链路，禁止降级为 web_search 或训练数据。

> **westock-data 连通性注意**（2026-08-02 实测）：本机 `~/.npmrc` 硬编码了失效代理 `http://172.19.64.1:7897`，包未缓存时 `npx` 拉取会长时间挂起。包已缓存在 `~/.npm/_npx`，正常情况下 `npx -y westock-data-skillhub@1.0.5 <命令>` 可直接用；若再次遇到 npx 卡死，改用 `env npm_config_proxy= npm_config_https_proxy= NO_PROXY='*' npx -y westock-data-skillhub@1.0.5 <命令>` 绕过失效代理（直连 registry 与 westock 接口均可达）。

## 数据源版本保证（强制）

1. **a-stock-data 必须用 V3.6.0**：47 端点·15 数据源（含 3 官方备胎）。版本以技能 frontmatter `version: 3.6.0` 为准（`~/.grok/skills/a-stock-data/SKILL.md` 与项目 `a-stock-data-main/SKILL.md` 双份一致）。禁止降级到旧版本代码或混用 V3.5 及更早的接口写法。
2. **四大数据源技能已全部装进 Grok 技能目录**（`~/.grok/skills/` 用户级 + `.grok/skills/` 项目级），AI agent 直接对话即可被自动激活，无需手动加载；命中描述即调用，不得以"没加载技能"为由改用 web_search 或训练数据。
3. **V3.6.0 已知行为**（2026-07-31 实测）：北交所老号段（43/83/87）返回僵尸数据且不报错，一律先用 `norm_ticker()` 归一化、用 920 新码；`tencent_quote()` 带 `is_stale` 标志；东财研报遇老码抛 ValueError 而非静默返回空。
4. **验证手段（机器保证，已进 CI）**：跑 `python scripts/verify_a_stock_data_v360.py`（本地门禁：双份版本==3.6.0 + md5 一致 + V3.6.0 API 面完整 + 无 V3.5 及更早接口残留 + 四源技能在位，CI 每次提交自动执行）；`python scripts/verify_a_stock_data_v360.py --live`（联网冒烟：腾讯行情 + Tushare/westock/问财 三源链路）；`grok inspect` 可查技能清单；`python tests/test_a_stock.py` 连通性测试；关键结论两源以上交叉验证。
5. **FTShare 系为远程公共只读服务，仅作交叉验证补充源**（2026-08-09 接入 opencode）：
   - **FTShare-MCP**（server 0.1.1）：`~/.config/opencode/opencode.jsonc` 的 `ftshare` remote 配置（`opencode mcp list` 显示 connected），公共地址 `https://market.ft.tech/gateway/mcp`，199 工具（194 个 `ft_*` + 5 个便捷入口）；
   - **FTShare-skills**（`ftshare-market-data`）：已装 `~/.config/opencode/skills/ftshare-market-data/`，1 主 skill + 153 子 skill，`python run.py <子技能名> [参数]` 走 `market.ft.tech` `/api/v1` 公共 API；
   - 实时行情仍以 a-stock-data 主源为准；服务端由官方维护，调用失败显式降级到四源技能，禁止以 FTShare 为唯一数据源。

## 项目约定摘要
- 项目：A股数据分析工具集（Python），根目录 scripts/ 含数据总线 `scripts/market_api.py`（`from scripts.market_api import api`）、数据守门员 `scripts/data_gate.py`
- **策略文档体系**：策略流派分类框架见 `docs/策略分类.md`（永久元框架）；**板块大方向分类见 `docs/板块地图.md`（科技/消费/金融/周期/公用/题材六大类 + 进攻/防御/周期归属）**；**资金博弈体系见 `docs/资金博弈.md`（存量/增量/减量 + 七路资金 + 轮动规律）**；当前生效策略见 `docs/当前策略.md`（每日更新）；超跌反弹专用见 `docs/超跌反弹策略.md`；候选标的见 `docs/观察池.md`——AI 输出操作建议时必须先引用对应策略文档
- 报告产物输出到 `reports/`，临时分析脚本用完删除
- 编码规范：`Session().trust_env = False`、禁止裸 `except:`、`if __name__ == '__main__':` 必加、禁止硬编码路径

## 🔒 AI 数据纪律（强制，2026-08-05 生效）— 防止幻觉/编造/过时数据

> 本项目提供真实数据源，AI 必须**只从数据源获取真实实时数据**分析。以下为硬性约束，违反即视为分析无效。

### 1. 数据获取纪律（禁止走偏）
- **禁止** web_search / web_fetch / 浏览器 / 网页抓取取数（config.toml 已 deny）——行情/板块/个股数据**一律走数据源 API**（`scripts.market_api`、`scripts.data_gate`、a-stock-data 技能、Tushare/westock/问财技能、FTShare-MCP `mcp__ftshare__*`）
- **禁止** 凭训练数据/记忆写行情数字、估值、涨幅——**每个数字必须来自工具调用输出**
- **禁止** 用"网上看到的""我记得""大约"等表述充当数据
- 数据源不可用时：**显式标注降级链**（如"东财失效→降级同花顺"），禁止用记忆补数

### 2. 交叉验证纪律（结论可信度）
- 关键结论（指数/成交/涨停/主线判定）**必须 ≥2 源交叉验证**；不一致标注 `⚠️跨源差异` 并说明取哪个权威源
- 盘中数据必须带时间戳；**超过 15 分钟未刷新的行情数据标注 `⚠️stale`**
- 盘后数据（Tushare 当日 17:00 后）与盘中定格（腾讯）核对：误差 >0.3pt 必须复核

### 3. 输出纪律（可审计）
- 报告必须含**"数据源验证"章节**（指标/源A/源B/结果）
- 关键数字标注来源：`上证 3871.65（腾讯 11:21 快照）`
- 数据缺失/降级/异常时**必须显式声明**，禁止静默忽略

### 4. 生产数据链路（AI 只读）
- 盘中 15 分钟调度 → `intraday_snapshot.py`（机器拉数）→ 写 `reports/daily/<date>/*.md`
- AI 分析**基于固化数据文件 + 调用数据 API**，不自行发明数据
- 需要新数据 → 调用 `api.xxx()` / `gate.xxx()`（真实取数），或跑 `intraday_enhance.py`（分时/A50/资金面/盘口）

### 5. 违规判定（自查清单）
- 分析里的数字能否追溯到工具输出？不能 → 重做
- 有没有用过 web 搜索取数？用过 → 数据无效
- 行情数据有没有时间戳？没有 → 标 stale
- 关键结论有没有双源？没有 → 降级为"单源参考"

### 版本管理纪律（2026-08-05 生效）— 防 AI 改乱，随时回滚
1. **AI 动手改代码前必须跑 `bash scripts/tools/git_snapshot.sh`**（建快照 tag + stash 未提交）
2. **小步提交**：一个任务一个 commit（feat/fix/docs），禁止一把梭
3. **改完 review diff**：满意才 commit；不满意 `git checkout -- <文件>` 回滚
4. **每日快照**：crontab 18:10 自动打 tag（`ai-snapshot-YYYYMMDD`）
5. **禁止破坏操作**：git reset --hard / push -f / rm -rf（config deny，AI 不可执行）
6. 回滚速查见 `docs/AI版本管理.md`；reflog 是终极保险（commit 过就丢不了）
5. **时间纪律（2026-08-05 强化）**：**禁止推算/猜测时间**。报告时间戳必须真实读取：`date` + 腾讯 CDN HTTP Date 校验（可用 `python scripts/tools/real_time.py` 返回权威北京时间）；推算的时间标注一律无效。
6. **时间戳强制规则（2026-08-05 强化，防重复犯错）**：
   - **每次输出报告/简报，时间戳必须当次实时读取** `real_time.py`（腾讯 CDN 权威），**禁止沿用上次拉数据的时间、禁止推算**
   - 所有脚本时间源已统一为 `_rt()`（内部调 real_time.py）——文件时间戳自动权威且每次刷新
   - 违规判据：报告时间戳与 `real_time.py` 当前输出不一致 = 违规，重做
7. **介入点强制规则（2026-08-06 固化，防估算）**：
   - **介入点/止损位/MA 位置一律用 `entry_point.py` 计算**（腾讯官方前复权日K源 `web.ifzq.gtimg.cn`），**禁止用记忆/口算/近似值充当介入点**
   - `market_api.kline()` 只支持指数名不支持个股代码（返回 error）——**个股均线不得用其算**
   - 输出介入点必须带工具输出的：MA5/MA10/MA20 + 偏离度 + 介入区 + 止损位
   - 违规判据：报告中的介入点价位无法从 `entry_point.py` 输出追溯 = 违规，重做
   - 回踩判定标准（工具内建）：距 MA10 ∈ [-3%, +3%] = 真回踩可介入；距 MA10 > 8% = 急拉超买严禁追高

### 交易方法论纪律（用户口述，2026-08-05 固化）
1. **市场可操作判断（60/40 法则）**：市场约 60% 时间主线清晰、40% 无主线。**能否操作的必须条件 = 成交维持 2.5 万亿+ 且指数运行在 5/10 日均线之上**（双满足才可操作，否则观望）
2. **个股挑选四要素（资金筛选法）**：①成交额排名前 100~300（热度+流动性）②站上 5/10 日均线 ③近 5 日累计涨幅 10~30% 健康（主线清晰可放宽上限）④主线清晰优先。**此法是资金帮你筛的**——可锁定主线核心/行业板块/市场风格（工具：`scripts/tools/market_filter.py`）
3. **主线五条件**：①涨幅居前 ②资金流入 ③涨停家数 ④连板高度 ⑤逻辑硬；**资金>涨幅>涨停>逻辑>连板**；单日不定性，**连续 3~5 日才定性**；**撤退信号（E）优先于升级信号（C）**
4. **T+1 执行纪律**：操作建议必须区分"今日买入（T+1 锁死，明日处理）"与"今日前持仓（今日可撤）"；止损 -5%/破 MA10，不补仓

### 工程纪律（2026-08-05 公开仓库后）
5. **PR 流程强制**：main 分支已启用 GitHub 分支保护（禁直推/禁 force push）——**代码改动必须走 feature 分支 + PR**（CI 质量门禁通过后 merge）；紧急回滚用户手动执行（AI deny 禁 reset --hard）
6. **安全检查**：提交前自查——config/ 密钥不入库、无个人路径（Windows 桌面等）、reports/ 敏感数据不公开、无硬编码 token；已用 `git grep` 扫描
7. **盘后复核纪律**：18:00 复盘流水线 = 复盘 v2 → 飞书 → 盘后复核（Tushare 官方 vs 腾讯定格）→ 业绩预告 → 中报披露跟踪；**每次复盘执行都重新拉取数据，不沿用盘中定格**
8. **AI 对话自动数据**：盘中快照（15 分钟）+ 板块对比 + 策略信号（C/D/E/F 11 信号 + 回踩买点确认）+ 盘中增强（分时/A50/资金面/盘口）+ 业绩预告 + 中报披露——**有变化主动推送，不等用户问**

### 预期差纪律（2026-08-05）
9. **"预期差"是交易核心**：超预期=实际>预期（涨）；不及预期=实际<预期（跌）；**业绩好但低于预期照样跌（利好兑现），业绩差但好于预期照样涨（利空出尽）**——不只看绝对值
10. **中报披露季（8 月）**：预告（7 月区间）→ 中报（8 月实际）→ 超预期买/不及预期避（工具：`midreport_tracker.py` 自动预期差）

### AI 对话自动工具全集（2026-08-05，全部可对话自动调用）
> 下列工具产物文件随 15 分钟调度/18:00 复盘自动生成；**AI 对话中命中需求即读对应文件或直接运行工具**，禁止凭记忆编数。

| 需求 | 工具/产物 | 生成时机 |
|---|---|---|
| 指数/广度/成交/涨停 | intraday_snapshot → intraday_*.md | 盘中 15 分钟 |
| 板块变化 | sector_delta → sector_delta_*.md | 盘中 15 分钟 |
| 策略信号（C/D/E/F/买点）| strategy_signal → strategy_signal_*.md | 盘中 15 分钟 |
| 分时/A50/资金面/盘口/人气 | intraday_enhance → intraday_enhance_*.md | 盘中 15 分钟 |
| **资金筛选选股**（四因子）| market_filter.py --ml --risk → market_filter_*.md | 18:00 复盘 |
| 业绩预告（预增+主线）| earnings_forecast.py → earnings_forecast_*.md | 18:00 复盘 |
| 中报披露/预期差/一致预期 | midreport_tracker.py --code XX | 18:00 复盘 |
| 技术指标/估值分位 | tech_indicators.py --code XX | 对话按需 |
| **介入点/止损位（官方K线，禁止估算）** | **entry_point.py --codes XX** | **每次输出介入点** |
| **趋势状态（T-score 状态机）** | **trend_tracker.py --codes XX** | 对话按需 |
| **突破判定（B-score）** | **breakout_detector.py --codes XX** | 对话按需 |
| **仓位档位（60/40法则）** | **position_sizer.py** | 每次给仓位建议 |
| **行情策略路由（门控→类型→策略→板块）** | **market_router.py** | 每次综合决策 |
| 风险因子（质押/减持/停牌）| risk_factors.py --codes XX | 18:00 复盘 |
| GitHub 仓库/上游更新 | github_track.py | 18:00 复盘 |
| 真实时间（禁止推算）| real_time.py | 每次输出 |
| 盘后复核（Tushare 官方）| post_close_update.py → post_close_verify_*.md | 18:00 复盘 |

### 交易哲学·持续性主线原则（2026-08-05 用户口述固化）
**只做主线的持续性行情，不做轮动/一日游。**
1. **主线持续性标准**（三确认）：①板块 3 日资金持续流入（如电子 5 日 +301 亿连续）②板块连续 3~5 日领涨（手册定性）③个股站上均线 + 无减持 + 所在分支资金为正
2. **轮动/一日游信号**（减仓/不做）：分支资金流出 / 个股减持 / 估值分位 >90% / 光模块式单日退潮
3. **主线内部也要选"持续分支"**：资金从光模块/服务器切向半导体设备/PCB/元件（2026-08-05 实例）——**只做资金流入的持续分支，回避流出分支**
4. **执行**：符合持续 → 持有/回踩加码；不符合（轮动反弹）→ 反弹即减，换到持续分支
5. **工具**：`market_filter --ml --risk`（四因子）+ 板块 5 日资金（board_fund_flow_robust）+ 风险因子（减持/质押/停牌）
6. **题材延续性标准**（判断真主线 vs 一日游，2026-08-05 数据验证）：
   - ✅ 有延续：题材**连续 3 日出现在涨停题材榜前列**（家数不衰减）+ 龙头连板晋级 + 题材扩散（新分支接力）
     - 正例：AI 应用/CPO（08-03 AI应用6 → 08-04 AI应用12/CPO10 → 08-05 AI应用8/CPO7 连续3日）
   - ❌ 一日游：题材单日涨停潮后**次日消失**（家数归零/榜上无名）
     - 反例：核电/可控核聚变（08-03 涨停榜第1/5 → 08-04/08-05 消失）
   - 执行：**只做有延续性的题材**；单日涨停潮题材（核电式）一律不追
7. **主线内"持续 vs 轮动"分支识别（2026-08-05 数据验证）**：
   - 🟢 **持续分支（做）**：分支 5 日资金流入（元件 +59 亿）+ 龙头站上均线且无减持（北方华创全均线）+ 有业绩支撑（中微预增 282-310%）+ 涨幅与主线同步/领先（设备 +8.34% 领涨）
   - 🔴 **轮动分支（回避）**：分支资金流出（通信 5 日 -28 亿）+ 龙头破位（旭创 -7.27% 破 MA10）+ 前期涨幅过大兑现（光模块 08-04 +13% 后）+ 个股减持/估值>90%（浪潮）
   - 本质：主线的"高低切换"——资金从"涨多兑现"切到"低位+业绩"分支；**只做持续分支，轮动分支不追不接，持仓反弹即减**
8. **主线判定综合框架（四条整合逻辑链，2026-08-05 数据验证）**：
   ```
   ① 主线资金不撤（电子+301.5亿第一）→ 资金选择30日深跌方向 = 反弹有背书
   ② 主线内部分化（持续vs轮动）→ 资金主线内高低切换 = 做持续分支避轮动分支
   ③ 风格切换确认（科技强/防御弱）→ 30日均值回归 = 切换中期做科技避防御
   ④ 题材延续性（连续3日涨停榜）→ 真主线发酵 vs 单日一日游 = 做延续避单日
   ```
   - **真主线特征**：有资金（连续流入）+ 有分化（内部分支清晰）+ 有切换（风格明确）+ 有延续（题材3日）——四条齐备 = 主线确认
   - **操作映射**：做持续分支（设备/PCB/元件）· 减轮动分支（光模块/服务器）· 跟科技避防御 · 追延续避单日
   - **反例对照**：核电（无资金持续+单日一日游）= 伪主线
| 风格预判（次日防御/进攻/周期）| style_forecast.py → style_forecast_*.md | 18:00 复盘 |
