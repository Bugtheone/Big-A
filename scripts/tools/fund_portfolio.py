#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公募基金重仓股洞察工具（tushare fund_portfolio）

按报告期拉取全市场基金十大重仓，按股票聚合出**机构抱团方向**：
  - 被最多基金重仓的股票（基金只数）
  - 机构持仓市值 TOP（重仓市值）
  - 与国家队直接持仓（state_team_scan.py）联动提示

数据源：Tushare fund_portfolio（period 按报告期全市场）+ fund_basic（基金名）。
用法:
  python scripts/tools/fund_portfolio.py                    # 最近报告期
  python scripts/tools/fund_portfolio.py --period 20260331  # 指定报告期
  python scripts/tools/fund_portfolio.py --top 30           # TOP N（默认 20）
输出: stdout Markdown + reports/raw/fund_portfolio_<period>.md
"""
import io
import os
import sys
from collections import defaultdict
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from scripts.tushare_api import get_pro  # noqa: E402


def _fetch_portfolio(pro, period: str, limit: int = 5000) -> list:
    """分页拉取指定报告期全市场基金持仓。"""
    rows, offset = [], 0
    while True:
        df = pro.fund_portfolio(period=period, limit=limit, offset=offset)
        if df is None or df.empty:
            break
        batch = df.to_dict("records")
        rows.extend(batch)
        offset += limit
        if len(batch) < limit or offset > 200000:
            break
    return rows


def main() -> int:
    args = sys.argv[1:]
    period_arg, top_n = None, 20
    for i, a in enumerate(args):
        if a == "--period" and i + 1 < len(args):
            period_arg = args[i + 1]
        elif a == "--top" and i + 1 < len(args):
            top_n = int(args[i + 1])

    pro = get_pro()
    # 探测最近报告期（从新到旧）
    candidates = ["20260331", "20251231", "20250930", "20250630",
                  "20241231", "20240930", "20240630", "20240331"]
    period = period_arg
    if period is None:
        for p in candidates:
            df = pro.fund_portfolio(period=p, limit=1)
            if df is not None and len(df):
                period = p
                break
    print(f"报告期: {period}（拉取全市场基金持仓...）")
    rows = _fetch_portfolio(pro, period)
    if not rows:
        print("无数据")
        return 1
    print(f"  持仓记录 {len(rows)} 条")

    # 按股票聚合
    agg = defaultdict(lambda: {"funds": set(), "mv": 0.0, "ratio": 0.0})
    for r in rows:
        sym, mv, ratio = r.get("symbol"), r.get("mkv") or 0, r.get("stk_mkv_ratio") or 0
        if not sym:
            continue
        a = agg[sym]
        a["funds"].add(r.get("ts_code"))
        a["mv"] += float(mv)
        a["ratio"] += float(ratio)

    # 名称
    name_map = {}
    try:
        df = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry")
        name_map = {r["ts_code"]: (r.get("name"), r.get("industry")) for r in df.to_dict("records")}
    except Exception:
        pass

    fund_count = {k: len(v["funds"]) for k, v in agg.items()}
    by_funds = sorted(agg.items(), key=lambda kv: -len(kv[1]["funds"]))[:top_n]
    by_mv = sorted(agg.items(), key=lambda kv: -kv[1]["mv"])[:top_n]

    L = [f"# 公募基金重仓股洞察（报告期 {period}）",
         "", f"> 生成：{datetime.now():%Y-%m-%d %H:%M}｜数据源：Tushare fund_portfolio 全市场",
         f"> 持仓记录 {len(rows)} 条 / 重仓股票 {len(agg)} 只", "",
         "## 一、机构抱团 TOP（被最多基金重仓）", "",
         "| 排名 | 代码 | 名称 | 行业 | 基金只数 | 持仓市值(亿) |",
         "|---|---|---|---|---:|---:|"]
    for i, (sym, a) in enumerate(by_funds, 1):
        nm, ind = name_map.get(sym, (sym, "—"))
        L.append(f"| {i} | {sym} | {nm} | {ind or '—'} | {len(a['funds'])} | {a['mv']/1e8:.1f} |")
    L += ["", "## 二、机构持仓市值 TOP（重仓市值）", "",
          "| 排名 | 代码 | 名称 | 行业 | 基金只数 | 持仓市值(亿) |",
          "|---|---|---|---|---:|---:|"]
    for i, (sym, a) in enumerate(by_mv, 1):
        nm, ind = name_map.get(sym, (sym, "—"))
        L.append(f"| {i} | {sym} | {nm} | {ind or '—'} | {len(a['funds'])} | {a['mv']/1e8:.1f} |")
    L += ["", "## 三、联动提示", "",
          "> 国家队**直接**持仓（top10 股东）见 `state_team_scan.py`（汇金/证金/社保新进）；",
          "> 本工具为公募基金重仓（机构抱团方向），两者结合 = 机构/国家队资金全景。"]

    text = "\n".join(L)
    print("\n" + text)
    outdir = os.path.join(_PROJECT_ROOT, "reports", "raw")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"fund_portfolio_{period}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(f"\n[已写入] {os.path.relpath(out, _PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
