#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""波段选股筛选器 — 2026-07-23
筛选逻辑：
1. 从今日涨停池 + 主线板块（电网设备/能源金属/中报预增）的白马股中初选
2. 腾讯日K线检查：均线结构、振幅、成交量、距支撑位距离
3. 情景B适配：偏好均线粘合待突破、回调至支撑附近的标的
"""

import json
import time
import os
import sys
from datetime import datetime
from collections import defaultdict

import requests

# ─── 配置 ───
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "log")
TODAY = "2026-07-23"
OUTPUT_FILE = os.path.join(LOG_DIR, f"{TODAY.replace('-', '')}_波段选股推荐.md")

# 腾讯日K线 API 模板
TENCENT_KLINE = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={market}{code},day,,,120,qfq"

# 涨停池股票（来自今日打板分析，去重后精选）
# 按主线分三组：电网设备、能源金属/锂电、中报预增
CANDIDATES = {
    "电网设备主线": [
        {"code": "000533", "name": "顺钠股份", "reason": "输变电龙头6板"},
        {"code": "002879", "name": "长缆科技", "reason": "线缆3连板"},
        {"code": "605117", "name": "新洁能",  "reason": "逆变器涨停"},
        {"code": "300001", "name": "特锐德",   "reason": "电网设备+充电桩龙头"},
        {"code": "002606", "name": "大连电瓷", "reason": "电网+特高压"},
        {"code": "601700", "name": "风范股份", "reason": "输变电铁塔"},
    ],
    "能源金属/锂电主线": [
        {"code": "603399", "name": "吉翔股份", "reason": "锂+能源金属双属性"},
        {"code": "300750", "name": "宁德时代", "reason": "电池龙头+超跌"},
        {"code": "603799", "name": "华友钴业", "reason": "镍+能源金属"},
        {"code": "002460", "name": "赣锋锂业", "reason": "锂龙头+超跌反弹"},
        {"code": "000603", "name": "盛达资源", "reason": "白银+3连板"},
        {"code": "600111", "name": "北方稀土", "reason": "稀土龙头"},
    ],
    "中报预增主线": [
        {"code": "000815", "name": "美利云",   "reason": "4连板+云计算+国资"},
        {"code": "002197", "name": "证通电子", "reason": "3连板+算力"},
        {"code": "603619", "name": "中曼石油", "reason": "2连板+油服"},
        {"code": "300191", "name": "潜能恒信", "reason": "油服+油气"},
        {"code": "600803", "name": "新奥股份", "reason": "天然气+业绩"},
        {"code": "603026", "name": "石大胜华", "reason": "电解液+中报扭亏"},
    ],
    "央企/权重波段": [
        {"code": "601857", "name": "中国石油", "reason": "上证50权重+能源"},
        {"code": "600028", "name": "中国石化", "reason": "上证50权重+炼化"},
        {"code": "601668", "name": "中国建筑", "reason": "央企+基建"},
        {"code": "600900", "name": "长江电力", "reason": "电力+防御"},
    ],
}

session = requests.Session()
session.trust_env = False
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})


def _code_to_market(code):
    """判断深圳/上海"""
    if code.startswith(('0', '3')):
        return 'sz'
    return 'sh'


def fetch_kline(code, market=None):
    """拉取最近120个交易日的日K线，返回 {dates, opens, closes, highs, lows, vols}"""
    if market is None:
        market = _code_to_market(code)
    url = TENCENT_KLINE.format(market=market, code=code)
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
        data = json.loads(r.text)
        klines = data["data"][f"{market}{code}"].get("qfqday")
        if not klines:
            klines = data["data"][f"{market}{code}"].get("day")
        if not klines:
            return None

        dates, opens, closes, highs, lows, vols = [], [], [], [], [], []
        for row in klines:
            # [date, open, close, high, low, volume]
            if len(row) < 6:
                continue
            dates.append(row[0])
            opens.append(float(row[1]))
            closes.append(float(row[2]))
            highs.append(float(row[3]))
            lows.append(float(row[4]))
            vols.append(float(row[5]))
        return {
            "dates": dates, "opens": opens, "closes": closes,
            "highs": highs, "lows": lows, "vols": vols
        }
    except Exception as e:
        print(f"  [WARN] {code} K线拉取失败: {e}", file=sys.stderr)
        return None


def calc_ma(values, n):
    """计算最近N日均值"""
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def calc_amplitude(highs, lows, closes, n=20):
    """近N日平均真实振幅 (ATR 简化版)"""
    if len(closes) < n + 1:
        return None
    tr_list = []
    for i in range(-n, 0):
        h = highs[i]
        l = lows[i]
        prev_c = closes[i - 1] if i > -len(closes) else opens[i]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)
    avg_tr = sum(tr_list) / n
    latest = closes[-1]
    return {
        "avg_true_range": round(avg_tr, 3),
        "atr_pct": round(avg_tr / latest * 100, 2),
        "avg_amplitude": round((highs[-1] - lows[-1]) / latest * 100, 2)  # 今日振幅
    }


def calc_vol_ratio(vols, n=5):
    """近N日量比：最近5日均量 / 20日均量"""
    if len(vols) < 20:
        return None
    vol5 = sum(vols[-5:]) / 5
    vol20 = sum(vols[-20:]) / 20
    return round(vol5 / vol20, 2) if vol20 > 0 else None


def score_ma_structure(closes, mas):
    """均线结构评分 (0-5分)"""
    score = 0
    details = []
    latest = closes[-1]

    # 价格 vs 均线
    vs_ma5 = latest - mas["ma5"] if mas["ma5"] else 0
    vs_ma10 = latest - mas["ma10"] if mas["ma10"] else 0
    vs_ma20 = latest - mas["ma20"] if mas["ma20"] else 0

    # 站上MA20 = +1.5分
    if vs_ma20 and vs_ma20 > 0:
        score += 1.5
        details.append("站上MA20")
    elif vs_ma20 and abs(vs_ma20) / mas["ma20"] < 0.02:
        score += 1.0
        details.append("贴近MA20(+/-2%)")

    # 均线多头排列 MA5 > MA10 > MA20 = +2分
    if mas["ma5"] and mas["ma10"] and mas["ma20"]:
        if mas["ma5"] > mas["ma10"] > mas["ma20"]:
            score += 2.0
            details.append("均线多头排列")
        elif mas["ma5"] > mas["ma10"]:
            score += 1.0
            details.append("MA5>MA10(部分多头)")

    # 均线粘合 (MA20附近密集) = +1分
    if mas["ma5"] and mas["ma10"] and mas["ma20"]:
        ma_range = max(mas["ma5"], mas["ma10"], mas["ma20"]) - min(mas["ma5"], mas["ma10"], mas["ma20"])
        if ma_range / mas["ma20"] < 0.05:
            score += 1.0
            details.append("均线粘合待突破")

    # 近期趋势：近5日涨幅
    if len(closes) >= 5:
        chg5 = (closes[-1] - closes[-5]) / closes[-5] * 100
        if 0 < chg5 < 10:
            score += 0.5
            details.append(f"5日温和上涨({chg5:.1f}%)")

    return {"score": min(score, 5), "details": details}


def analyze_stock(code, name, reason, kline_data):
    """综合打分"""
    if not kline_data:
        return None

    closes = kline_data["closes"]
    highs = kline_data["highs"]
    lows = kline_data["lows"]
    vols = kline_data["vols"]
    latest = closes[-1]

    # 均线
    mas = {
        "ma5": calc_ma(closes, 5),
        "ma10": calc_ma(closes, 10),
        "ma20": calc_ma(closes, 20),
        "ma60": calc_ma(closes, 60),
    }

    # 均线结构评分
    structure = score_ma_structure(closes, mas)

    # 振幅
    amp = calc_amplitude(highs, lows, closes)

    # 量比
    vol_ratio = calc_vol_ratio(vols)

    # 距支撑位距离 (MA20作为支撑)
    dist_to_ma20 = None
    if mas["ma20"]:
        dist_to_ma20 = round((latest - mas["ma20"]) / mas["ma20"] * 100, 2)

    # 近20日涨跌幅
    chg20 = None
    if len(closes) >= 20:
        chg20 = round((latest - closes[-20]) / closes[-20] * 100, 2)

    # 波段适宜度综合评分
    swing_score = 0
    swing_reasons = []

    # 振幅适中 (2-7% ATR) → 有波段空间但不太极端
    if amp and 2 <= amp["atr_pct"] <= 7:
        swing_score += 2
        swing_reasons.append(f"振幅适中(ATR {amp['atr_pct']}%)")
    elif amp and amp["atr_pct"] < 2:
        swing_score += 0.5
        swing_reasons.append(f"振幅偏小(ATR {amp['atr_pct']}%)，波段空间有限")
    elif amp:
        swing_score += 1
        swing_reasons.append(f"振幅偏大(ATR {amp['atr_pct']}%)，需严止损")

    # 放量 = 资金参与度高
    if vol_ratio and vol_ratio > 1.5:
        swing_score += 1.5
        swing_reasons.append(f"放量(量比{vol_ratio})")
    elif vol_ratio and vol_ratio > 1.0:
        swing_score += 1.0
        swing_reasons.append(f"温和放量(量比{vol_ratio})")

    # 靠近支撑位买入更安全
    if dist_to_ma20 is not None and -3 <= dist_to_ma20 <= 3:
        swing_score += 1.5
        swing_reasons.append(f"靠近MA20支撑({dist_to_ma20:+.1f}%)")
    elif dist_to_ma20 is not None and dist_to_ma20 > 3:
        swing_score += 0.5
        swing_reasons.append(f"偏离MA20({dist_to_ma20:+.1f}%)，追高风险")
    elif dist_to_ma20 is not None and dist_to_ma20 < -3:
        swing_reasons.append(f"跌破MA20({dist_to_ma20:+.1f}%)，趋势偏弱")

    # 均线结构加分
    swing_score += structure["score"] * 0.5

    # 20日跌幅大 = 超跌反弹潜力
    if chg20 is not None and chg20 < -10:
        swing_score += 1.0
        swing_reasons.append(f"20日超跌({chg20:+.1f}%)，反弹空间大")

    return {
        "code": code,
        "name": name,
        "latest": latest,
        "mas": mas,
        "amp": amp,
        "vol_ratio": vol_ratio,
        "dist_to_ma20": dist_to_ma20,
        "chg20": chg20,
        "structure": structure,
        "swing_score": round(swing_score, 1),
        "swing_reasons": swing_reasons,
        "reason": reason,
    }


def main():
    print(f"=== 波段选股筛选器 | {TODAY} ===")
    print(f"情景B：高波动结构性调整市 — 偏好均线粘合、振幅适中、靠近支撑的标的\n")

    all_results = {}
    total = sum(len(v) for v in CANDIDATES.values())
    done = 0

    for group_name, stocks in CANDIDATES.items():
        print(f"\n{'='*50}")
        print(f"【{group_name}】")
        print(f"{'='*50}")
        group_results = []

        for s in stocks:
            code = s["code"]
            name = s["name"]
            reason = s["reason"]
            print(f"\n  分析 {name}({code}) ...", end=" ", flush=True)
            kline = fetch_kline(code)
            done += 1
            if not kline:
                print("K线数据缺失")
                continue
            result = analyze_stock(code, name, reason, kline)
            if result:
                group_results.append(result)
                print(f"波段分={result['swing_score']:.1f} | 价={result['latest']:.2f} | ATR={result['amp']['atr_pct']}%")
            time.sleep(0.3)  # 腾讯API限流

        group_results.sort(key=lambda x: x["swing_score"], reverse=True)
        all_results[group_name] = group_results

    # ─── 生成报告 ───
    report = generate_report(all_results)
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n\n[OK] 报告已保存至: {OUTPUT_FILE}")
    print(report[:500])


def generate_report(all_results):
    lines = []
    lines.append(f"# {TODAY} 波段选股推荐")
    lines.append("")
    lines.append(f"> 报告时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 市场状态：情景B — 高波动结构性调整市")
    lines.append(f"> 筛选逻辑：主线板块涨停股 + 均线结构 + 振幅 + 成交量 + 距支撑位距离")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 汇总排名
    all_stocks = []
    for group, results in all_results.items():
        for r in results:
            all_stocks.append({**r, "group": group})
    all_stocks.sort(key=lambda x: x["swing_score"], reverse=True)

    lines.append("## 一、综合排名 TOP10")
    lines.append("")
    lines.append("| 排名 | 代码 | 名称 | 板块 | 波段分 | 现价 | ATR% | 量比 | 距MA20 | 核心逻辑 |")
    lines.append("|------|------|------|------|--------|------|------|------|--------|----------|")
    for i, s in enumerate(all_stocks[:10], 1):
        dist = f"{s['dist_to_ma20']:+.1f}%" if s["dist_to_ma20"] is not None else "—"
        vol = f"{s['vol_ratio']:.1f}" if s["vol_ratio"] else "—"
        atr = f"{s['amp']['atr_pct']}%" if s["amp"] else "—"
        reason = "; ".join(s["swing_reasons"][:2])
        lines.append(f"| {i} | {s['code']} | {s['name']} | {s['group']} | **{s['swing_score']:.1f}** | {s['latest']:.2f} | {atr} | {vol} | {dist} | {reason} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # 分组详情
    lines.append("## 二、分组详细分析")
    lines.append("")

    for group_name, results in all_results.items():
        if not results:
            continue
        lines.append(f"### {group_name}")
        lines.append("")

        for rank, s in enumerate(results, 1):
            stars = "★" * min(int(s["swing_score"]) + 1, 5)
            lines.append(f"#### {rank}. {s['name']}（{s['code']}）  {stars}  {s['swing_score']:.1f}分")
            lines.append("")
            lines.append(f"- **现价**：{s['latest']:.2f}")
            lines.append(f"- **入选理由**：{s['reason']}")

            # 均线
            ma_line = []
            for key, label in [("ma5", "MA5"), ("ma10", "MA10"), ("ma20", "MA20"), ("ma60", "MA60")]:
                if s["mas"][key]:
                    ma_line.append(f"{label}={s['mas'][key]:.2f}")
            lines.append(f"- **均线**：{' | '.join(ma_line)}")
            lines.append(f"- **均线结构**：{'；'.join(s['structure']['details']) if s['structure']['details'] else '偏弱'}")

            # 振幅
            if s["amp"]:
                lines.append(f"- **振幅**：ATR={s['amp']['avg_true_range']}({s['amp']['atr_pct']}%)，今日振幅={s['amp']['avg_amplitude']}%")
            if s["vol_ratio"]:
                lines.append(f"- **量比(5/20)**：{s['vol_ratio']}")
            if s["dist_to_ma20"] is not None:
                lines.append(f"- **距MA20**：{s['dist_to_ma20']:+.1f}%")
            if s["chg20"] is not None:
                lines.append(f"- **20日涨跌**：{s['chg20']:+.1f}%")

            lines.append(f"- **波段适宜度**：{'；'.join(s['swing_reasons'])}")
            lines.append("")

    # 情景B策略建议
    lines.append("---")
    lines.append("")
    lines.append("## 三、情景B波段策略")
    lines.append("")
    lines.append("当前市场状态（情景B）下的波段交易核心原则：")
    lines.append("")
    lines.append("### 入场条件")
    lines.append("1. **靠近MA20支撑位**（距MA20 ±3%以内）分批建仓")
    lines.append("2. **量比 >1.0** 确认资金参与，无量不进场")
    lines.append("3. **优先均线粘合待突破**的标的，方向选择后顺势")
    lines.append("4. **回避偏离MA20 >10%** 的追高品种")
    lines.append("")
    lines.append("### 出场条件")
    lines.append("1. **盈利5-8% 止盈一半**，情景B不适合贪心")
    lines.append("2. **跌破MA20 + 量缩** 无条件离场")
    lines.append("3. **板块轮动切换**信号出现时减仓")
    lines.append("4. **上证50跌破2930** 是系统性撤退信号")
    lines.append("")
    lines.append("### 仓位管理")
    lines.append("- 总仓位：半仓（高波动环境）")
    lines.append("- 单票仓位：10-15%")
    lines.append("- 同时持股：2-3只，分散板块风险")
    lines.append("")
    lines.append("### 板块优先级")
    lines.append("```")
    lines.append("电网设备 > 能源金属/锂电 > 中报预增 > 央企权重")
    lines.append("```")
    lines.append("> 电网设备有政策支撑（电网建设加速），能源金属属于超跌反弹，央企权重作为防御底仓。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*报告由 `_swing_screener.py` 自动生成 | 数据源：腾讯日K线 API | {TODAY}*")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
