#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""趋势跟踪策略量化工具（T-score 状态机，官方K线源，禁止估算）

纪律（2026-08-06 固化）：
- 趋势状态与分数一律用腾讯官方前复权日K接口计算
- 禁止用记忆/估算判定趋势；本工具是趋势跟踪策略的唯一量化来源

T-score 六因子（0~100）：
  ① MA排列(25) ② 价格位置(20) ③ 均线斜率(15) ④ 回撤深度(15) ⑤ 动量ROC(15) ⑥ 量能配合(10)
分级：
  ≥80 🟢🟢 强多头（主升持有）· 65~79 🟢 多头（持有）
  50~64 🟡 震荡偏多（回踩介入）· 35~49 🔴 偏空（减仓）
  <35  🔴🔴 空头（空仓）

状态机（连续判定）：
  强多头 → 多头 → 震荡偏多 → 偏空 → 空头 →（趋势反转重新确认）

用法：
  python scripts/tools/trend_tracker.py --code 601138
  python scripts/tools/trend_tracker.py --codes 601138,300476,000977 --json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def _norm(code: str) -> str:
    c = code.strip().upper()
    if c.startswith(("SH", "SZ", "BJ")):
        c = c[2:]
    if c.startswith(("6", "9")):
        return "sh" + c
    return "sz" + c


def _fetch_kline(session, pref, n_days=90):
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    r = session.get(url, params={"param": f"{pref},day,,,{n_days},qfq"}, timeout=10)
    d = r.json()["data"][pref]
    kl = d.get("qfqday") or d.get("day") or []
    if len(kl) < 20:
        raise ValueError(f"K线不足({len(kl)})")
    return kl


def calc_trend(code: str, session=None) -> dict:
    """计算单只标的趋势状态与 T-score"""
    import requests
    if session is None:
        session = requests.Session()
        session.trust_env = False
        session.headers.update({"User-Agent": "Mozilla/5.0"})

    pref = _norm(code)
    kl = _fetch_kline(session, pref)
    closes = [float(x[2]) for x in kl]
    vols = [float(x[5]) for x in kl]
    highs = [float(x[3]) for x in kl]
    cur = closes[-1]

    def ma(n):
        return sum(closes[-n:]) / n

    ma5, ma10, ma20, ma60 = ma(5), ma(10), ma(20), ma(60)
    # 均线斜率：MA20 近5日变化
    ma20_prev = sum(closes[-25:-5]) / 20
    slope20 = (ma20 / ma20_prev - 1) * 100

    # 因子1 MA排列（25分）
    ma_bull = ma5 > ma10 > ma20 > ma60
    ma_bull_3 = ma5 > ma10 > ma20
    if ma_bull:
        s_ma = 25
    elif ma_bull_3:
        s_ma = 19
    elif ma5 > ma10:
        s_ma = 10
    elif ma10 > ma20:
        s_ma = 6
    else:
        s_ma = 0

    # 因子2 价格位置（20分）：站上几条均线
    above = sum(1 for m in (ma5, ma10, ma20, ma60) if cur > m)
    s_pos = above * 5  # 0~20

    # 因子3 均线斜率（15分）：MA20 向上为正趋势
    if slope20 > 0.3:
        s_slope = 15
    elif slope20 > 0:
        s_slope = 10
    elif slope20 > -0.3:
        s_slope = 5
    else:
        s_slope = 0

    # 因子4 回撤深度（15分）：距60日高点
    high60 = max(highs[-60:])
    drawdown = (high60 - cur) / high60 * 100
    if drawdown < 5:
        s_dd = 15
    elif drawdown < 10:
        s_dd = 11
    elif drawdown < 15:
        s_dd = 7
    elif drawdown < 25:
        s_dd = 3
    else:
        s_dd = 0

    # 因子5 动量 ROC(10日)（15分）
    if len(closes) >= 11:
        roc10 = (cur / closes[-11] - 1) * 100
    else:
        roc10 = 0
    if roc10 > 15:
        s_mom = 15
    elif roc10 > 5:
        s_mom = 12
    elif roc10 > 0:
        s_mom = 8
    elif roc10 > -5:
        s_mom = 4
    else:
        s_mom = 0

    # 因子6 量能配合（10分）：5日均量 > 20日均量（放量趋势）
    v5 = sum(vols[-5:]) / 5
    v20 = sum(vols[-20:]) / 20
    vr = v5 / v20 if v20 > 0 else 1.0
    if vr > 1.3:
        s_vol = 10
    elif vr > 1.1:
        s_vol = 7
    elif vr > 0.9:
        s_vol = 4
    else:
        s_vol = 0

    total = s_ma + s_pos + s_slope + s_dd + s_mom + s_vol
    if total >= 80:
        grade, state, tag = "A", "强多头", "🟢🟢 主升持有"
    elif total >= 65:
        grade, state, tag = "B", "多头", "🟢 持有"
    elif total >= 50:
        grade, state, tag = "C", "震荡偏多", "🟡 回踩介入"
    elif total >= 35:
        grade, state, tag = "D", "偏空", "🔴 减仓"
    else:
        grade, state, tag = "E", "空头", "🔴🔴 空仓"

    return {
        "code": code, "source": "tencent_fqkline", "date": kl[-1][0],
        "close": round(cur, 2),
        "ma5": round(ma5, 2), "ma10": round(ma10, 2),
        "ma20": round(ma20, 2), "ma60": round(ma60, 2),
        "slope20_pct": round(slope20, 2),
        "drawdown_60d_pct": round(drawdown, 1),
        "roc10_pct": round(roc10, 1),
        "vol_5d_over_20d": round(vr, 2),
        "t_score": total, "t_grade": grade, "state": state, "tag": tag,
        "factors": {"MA排列": s_ma, "价格位置": s_pos, "均线斜率": s_slope,
                    "回撤深度": s_dd, "动量ROC": s_mom, "量能配合": s_vol},
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", help="单只代码，如 601138")
    ap.add_argument("--codes", help="批量代码，逗号分隔")
    ap.add_argument("--json", action="store_true")
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
            results.append(calc_trend(c, session=S))
        except Exception as e:
            results.append({"code": c, "error": str(e)})

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return 0

    print(f"=== 趋势跟踪 T-score（{t['used']} 腾讯CDN · 官方前复权K线源）===")
    for r in results:
        if "error" in r:
            print(f"❌ {r['code']}: {r['error']}")
            continue
        print(f"--- {r['code']} {r['date']} 收{r['close']} ---")
        print(f"  MA5 {r['ma5']} | MA10 {r['ma10']} | MA20 {r['ma20']} | MA60 {r['ma60']}")
        print(f"  T-score {r['t_score']} {r['tag']}（{r['state']}）")
        print(f"  斜率MA20 {r['slope20_pct']}% · 回撤 {r['drawdown_60d_pct']}% · ROC10 {r['roc10_pct']}% · 量能 {r['vol_5d_over_20d']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
