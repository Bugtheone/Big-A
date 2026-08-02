# MarketAPI 速查卡

> **一行导入**：`from scripts.market_api import api`
> **一切数据走此入口**，自动经过 DataGate 守门员验证

---

## 零、交易时段判断

| 方法 | 返回 |
|------|------|
| `api.trading_status()` | 当前交易时段、交易日判断、数据时效性 |

```python
ts = api.trading_status()
# {'session_cn': '收盘后',      # 盘前/集合竞价/盘中(上午)/午休/盘中(下午)/收盘后/周末/节假日
#  'data_freshness': '收盘',    # 实时/收盘/盘前/午间/历史 → 区分盘中vs盘后数据
#  'is_trading_day': True,      # 是否为交易日(Tushare trade_cal验证)
#  'is_trading_hour': False,    # 是否在9:30-15:00交易时段
#  'is_post_market': True,      # 是否已在15:00收盘后
#  'next_event': '次日集合竞价 9:15',
#  'suggestion': '收盘复盘模式，数据为今日最终数据'}

# full_snapshot / stop_falling_check / daily_review 的返回 dict 中已自动包含 trading_status
```

**使用场景**：每次分析前先 `ts = api.trading_status()`，根据 `data_freshness` 决定数据解读方式——"实时"数据存在波动，"收盘"数据是最终值，"历史"数据是最新交易日收盘值。

---

## 一、大盘行情

| 方法 | 参数 | 返回 |
|------|------|------|
| `api.index_snapshot()` | `names`(可选) | 九大指数实时快照：价格/涨跌幅/成交量/成交额/PE |
| `api.turnover()` | — | `{total_yi, sh_yi, sz_yi}` 两市成交额 |

```python
idx = api.index_snapshot()
# [ {name:'上证指数', price:3876.78, change_pct:0.25, turnover_yi:10259,...}, ... ]

to = api.turnover()
# {'total_yi': 21953, 'sh_yi': 10259, 'sz_yi': 11694}
```

---

## 二、K线 & 技术指标

| 方法 | 参数 | 返回 |
|------|------|------|
| `api.kline("上证指数", 30)` | 指数名+天数 | K线+MA5/10/20/60+量比+振幅+MA位置关系 |
| `api.kline_batch(["上证50","沪深300"], 10)` | 批量指数 | `{名称: kline结果, ...}` |

```python
k = api.kline("上证指数", 10)
print(k['indicators']['ma_position'])
# "站上MA5(3833.7) | 跌破MA10(3938.0) | MA5↓MA10(死叉) | MA10↓MA20(死叉)"
print(k['indicators']['amplitude_5d_avg'])  # 近5日平均振幅%
```

---

## 三、资金面

| 方法 | 参数 | 返回 |
|------|------|------|
| `api.north_flow(5)` | 天数 | 北向每日净流入+连续天数+汇总判断 |
| `api.board_fund_flow("概念", "今日", 10)` | 类型/周期/TOP N | 板块主力四档资金流向 |

```python
nf = api.north_flow(3)
print(nf['summary']['conclusion'])
# "近3日净流入25.3亿，2入1出"
print(nf['summary']['streak_days'])  # 连续流入天数

bf = api.board_fund_flow("行业", "5日", 5)
# [{name:'能源金属', main_net_yi:12.5, ...}, ...]
```

---

## 四、打板数据

| 方法 | 参数 | 返回 |
|------|------|------|
| `api.board_summary()` | — | 涨停数/炸板率/跌停数/情绪评估 |

```python
bs = api.board_summary()
# {'zt_count':115, 'zr_rate':17.9, 'dt_count':2, 'mood':'热烈', 'zt_total':140}
```

---

## 五、板块排名 & 新闻

| 方法 | 参数 | 返回 |
|------|------|------|
| `api.sectors(10)` | TOP N | 行业板块涨幅排名 |
| `api.telegraph(10)` | 条数 | 财联社7x24实时电报 |

```python
sc = api.sectors(3)
# [{name:'能源金属', change_pct:5.65}, ...]

tg = api.telegraph(3)
# [{title:'...', content:'...', time:'2026-07-23 21:07:25'}, ...]
```

---

## 六、个股实时行情

| 方法 | 参数 | 返回 |
|------|------|------|
| `api.stock_realtime(["000001","600519"])` | 代码列表 | `{code: {name,price,change_pct,...}, ...}` |

```python
st = api.stock_realtime(["000001", "600519", "300750"])
for code, d in st.items():
    print(f"{d['name']}: {d['price']} {d['direction']}{d['change_pct']}%")
```

---

## 七、综合分析（一键）

| 方法 | 场景 | 返回内容 |
|------|------|----------|
| `api.full_snapshot()` | **盘中快速看盘** | 指数+成交额+板块+打板+北向+电报+涨跌比+审计 |
| `api.stop_falling_check()` | **收盘判断止跌** | 五层信号塔逐项评分+综合判定 |
| `api.daily_review()` | **收盘一键复盘** | 指数+成交额+板块+打板+北向+审计 |

```python
# 盘中花3秒看清全局
snap = api.full_snapshot()
print(f"情绪:{snap['board']['mood']} | 成交:{snap['turnover']['total_yi']:.0f}亿 | {snap['performance']['up_count']}/{snap['performance']['down_count']}涨")

# 收盘判断止跌
sf = api.stop_falling_check()
print(f"判定:{sf['verdict']} | 得分:{sf['total_score']}/{sf['max_score']}")

# 收盘复盘
rv = api.daily_review()
```

---

## 八、审计

| 方法 | 用途 |
|------|------|
| `api.audit_report()` | Markdown 审计报告 |
| `api.reset_audit()` | 新任务开始前重置审计轨迹 |
| `api.audit_health()` | 健康度评分 0-100 |

---

## 典型使用场景

### 场景1：开盘快速看盘
```python
from scripts.market_api import api
api.reset_audit()
snap = api.full_snapshot()
# 5秒看完：指数涨跌、成交额、涨停家数、板块热点、北向、电报头条
```

### 场景2：尾盘判断要不要加仓
```python
sf = api.stop_falling_check()
# 80%+ → 加仓；60-80% → 观望；40-60% → 减仓；<40% → 清仓
```

### 场景3：盘中监控风格切换
```python
kb = api.kline_batch(["上证50", "中证1000"], 5)
s50_5d = kb["上证50"]["indicators"]["latest_close"]/kb["上证50"]["klines"][0][2]-1
z1k_5d = kb["中证1000"]["indicators"]["latest_close"]/kb["中证1000"]["klines"][0][2]-1
print(f"剪刀差: {s50_5d-z1k_5d:.1%}")  # >2%警惕风格极度分裂
```

### 场景4：盯着北向做决策
```python
nf = api.north_flow(5)
if nf['summary']['streak_direction'] == 'in' and nf['summary']['streak_days'] >= 3:
    print("北向连续流入，可考虑加仓")
```

---

## 与旧方式的对比

| 旧方式 | 新方式 |
|--------|--------|
| 手写临时脚本 → 运行 → 调试 → 读输出 | `from scripts.market_api import api` 一行 |
| 腾讯API/EastMoney/Tushare 各自import | 统一 `api.xxx()` 入口 |
| 不知道数据对不对 | 自动 DataGate 验证 + 审计报告 |
| 每次重复代码量50+行 | 一行调用 |
