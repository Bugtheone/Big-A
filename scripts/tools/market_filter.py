# -*- coding: utf-8 -*-
"""资金筛选法（2026-08-05 用户方法论落地）：锁定主线核心 + 判断市场风格。

方法（由资金筛选）：
  ① 成交额排名前 100~300（热度+流动性）
  ② 站上 5/10 日均线
  ③ 近 5 日累计涨幅 10~30% 健康区间（主线清晰可放宽）
  ④ 按行业聚类 → 锁定主线核心板块 + 判断交易风格（成长/价值/题材）

用法:
  python scripts/tools/market_filter.py                 # 默认: TOP300, 5日涨幅10-30%
  python scripts/tools/market_filter.py --top 300 --min-chg 10 --max-chg 30
  python scripts/tools/market_filter.py --json          # 机器可读
"""
import sys, os, argparse, json
from datetime import datetime
from collections import Counter

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


def _out(*a):
    print(*a, flush=True)


def fetch_top(S, top, fs="m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"):
    """东财全市场按成交额(f6)排名取 TOP。返回 [{code,name,chg,amount,cap,ind,chg5d}]"""
    rows, page = [], 1
    while len(rows) < top and page <= 10:
        ok = False
        for host in ("push2.eastmoney.com", "push2delay.eastmoney.com"):
            try:
                r = S.get(f"https://{host}/api/qt/clist/get",
                          params={"pn": page, "pz": "100", "po": "1", "np": "1",
                                  "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": "2", "invt": "2",
                                  "fid": "f6", "fs": fs, "fields": "f2,f3,f6,f12,f14,f20,f100,f109"},
                          timeout=10)
                d = (r.json().get("data") or {}).get("diff") or []
                if d:
                    ok = True
                    for it in d:
                        rows.append({
                            "code": str(it.get("f12") or "").zfill(6),
                            "name": it.get("f14"), "chg": it.get("f3"),
                            "price": it.get("f2"),
                            "amount_yi": round((it.get("f6") or 0) / 1e8, 1),
                            "cap_yi": round((it.get("f20") or 0) / 1e8, 0),
                            "ind": it.get("f100") or "—",
                            "chg5d": it.get("f109"),
                        })
                    break
            except Exception:
                continue
        if not ok:
            break
        page += 1
    return rows[:top]


def calc_ma(S, code):
    """腾讯日K 算 MA5/MA10，返回 (ma5, ma10) 或 None。"""
    pref = ("sh" if code.startswith(("6", "9")) else "sz") + code
    try:
        r = S.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                  params={"param": f"{pref},day,,,70,qfq"}, timeout=8)
        d = r.json()["data"][pref]
        kl = d.get("qfqday") or d.get("day") or []
        closes = [float(x[2]) for x in kl]
        if len(closes) < 10:
            return None
        return sum(closes[-5:]) / 5, sum(closes[-10:]) / 10
    except Exception:
        return None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=300, help="成交额排名取前 N（默认 300）")
    ap.add_argument("--min-chg", type=float, default=10.0, help="近5日最小涨幅%（默认 10）")
    ap.add_argument("--max-chg", type=float, default=30.0, help="近5日最大涨幅%（默认 30，主线清晰可放宽）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    import requests
    S = requests.Session(); S.trust_env = False
    S.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"})
    now = datetime.now()

    # ① 成交额 TOP N
    top = fetch_top(S, args.top)
    if not top:
        _out("❌ 成交额榜拉取失败")
        return 1

    # ② 过滤 5 日涨幅区间 + 当日上涨
    cand = [s for s in top
            if s["chg5d"] is not None
            and args.min_chg <= float(s["chg5d"]) <= args.max_chg
            and (s["chg"] or 0) >= 0]

    # ③ 站上 5/10 日均线（拉腾讯 K 线验证）
    passed = []
    for s in cand:
        ma = calc_ma(S, s["code"])
        if not ma:
            continue
        ma5, ma10 = ma
        price = s.get("price") or 0
        if price and price > ma5 and price > ma10:
            passed.append({**s, "ma5": round(ma5, 2), "ma10": round(ma10, 2),
                           "above_ma5": True, "above_ma10": True})

    # ── 输出 ──────────────────────────────────────────────
    # 行业聚类（锁定主线）
    ind_cnt = Counter(s["ind"] for s in passed)
    style = "成长(科技)主导" if any(k in ind_cnt for k in ("半导体", "通信设备", "电子", "计算机")) else "混合/题材"
    result = {"ts": now.strftime("%Y-%m-%d %H:%M:%S"),
              "成交额TOP": len(top), "候选(5日涨幅区间)": len(cand),
              "均线过滤后": len(passed),
              "行业聚类": ind_cnt.most_common(10),
              "风格": style, "个股": passed}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    _out(f"=== 资金筛选 {now:%H:%M:%S}（成交额TOP{args.top}·5日涨幅{args.min_chg}-{args.max_chg}%·站上双均线）===")
    _out(f"成交额TOP {len(top)} → 5日涨幅区间 {len(cand)} → 站上5/10日线 {len(passed)}")
    _out(f"\n[行业聚类·主线锁定]")
    for ind, n in ind_cnt.most_common(10):
        names = [s["name"] for s in passed if s["ind"] == ind][:5]
        _out(f"  {ind}: {n}只 -> {', '.join(names)}")
    _out(f"\n[市场风格] {style}")
    _out(f"\n[候选明细 TOP20]")
    passed.sort(key=lambda s: -(s["chg5d"] or 0))
    for s in passed[:20]:
        _out(f"  {s['name']}({s['code']}): 成交额{s['amount_yi']}亿 5日+{s['chg5d']}% 今日{s['chg']}% [{s['ind']}]")

    # 写文件
    dstr = now.strftime("%Y-%m-%d")
    outdir = os.path.join(_PROJECT_ROOT, "reports", "daily", dstr)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"market_filter_{now.strftime('%H%M')}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# 资金筛选 — {now.strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"成交额TOP {len(top)} → 5日涨幅区间 {len(cand)} → 站上双均线 {len(passed)}\n\n")
        f.write("## 行业聚类（主线）\n")
        for ind, n in ind_cnt.most_common(10):
            f.write(f"- {ind}: {n}只\n")
        f.write(f"\n## 风格\n{style}\n")
    _out(f"\n[已写入] {os.path.relpath(out, _PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
