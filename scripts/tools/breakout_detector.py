#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""突破交易策略量化工具（B-score，官方K线源，禁止估算）

纪律（2026-08-06 固化）：
- 突破判定一律用腾讯官方前复权日K接口计算
- 禁止凭感觉判断"是否突破"；本工具是突破交易策略的唯一量化来源

B-score 六因子（0~100）：
  ① 突破幅度(25) ② 量能爆发(25) ③ 平台整理(15) ④ 趋势方向(15) ⑤ 回踩确认(10) ⑥ 位置安全(10)
分级：
  ≥75 🟢🟢 A级 真突破（可追）· 60~74 🟢 B级 有效突破（回踩介入）
  45~59 🟡 C级 弱突破（观察）· <45 🔴 D级 假突破/追高（禁止）

用法：
  python scripts/tools/breakout_detector.py --code 601138
  python scripts/tools/breakout_detector.py --codes 601138,300476 --json
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
    if len(kl) < 25:
        raise ValueError(f"K线不足({len(kl)})")
    return kl


def calc_breakout(code: str, session=None) -> dict:
    """计算单只标的是否构成有效突破（B-score）"""
    import requests
    if session is None:
        session = requests.Session()
        session.trust_env = False
        session.headers.update({"User-Agent": "Mozilla/5.0"})

    pref = _norm(code)
    kl = _fetch_kline(session, pref)
    closes = [float(x[2]) for x in kl]
    highs = [float(x[3]) for x in kl]
    vols = [float(x[5]) for x in kl]
    cur = closes[-1]

    # 前 20 日高点（不含今日，作突破基准）
    high20_prev = max(highs[-21:-1])
    breakout_pct = (cur / high20_prev - 1) * 100

    # 因子1 突破幅度（25分）
    if breakout_pct > 3:
        s_amp = 25
    elif breakout_pct > 1:
        s_amp = 20
    elif breakout_pct > 0:
        s_amp = 14
    elif breakout_pct > -2:
        s_amp = 6  # 未突破
    else:
        s_amp = 0

    # 因子2 量能爆发（25分）：今日量 vs 5日均量
    v5 = sum(vols[-6:-1]) / 5
    vr = vols[-1] / v5 if v5 > 0 else 1.0
    if vr > 2.0:
        s_vol = 25
    elif vr > 1.5:
        s_vol = 20
    elif vr > 1.2:
        s_vol = 14
    elif vr > 1.0:
        s_vol = 8
    else:
        s_vol = 0  # 缩量突破 = 假突破高概率

    # 因子3 平台整理（15分）：此前横盘时间（波动收敛）
    recent = closes[-11:-1]
    spread = (max(recent) - min(recent)) / min(recent) * 100 if min(recent) > 0 else 99
    if spread < 8:
        s_plat = 15  # 窄幅整理充分
    elif spread < 12:
        s_plat = 10
    elif spread < 20:
        s_plat = 5
    else:
        s_plat = 0  # 波动大非平台

    # 因子4 趋势方向（15分）：MA20 斜率
    ma20 = sum(closes[-20:]) / 20
    ma20_prev = sum(closes[-25:-5]) / 20
    slope20 = (ma20 / ma20_prev - 1) * 100 if ma20_prev else 0
    if slope20 > 0.3:
        s_tr = 15
    elif slope20 > 0:
        s_tr = 10
    elif slope20 > -0.3:
        s_tr = 5
    else:
        s_tr = 0

    # 因子5 回踩确认（10分）：突破后是否回踩不破
    if len(closes) >= 4:
        c3 = closes[-4]  # 3 日前收盘
        c_now = closes[-1]
        if c_now >= max(closes[-4:-1]) or c3 >= high20_prev * 0.98:
            s_conf = 10  # 站稳突破位
        elif c_now > high20_prev:
            s_conf = 6
        else:
            s_conf = 2  # 跌回突破位下方
    else:
        s_conf = 5

    # 因子6 位置安全（10分）：距 60 日高点回撤 <15% 的突破更可信
    high60 = max(highs[-60:])
    drawdown = (high60 - cur) / high60 * 100
    if drawdown < 5:
        s_safe = 10  # 创新高附近
    elif drawdown < 15:
        s_safe = 7
    elif drawdown < 30:
        s_safe = 3
    else:
        s_safe = 0  # 深跌后反弹突破（超跌反弹性质）

    total = s_amp + s_vol + s_plat + s_tr + s_conf + s_safe
    if total >= 75:
        grade, tag = "A", "🟢🟢 真突破（可追）"
    elif total >= 60:
        grade, tag = "B", "🟢 有效突破（回踩介入）"
    elif total >= 45:
        grade, tag = "C", "🟡 弱突破（观察）"
    else:
        grade, tag = "D", "🔴 假突破/追高（禁止）"

    return {
        "code": code, "source": "tencent_fqkline", "date": kl[-1][0],
        "close": round(cur, 2),
        "high20_prev": round(high20_prev, 2),
        "breakout_pct": round(breakout_pct, 1),
        "vol_ratio_1d": round(vr, 2),
        "platform_spread_pct": round(spread, 1),
        "slope20_pct": round(slope20, 2),
        "drawdown_60d_pct": round(drawdown, 1),
        "b_score": total, "b_grade": grade, "tag": tag,
        "factors": {"突破幅度": s_amp, "量能爆发": s_vol, "平台整理": s_plat,
                    "趋势方向": s_tr, "回踩确认": s_conf, "位置安全": s_safe},
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", help="单只代码")
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
            results.append(calc_breakout(c, session=S))
        except Exception as e:
            results.append({"code": c, "error": str(e)})

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return 0

    print(f"=== 突破交易 B-score（{t['used']} 腾讯CDN · 官方前复权K线源）===")
    for r in results:
        if "error" in r:
            print(f"❌ {r['code']}: {r['error']}")
            continue
        print(f"--- {r['code']} {r['date']} 收{r['close']} ---")
        print(f"  B-score {r['b_score']} {r['tag']}")
        print(f"  突破20日高{r['high20_prev']} ({(r['breakout_pct']):+.1f}%) · 量比{r['vol_ratio_1d']} · 平台波幅{r['platform_spread_pct']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
