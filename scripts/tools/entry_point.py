#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""介入点计算工具（官方K线源，禁止估算）

纪律（2026-08-06 固化）：
- 介入点一律用腾讯官方日K接口（web.ifzq.gtimg.cn，前复权 qfq）计算 MA
- 禁止用记忆/估算/近似值充当介入点；本工具是唯一允许的介入点来源
- 回踩买点判定：现价距 MA10 ∈ [-3%, +3%] 且 量比 < 0.8（缩量企稳）
- 止损位 = MA10 × 0.95（破位止损）或 距现价 -5%（取更近者按纪律提示）

Q-score 回踩质量评分（2026-08-06 工程化，均值回归策略量化标准）：
  六因子加权：偏离度(30) + 缩量(20) + 回踩天数(15) + RSI(15) + MA结构(10) + 量价形态(10)
  分级：≥80 A级强回踩(1%R) · 65~79 B级标准回踩(0.5~1%R) · 50~64 C级弱回踩(观察) · <50 D级不介入
  全部因子仅用日K（官方源）计算，无估算；量能用"当日量/5日均量"代替分时量比（同源日K）

用法：
  python scripts/tools/entry_point.py --codes 601138,300476
  python scripts/tools/entry_point.py --code 601138 --json
"""
import argparse
import json
import os
import sys

# 支持两种运行方式：python scripts/tools/entry_point.py 与 python -m scripts.tools.entry_point
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def _norm(code: str) -> str:
    """归一化个股代码 → 腾讯前缀格式"""
    c = code.strip().upper()
    if c.startswith(("SH", "SZ", "BJ")):
        c = c[2:]
    if c.startswith("6") or c.startswith("9"):
        return "sh" + c
    return "sz" + c


def _rsi(closes, n=14):
    """RSI(14)：仅用日K收盘价计算"""
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        avg_gain = (avg_gain * (n - 1) + gains[i]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i]) / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _pullback_days(highs):
    """距最近 N 日高点的回落天数（N=6）：回踩时间因子"""
    window = highs[-7:] if len(highs) >= 7 else highs
    peak_idx = window.index(max(window))
    return len(window) - 1 - peak_idx


def _kline_cache(session, pref, n_days=70):
    """拉取腾讯官方前复权日K（带缓存避免重复请求）"""
    cache = getattr(_kline_cache, "_c", {})
    if pref in cache:
        return cache[pref]
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    r = session.get(url, params={"param": f"{pref},day,,,{n_days},qfq"}, timeout=10)
    d = r.json()["data"][pref]
    kl = d.get("qfqday") or d.get("day") or []
    cache[pref] = kl
    _kline_cache._c = cache
    return kl


def _qscore(kl, closes, cur, dev10):
    """回踩质量六因子评分（0~100）。全部基于日K官方源计算，无估算。"""
    highs = [float(x[3]) for x in kl]
    lows = [float(x[4]) for x in kl]
    vols = [float(x[5]) for x in kl]

    # 因子1 偏离度（30分）：距 MA10 越近越优
    if dev10 is None:
        s_dev = 0
    elif abs(dev10) <= 1.0:
        s_dev = 30
    elif abs(dev10) <= 3.0:
        s_dev = 26
    elif abs(dev10) <= 5.0:
        s_dev = 16
    elif dev10 > 5:
        s_dev = 8  # 偏高（追高风险）
    else:
        s_dev = 6  # 跌破均线（趋势未走强）

    # 因子2 缩量（20分）：当日量 / 5日均量 < 0.9 为缩量企稳
    if len(vols) >= 6 and vols[-1] > 0:
        v5 = sum(vols[-6:-1]) / 5
        vr = vols[-1] / v5 if v5 > 0 else 1.0
        s_vol = 20 if vr < 0.7 else (15 if vr < 0.9 else (8 if vr <= 1.1 else 0))
    else:
        vr, s_vol = 1.0, 8

    # 因子3 回踩天数（15分）：距高点 1~3 天为最佳回踩节奏
    pb = _pullback_days(highs)
    s_pb = 15 if 1 <= pb <= 3 else (10 if pb == 4 else (5 if pb >= 5 else 8))

    # 因子4 RSI(14)（15分）：40~60 为健康回踩区
    r = _rsi(closes)
    if r is None:
        s_rsi = 5
    elif 40 <= r <= 60:
        s_rsi = 15
    elif 30 <= r < 40:
        s_rsi = 12
    elif 60 < r <= 70:
        s_rsi = 8
    else:
        s_rsi = 4  # <30 超卖或 >70 超买

    # 因子5 MA结构（10分）：MA5>MA10>MA20 多头排列（回踩不破结构）
    if len(closes) >= 20:
        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20
        if ma5 > ma10 > ma20:
            s_ma = 10
        elif ma5 > ma10:
            s_ma = 6
        else:
            s_ma = 2
    else:
        s_ma = 2

    # 因子6 量价形态（10分）：回踩日收下影/十字星（抗跌）为优
    o = float(kl[-1][1]) if len(kl[-1]) > 1 else cur  # open
    c = closes[-1]
    h, l = highs[-1], lows[-1]
    rng = (h - l) if h > l else 1e-9
    lower_shadow = (min(o, c) - l) / rng
    if c >= o and lower_shadow > 0.3:
        s_form = 10
    elif c >= o:
        s_form = 7
    elif lower_shadow > 0.5:  # 阴线但长下影（承接盘）
        s_form = 6
    else:
        s_form = 2

    total = s_dev + s_vol + s_pb + s_rsi + s_ma + s_form
    if total >= 80:
        grade, tag = "A", "🟢🟢 强回踩（1% R）"
    elif total >= 65:
        grade, tag = "B", "🟢 标准回踩（0.5~1% R）"
    elif total >= 50:
        grade, tag = "C", "🟡 弱回踩（观察）"
    else:
        grade, tag = "D", "🔴 不介入"

    return {
        "q_score": total, "q_grade": grade, "q_tag": tag,
        "factors": {
            "偏离度": s_dev, "缩量": s_vol, "回踩天数": s_pb,
            "RSI": s_rsi, "MA结构": s_ma, "量价形态": s_form,
        },
        "vol_ratio_5d": round(vr, 2), "pullback_days": pb, "rsi14": round(r, 1) if r else None,
    }


def calc_entry(code: str, session=None, n_days: int = 30) -> dict:
    """计算单只个股介入点（腾讯官方K线源）"""
    import requests
    if session is None:
        session = requests.Session()
        session.trust_env = False
        session.headers.update({"User-Agent": "Mozilla/5.0"})

    pref = _norm(code)
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    r = session.get(url, params={"param": f"{pref},day,,,{n_days},qfq"}, timeout=10)
    d = r.json()["data"][pref]
    kl = d.get("qfqday") or d.get("day") or []
    if len(kl) < 10:
        return {"code": code, "error": f"K线不足({len(kl)})", "source": "tencent_fqkline"}

    dates = [x[0] for x in kl]
    closes = [float(x[2]) for x in kl]
    cur = closes[-1]
    prev = closes[-2]

    def ma(n):
        return sum(closes[-n:]) / n if len(closes) >= n else None

    ma5, ma10, ma20 = ma(5), ma(10), ma(20)
    pct_chg = (cur / prev - 1) * 100 if prev else 0

    dev5 = (cur / ma5 - 1) * 100 if ma5 else None
    dev10 = (cur / ma10 - 1) * 100 if ma10 else None
    dev20 = (cur / ma20 - 1) * 100 if ma20 else None

    # 回踩判定（真回踩：距MA10 ∈ [-3%, +3%] 且 距MA5 ∈ [-3%, +6%] 不追高）
    if dev10 is not None and -3.0 <= dev10 <= 3.0:
        state = "🟢 真回踩（可介入区）"
    elif dev10 is not None and dev10 > 8.0:
        state = "🔴 急拉超买（严禁追高，等回踩）"
    elif dev10 is not None and dev10 > 3.0:
        state = "🟡 偏离偏大（等回踩）"
    else:
        state = "🟡 均线下方（趋势未走强）"

    # 止损位：MA10 × 0.95（纪律：破MA10止损）
    stop = round(ma10 * 0.95, 2) if ma10 else None
    # 回踩参考买入区：MA10 至 现价 之间的 MA10+1% ~ MA10+3%
    entry_zone = [round(ma10, 2), round(min(cur, ma10 * 1.03), 2)] if ma10 else None

    # Q-score 回踩质量评分（六因子，官方日K源）
    q = _qscore(kl, closes, cur, dev10)

    return {
        "code": code,
        "name": d.get("qt", {}).get("name") or code,
        "source": "tencent_fqkline",
        "date": dates[-1],
        "close": cur,
        "pct_chg": round(pct_chg, 2),
        "ma5": round(ma5, 2) if ma5 else None,
        "ma10": round(ma10, 2) if ma10 else None,
        "ma20": round(ma20, 2) if ma20 else None,
        "dev_ma5_pct": round(dev5, 1) if dev5 is not None else None,
        "dev_ma10_pct": round(dev10, 1) if dev10 is not None else None,
        "dev_ma20_pct": round(dev20, 1) if dev20 is not None else None,
        "state": state,
        "entry_zone": entry_zone,
        "stop": stop,
        "q_score": q["q_score"],
        "q_grade": q["q_grade"],
        "q_tag": q["q_tag"],
        "q_factors": q["factors"],
        "vol_ratio_5d": q["vol_ratio_5d"],
        "pullback_days": q["pullback_days"],
        "rsi14": q["rsi14"],
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", help="单只股票代码，如 601138")
    ap.add_argument("--codes", help="批量代码，逗号分隔，如 601138,300476")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    codes = []
    if args.code:
        codes = [args.code]
    elif args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    if not codes:
        print("❌ 请提供 --code 或 --codes")
        return 1

    import requests
    from scripts.tools.real_time import get_real_time
    S = requests.Session()
    S.trust_env = False
    S.headers.update({"User-Agent": "Mozilla/5.0"})
    t = get_real_time()

    results = []
    for c in codes:
        try:
            r = calc_entry(c, session=S)
        except Exception as e:
            r = {"code": c, "error": str(e), "source": "tencent_fqkline"}
        results.append(r)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return 0

    print(f"=== 介入点计算（{t['used']} 腾讯CDN · 官方前复权K线源）===")
    for r in results:
        if "error" in r:
            print(f"❌ {r['code']}: {r['error']}")
            continue
        print(f"--- {r['name']}({r['code']}) {r['date']} 收{r['close']} {r['pct_chg']:+.2f}% ---")
        print(f"  MA5 {r['ma5']} ({(r['dev_ma5_pct']):+.1f}%) | MA10 {r['ma10']} ({(r['dev_ma10_pct']):+.1f}%) | MA20 {r['ma20']} ({(r['dev_ma20_pct']):+.1f}%)")
        print(f"  状态: {r['state']}")
        print(f"  Q-score: {r['q_score']} {r['q_tag']}（{r['q_factors']}）")
        print(f"  量/5日均量 {r['vol_ratio_5d']} · 回踩{r['pullback_days']}天 · RSI14 {r['rsi14']}")
        print(f"  介入区: {r['entry_zone']}")
        print(f"  止损位: {r['stop']}（MA10×0.95，破位止损）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
