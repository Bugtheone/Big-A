#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""题材归因 + 腾讯实时行情交叉验证"""
import sys, io

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    import requests, urllib.request, json
    _session = requests.Session()
    _session.trust_env = False

    from collections import Counter
    from datetime import date

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"
    today = date.today().strftime("%Y-%m-%d")

    # ── Step 1: 同花顺强势股题材归因 ──
    url = f"http://zx.10jqka.com.cn/event/api/getharden/date/{today}/orderby/date/orderway/desc/charset/GBK/"
    r = _session.get(url, headers={"User-Agent": UA}, timeout=10)
    data = r.json()
    if data.get("errocode", 0) != 0:
        print(f"API错误: {data.get('errormsg', '')}")
        sys.exit(1)

    rows = data.get("data") or []
    print(f"=== 同花顺强势股题材归因 ({today}) ===\n  强势股: {len(rows)} 只\n")

    if not rows:
        print("  (非交易日或无数据)")
        sys.exit(0)

    # ── Step 2: 腾讯实时行情 ──
    codes = [r.get("code", "") for r in rows]

    # 前缀路由
    SH_INDEX = {"000300", "000905", "000016", "000688", "000852", "000010"}
    prefixed = []
    code_map = {}  # prefixed_str -> original_code
    for c in codes:
        if c.startswith(("5", "6", "9")):
            p = f"sh{c}"
        elif c.startswith(("4", "8", "92")):
            p = f"bj{c}"
        elif c in SH_INDEX:
            p = f"sh{c}"
        else:
            p = f"sz{c}"
        prefixed.append(p)
        code_map[p] = c

    # 批量拉取（每次最多50个）
    CHUNK = 50
    all_quotes = {}
    for i in range(0, len(prefixed), CHUNK):
        batch = prefixed[i:i+CHUNK]
        qurl = "https://qt.gtimg.cn/q=" + ",".join(batch)
        req = urllib.request.Request(qurl)
        req.add_header("User-Agent", UA)
        resp = urllib.request.urlopen(req, timeout=15)
        raw = resp.read().decode("gbk")
        for line in raw.strip().split(";"):
            if not line.strip() or "=" not in line or '"' not in line:
                continue
            key = line.split("=")[0].split("_")[-1]
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            c = code_map.get(key, key)
            all_quotes[c] = {
                "name": vals[1],
                "price": float(vals[3]) if vals[3] else 0,
                "last_close": float(vals[4]) if vals[4] else 0,
                "change_pct": float(vals[32]) if vals[32] else 0,
                "high": float(vals[33]) if vals[33] else 0,
                "low": float(vals[34]) if vals[34] else 0,
                "amount_wan": float(vals[37]) if vals[37] else 0,
                "turnover_pct": float(vals[38]) if vals[38] else 0,
                "pe_ttm": float(vals[39]) if vals[39] else 0,
                "mcap_yi": float(vals[45]) if vals[45] else 0,
                "pb": float(vals[46]) if vals[46] else 0,
                "vol_ratio": float(vals[49]) if vals[49] else 0,
            }

    # ── Step 3: 合并排序 ──
    merged = []
    for r in rows:
        code = r.get("code", "")
        q = all_quotes.get(code, {})
        merged.append({
            "code": code,
            "name": q.get("name") or r.get("name", ""),
            "reason": r.get("reason", ""),
            "change_pct": q.get("change_pct", 0),
            "price": q.get("price", 0),
            "turnover_pct": q.get("turnover_pct", 0),
            "pe_ttm": q.get("pe_ttm", 0),
            "mcap_yi": q.get("mcap_yi", 0),
            "vol_ratio": q.get("vol_ratio", 0),
        })

    merged.sort(key=lambda x: x["change_pct"], reverse=True)

    # ── 输出 ──
    print(f"━" * 70)
    print(f" {'排名':<5}{'代码':<8}{'名称':<10}{'涨幅%':>7}  {'换手%':>6}  {'PE':>7}  {'市值(亿)':>9}  题材归因")
    print("-" * 70)
    for i, m in enumerate(merged[:30], 1):
        pe_str = f"{m['pe_ttm']:.1f}" if m['pe_ttm'] else "-"
        mcap_str = f"{m['mcap_yi']:.1f}" if m['mcap_yi'] else "-"
        print(f" #{i:<3}  {m['code']:<8}{m['name']:<10}{m['change_pct']:>+6.2f}%  {m['turnover_pct']:>5.2f}%  {pe_str:>6}  {mcap_str:>8}  {m['reason'][:50]}")

    # ── 涨幅统计 ──
    pos = [m for m in merged if m["change_pct"] > 0]
    neg = [m for m in merged if m["change_pct"] < 0]
    zt = [m for m in merged if m["change_pct"] >= 9.8]
    zt5 = [m for m in merged if m["change_pct"] >= 5]
    print(f"\n  红盘: {len(pos)}只  |  绿盘: {len(neg)}只  |  涨停(≥9.8%): {len(zt)}只  |  涨超5%: {len(zt5)}只")

    # ── 题材热度词频 ──
    all_tags = []
    for m in merged:
        tags = [t.strip() for t in str(m["reason"]).split("+") if t.strip()]
        all_tags.extend(tags)
    cnt = Counter(all_tags)
    print(f"\n{'━' * 70}")
    print(f" 题材热度 TOP15（共 {len(cnt)} 个标签）")
    print("-" * 70)
    for tag, n in cnt.most_common(15):
        bar = "█" * min(n, 30)
        # 该题材平均涨幅
        tag_stocks = [m for m in merged if tag in str(m["reason"]).split("+")]
        avg_pct = sum(m["change_pct"] for m in tag_stocks) / len(tag_stocks) if tag_stocks else 0
        print(f"  {tag:<18s} {n:>3}只  avg{avg_pct:>+6.2f}%  {bar}")

    print(f"\n{'━' * 70}")
    print(" 数据源: 同花顺(题材归因) + 腾讯(实时行情) 交叉验证")
    print(f"{'━' * 70}")
