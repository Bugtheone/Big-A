# -*- coding: utf-8 -*-
"""业绩预告情报模块（P0 预期差落地，2026-08-05）：
  ① 拉取近 N 日业绩预告（Tushare forecast：类型/变动幅度）
  ② 主线标记（个股是否属 AI 算力主线：半导体/芯片/CPO/PCB/算力/AI/存储...）
  ③ 输出"预增 + 主线"最强信号清单（对应今日"中报预增 13 家涨停"逻辑）
  ④ 供 market_filter 复用（业绩因子）

用法:
  python scripts/tools/earnings_forecast.py                 # 近7日预告
  python scripts/tools/earnings_forecast.py --days 30 --json
  python scripts/tools/earnings_forecast.py --code 688012   # 单只
"""
import sys, os, argparse, json
from datetime import datetime, timedelta
from collections import Counter

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

# 主线概念关键词（AI 算力半导体链）
_MAINLINE_KW = ["半导体", "芯片", "集成电路", "光模块", "光通信", "光器件",
                "PCB", "覆铜板", "算力", "人工智能", "AI", "存储", "CPO",
                "先进封装", "晶振", "元件", "电子"]
# 预告类型正负向
_POSITIVE = {"预增", "扭亏", "续盈", "略增", "减亏"}
_NEGATIVE = {"预减", "首亏", "续亏", "略减", "增亏"}


def _rows(df):
    return df if isinstance(df, list) else df.to_dict("records")


def fetch_forecasts(start_date=None, end_date=None):
    """拉取业绩预告（Tushare forecast，逐日 ann_date 循环——接口不支持日期范围）。
    返回 list[dict]。"""
    from scripts.tushare_pro_data import ts_forecast
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
    rows = []
    cur = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    while cur <= end:
        try:
            df = ts_forecast(ann_date=cur.strftime("%Y%m%d"))
            rows.extend(_rows(df))
        except Exception as e:
            print(f"[WARN] {cur.strftime('%Y%m%d')} 预告失败: {str(e)[:40]}")
        cur += timedelta(days=1)
    return rows


def mainline_check(code, plates=None):
    """主线判断：个股概念/行业是否含主线关键词。返回命中列表。"""
    if plates is None:
        try:
            from scripts.tools.stock_plates import get_plates
            p = get_plates(code)
            concepts = p.get("概念", []) + p.get("行业", [])
        except Exception:
            concepts = []
    else:
        concepts = plates
    return [c for c in concepts if any(k in c for k in _MAINLINE_KW)]


def classify(row):
    """预告类型分类 → 正向/负向/不确定。"""
    t = str(row.get("type") or "不确定")
    if t in _POSITIVE:
        return "正向"
    if t in _NEGATIVE:
        return "负向"
    return "中性"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="近 N 日预告")
    ap.add_argument("--code", help="单只查询")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.code:
        # 单只：近180日预告 + 主线判断
        rows = fetch_forecasts(
            start_date=(datetime.now() - timedelta(days=180)).strftime("%Y%m%d"))
        mine = [r for r in rows if r.get("ts_code", "").startswith(args.code)]
        if not mine:
            print(f"⚠️ {args.code} 近180日无业绩预告")
            return 0
        ml = mainline_check(args.code)
        print(f"=== {args.code} 业绩预告（主线:{'/'.join(ml[:4]) if ml else '非主线'}）===")
        for r in mine:
            print(f"  {r.get('ann_date')} 报告期{r.get('end_date')} [{r.get('type')}] "
                  f"变动{r.get('p_change_min')}~{r.get('p_change_max')}%")
            if r.get("forecast_content"):
                print(f"    内容: {str(r['forecast_content'])[:80]}")
        return 0

    rows = fetch_forecasts(
        start_date=(datetime.now() - timedelta(days=args.days)).strftime("%Y%m%d"))
    if not rows:
        print(f"⚠️ 近{args.days}日无业绩预告数据（Tushare forecast）")
        return 0

    # 逐只主线判断（最多 30 只，避免 adata 限流）
    result = []
    seen_codes = set()
    for r in rows[:60]:
        code = str(r.get("ts_code", "")).split(".")[0]
        key = f"{code}_{r.get('end_date')}"
        if key in seen_codes:
            continue  # 去重（逐日拉取同预告多天出现）
        seen_codes.add(key)
        ml = mainline_check(code)
        result.append({
            "code": code, "name": r.get("ts_code", "").split(".")[0],
            "ann_date": r.get("ann_date"), "end_date": r.get("end_date"),
            "type": r.get("type"), "class": classify(r),
            "p_change_min": r.get("p_change_min"), "p_change_max": r.get("p_change_max"),
            "mainline": "/".join(ml[:3]) if ml else "",
        })

    # 排序：正向+主线 优先
    def score(x):
        s = 0
        if x["class"] == "正向":
            s += 2
        if x["mainline"]:
            s += 1
        return -s
    result.sort(key=score)

    if args.json:
        print(json.dumps({"days": args.days, "total": len(rows), "items": result},
                         ensure_ascii=False, indent=1))
        return 0

    print(f"=== 业绩预告情报（近{args.days}日，共{len(rows)}条，展示前{len(result)}）===")
    print("\n[💹 正向 + 主线 = 最强信号]")
    for x in result:
        if x["class"] == "正向" and x["mainline"]:
            print(f"  {x['code']} [{x['type']}] 变动{x['p_change_min']}~{x['p_change_max']}% 主线:{x['mainline']}")
    print("\n[全部预告分类统计]")
    c = Counter(x["class"] for x in result)
    print(f"  正向 {c['正向']} · 负向 {c['负向']} · 中性 {c['中性']}")

    # 写文件
    dstr = datetime.now().strftime("%Y-%m-%d")
    outdir = os.path.join(_PROJECT_ROOT, "reports", "daily", dstr)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"earnings_forecast_{datetime.now().strftime('%H%M')}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# 业绩预告情报 — {dstr}\n\n")
        for x in result:
            f.write(f"- {x['code']} [{x['type']}/{x['class']}] 变动{x['p_change_min']}~{x['p_change_max']}% 主线:{x['mainline'] or '—'}\n")
    print(f"\n[已写入] {os.path.relpath(out, _PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
