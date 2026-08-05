# -*- coding: utf-8 -*-
"""中报披露季跟踪（2026-08-05 用户要求）：
  ① 中报预约披露计划（Tushare disclosure_date，end_date=20260630）
  ② 今日/近 N 日预披露清单
  ③ 预期差判断：中报实际增速 vs 业绩预告区间（超预期/符合/不及预期）
  ④ 接入复盘流水线（每日自动）

用法:
  python scripts/tools/midreport_tracker.py --days 3      # 近3日披露+预期差
  python scripts/tools/midreport_tracker.py --code 688012  # 单只预期差
"""
import sys, os, argparse
from datetime import datetime, timedelta
from collections import Counter

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


def _rows(df):
    return df if isinstance(df, list) else df.to_dict("records")


def fetch_disclosure(end_date="20260630"):
    """中报披露计划。返回 [{ts_code, pre_date, actual_date}]。"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    try:
        df = pro.disclosure_date(end_date=end_date)
        return _rows(df)
    except Exception as e:
        print(f"[WARN] 披露计划失败: {e}")
        return []


def fetch_forecast(code):
    """单只业绩预告（中报期 end_date=20260630）。返回区间 dict 或 None。"""
    from scripts.tushare_pro_data import ts_forecast
    try:
        df = ts_forecast(ts_code=code + ".SH" if code.startswith("6") else code + ".SZ")
        rows = _rows(df)
        for r in rows:
            if str(r.get("end_date", "")) == "20260630":
                return {"type": r.get("type"),
                        "pmin": r.get("p_change_min"), "pmax": r.get("p_change_max")}
    except Exception:
        pass
    return None


def calc_expected_diff(code):
    """预期差：中报实际增速 vs 预告区间。中报未披露返回 {'status':'待披露'}。"""
    from scripts.tushare_pro_data import ts_income
    f = fetch_forecast(code)
    if not f or f.get("pmin") is None:
        return None
    try:
        ts = code + ".SH" if code.startswith("6") else code + ".SZ"
        # 中报实际（period=20260630）
        df = ts_income(ts_code=ts, period="20260630")
        rows = _rows(df)
        if not rows:
            return {"status": "中报待披露", "forecast": f"{f['pmin']}~{f['pmax']}%"}
        cur = float(rows[0].get("n_income_attr_p") or 0)
        # 去年同期（period=20250630）
        df2 = ts_income(ts_code=ts, period="20250630")
        rows2 = _rows(df2)
        if not rows2 or float(rows2[0].get("n_income_attr_p") or 0) == 0:
            return {"status": "去年同期缺失"}
        prev = float(rows2[0].get("n_income_attr_p") or 0)
        actual_chg = round((cur - prev) / abs(prev) * 100, 1)
        pmin, pmax = float(f["pmin"]), float(f["pmax"])
        if actual_chg > pmax:
            verdict = "🟢超预期"
        elif actual_chg < pmin:
            verdict = "🔴不及预期"
        else:
            verdict = "⚪符合预期"
        return {"type": f["type"], "forecast": f"{pmin}~{pmax}%",
                "actual_chg": actual_chg, "verdict": verdict}
    except Exception as e:
        return {"status": f"计算失败:{str(e)[:30]}"}


def fetch_consensus(code):
    """一致预期（问财：预测净利润中值/预测EPS，全年维度）。返回 dict 或 None。"""
    try:
        from scripts.market_api import api
        w = api.iwencai_query(f"{code} 一致预期净利润", limit=1)
        rows = w.get("data") or []
        if rows:
            c = rows[0].get("consensus") or {}
            if c:
                # 取预测净利润字段（如 预测净利润中值[20261231]）
                np_vals = {k: v for k, v in c.items() if "净利润" in str(k) and "中值" in str(k)}
                eps_vals = {k: v for k, v in c.items() if "每股收益" in str(k)}
                return {"net_profit_mid": next(iter(np_vals.values()), None),
                        "eps": next(iter(eps_vals.values()), None),
                        "raw": {str(k)[:30]: v for k, v in list(c.items())[:5]}}
    except Exception as e:
        return {"error": str(e)[:40]}
    return None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="近 N 日披露")
    ap.add_argument("--code", help="单只预期差")
    args = ap.parse_args()

    if args.code:
        print(f"=== {args.code} 预期差 + 一致预期 ===")
        d = calc_expected_diff(args.code)
        f = fetch_forecast(args.code)
        c = fetch_consensus(args.code)
        print(f"  业绩预告: {f}")
        print(f"  预期差: {d}")
        if c:
            print(f"  一致预期(问财): 2026预测净利中值={c.get('net_profit_mid')} 预测EPS={c.get('eps')}")
            if c.get("raw"):
                print(f"    {c['raw']}")
        return 0

    disc = fetch_disclosure()
    if not disc:
        print("⚠️ 披露计划不可用")
        return 0
    today = datetime.now()
    window = (today - timedelta(days=args.days - 1)).strftime("%Y%m%d")
    due = sorted([r for r in disc
                  if str(r.get("pre_date", "")) >= window
                  and str(r.get("pre_date", "")) <= today.strftime("%Y%m%d")],
                 key=lambda r: str(r.get("pre_date", "")))

    print(f"=== 中报披露季跟踪（{window}~今日，共 {len(due)} 只预披露）===")
    # 分组按日期
    by_date = {}
    for r in due:
        d = str(r.get("pre_date", ""))
        by_date.setdefault(d, []).append(r)
    for d in sorted(by_date.keys()):
        print(f"\n[{d}] {len(by_date[d])} 只")
        for r in by_date[d][:20]:
            code = str(r.get("ts_code", "")).split(".")[0]
            print(f"  {r.get('ts_code')}")

    # 今日披露的预期差（最多 8 只，避免 Tushare 限流）
    print("\n[今日预披露预期差（样例）]")
    today_due = by_date.get(today.strftime("%Y%m%d"), [])
    for r in today_due[:8]:
        code = str(r.get("ts_code", "")).split(".")[0]
        d = calc_expected_diff(code)
        if d:
            print(f"  {r.get('ts_code')}: 预告[{d['type']} {d['forecast']}] 实际{d['actual_chg']}% → {d['verdict']}")
        else:
            print(f"  {r.get('ts_code')}: （无预告或无中报数据）")

    # 写文件
    dstr = today.strftime("%Y-%m-%d")
    outdir = os.path.join(_PROJECT_ROOT, "reports", "daily", dstr)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"midreport_{today.strftime('%H%M')}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# 中报披露季跟踪 — {dstr}\n\n")
        for d in sorted(by_date.keys()):
            f.write(f"\n## {d}\n")
            for r in by_date[d][:30]:
                f.write(f"- {r.get('ts_code')}\n")
    print(f"\n[已写入] {os.path.relpath(out, _PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
