#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
均值回归策略落地执行 — 当前大盘：震荡市（沪深300在MA250~MA60之间）
按《A股均值回归策略.md》+《细目.md》框架，拉真实数据跑信号。
"""

import os, sys, time, json, math, requests
from datetime import datetime, timedelta
from collections import OrderedDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

UA = "Mozilla/5.0"
TDX_SERVERS = [
    ('119.97.185.59', 7709), ('124.70.133.119', 7709), ('116.205.183.150', 7709),
]
sess = requests.Session()
sess.trust_env = False
sess.headers.update({"User-Agent": UA})

# ── 标的池：用户偏好的ETF + 主要宽基 ──
ETF_POOL = OrderedDict({
    "510050": "上证50ETF",
    "510300": "沪深300ETF",
    "510880": "红利ETF",
    "159928": "消费ETF",
    "512690": "酒ETF",
    "512880": "证券ETF",
    "512800": "银行ETF",
    "510500": "中证500ETF",
    "159915": "创业板ETF",
    "588000": "科创50ETF",
})

INDEX_POOL = OrderedDict({
    "000001": "上证指数",
    "000300": "沪深300",
    "399006": "创业板指",
    "000688": "科创50",
    "000905": "中证500",
})

# ── 1. 腾讯K线拉取 ──
SH_INDEX = frozenset({"000001", "000300", "000905", "000016", "000688", "000852", "000010"})

def get_prefix(code):
    lo = code.lower()
    if lo.startswith(("sh", "sz", "bj")):
        return lo[:2]
    if lo.startswith(("5", "6", "9")):
        return "sh"
    if lo.startswith(("4", "8", "92")):
        return "bj"
    if code in SH_INDEX:
        return "sh"
    return "sz"

def tencent_kline(code, days=300):
    """腾讯K线，返回 [{date, open, close, high, low, volume}]"""
    prefix = get_prefix(code)
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
    try:
        r = sess.get(url, headers={"Host": "web.ifzq.gtimg.cn"}, timeout=10)
        d = r.json()
        kdata = d.get("data", {}).get(f"{prefix}{code}", {}).get("qfqday", []) or \
                d.get("data", {}).get(f"{prefix}{code}", {}).get("day", [])
    except Exception as e:
        print(f"  [ERR] {code} K线拉取失败: {e}")
        return []
    rows = []
    for k in kdata:
        try:
            rows.append({
                "date": k[0],
                "open": float(k[1]),
                "close": float(k[2]),
                "high": float(k[3]),
                "low": float(k[4]),
                "vol": float(k[5]),
            })
        except (IndexError, ValueError):
            continue
    return rows


# ── 2. 均值回归信号计算 ──
def calc_ma(prices, n):
    if len(prices) < n:
        return None
    return sum(prices[-n:]) / n

def calc_std(prices, n):
    if len(prices) < n:
        return None
    avg = calc_ma(prices, n)
    var = sum((p - avg) ** 2 for p in prices[-n:]) / n
    return math.sqrt(var)

def calc_rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(-n, 0):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / n
    avg_loss = sum(losses) / n
    if avg_loss == 0:
        return 100
    return 100 - 100 / (1 + avg_gain / avg_loss)

def analyze_target(code, name, klines, days=300):
    """对单标的计算所有均值回归指标"""
    if len(klines) < 60:
        return None
    
    closes = [k["close"] for k in klines]
    vols   = [k["vol"] for k in klines]
    highs  = [k["high"] for k in klines]
    lows   = [k["low"] for k in klines]
    
    latest   = closes[-1]
    latest_date = klines[-1]["date"]
    
    # MA均线
    ma20  = calc_ma(closes, 20)
    ma60  = calc_ma(closes, 60)
    ma250 = calc_ma(closes, 250)
    
    # BIAS 乖离率
    bias20  = (latest - ma20) / ma20 * 100 if ma20 else None
    bias60  = (latest - ma60) / ma60 * 100 if ma60 else None
    bias250 = (latest - ma250) / ma250 * 100 if ma250 else None
    
    # 布林带 / Z-score
    ma20_val = calc_ma(closes, 20)
    std20    = calc_std(closes, 20)
    z_score  = (latest - ma20_val) / std20 if (ma20_val and std20 and std20 > 0) else None
    boll_upper = ma20_val + 2 * std20 if (ma20_val and std20) else None
    boll_lower = ma20_val - 2 * std20 if (ma20_val and std20) else None
    boll_width = (boll_upper - boll_lower) / ma20_val * 100 if (ma20_val and boll_lower) else None
    
    # RSI
    rsi14 = calc_rsi(closes, 14)
    rsi6  = calc_rsi(closes, 6)
    
    # 量能
    vol_ma5  = calc_ma(vols, 5)
    vol_ma20 = calc_ma(vols, 20)
    vol_ratio5  = vols[-1] / vol_ma5 if vol_ma5 and vol_ma5 > 0 else 1
    vol_ratio20 = vols[-1] / vol_ma20 if vol_ma20 and vol_ma20 > 0 else 1
    
    # 近期高低点
    recent_60_high = max(highs[-60:])
    recent_60_low  = min(lows[-60:])
    pos_in_range = (latest - recent_60_low) / (recent_60_high - recent_60_low) * 100 if recent_60_high != recent_60_low else 50
    
    # 20日区间
    range_20_high = max(highs[-20:])
    range_20_low  = min(lows[-20:])
    
    # ADX 简化版
    adx = None
    if len(highs) >= 29:
        tr_list = []
        dm_plus_list = []
        dm_minus_list = []
        for i in range(-28, 1):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            tr_list.append(tr)
            up = highs[i] - highs[i-1]
            dn = lows[i-1] - lows[i]
            dm_plus_list.append(up if up > dn and up > 0 else 0)
            dm_minus_list.append(dn if dn > up and dn > 0 else 0)
        tr14 = sum(tr_list[-14:]) / 14
        if tr14 > 0:
            di_plus  = (sum(dm_plus_list[-14:]) / 14) / tr14 * 100
            di_minus = (sum(dm_minus_list[-14:]) / 14) / tr14 * 100
            dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100 if (di_plus + di_minus) > 0 else 0
            adx = dx  # 简化：用当日DX近似
    
    # 均线排列
    if ma20 and ma60 and ma250:
        if ma20 > ma60 > ma250:
            ma_arrange = "多头排列"
        elif ma20 < ma60 < ma250:
            ma_arrange = "空头排列"
        else:
            ma_arrange = "均线缠绕"
    else:
        ma_arrange = "数据不足"
    
    # ── 信号判定 ──
    signals = []
    
    # BIAS 信号
    if bias20 is not None and bias20 <= -8:
        signals.append(f"BIAS(20)={bias20:.1f}% 极度超卖")
    elif bias20 is not None and bias20 <= -5:
        signals.append(f"BIAS(20)={bias20:.1f}% 超卖")
    
    # Z-score 信号
    if z_score is not None:
        if z_score <= -2:
            signals.append(f"Z-score={z_score:.2f} 触及布林下轨(强)")
        elif z_score <= -1.5:
            signals.append(f"Z-score={z_score:.2f} 接近布林下轨")
    
    # RSI 信号
    if rsi14 is not None:
        if rsi14 < 25:
            signals.append(f"RSI(14)={rsi14:.1f} 深度超卖")
        elif rsi14 < 30:
            signals.append(f"RSI(14)={rsi14:.1f} 超卖")
        elif rsi14 > 75:
            signals.append(f"RSI(14)={rsi14:.1f} 超买(回归卖出候选)")
        elif rsi14 > 70:
            signals.append(f"RSI(14)={rsi14:.1f} 偏超买")
    
    # 成交量缩量
    if vol_ratio5 is not None and vol_ratio5 < 0.7:
        signals.append(f"缩量(量比={vol_ratio5:.2f})")
    
    # 区间位置
    if pos_in_range <= 15:
        signals.append(f"处于60日区间低位({pos_in_range:.0f}%)")
    elif pos_in_range >= 85:
        signals.append(f"处于60日区间高位({pos_in_range:.0f}%)")
    
    # ADX
    if adx is not None and adx < 20:
        signals.append(f"ADX={adx:.1f}(<20震荡确认)")
    
    # 综合操作建议
    action = "观望"
    buy_score = 0
    if z_score is not None and z_score <= -1.5:
        buy_score += 2
    if rsi14 is not None and rsi14 < 35:
        buy_score += 2
    if bias20 is not None and bias20 <= -5:
        buy_score += 2
    if vol_ratio5 is not None and vol_ratio5 < 0.7:
        buy_score += 1  # 缩量企稳好于放量下杀
    if pos_in_range <= 20:
        buy_score += 1
    
    if buy_score >= 5:
        action = "分批买入(1/3仓位)"
    elif buy_score >= 3:
        action = "关注(等待企稳确认)"
    elif rsi14 is not None and rsi14 > 70:
        action = "考虑减仓/止盈"
    
    return {
        "code": code,
        "name": name,
        "date": latest_date,
        "close": latest,
        "ma20": round(ma20, 2) if ma20 else None,
        "ma60": round(ma60, 2) if ma60 else None,
        "ma250": round(ma250, 2) if ma250 else None,
        "bias20": round(bias20, 2) if bias20 else None,
        "bias60": round(bias60, 2) if bias60 else None,
        "z_score": round(z_score, 2) if z_score else None,
        "boll_lower": round(boll_lower, 2) if boll_lower else None,
        "boll_upper": round(boll_upper, 2) if boll_upper else None,
        "boll_width_pct": round(boll_width, 2) if boll_width else None,
        "rsi14": round(rsi14, 1) if rsi14 else None,
        "rsi6": round(rsi6, 1) if rsi6 else None,
        "adx": round(adx, 1) if adx else None,
        "vol_ratio5": round(vol_ratio5, 2) if vol_ratio5 else None,
        "pos_in_range_pct": round(pos_in_range, 1),
        "recent_60_high": round(recent_60_high, 2),
        "recent_60_low": round(recent_60_low, 2),
        "ma_arrange": ma_arrange,
        "signals": signals,
        "action": action,
        "buy_score": buy_score,
    }


# ── 3. 主流程 ──
def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print("=" * 80)
    print(f"  均值回归策略落地执行 — {today}")
    print("  大盘背景：震荡市（沪深300 MA250~MA60之间）")
    print("  策略启用条件：✓ 震荡档 ✓ 标的优先ETF ✓ 五类信号扫描")
    print("=" * 80)
    
    # ── 第一步：确认大盘环境 ──
    print("\n[1/3] 大盘环境确认...")
    idx_data = {}
    for code, name in INDEX_POOL.items():
        k = tencent_kline(code, 300)
        if k:
            idx_data[code] = analyze_target(code, name, k)
    
    hs300 = idx_data.get("000300", {})
    if hs300:
        print(f"  沪深300: 收盘{hs300['close']} MA20={hs300['ma20']} MA60={hs300['ma60']} MA250={hs300['ma250']}")
        print(f"  ADX={hs300['adx']} 均线={hs300['ma_arrange']} RSI14={hs300['rsi14']}")
        env_ok = hs300.get("adx") and hs300["adx"] < 20
        print(f"  震荡环境判定: {'✓ ADX<20 震荡确认' if env_ok else '⚠ ADX偏高，注意趋势风险'}")
        print(f"  布林带宽: {hs300.get('boll_width_pct')}% {'(收口—回归黄金期!)' if hs300.get('boll_width_pct') and hs300['boll_width_pct'] < 10 else '(带宽正常)'}")
    
    # ── 第二步：ETF回归信号扫描 ──
    print("\n[2/3] ETF池均值回归信号扫描（共{}只）...".format(len(ETF_POOL)))
    
    etf_results = []
    for code, name in ETF_POOL.items():
        print(f"  拉取 {name}({code})...", end=" ")
        k = tencent_kline(code, 300)
        if not k:
            print("失败")
            continue
        r = analyze_target(code, name, k)
        if r:
            etf_results.append(r)
            sig_str = ", ".join(r["signals"]) if r["signals"] else "无信号"
            print(f"OK | 收盘{r['close']} Z={r['z_score']} RSI={r['rsi14']} {sig_str}")
        else:
            print("数据不足")
        time.sleep(0.6)
    
    # ── 排序 ──
    # 回归买入信号按 buy_score 降序
    buy_candidates = sorted(
        [r for r in etf_results if r["buy_score"] >= 3],
        key=lambda x: x["buy_score"], reverse=True
    )
    
    # 超买/止盈信号
    sell_candidates = sorted(
        [r for r in etf_results if r.get("rsi14") and r["rsi14"] > 65],
        key=lambda x: x["rsi14"], reverse=True
    )
    
    # ── 第三步：输出结果 ──
    print("\n" + "=" * 80)
    print("  [3/3] 均值回归信号汇总")
    print("=" * 80)
    
    # 完整表格
    print(f"\n{'代码':<8} {'名称':<10} {'收盘':>8} {'Z-score':>8} {'RSI14':>7} {'BIAS20':>8} {'ADX':>7} {'布林带宽':>8} {'60日%':>6} {'操作建议'}")
    print("-" * 110)
    for r in etf_results:
        zs = f"{r['z_score']:.2f}" if r['z_score'] is not None else "N/A"
        rs = f"{r['rsi14']:.1f}" if r['rsi14'] is not None else "N/A"
        bs = f"{r['bias20']:.1f}%" if r['bias20'] is not None else "N/A"
        ax = f"{r['adx']:.1f}" if r['adx'] is not None else "N/A"
        bw = f"{r['boll_width_pct']:.1f}%" if r['boll_width_pct'] else "N/A"
        print(f"{r['code']:<8} {r['name']:<10} {r['close']:>8.2f} {zs:>8} {rs:>7} {bs:>8} {ax:>7} {bw:>8} {r['pos_in_range_pct']:>5.0f}% {r['action']}")
    
    # ── 买入候选 ──
    print("\n" + "=" * 80)
    print("  ◆ 均值回归买入候选（buy_score≥3）")
    print("=" * 80)
    if buy_candidates:
        for r in buy_candidates:
            print(f"\n  [{r['code']}] {r['name']}  评分:{r['buy_score']}/7")
            print(f"    收盘:{r['close']}  Z-score:{r['z_score']}  RSI:{r['rsi14']}  BIAS20:{r['bias20']}%")
            print(f"    布林下轨:{r['boll_lower']}  上轨:{r['boll_upper']}  带宽:{r['boll_width_pct']}%")
            print(f"    量比:{r['vol_ratio5']}  60日位置:{r['pos_in_range_pct']:.0f}%")
            print(f"    均线:{r['ma_arrange']}  ADX:{r['adx']}")
            print(f"    信号: {', '.join(r['signals'])}")
            print(f"    ★ 操作: {r['action']}")
    else:
        print("\n  当前无高评分买入信号（所有ETF不在超卖区）")
    
    # ── 超买/止盈候选 ──
    print("\n" + "=" * 80)
    print("  ◆ 潜在止盈/减仓候选（RSI偏高）")
    print("=" * 80)
    if sell_candidates:
        for r in sell_candidates:
            print(f"  [{r['code']}] {r['name']}  RSI={r['rsi14']}  Z={r['z_score']}  BIAS20={r['bias20']}%")
    else:
        print("  当前无超买信号")
    
    # ── 五种策略逐一对照 ──
    print("\n" + "=" * 80)
    print("  ◆ 五类均值回归策略适用性评估")
    print("=" * 80)
    
    # 1. BIAS乖离率回归 — 看BIAS20<-5的标的
    bias_targets = [r for r in etf_results if r.get("bias20") and r["bias20"] <= -5]
    print(f"\n  ① 乖离率回归(BIAS): {'✓ 有{0}个标的BIAS20<-5%'.format(len(bias_targets)) if bias_targets else '✗ 当前无深度乖离信号'}")
    if bias_targets:
        for t in bias_targets:
            print(f"     {t['code']} {t['name']}: BIAS20={t['bias20']}%")
    
    # 2. 布林带/Z-score
    z_targets = [r for r in etf_results if r.get("z_score") and r["z_score"] <= -1.5]
    print(f"\n  ② 布林带/Z-score回归: {'✓ 有{0}个标的Z≤-1.5'.format(len(z_targets)) if z_targets else '✗ 无标的触及下轨'}")
    if z_targets:
        for t in z_targets:
            print(f"     {t['code']} {t['name']}: Z={t['z_score']} 下轨={t['boll_lower']}")
    
    # 3. RSI/KDJ
    rsi_targets = [r for r in etf_results if r.get("rsi14") and r["rsi14"] < 35]
    print(f"\n  ③ RSI超买超卖回归: {'✓ 有{0}个标的RSI<35'.format(len(rsi_targets)) if rsi_targets else '✗ 无超卖信号'}")
    if rsi_targets:
        for t in rsi_targets:
            print(f"     {t['code']} {t['name']}: RSI14={t['rsi14']}")
    
    # 4. 箱体 — 看60日位置
    box_targets = [r for r in etf_results if r["pos_in_range_pct"] <= 20]
    print(f"\n  ④ 箱体高抛低吸: {'✓ 有{0}个标的在60日箱体底部20%'.format(len(box_targets)) if box_targets else '✗ 无标的在箱底'}")
    if box_targets:
        for t in box_targets:
            print(f"     {t['code']} {t['name']}: 位置={t['pos_in_range_pct']:.0f}% 下沿={t['recent_60_low']}")
    
    # 5. 网格 — 评估布林带宽
    narrow_bw = [r for r in etf_results if r.get("boll_width_pct") and r["boll_width_pct"] < 12]
    print(f"\n  ⑤ 网格交易: {'✓ 有{0}个标的布林带宽<12%(适合网格)'.format(len(narrow_bw)) if narrow_bw else '✗ 带宽偏宽，网格效率低'}")
    
    # ── 交易清单（一页纸打勾） ──
    print("\n" + "=" * 80)
    print("  ◆ 均值回归交易检查清单（一页纸）")
    print("=" * 80)
    checks = [
        ("[✓] 当前是震荡档环境(大盘开关 + ADX<20)", hs300.get("adx") and hs300["adx"] < 20 if hs300 else False),
        ("[✓] 标的是指数/ETF（不会死的品种）", True),  # 我们只扫ETF
        ("[?] 存在可识别的中枢（需逐票确认）", None),
        ("[?] 信号触发时缩量企稳（需实时看盘确认）", None),
        ("[?] 补仓次数上限已写死（最多2次）", None),
        ("[?] 三种失效止损位已写下（结构/偏离/趋势确认）", None),
        ("[?] 时间止损日期已写下（进场后15个交易日）", None),
        ("[?] 回归目标位已写下（MA20/布林中轨），承诺到点至少卖一半", None),
        ("[!] 已接受「这笔可能是不回归的35%，而且会是大亏」", None),
    ]
    for desc, status in checks:
        mark = " ✓" if status is True else (" ?" if status is None else " ✗")
        print(f"  {mark} {desc}")
    
    print("\n" + "=" * 80)
    print("  核心提醒（策略文档重点）：")
    print("  1. 回归系统的生死取决于控制「那一次不回归」——左尾比趋势系统更厚")
    print("  2. 到目标必走、破结构必走、时间到必走——三纪律比选股重要十倍")
    print("  3. 回归单拿成趋势单是最常见的坐电梯方式：到MA20至少卖一半")
    print("  4. 连续小赚后警惕第11次扛单——每笔进场前预演「这笔可能就是那35%」")
    print("=" * 80)


if __name__ == "__main__":
    main()
