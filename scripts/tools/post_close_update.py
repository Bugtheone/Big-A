# -*- coding: utf-8 -*-
"""盘后复核更新 — 复盘每次执行时重新拉取 Tushare 官方数据，复核并更新收盘总结。

背景（2026-08-05 用户要求）：复盘每次执行都要重新更新数据，不沿用盘中定格。
流程：
  ① 拉 Tushare 当日 7 大指数收盘（盘后 17:00+ 已刷新，官方口径）
  ② 与腾讯收盘定格对比（误差标注，>0.3pt 复核）
  ③ 更新 reports/daily/<日期>/closing_summary_<日期>.md（追加 Tushare 复核章节）
  ④ 写 post_close_verify_<日期>.md

用法:
  python scripts/tools/post_close_update.py            # 复盘后自动调用
  python scripts/tools/post_close_update.py --date 20260805  # 指定日期
"""
import sys, os, json
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

_IDX = {"000001.SH": "上证指数", "399001.SZ": "深证成指", "399006.SZ": "创业板指",
        "000688.SH": "科创50", "000016.SH": "上证50", "000300.SH": "沪深300",
        "000852.SH": "中证1000"}


def _rows(df):
    return df if isinstance(df, list) else df.to_dict("records")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y%m%d"), help="YYYYMMDD")
    args = ap.parse_args()
    date_s = args.date
    dstr = f"{date_s[:4]}-{date_s[4:6]}-{date_s[6:]}"

    from scripts.tools.real_time import get_real_time
    from scripts.data_gate import gate
    from scripts.market_api import api

    t = get_real_time()
    print(f"[post_close] 真实时间 {t['used']} 复核日期 {dstr}")

    # ① Tushare 当日收盘
    ts = {}
    for code, nm in _IDX.items():
        try:
            rows = _rows(gate.ts_index_daily(ts_code=code, start=date_s, end=date_s))
            if rows:
                r = rows[0]
                ts[nm] = {"close": float(r["close"]), "pct": r.get("pct_chg")}
        except Exception as e:
            print(f"  [WARN] {nm} Tushare 失败: {str(e)[:40]}")
    if not ts:
        print(f"⚠️ Tushare 当日数据未刷新（{dstr}），跳过复核（盘后 17:00 后重试）")
        return 0

    # ② 腾讯收盘定格对比（仅当日有效——腾讯接口只给当前实时，跨日无法取历史定格）
    today = datetime.now().strftime("%Y%m%d")
    is_today = date_s == today
    tz = {s["name"]: s for s in api.index_snapshot()} if is_today else {}
    verify_lines = ["## Tushare 官方复核（复盘时重新拉取）", ""]
    verify_lines.append("| 指数 | Tushare 收盘 | 腾讯定格 | 误差 |")
    verify_lines.append("|---|---:|---:|---:|")
    mism = 0
    for nm in _IDX.values():
        s = ts.get(nm)
        q = tz.get(nm) if is_today else None
        if s and q:
            diff = round(abs(s["close"] - q["price"]), 2)
            mark = "✅" if diff <= 0.3 else "⚠️"
            if diff > 0.3:
                mism += 1
            verify_lines.append(f"| {nm} | {s['close']} | {q['price']} | {mark} {diff} |")
        elif s:
            note = "（非当日，无腾讯定格）" if not is_today else "腾讯无"
            verify_lines.append(f"| {nm} | {s['close']} | — | {note} |")
    verify_lines.append("")
    verify_lines.append(f"> 复核时间：{t['used']}（腾讯 CDN）· 误差>0.3pt 计数：{mism}")

    # ③ 更新 closing_summary
    outdir = os.path.join(_PROJECT_ROOT, "reports", "daily", dstr)
    os.makedirs(outdir, exist_ok=True)
    summary_path = os.path.join(outdir, f"closing_summary_{date_s}.md")
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            src = f.read()
        # 移除旧复核章节（若存在）后追加新复核
        idx = src.find("## Tushare 官方复核")
        if idx != -1:
            src = src[:idx].rstrip() + "\n\n"
        src += "\n".join(verify_lines) + "\n"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"✅ 已更新 {os.path.relpath(summary_path, _PROJECT_ROOT)}")
    else:
        print(f"⚠️ 未找到 {summary_path}（跳过更新）")

    # ④ 写复核文件
    out = os.path.join(outdir, f"post_close_verify_{date_s}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# 盘后复核 — {dstr}\n\n" + "\n".join(verify_lines) + "\n")
    print(f"✅ 复核报告: {os.path.relpath(out, _PROJECT_ROOT)}")
    return 0 if mism == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
