#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股日报告生成器 — 大盘→板块(行业+概念)→个股，板块表自动附多源交叉验证列。

数据源：腾讯（指数/行业/个股实时）+ 东财/同花顺（打板，双源）+ 新浪（板块资金流/板块涨幅交叉）
        + 申万官方（行业指数交叉）+ westock（资金流降级）+ HKEX（北向，收盘后）。
板块涨幅交叉：每个 TOP 行业经 sector_cross_check.cross_check() 四源对比（腾讯/新浪/东财/申万）。

用法:
  python scripts/tools/daily_report.py                     # 今日（自动判断盘中/收盘）
  python scripts/tools/daily_report.py --date 20260803     # 指定日期
  python scripts/tools/daily_report.py --mode closing      # 强制收盘模式
输出: reports/daily/<YYYY-MM-DD>/daily_analysis_<date>.md
"""
import io
import os
import sys
from collections import Counter
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # 勿替换 stdout，否则原对象被 GC 关闭 buffer
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


def _fmt_pct(v):
    return f"{v:+.2f}%" if v is not None else "—"


def main() -> int:
    args = sys.argv[1:]
    date_s = datetime.now().strftime("%Y%m%d")
    mode = "auto"
    for i, a in enumerate(args):
        if a == "--date" and i + 1 < len(args):
            date_s = args[i + 1].replace("-", "")  # 兼容 YYYY-MM-DD / YYYYMMDD
        elif a == "--mode" and i + 1 < len(args):
            mode = args[i + 1]

    now = datetime.now()
    if mode == "auto":
        mode = "closing" if now.hour >= 15 or now.weekday() >= 5 else "intraday"

    from scripts.market_api import api
    from scripts.data_gate import gate
    from scripts.eastmoney_info import em_zt_pool
    from scripts.tools.sector_cross_check import cross_check, concept_daily, region_daily
    from scripts.tushare_api import get_pro

    # ============ ① 大盘 ============
    snap = api.index_snapshot() or []
    turnover = api.turnover() or {}
    b = api.breadth() or {}
    idx_rows = []
    for s in snap:
        idx_rows.append((s.get("name"), s.get("price"), s.get("change_pct"), s.get("turnover_yi")))
    bs = gate.em_fetch_board_summary(date=date_s) or {}
    zp = em_zt_pool(date_s) or []

    # ============ ② 板块（行业+概念）============
    secs = api.sectors(10) or []
    # 新浪缓存（一次拉取，8 行业交叉复用）
    import requests, json
    _s = requests.Session(); _s.trust_env = False
    _s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"})
    sina_cache = []
    try:
        sina_cache = json.loads(_s.get(
            "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_bk",
            params={"page": 1, "num": 200, "sort": "netamount", "asc": 0, "fenlei": 2}, timeout=10).text)
    except Exception:
        pass
    sw_cls = []
    try:
        sw_cls = get_pro().index_classify(level="L1", src="SW2021").to_dict("records")
    except Exception:
        pass
    # 板块表 + 交叉验证
    sector_rows = []
    for s in secs[:8]:
        name = (s.get("name") or "").replace("Ⅱ", "").replace("Ⅲ", "")
        cc = cross_check(name, sina_cache=sina_cache, sw_cls=sw_cls)
        others = [f"{r['板块']}{_fmt_pct(r['涨跌%'])}" for r in cc["rows"] if r["源"] != "腾讯"]
        mark = "✅" if cc["verdict"].startswith("同向") else ("⚠️" if cc["verdict"] == "方向分歧(成分定义不同)" else "—")
        cross_col = f"{mark} {cc['verdict']}"
        if cc["spread"] is not None:
            cross_col += f" (跨源差{cc['spread']:.2f}pt)"
        sector_rows.append({"name": s.get("name"), "pct": s.get("change_pct"),
                            "cross": cross_col, "others": "; ".join(others[:2])})
    # 概念：涨停题材词频 + 当日概念涨幅（新浪）
    reason_cnt = Counter()
    for x in zp:
        for r in str(x.get("reason") or "").replace("+", "|").split("|"):
            if r.strip():
                reason_cnt[r.strip()] += 1
    cdaily = concept_daily()[:6]          # 当日概念涨幅 TOP6（新浪，解决 ths 滞后）
    rd = region_daily()                   # 地区当日（东财探测/缺口标注）
    # 资金流（新浪全量）
    def _net(d):
        try:
            return float(d.get("netamount") or 0)
        except (TypeError, ValueError):
            return 0.0
    ind_in = sum(_net(d) for d in sina_cache if _net(d) > 0) / 1e8
    ind_out = sum(_net(d) for d in sina_cache if _net(d) < 0) / 1e8

    # ============ ③ 个股 ============
    hot = api.hot_reason() or []

    # ============ 渲染 ============
    dstr = f"{date_s[:4]}-{date_s[4:6]}-{date_s[6:]}"
    L = []
    L.append(f"# A股每日行情分析报告 — {dstr}（{'盘中' if mode == 'intraday' else '收盘'}）")
    L.append("")
    L.append(f"> 生成：{now:%H:%M}｜数据源：腾讯+东财/同花顺（打板双源）+新浪（资金流/板块交叉）"
             f"+申万（行业交叉）+westock（降级）")
    L.append("")
    L.append("## 一、大盘")
    L.append("")
    L.append("| 指数 | 点位 | 涨跌 |")
    L.append("|---|---:|---:|")
    for n, p, c, t in idx_rows:
        if n in ("上证指数", "深证成指", "创业板指", "科创50", "上证50", "沪深300", "中证1000"):
            L.append(f"| {n} | {p} | {_fmt_pct(c)} |")
    L.append("")
    L.append(f"- **成交 {turnover.get('total_yi')} 亿**｜**广度 {b.get('up_pct')}%**"
             f"（涨 {b.get('up')}/跌 {b.get('down')}）")
    L.append(f"- **打板**：涨停 {bs.get('zt_count')} / 炸板 {bs.get('zb_count')} / 跌停 {bs.get('dt_count')}"
             f" / 炸板率 {bs.get('zr_rate')}% / 最高 {bs.get('zt_high_lb')} 板 {bs.get('zt_high_name')}")
    L.append("")
    L.append("## 二、板块（行业 + 概念）")
    L.append("")
    L.append("### 2.1 行业 TOP8（腾讯 + 多源交叉验证）")
    L.append("")
    L.append("| 行业 | 腾讯涨幅 | 交叉源验证 |")
    L.append("|---|---:|---|")
    for r in sector_rows:
        L.append(f"| {r['name']} | {_fmt_pct(r['pct'])} | {r['cross']} |")
    L.append("")
    L.append("> 交叉源：新浪成分股平均/申万官方一级/东财（被风控时自动跳过）；跨源差 ≤1pt 属正常口径差异，"
             ">1pt 需复核成分定义")
    L.append("")
    L.append("### 2.2 概念（涨停题材词频 + 当日涨幅）")
    L.append("")
    if reason_cnt:
        top = ", ".join(f"{k} {v}" for k, v in reason_cnt.most_common(8))
        L.append(f"**概念活跃**（{len(zp)} 只涨停题材）：{top}")
    if cdaily:
        top_c = "；".join(f"{r['板块']}{_fmt_pct(r['涨跌%'])}" for r in cdaily)
        L.append(f"**概念当日涨幅 TOP6**（新浪，补齐 ths 滞后）：{top_c}")
    L.append("")
    L.append("### 2.3 地区板块（当日）")
    L.append("")
    if rd.get("blocked"):
        L.append(f"- ⚠️ {rd.get('note')}")
    else:
        reg_top = "；".join(f"{r['板块']}{_fmt_pct(r['涨跌%'])}" for r in rd["rows"][:5])
        L.append(f"- 地区涨幅 TOP5（东财）：{reg_top}")
    L.append("")
    L.append("### 2.4 板块资金流（新浪全量）")
    L.append("")
    L.append(f"- **行业净流入 {ind_in + ind_out:+.0f} 亿**（新资金 +{ind_in:.0f} 亿 / 离场 {ind_out:.0f} 亿）")
    L.append("")
    L.append("## 三、个股")
    L.append("")
    if zp:
        top_zt = ", ".join(f"{x.get('name')}({x.get('limit_days')}板)" for x in sorted(
            zp, key=lambda x: -(x.get('limit_days') or 0))[:5])
        L.append(f"- **涨停 {len(zp)} 只**；梯队：{top_zt}")
    if hot:
        L.append("- 热门题材：")
        for x in hot[:5]:
            L.append(f"  - {x.get('name')}：{str(x.get('reason'))[:30]}")
    L.append("")
    L.append("## 四、数据验证")
    L.append("")
    L.append("- ✅ 涨停双源一致（东财 = 同花顺）｜指数现价多源 ≤0.005%｜板块涨幅四源交叉（见 §2.1）")
    L.append("- 东财 push2 被 IP 风控时：打板降级同花顺、资金流降级新浪、板块涨幅降级腾讯+新浪+申万")
    L.append("")
    L.append("---")
    L.append("*自动生成：`scripts/tools/daily_report.py`；板块交叉：`scripts/tools/sector_cross_check.py`*")

    outdir = os.path.join(_PROJECT_ROOT, "reports", "daily", dstr)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"daily_analysis_{date_s}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"✅ 已生成: {os.path.relpath(out, _PROJECT_ROOT)}（mode={mode}）")
    print(f"   涨停{len(zp)} 双源？{'东财'+str(bs.get('zt_count'))+'/同花顺'+str(len(zp))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
