#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国家队新进前十股东筛选工具（tushare 版）

对比最近两个报告期，筛选"最新一期新进入前十股东、而上一期没有"的国家队机构
（中央汇金/中国证金/社保基金）。数据源：Tushare top10_holders 全市场，
不依赖东财网页/PDF（借鉴 east-money-information 逻辑，数据源更稳）。

用法:
  python scripts/tools/state_team_scan.py                 # 自动探测最近两期
  python scripts/tools/state_team_scan.py --period 20260630  # 指定最新期（上一期自动回退）
  python scripts/tools/state_team_scan.py --all-mv        # 不筛市值（默认全量输出）

输出: stdout Markdown 表 + reports/raw/state_team_<period>.md
"""
import io
import os
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from scripts.tushare_api import get_pro  # noqa: E402

# 国家队机构关键词（含汇金/证金/社保及常见变体）
_STATE_TEAM_KW = ("汇金", "证金", "社会保障", "社保基金", "全国社保")


def _fetch_holders(pro, period: str, limit: int = 5000) -> list:
    """分页拉取指定报告期全市场十大股东。"""
    rows, offset = [], 0
    while True:
        df = pro.query("top10_holders", period=period, limit=limit, offset=offset)
        if df is None or df.empty:
            break
        batch = df.to_dict("records")
        rows.extend(batch)
        offset += limit
        if len(batch) < limit or offset > 200000:
            break
    return rows


def _is_state_team(name) -> bool:
    return any(k in str(name) for k in _STATE_TEAM_KW)


def main() -> int:
    args = sys.argv[1:]
    period_arg = None
    allow_partial = False
    for i, a in enumerate(args):
        if a == "--period" and i + 1 < len(args):
            period_arg = args[i + 1]
        elif a == "--allow-partial":
            allow_partial = True

    pro = get_pro()
    # 候选报告期（从新到旧）
    candidates = ["20260630", "20260331", "20251231", "20250930", "20250630",
                  "20241231", "20240930", "20240630"]
    # 完整期阈值：预期全市场约 5 万条（5000 股 × 10），< 30% 视为披露中不完整
    COMPLETE_MIN = 15000

    def _count(period):
        df = pro.query("top10_holders", period=period, limit=1)
        return df is not None and len(df) > 0

    # 选定"操作期"：默认最近完整期；--allow-partial 时保留真正最新期
    latest = period_arg
    if latest is not None:
        pass
    else:
        for p in candidates:
            if _count(p):
                latest = p
                break
    # 拉最新期全量，判断是否完整
    rows_new = _fetch_holders(pro, latest)
    is_partial = len(rows_new) < COMPLETE_MIN
    if is_partial and not allow_partial:
        print(f"⚠️ 最新期 {latest} 仅 {len(rows_new)} 条（披露中不完整），自动回退到上一完整期")
        latest = None
        for p in candidates:
            if p == period_arg:
                continue
            df = pro.query("top10_holders", period=p, limit=1)
            if df is not None and len(df):
                cand_rows = _fetch_holders(pro, p)
                if len(cand_rows) >= COMPLETE_MIN:
                    latest = p
                    rows_new = cand_rows
                    break
    # 上一期：最新期之前的完整期
    prev = None
    for p in candidates:
        if p == latest:
            continue
        df = pro.query("top10_holders", period=p, limit=1)
        if df is not None and len(df):
            cand_rows = _fetch_holders(pro, p)
            if len(cand_rows) >= COMPLETE_MIN:
                prev = p
                rows_prev = cand_rows
                break
    if not latest or not prev:
        print("无法确定两个完整报告期")
        return 1
    if is_partial and allow_partial:
        rows_prev = _fetch_holders(pro, prev)
    print(f"报告期: 最新 {latest}（{'披露中' if is_partial and allow_partial else '完整'}）"
          f"vs 上一期 {prev}（完整）")
    print(f"  最新期 {len(rows_new)} 条 / 上一期 {len(rows_prev)} 条")

    # 国家队持仓：最新期 {ts_code: [(holder, ratio), ...]}
    new_state = {}
    for r in rows_new:
        if _is_state_team(r.get("holder_name")):
            new_state.setdefault(r["ts_code"], []).append(
                (str(r.get("holder_name")), r.get("hold_ratio")))
    prev_state_codes = {r["ts_code"] for r in rows_prev if _is_state_team(r.get("holder_name"))}

    # 新进：最新期有国家队、上一期没有
    newly = sorted([(c, h) for c, h in new_state.items() if c not in prev_state_codes],
                   key=lambda x: -max(r for _, r in x[1]))
    print(f"国家队新进前十股东: {len(newly)} 只")

    # 补充市值（最新交易日）
    mv = {}
    try:
        df = pro.daily_basic(trade_date=latest, fields="ts_code,total_mv")
        mv = {r["ts_code"]: round(r["total_mv"] / 10000, 1) for r in df.to_dict("records")}  # 万元→亿
    except Exception:
        pass

    # 名称
    name_map = {}
    try:
        df = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
        name_map = {r["ts_code"]: r["name"] for r in df.to_dict("records")}
    except Exception:
        pass

    # 输出 Markdown
    L = [f"# 国家队新进前十股东筛选（报告期 {latest} vs {prev}）",
         "", f"> 生成：{datetime.now():%Y-%m-%d %H:%M}｜数据源：Tushare top10_holders 全市场",
         f"> 新进 {len(newly)} 只（最新期新入前十、上一期无国家队持仓）", "",
         "| 代码 | 名称 | 新进国家队股东 | 持股比例% | 总市值(亿) |",
         "|---|---|---|---|---:|"]
    for code, holders in newly:
        nm = name_map.get(code, code)
        mv_str = f"{mv.get(code, '—')}"
        for hname, ratio in holders:
            L.append(f"| {code} | {nm} | {hname} | {ratio or '—'} | {mv_str} |")

    text = "\n".join(L)
    print("\n" + text)
    # 存文件
    outdir = os.path.join(_PROJECT_ROOT, "reports", "raw")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"state_team_{latest}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(f"\n[已写入] {os.path.relpath(out, _PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
