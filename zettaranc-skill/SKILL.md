---
name: zettaranc-skill
description: Z哥/万千交易纪律蒸馏系统（zettaranc-skill v4.3.0，项目内 zettaranc-skill/）。当用户需要以下任一服务时使用：①分析 A 股个股的技术面/买卖点/卖点纪律（KDJ/MACD/BBI/砖型图/沙漏/牛绳），或问某只股票能不能买/卖/减仓；②解读「少妇战法」「四块砖」「麒麟会」「三波理论」「B1/B2」「双线趋势」等 Z哥交易体系战法信号；③策略回测/端到端模拟/交割单点评/持仓诊断/防卖飞评分；④批量选股（screen）或综合评分（score）；⑤用户明确说「切换到 Z哥」「用万千视角」「zettaranc 分析」等角色指令。命中即用下述命令调用，禁止凭记忆编造战法信号。Do NOT load：美股/港股/期货/加密分析、纯代码问题。
---

# zettaranc-skill 对话调用（项目内 zettaranc-skill/）

**安装位置**：`/home/dev/grok_code/zettaranc-skill/`（v4.3.0，MIT）
**数据源**：`DATA_MODE=websearch` → 复用本项目 a-stock-data 免费链路（腾讯/百度/东财，零 Token）
**数据库**：`zettaranc-skill/data/stock_data.db`（SQLite，按代码同步）

## 调用方式（一律用 bash；**推荐 zt_auto.py 一键自动链路**）

**推荐入口 `zt_auto.py`**：自动检测 DB 数据新鲜度 → 缺数据/过期先 sync（250天+指标）→ 转发 CLI。AI 对话中**一条命令完成全流程**，用户无感：

```bash
python /home/dev/grok_code/zettaranc-skill/zt_auto.py analyze <代码>          # 自动sync+分析
python /home/dev/grok_code/zettaranc-skill/zt_auto.py diagnose <代码>         # 自动sync+持仓诊断
python /home/dev/grok_code/zettaranc-skill/zt_auto.py score <代码>            # 自动sync+综合评分
python /home/dev/grok_code/zettaranc-skill/zt_auto.py backtest shaofu <代码>  # 自动sync+回测
python /home/dev/grok_code/zettaranc-skill/zt_auto.py analyze <代码> --json   # JSON 输出
```

- 代码格式：`600519.SH` / `000001.SZ`（补 .SH/.SZ 后缀也可，zt_auto 自动规范化为 `600519`）
- 已同步且 7 天内的新鲜数据自动跳过 sync（stderr 会提示）

### 手动分步方式（zt_auto 不可用时备用）

所有命令**必须在 `zettaranc-skill/` 目录内执行**（相对导入）：

1. 数据同步（分析新代码前必须，否则返回空指标）：

```bash
cd /home/dev/grok_code/zettaranc-skill && python -m modules.data_sync sync --ts_code <代码> --days <N> --indicators
```

2. 分析：`python -m modules.cli analyze <代码> --json`（在 zettaranc-skill 目录内执行）

- 代码格式 tushare 式：`600519.SH` / `000001.SZ` / `300750.SZ`
- days 建议 250（一年）或 120；`--indicators` 同步指标缓存
- 查已同步：`python -m modules.cli sync status`

| 需求 | 命令 |
|---|---|
| 综合评分 | `python -m modules.cli score <代码>` |
| 策略回测 | `python -m modules.cli backtest shaofu <代码> --days 250` |
| 多策略回测 | `python -m modules.cli backtest multi <代码> --strategy b1,b2` |
| 端到端模拟 | `python -m modules.cli simulate <代码> --days 250` |
| 批量选股 | `python -m modules.cli screen --strategy B1 --limit 20` |
| 持仓诊断 | `python -m modules.cli diagnose <代码>` |
| 观察池 | `python -m modules.cli watchlist add <代码> --tags 标签` / `watchlist scan` |
| 交割单点评 | `python -m modules.cli trade add "4月25号买了100股茅台1800块"` → `trade review` |
| 每日工作流 | `python -m modules.cli daily` |
| 市场择时 | `python -m modules.cli market` |

## 与本项目策略文档的关系（输出时必须说明）

- **Z哥框架 = 卖点纪律与战法信号**（如"S3最后逃生""四块砖翻绿止损""牛绳断减仓"）
- **本项目（market_api/entry_point/策略文档）= 数据与买点**
- 操作建议**以本项目策略文档为准**，Z哥信号作交叉参考；涉及具体投资建议须附免责声明（不构成投资建议）

## 对话输出规范（用户无命令行）

1. **不要向用户展示命令或报错**——zt_auto 的 sync/CLI 过程自动完成，用户只看到结论
2. 输出结构：一句话结论（Z哥口吻，先铺垫后结论）→ 技术面快照表 → 多空信号对照（卖点纪律 vs 买点体系）→ 分情况操作映射（持仓/空仓/想抄底）→ 本项目策略文档交叉验证 → 免责声明
3. analyze 的 strategies 输出按 action 分组：SELL/HOLD 归"卖点纪律"，BUY 归"买点体系"，两边冲突时**以卖点纪律优先**（Z哥核心：管住卖出的手）

- 上游测试 1500 passed（已修 conftest 导入路径，勿回退 tests/__init__.py）
- analyze 前未 sync 会返回空指标（日期/KDJ 全为 0），不是 bug，先补 sync
- 数据库为本地 SQLite，全市场同步用 `scripts/sync_full_market.py`（较慢）

## 已知约束

- 上游测试 1500 passed（已修 conftest 导入路径，勿回退 tests/__init__.py）
- analyze 前未 sync 会返回空指标（日期/KDJ 全为 0），zt_auto 已自动处理；手动模式需先补 sync
- 数据库为本地 SQLite，全市场同步用 `scripts/sync_full_market.py`（较慢）
- 百度K线对 python-requests 有 TLS/JA3 风控（已修：curl 兜底），若仍空数据先跑 `python -c "from modules.a_stock_data_client import baidu_kline_to_dataframe; print(baidu_kline_to_dataframe('600519', days=10))"` 验证链路
