---
name: tushare-pro
description: Tushare Pro 数据源（5000积分档）。A股日/周/月K线、复权因子、停复牌、每日指标(PE/PB/换手)、三大报表、业绩预告、分红、股东户数/十大股东、融资融券、个股资金流、指数行情/估值、Alpha因子、基金净值、同花顺概念、新闻、港股通资金、沪深港通持仓(hk_hold)等 39 个封装函数。当需要 Tushare 独有能力（Alpha因子、停复牌、股东户数、业绩预告、复权因子、指数估值、同花顺概念指数）或需要与东财/腾讯交叉验证时使用；命中能力域时禁止 web_search/编造数据替代。
---

# Tushare Pro 数据源（项目封装版）

**调用方式**：直接 import 项目封装模块（无需自己写 tushare 调用代码）。

```python
import sys, os
sys.path.insert(0, os.path.abspath("."))          # 项目根
from scripts.tushare_pro_data import ts_daily, ts_daily_basic, ts_income  # 等
# 或直接底层：
from scripts.tushare_api import get_pro
pro = get_pro()                                    # 单例，自动读 config/tushare_config.json
```

- **token 配置**：`config/tushare_config.json`（已配好，勿改；`timeout=30`、`retry_count=3`）
- **依赖**：`pip install tushare pandas`（requirements.txt 已含）
- 所有封装函数返回 `list[dict]`，统一异常处理、自动分页，**不会抛异常**（失败返回 `[]`）

## 核心铁律

1. **禁止编造**——Tushare 返回空 `[]` 时如实告知，禁止用训练数据补数、禁止 web_search 替代。
2. **日期格式**：一律 `YYYYMMDD`（如 `"20260701"`），不是 `2026-07-01`。
3. **股票代码格式**：Tushare 用 `000001.SZ` / `600519.SH` / `688017.SH` / `830799.BJ`（**带交易所后缀**），与 a-stock-data 的纯 6 位不同，转换用 `norm_ticker()` 后自行加后缀（0/3→SZ，6/68→SH，4/8/92→BJ）。
4. **单位**：金额多为元；`ts_moneyflow` 净流入为万元；`ts_margin` 余额为元。展示时换算成亿/万。
5. **权限**：本封装按 500元/5000积分 档设计，`ts_stk_factor_pro` 等需要更高积分时如实说明取不到。
6. **限流**：Tushare 按积分限频（多数接口 200 次/分钟起），批量任务间隔 ≥0.5s；单次查询失败重试由封装内部处理。

## 函数速查（39 个，按层分组）

### 行情层
| 函数 | 数据 | 说明 |
|------|------|------|
| `ts_daily(ts_code, start, end, trade_date)` | 日线 | 开高低收/量额/涨跌幅，按日或按股票 |
| `ts_weekly(ts_code, start, end)` | 周线 | |
| `ts_monthly(ts_code, start, end)` | 月线 | |
| `ts_adj_factor(ts_code, trade_date)` | 复权因子 | 前/后复权计算必需 |
| `ts_suspend(ts_code, suspend_date)` | 停复牌 | 全市场当日停牌列表（东财无此端点） |
| `ts_daily_basic(trade_date, ts_code)` | 每日指标 | **PE/PB/PS、总市值/流通市值、换手率、量比**（腾讯/东财之外第三来源） |

### 财务层
| 函数 | 数据 |
|------|------|
| `ts_income(ts_code, period, report_type)` | 利润表（report_type="1" 合并报表） |
| `ts_balancesheet(...)` | 资产负债表 |
| `ts_cashflow(...)` | 现金流量表 |
| `ts_forecast(ts_code, ann_date, period)` | 业绩预告（预增/预减/扭亏等） |
| `ts_dividend(ts_code, ex_date)` | 分红送转 |
| `ts_disclosure_date(...)` | 财报披露计划日期 |

### 股东层
| 函数 | 数据 |
|------|------|
| `ts_stk_holdernumber(ts_code, start, end)` | 股东户数变化 |
| `ts_top10_holders(ts_code, period)` | 十大股东 |
| `ts_top10_floatholders(...)` | 十大流通股东 |

### 资金/信号层
| 函数 | 数据 |
|------|------|
| `ts_margin(ts_code, trade_date)` | 融资融券汇总（余额/买入/偿还） |
| `ts_margin_detail(...)` | 融资融券明细 |
| `ts_moneyflow(ts_code, trade_date)` | 个股资金流（主力/大/中/小单净额，**万元**） |
| `ts_daily_info(ts_code, trade_date)` | 每日筹码分布（换手/振幅/人均流通市值） |

### 公司/指数/因子/基金/概念/新闻层
| 函数 | 数据 |
|------|------|
| `ts_stock_company(ts_code)` | 上市公司基本信息（注册地/行业/主营业务） |
| `ts_namechange(...)` | 股票曾用名变更 |
| `ts_index_daily / _weekly / _monthly` | 指数行情 |
| `ts_index_dailybasic(...)` | 指数估值（PE/PB 分位） |
| `ts_stk_factor / ts_stk_factor_pro` | **Alpha 因子**（Tushare 独有，东财/腾讯均无） |
| `ts_fund_daily(...)` | 场内基金净值 |
| `ts_ths_index / ts_ths_daily` | 同花顺概念指数行情 |
| `ts_major_news(...)` | 新闻快讯（带股票关联） |
| `ts_ggt_daily(...)` | 港股通每日成交 |
| `ts_hk_hold(ts_code, trade_date, start, end, exchange)` | **沪深港通持股明细（周频周五）**——南向港股通持仓可用（959行/周五实测）；北向(SH/SZ)持股明细 5000 积分档实测返回空（需更高档）；北向成交额备胎用 `fetch_moneyflow_hsgt` |

### 便捷入口
```python
from scripts.tushare_api import fetch_moneyflow_hsgt
flow = fetch_moneyflow_hsgt("20260701", "20260710")   # 北向+南向 亿元，东财断供时的权威备胎
```

## 常用示例

```python
# 1. 贵州茅台日线 + 复权
daily = ts_daily("600519.SH", "20260601", "20260723")
adj = ts_adj_factor("600519.SH", trade_date="20260723")
# 前复权价 = close / adj_factor * 最新adj_factor

# 2. 全市场当日 PE/PB 排行
basic = ts_daily_basic(trade_date="20260723")   # 不传 ts_code = 全市场
pe_rank = sorted(basic, key=lambda x: x.get("pe_ttm") or 1e9)[:20]

# 3. 业绩预告
forecast = ts_forecast(period="20260630")        # 2026 中报预告
# 4. 停牌股票（东财无此数据）
suspended = ts_suspend(suspend_date="20260723")
# 5. Alpha 因子
factors = ts_stk_factor(ts_code="600519.SH", start="20260701", end="20260723")
```

## 与其它数据源分工（路由）

| 场景 | 用谁 |
|------|------|
| 实时价/估值/盘口 | a-stock-data §1（mootdx/腾讯，不封IP）优先 |
| K线历史/研报/龙虎榜/解禁 | a-stock-data（东财系） |
| **停复牌 / Alpha因子 / 业绩预告 / 复权因子 / 指数估值 / 股东户数 / 融资融券明细 / 沪深港通持仓(hk_hold)** | **本技能（Tushare 独有或更全）** |
| 宏观/申万行业/美股港股 K线 | westock-data（腾讯自选股） |
| 自然语言选股/题材搜索 | 问财 hithink-astock-selector / a-stock-data §2.3 iwencai |
| 交叉验证关键结论 | 任意两源以上对比（如 PE：腾讯 vs Tushare daily_basic） |

> 数据说明：Tushare 数据延迟一天（日终数据），不含实时行情；积分不足的字段返回空列表，如实转述即可。
