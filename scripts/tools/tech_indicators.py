# -*- coding: utf-8 -*-
"""技术指标库 + 估值历史分位（2026-08-05 P0 落地）：
  ① 技术指标：RSI(14)/MACD(12,26,9)/KDJ(9)/BOLL(20,2)/ATR(14)——本地 K 线计算
  ② 估值历史分位：PE/PB 近 N 日百分位（Tushare daily_basic 历史）

用法:
  python scripts/tools/tech_indicators.py --code 000977       # 单只指标+估值分位
  python scripts/tools/tech_indicators.py --code 000977 --json
"""
import sys, os, argparse, math

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


def _rows(df):
    return df if isinstance(df, list) else df.to_dict("records")


# ── ① 技术指标 ────────────────────────────────────────────
def ema(vals, n):
    k = 2 / (n + 1)
    e = vals[0]
    out = [e]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def rsi(closes, n=14):
    """RSI(14)。"""
    if len(closes) <= n:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[-n:]) / n
    al = sum(losses[-n:]) / n
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 1)


def macd(closes, fast=12, slow=26, signal=9):
    """MACD(12,26,9)：返回 (dif, dea, hist)。"""
    if len(closes) < slow + signal:
        return None
    ef = ema(closes, fast)
    es = ema(closes, slow)
    dif = [a - b for a, b in zip(ef, es)]
    dea = ema(dif, signal)
    hist = (dif[-1] - dea[-1]) * 2
    return round(dif[-1], 3), round(dea[-1], 3), round(hist, 3)


def kdj(closes, highs, lows, n=9):
    """KDJ(9,3,3)。"""
    if len(closes) < n:
        return None
    k, d = 50.0, 50.0
    for i in range(len(closes) - n, len(closes)):
        hh = max(highs[i - n + 1:i + 1])
        ll = min(lows[i - n + 1:i + 1])
        if hh == ll:
            continue
        rsv = (closes[i] - ll) / (hh - ll) * 100
        k = 2 / 3 * k + 1 / 3 * rsv
        d = 2 / 3 * d + 1 / 3 * k
    j = 3 * k - 2 * d
    return round(k, 1), round(d, 1), round(j, 1)


def boll(closes, n=20, k=2.0):
    """BOLL(20,2)。"""
    if len(closes) < n:
        return None
    mid = sum(closes[-n:]) / n
    var = sum((c - mid) ** 2 for c in closes[-n:]) / n
    std = math.sqrt(var)
    return round(mid, 2), round(mid + k * std, 2), round(mid - k * std, 2)


def atr(highs, lows, closes, n=14):
    """ATR(14)。"""
    if len(closes) < n + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    return round(sum(trs[-n:]) / n, 2)


def calc_indicators(closes, highs, lows):
    """综合指标。"""
    return {
        "RSI(14)": rsi(closes),
        "MACD": macd(closes),
        "KDJ": kdj(closes, highs, lows),
        "BOLL": boll(closes),
        "ATR(14)": atr(highs, lows, closes),
    }


# ── ② 估值历史分位 ────────────────────────────────────────
def pe_pb_percentile(code, days=250):
    """PE/PB 近 N 日历史分位（Tushare daily_basic）。返回 {pe_pct, pb_pct, cur_pe, cur_pb}。"""
    from scripts.tushare_pro_data import ts_daily_basic
    ts = code + ".SH" if code.startswith("6") else code + ".SZ"
    try:
        from datetime import datetime, timedelta
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=int(days * 1.5))).strftime("%Y%m%d")
        df = ts_daily_basic(ts_code=ts, start=start, end=end)
        rows = _rows(df)
        # 按日期降序（最新在前）
        pes = [float(r["pe_ttm"]) for r in rows if r.get("pe_ttm")]
        pbs = [float(r["pb"]) for r in rows if r.get("pb")]
        if not pes or not pbs:
            return None

        def pct(val, arr):
            below = sum(1 for x in arr if x <= val)
            return round(below / len(arr) * 100, 1)

        return {"cur_pe": round(pes[0], 1), "pe_pct": pct(pes[0], pes[:days]),
                "cur_pb": round(pbs[0], 2), "pb_pct": pct(pbs[0], pbs[:days]),
                "n": min(len(pes), days)}
    except Exception as e:
        return {"error": str(e)[:50]}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    from scripts.tools.real_time import get_real_time
    import requests
    S = requests.Session(); S.trust_env = False
    S.headers.update({"User-Agent": "Mozilla/5.0"})
    t = get_real_time()
    pref = ("sh" if args.code.startswith(("6", "9")) else "sz") + args.code

    # K 线（70 日）
    try:
        r = S.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                  params={"param": f"{pref},day,,,70,qfq"}, timeout=8)
        d = r.json()["data"][pref]
        kl = d.get("qfqday") or d.get("day") or []
        closes = [float(x[2]) for x in kl]
        highs = [float(x[3]) for x in kl]
        lows = [float(x[4]) for x in kl]
        if len(closes) < 25:
            print(f"⚠️ {args.code} K线不足（{len(closes)}）")
            return 1
    except Exception as e:
        print(f"❌ K线拉取失败: {e}")
        return 1

    ind = calc_indicators(closes, highs, lows)
    val = pe_pb_percentile(args.code)

    print(f"=== {args.code} 技术指标+估值分位（{t['used']} 腾讯CDN）===")
    print(f"  现价: {closes[-1]}")
    if ind["RSI(14)"] is not None:
        r = ind["RSI(14)"]
        tag = "超买⚠️" if r > 70 else ("超卖🟢" if r < 30 else "中性")
        print(f"  RSI(14): {r} {tag}")
    m = ind["MACD"]
    if m:
        tag = "金叉🟢" if m[0] > m[1] else "死叉🔴"
        print(f"  MACD: DIF={m[0]} DEA={m[1]} 柱={m[2]} {tag}")
    k = ind["KDJ"]
    if k:
        print(f"  KDJ: K={k[0]} D={k[1]} J={k[2]}" + ("超买⚠️" if k[0] > 80 else ""))
    b = ind["BOLL"]
    if b:
        pos = "上轨附近" if closes[-1] > b[1] * 0.98 else ("下轨附近🟢" if closes[-1] < b[2] * 1.02 else "中轨区")
        print(f"  BOLL: 中{b[0]} 上{b[1]} 下{b[2]} {pos}")
    a = ind["ATR(14)"]
    if a:
        print(f"  ATR(14): {a}（止损参考 {round(closes[-1] - 2*a, 2)}）")
    if val and "error" not in val:
        print(f"  PE_TTM: {val['cur_pe']}（近{val['n']}日分位 {val['pe_pct']}%）" +
              ("低位🟢" if val["pe_pct"] < 20 else ("高位⚠️" if val["pe_pct"] > 80 else "中位")))
        print(f"  PB: {val['cur_pb']}（近{val['n']}日分位 {val['pb_pct']}%）")
    elif val and "error" in val:
        print(f"  估值分位: 不可用（{val['error']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
