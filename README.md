# A股大数据量化分析工作台

基于 [a-stock-data V3.6.0](https://github.com/simonlin1212/a-stock-data)（47端点·15数据源）的全方位 A 股量化分析系统。

## 项目结构

```
├── README.md
├── requirements.txt
├── .gitignore
├── config/                     # 配置文件（飞书/同花顺/问财）
├── scripts/
│   ├── market_api.py           # API 统一入口（单例总线）
│   ├── data_gate.py            # 数据守门员（限流/降级/缓存）
│   ├── data_validator.py       # 交叉验证引擎
│   ├── tushare_fetch.py        # 同花顺数据获取
│   │
│   ├── analysis/               # ── 分析脚本 ──
│   │   ├── 30d/                #   30日趋势分析（主线/持续性/验证）
│   │   ├── intraday/           #   日内分析（三层/盘中报告/验证）
│   │   ├── daily/              #   每日复盘（step0/日评/v2迭代）
│   │   ├── sector/             #   板块/概念分析（入场/30日/资金流）
│   │   ├── fund_flow/          #   资金面（北向/个股资金流）
│   │   ├── industry/           #   行业排名/审计
│   │   ├── hot_topic/          #   热门题材/龙虎榜/归因
│   │   ├── backtest/           #   回测/验证/持续性检查
│   │   └── market/             #   大盘快照/日内行情
│   │
│   ├── tools/                  # ── 业务工具 ──
│   │   ├── daily_feishu_report.py   # 飞书每日推送
│   │   ├── intraday_monitor.py      # 盘中监控
│   │   ├── _l1_cross_validate.py    # L1交叉验证
│   │   └── _l3_cross_validate.py    # L3交叉验证
│   │
│   ├── utils/                  # ── 辅助脚本 ──
│   │   ├── _cache_sw31.py      #   SW31行业缓存
│   │   ├── _check_601136.py    #   个股检查
│   │   ├── _check_kline.py     #   K线数据校验
│   │   └── _v360_new_endpoints_verify.py  # V3.6.0新端点验证
│   │
│   ├── install/                # 技能安装
│   ├── scrape/                 # 社区技能爬取
│   └── explore/                # API探索
│
├── a-stock-data-main/          # 数据引擎（47端点·15数据源）
├── data/                       # 数据文件（缓存/中间结果）
├── reports/                    # 分析报告
│   ├── txt/                    #   纯文本报告
│   └── md/                     #   Markdown报告
├── docs/                       # 文档手册
├── tests/                      # 测试脚本
├── assets/                     # 静态资源（图片等）
├── log/                        # 操作日志
└── skills/                     # 已安装技能（159+个）
```

## 分析工作流

```
大盘（Gate0~3门控）
  → 行业板块（SW31·THS概念）
    → 个股（打分卡·五源交叉验证）
      → 飞书推送 / 报告输出
```

### 核心分析脚本速查

| 场景 | 脚本 | 输出 |
|------|------|------|
| 30日主线全景 | `scripts/analysis/30d/_30d_mainline.py` | 板块三阶段轮动+SW31排名 |
| 日内三层 | `scripts/analysis/intraday/_daily_triple_layer.py` | 大盘→板块→个股三层联动 |
| 每日复盘 | `scripts/analysis/daily/_daily_review_v2.py` | 日评+门控+打分卡 |
| 入场板块 | `scripts/analysis/sector/_entry_sectors.py` | Gate门控+A~D级分类 |
| 北向资金 | `scripts/analysis/fund_flow/_northbound_audit.py` | 北向流入流出审计 |
| 飞书日报 | `scripts/tools/daily_feishu_report.py` | 自动推送飞书机器人 |
| 重点监控 | `scripts/utils/_v360_new_endpoints_verify.py` | 监管池+异动池（V3.6.0） |

## 数据源

| 源 | 鉴权 | 封IP风险 | 用途 |
|----|------|---------|------|
| 通达信(mootdx) | 免费TCP | 不封 | K线/盘口/财务/F10 |
| 腾讯财经 | 免费HTTP | 不封 | 行情/指数/ETF/分钟K线 |
| 同花顺 | 免费 | 极低 | 一致预期/热榜/强势股归因 |
| 百度股市通 | 免费 | 不封 | K线备胎 |
| 新浪财经 | 免费 | 低 | 财报三表/ETF期权 |
| 财联社 | 免费 | 低 | 7x24实时电报 |
| 巨潮 cninfo | 免费 | 低 | 公告全文/互动易 |
| 东方财富 | 免费（限流） | 中 | 研报/资金流/龙虎榜/打板 |
| iwencai | 需API Key | 低 | NL语义搜索研报 |
| 上交所/深交所 | 免费 | 极低 | 官方一手数据（备胎） |

> **优先级**：mootdx = 腾讯 > 同花顺/百度/新浪/巨潮/财联社 > iwencai > 东财（仅独有数据用）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 1b. 安装开发/测试依赖（pytest / ruff / mypy / pre-commit）
pip install -r requirements-dev.txt
pre-commit install   # 安装本地质量门禁钩子（可选但推荐）

# 2. 配置 API Key（可选）
setx IWENCAI_API_KEY "your_key_here"

# 3. 运行测试
python tests/test_a_stock.py          # 连通性验证（需网络）
python -m pytest tests/ -v            # 单元测试（纯函数，无网络依赖）

# 4. 运行分析（从项目根目录执行）
python scripts/analysis/30d/_30d_mainline.py
python scripts/analysis/intraday/_daily_triple_layer.py
python scripts/analysis/daily/_daily_review_v2.py

# 5. 飞书每日推送
python scripts/tools/daily_feishu_report.py
```

> 质量门禁（提交前自动执行）：`pre-commit` 钩子会跑 ruff + mypy + 主入口检查；
> CI 全绿（语法 + 规范 + ruff + mypy + pytest）方可合入 `main`。

## 文档导航

| 目录 | 内容 |
|------|------|
| `docs/` | 核心文档（SKILL.md·板块映射·年度全景） |
| `reports/` | 自动生成的分析报告 |
| `log/` | 操作日志与集成指南 |
| `skills/` | 159+技能自带 SKILL.md |
