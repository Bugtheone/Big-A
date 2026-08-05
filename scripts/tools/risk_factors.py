# -*- coding: utf-8 -*-
"""个股风险因子（2026-08-05 P2 落地）：
  ① 质押率（Tushare pledge_stat 最新，>30% 高风险）
  ② 减持（Tushare stk_holdertrade 近90日，DE=减持预警）
  ③ 停牌检测（腾讯行情量=0）
  供 market_filter --risk 集成（选股排除/标记风险）。

用法:
  python scripts/tools/risk_factors.py --code 000977     # 单只
  python scripts/tools/risk_factors.py --codes 000977,603019
"""
import sys, os, argparse
from datetime import datetime, timedelta

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


def _rows(df):
    return df if isinstance(df, list) else df.to_dict("records")


def check_pledge(code):
    """最新质押率。返回 {ratio, date} 或 None。"""
    try:
        from scripts.tushare_pro_data import ts_pledge_stat
        ts = code + ".SH" if code.startswith("6") else code + ".SZ"
        df = ts_pledge_stat(ts_code=ts)
        rows = _rows(df)
        if rows:
            r = rows[0]
            return {"ratio": round(float(r.get("pledge_ratio") or 0), 1),
                    "date": str(r.get("end_date", ""))[:10]}
    except Exception:
        pass
    return None


def check_reduce(code, days=90):
    """近 N 日减持（DE=减持）。返回 (次数, 最新日期) 或 None。"""
    try:
        from scripts.tushare_pro_data import ts_stk_holdertrade
        ts = code + ".SH" if code.startswith("6") else code + ".SZ"
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        df = ts_stk_holdertrade(ts_code=ts, start=start, end=datetime.now().strftime("%Y%m%d"))
        rows = _rows(df)
        reduces = [r for r in rows if r.get("in_de") == "DE"]
        if reduces:
            return {"count": len(reduces),
                    "latest": str(reduces[0].get("ann_date", ""))[:10],
                    "names": [r.get("holder_name") for r in reduces[:3]]}
    except Exception:
        pass
    return None


def check_suspend(S, code):
    """腾讯行情检测停牌（成交量=0 且现价==昨收近似）。"""
    pref = ("sh" if code.startswith(("6", "9")) else "sz") + code
    try:
        r = S.get(f"https://qt.gtimg.cn/q={pref}", timeout=8)
        r.encoding = "gbk"
        f = r.text.split('"')[1].split("~")
        if len(f) > 6:
            vol = float(f[6]) if f[6] else 0
            return vol == 0
    except Exception:
        pass
    return None


def check_risk(S, code):
    """综合风险因子。"""
    p = check_pledge(code)
    rd = check_reduce(code)
    sp = check_suspend(S, code)
    risks = []
    if sp:
        risks.append("🛑停牌")
    if p and p["ratio"] > 30:
        risks.append(f"⚠️质押{p['ratio']}%")
    if rd and rd["count"] > 0:
        risks.append(f"⚠️近90日减持{rd['count']}次({','.join(rd['names'][:2])})")
    return {"code": code, "pledge": p, "reduce": rd, "suspend": sp,
            "risk": "/".join(risks) if risks else "✅正常"}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", help="单只")
    ap.add_argument("--codes", help="逗号分隔批量")
    args = ap.parse_args()

    import requests
    S = requests.Session(); S.trust_env = False
    S.headers.update({"User-Agent": "Mozilla/5.0"})
    from scripts.tools.real_time import get_real_time
    t = get_real_time()
    print(f"=== 个股风险因子（{t['used']} 腾讯CDN）===")

    codes = []
    if args.code:
        codes = [args.code]
    elif args.codes:
        codes = args.codes.split(",")
    else:
        print("用法: --code 000977 或 --codes 000977,603019")
        return 1

    for c in codes:
        r = check_risk(S, c)
        print(f"\n{c}: {r['risk']}")
        if r["pledge"]:
            print(f"  质押率: {r['pledge']['ratio']}%（{r['pledge']['date']}）")
        if r["reduce"]:
            print(f"  减持: {r['reduce']['count']}次（最近{r['reduce']['latest']}）")
        if r["suspend"]:
            print(f"  状态: 疑似停牌（量=0）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
