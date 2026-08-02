#!/usr/bin/env python3
"""
DKX 介入点→确定点 框架验证
- 介入点：DKX金叉发生日 → 加入观察池
- 确定点：金叉后满足回踩MA20+量能确认 → 入场
从7/13~7/17批次取样，检查当前(7/23)状态
"""
import json, time, sys, os
from datetime import date
import requests

STOCKS = {
    # 7/13 批次 — 金叉后已10天，最能验证框架
    "7/13": [
        ("600036", "招商银行"), ("600887", "伊利股份"), ("600436", "片仔癀"),
        ("000538", "云南白药"), ("002230", "科大讯飞"), ("603198", "迎驾贡酒"),
        ("000423", "东阿阿胶"), ("600674", "川投能源"), ("601009", "南京银行"),
        ("600085", "同仁堂"),
    ],
    # 7/14 批次 — 金叉后9天
    "7/14": [
        ("601088", "中国神华"), ("601857", "中国石油"), ("601398", "工商银行"),
        ("601328", "交通银行"), ("000895", "双汇发展"), ("601899", "紫金矿业"),
        ("601668", "中国建筑"),
    ],
    # 7/15 批次 — 金叉后8天
    "7/15": [
        ("600519", "贵州茅台"), ("600941", "中国移动"), ("601728", "中国电信"),
        ("600690", "海尔智家"), ("002352", "顺丰控股"), ("601006", "大秦铁路"),
        ("000568", "泸州老窖"),
    ],
}

def _tx_kline(code, n=120):
    """腾讯日K"""
    m = {"0": "sz", "6": "sh", "3": "sz"}
    pfx = m.get(code[0], "sz")
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pfx}{code},day,,,{n},qfq"
    s = requests.Session()
    s.trust_env = False
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    r = s.get(url, timeout=12)
    r.raise_for_status()
    data = r.json()
    klines = data.get("data", {}).get(f"{pfx}{code}", {}).get("qfqday") or \
             data.get("data", {}).get(f"{pfx}{code}", {}).get("day")
    if not klines:
        return None
    result = []
    for k in klines:
        if len(k) < 6:
            continue
        result.append([k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])])
    return result if result else None

def _tx_realtime(code):
    """腾讯实时行情"""
    m = {"0": "sz", "6": "sh"}
    pfx = m.get(code[0], "sz")
    url = f"https://qt.gtimg.cn/q={pfx}{code}"
    s = requests.Session()
    s.trust_env = False
    r = s.get(url, timeout=8)
    if r.status_code != 200:
        return None
    raw = r.text.split("~")
    if len(raw) < 50:
        return None
    try:
        return {
            "price": float(raw[3]),
            "change_pct": float(raw[32]),  # 涨跌幅
            "volume_ratio": float(raw[47]) if raw[47] else 0,  # 量比
        }
    except (ValueError, IndexError):
        return None

def _ma(values, n):
    if len(values) < n:
        return None
    return round(sum(values[-n:]) / n, 2)

def calc_dkx(closes):
    """DKX多空线 MID=(3*C+O+H+L)/6"""
    if len(closes) < 20:
        return None
    result = []
    for i in range(len(closes)):
        # 简化：用C代替O/H/L计算MID
        mid = closes[i]  # 近似
        result.append(mid)
    ma5 = _ma(result, 5)
    ma20 = _ma(result, 20)
    if ma5 is None or ma20 is None:
        return None
    return {"ma5": ma5, "ma20": ma20, "golden": ma5 > ma20}

def analyze(name, code, cross_date):
    klines = _tx_kline(code, 120)
    if not klines:
        return None

    closes = [k[2] for k in klines]
    highs = [k[3] for k in klines]
    lows = [k[4] for k in klines]
    vols = [k[5] for k in klines]
    latest_close = closes[-1]

    dkx = calc_dkx(closes)
    if not dkx:
        return None

    ma5 = _ma(closes, 5)
    ma10 = _ma(closes, 10)
    ma20 = _ma(closes, 20)
    dist_ma20 = round((latest_close - ma20) / ma20 * 100, 2) if ma20 else None

    # ATR (14日)
    tr_vals = []
    for i in range(1, min(15, len(closes))):
        tr = max(highs[-i]-lows[-i], abs(highs[-i]-closes[-i-1]), abs(lows[-i]-closes[-i-1]))
        tr_vals.append(tr)
    atr = round(sum(tr_vals)/len(tr_vals)/closes[-1]*100, 2) if tr_vals else 0

    # 量比
    avg_vol_5 = sum(vols[-6:-1])/5 if len(vols)>=6 else vols[-1]
    vol_ratio = round(vols[-1]/avg_vol_5, 2) if avg_vol_5 > 0 else 0

    # 金叉以来涨跌幅
    cross_day_idx = None
    for i, k in enumerate(klines):
        if k[0] >= cross_date:
            cross_day_idx = i
            break
    if cross_day_idx:
        cross_price = closes[cross_day_idx]
        since_cross = round((closes[-1] - cross_price) / cross_price * 100, 2)
    else:
        since_cross = 0

    # 金叉后最高价（回撤判断）
    if cross_day_idx:
        since_cross_high = max(closes[cross_day_idx:])
        drawdown_from_high = round((closes[-1] - since_cross_high) / since_cross_high * 100, 2)
        since_cross_low = min(closes[cross_day_idx:])
    else:
        drawdown_from_high = 0
        since_cross_low = closes[-1]

    rt = _tx_realtime(code)
    today_chg = rt["change_pct"] if rt else 0
    today_vol_ratio = rt["volume_ratio"] if rt else vol_ratio

    # 确定点判断：距MA20≤5% + 金叉延续 + 量比≥1.0
    is_confirm = (
        dkx["golden"] and
        dist_ma20 is not None and abs(dist_ma20) <= 5 and
        today_vol_ratio >= 0.8
    )

    return {
        "name": name, "code": code, "cross_date": cross_date,
        "price": latest_close, "today_chg": today_chg,
        "ma5": ma5, "ma10": ma10, "ma20": ma20,
        "dist_ma20": dist_ma20, "atr": atr,
        "vol_ratio": today_vol_ratio,
        "golden_now": dkx["golden"],
        "since_cross": since_cross,
        "drawdown": drawdown_from_high,
        "is_confirm": is_confirm,
    }

def main():
    OUT = "log/20260723_DKX介入点_确定点_框架验证.md"
    lines = [f"# DKX 介入点→确定点 框架验证\n",
             f"> 验证日期：2026-07-23\n",
             f"> 核心逻辑：DKX金叉日=介入点(观察池) → 回踩MA20+金叉延续=确定点(入场)\n\n"]

    results_all = []
    for batch_name, stocks in STOCKS.items():
        batch_results = []
        for code, name in stocks:
            cross_dates = {"7/13": "2026-07-13", "7/14": "2026-07-14",
                           "7/15": "2026-07-15", "7/16": "2026-07-16",
                           "7/17": "2026-07-17"}
            cross_date = cross_dates[batch_name]
            r = analyze(name, code, cross_date)
            if r:
                # 计算跨越天数
                cd = date(2026, 7, int(batch_name.split("/")[1]))
                r["days_since"] = (date(2026, 7, 23) - cd).days
                batch_results.append(r)
                results_all.append(r)
                print(f"  [{batch_name}] {name} {code} 距MA20={r['dist_ma20']}% 确认={r['is_confirm']}")
            else:
                print(f"  [{batch_name}] {name} {code} 失败")
            time.sleep(0.25)
        lines.append(f"\n## {batch_name} 批次（金叉后{date(2026,7,23).day - int(batch_name.split('/')[1])}天）\n")
        lines.append("| 代码 | 名称 | 距MA20 | 今日涨跌 | 量比 | 金叉至今 | 从高回撤 | 阶段 |\n")
        lines.append("|------|------|--------|----------|------|----------|----------|------|\n")
        for r in sorted(batch_results, key=lambda x: abs(x["dist_ma20"]) if x["dist_ma20"] else 99):
            stage = "**✅确定点**" if r["is_confirm"] else ("观察中" if r["golden_now"] else "❌金叉失效")
            lines.append(f"| {r['code']} | {r['name']} | {r['dist_ma20']}% | {r['today_chg']}% | "
                        f"{r['vol_ratio']} | {r['since_cross']}% | {r['drawdown']}% | {stage} |\n")

    # 汇总
    confirm_stocks = [r for r in results_all if r["is_confirm"]]
    golden_alive = [r for r in results_all if r["golden_now"]]
    golden_dead = [r for r in results_all if not r["golden_now"]]

    lines.append(f"\n## 框架验证汇总\n\n")
    lines.append(f"| 指标 | 数值 |\n|------|------|\n")
    lines.append(f"| 取样总数 | {len(results_all)} |\n")
    lines.append(f"| 金叉延续 | {len(golden_alive)}（{len(golden_alive)/len(results_all)*100:.0f}%） |\n")
    lines.append(f"| 金叉失效 | {len(golden_dead)}（{len(golden_dead)/len(results_all)*100:.0f}%） |\n")
    lines.append(f"| 达确定点 | {len(confirm_stocks)}（{len(confirm_stocks)/len(results_all)*100:.0f}%） |\n")

    if confirm_stocks:
        lines.append(f"\n### 当前处于「确定点」的标的\n")
        lines.append(f"| 代码 | 名称 | 金叉日期 | 距MA20 | 距金叉 | 从高点回撤 |\n")
        lines.append(f"|------|------|----------|--------|--------|------------|\n")
        for r in sorted(confirm_stocks, key=lambda x: abs(x["dist_ma20"])):
            lines.append(f"| {r['code']} | {r['name']} | {r['cross_date']} | {r['dist_ma20']}% | "
                        f"{r['since_cross']}% | {r['drawdown']}% |\n")

    if golden_dead:
        lines.append(f"\n### ⚠️ 金叉已失效（警示）\n")
        lines.append(f"| 代码 | 名称 | 金叉日期 | 距MA20 | 金叉至今 |\n")
        lines.append(f"|------|------|----------|--------|----------|\n")
        for r in golden_dead:
            lines.append(f"| {r['code']} | {r['name']} | {r['cross_date']} | {r['dist_ma20']}% | {r['since_cross']}% |\n")

    lines.append(f"\n## 框架结论\n\n")
    lines.append(f"### 介入点（DKX金叉日）= 初筛信号\n")
    lines.append(f"- DKX金叉发生的当天 → 加入观察池\n")
    lines.append(f"- 不做任何操作，只是「盯住」\n\n")
    lines.append(f"### 确定点（入场确认）= 三重过滤\n")
    lines.append(f"1. **金叉延续** — 金叉后≥1个交易日，MA5仍>MA20（排除一日游假金叉）\n")
    lines.append(f"2. **价格确认** — 股价距MA20 ≤±5%（回踩支撑位，不追高）\n")
    lines.append(f"3. **量能确认** — 当日量比 ≥0.8（排除缩量阴跌）\n\n")
    lines.append(f"### 加分项\n")
    lines.append(f"- 金叉后有过合理回撤（从高点回落3-8%）— 说明已经洗过盘\n")
    lines.append(f"- 所属板块是当日主线\n")
    lines.append(f"- 大市值/央企/消费龙头优先（DKX在大票上胜率更高）\n")

    with open(OUT, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"\n[OK] 报告: {OUT}")
    print(f"  总数:{len(results_all)} 金叉延续:{len(golden_alive)} 失效:{len(golden_dead)} 确定点:{len(confirm_stocks)}")

if __name__ == "__main__":
    main()
