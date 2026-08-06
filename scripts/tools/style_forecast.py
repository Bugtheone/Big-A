# -*- coding: utf-8 -*-
"""风格预判三维评分（2026-08-06 用户方法论落地）：
  预判次日资金风格（防御/进攻/周期）：
    维度1 当日资金流向（成长/周期/避险）
    维度2 隔夜外盘（美股科技/A50/资金面）
    维度3 情绪量能（广度/涨停/炸板率）
  输出三风格得分 + 次日预判。

⚠️ 预判用于准备，执行按"持续主线"原则（AGENTS.md）。

用法:
  python scripts/tools/style_forecast.py          # 全量评分
  python scripts/tools/style_forecast.py --json
"""
import sys, os, argparse, json
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

# 成长/周期/避险 行业关键词
_GROWTH_KW = ["电子", "半导体", "通信设备", "软件开发", "计算机", "元件", "光学光电子", "消费电子"]
_CYCLE_KW = ["有色金属", "贵金属", "煤炭", "石油", "基础化工", "钢铁", "工业金属", "小金属"]
_DEFENSE_KW = ["黄金", "银行", "公用事业", "食品饮料", "家用电器", "交通运输", "医药商业", "白酒"]


def _rows(df):
    return df if isinstance(df, list) else df.to_dict("records")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    from scripts.tools.real_time import get_real_time
    from scripts.market_api import api
    from scripts.data_gate import gate
    t = get_real_time()

    # ── 维度1：资金流向 ───────────────────────────────────
    grow_ff, cycle_ff, defen_ff = 0, 0, 0
    try:
        bf = api.board_fund_flow_robust("行业", "今日", 20)
        for it in (bf.get("items") or []):
            nm = str(it.get("name") or "")
            net = float(it.get("main_net_yi") or 0)
            if any(k in nm for k in _GROWTH_KW):
                grow_ff += net
            if any(k in nm for k in _CYCLE_KW):
                cycle_ff += net
            if any(k in nm for k in _DEFENSE_KW):
                defen_ff += net
    except Exception as e:
        print(f"[WARN] 资金流: {e}")

    # ── 维度2：外盘/资金面 ────────────────────────────────
    us_tech = None  # AI 四巨头均值
    a50 = None
    gc = None
    try:
        from scripts.tools.intraday_enhance import global_ai, a50_check, money_rate
        import requests
        S = requests.Session(); S.trust_env = False
        S.headers.update({"User-Agent": "Mozilla/5.0"})
        g = global_ai(S)
        us_tech = g.get("_ai4_avg")
        a = a50_check(S)
        a50 = a["chg"] if a else None
        m = money_rate(S)
        gc = (m.get("GC001") or {}).get("rate")
    except Exception:
        pass

    # ── 维度3：情绪量能 ───────────────────────────────────
    breadth = None
    zt_cnt, zr = None, None
    try:
        b = api.breadth()
        breadth = b.get("up_pct")
    except Exception:
        pass
    try:
        bs = gate.em_fetch_board_summary(date=datetime.now().strftime("%Y%m%d"))
        if bs:
            zt_cnt = bs.get("zt_count")
            zr = bs.get("zr_rate")
    except Exception:
        pass

    # ── 三维评分 ──────────────────────────────────────────
    # 维度1 资金（满分 40）：成长 + 周期 + 避险 相对
    total_ff = abs(grow_ff) + abs(cycle_ff) + abs(defen_ff) or 1
    s1_grow = max(0, grow_ff) / total_ff * 40
    s1_cycle = max(0, cycle_ff) / total_ff * 40
    s1_defen = max(0, defen_ff) / total_ff * 40

    # 维度2 外盘（满分 30）：美股科技+/A50+/利率低 → 进攻；避险资产→防御
    s2_grow = s2_cycle = s2_defen = 0
    if us_tech is not None:
        if us_tech > 0.5:
            s2_grow += 15
        elif us_tech < -0.5:
            s2_defen += 10
    if a50 is not None:
        if a50 > 0.3:
            s2_grow += 10
            s2_cycle += 5
        elif a50 < -0.3:
            s2_defen += 10
    if gc is not None:
        if gc < 2.5:
            s2_grow += 5  # 资金宽松利于进攻
        elif gc > 4:
            s2_defen += 5  # 资金紧→防御

    # 维度3 情绪（满分 30）
    s3_grow = s3_defen = s3_cycle = 0
    if breadth is not None:
        if breadth >= 60:
            s3_grow += 15
        elif breadth < 45:
            s3_defen += 15
    if zt_cnt is not None:
        if zt_cnt >= 80:
            s3_grow += 10
        elif zt_cnt < 50:
            s3_defen += 10
    if zr is not None:
        if zr > 20:
            s3_defen += 5  # 炸板率高→情绪弱→防御

    scores = {
        "进攻(成长)": round(s1_grow + s2_grow + s3_grow, 1),
        "周期(资源)": round(s1_cycle + s2_cycle + s3_cycle, 1),
        "防御(避险)": round(s1_defen + s2_defen + s3_defen, 1),
    }
    top = max(scores, key=scores.get)
    result = {
        "ts": t["used"],
        "维度1资金": {"成长": round(grow_ff, 1), "周期": round(cycle_ff, 1), "避险": round(defen_ff, 1)},
        "维度2外盘": {"美股AI": us_tech, "A50": a50, "GC001": gc},
        "维度3情绪": {"广度": breadth, "涨停": zt_cnt, "炸板率": zr},
        "风格得分": scores,
        "预判": f"次日风格主基调 = {top}",
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    print(f"=== 风格预判三维评分（{t['used']} 腾讯CDN）===")
    print(f"\n[维度1 当日资金(亿)] 成长{grow_ff:+.0f} 周期{cycle_ff:+.0f} 避险{defen_ff:+.0f}")
    print(f"[维度2 外盘] 美股AI四巨头 {us_tech}% · A50 {a50}% · GC001 {gc}%")
    print(f"[维度3 情绪] 广度 {breadth}% · 涨停 {zt_cnt} · 炸板率 {zr}%")
    print(f"\n[风格得分] " + " · ".join(f"{k}:{v}" for k, v in scores.items()))
    print(f"\n🎯 预判：次日风格主基调 = {top}")

    dstr = datetime.now().strftime("%Y-%m-%d")
    outdir = os.path.join(_PROJECT_ROOT, "reports", "daily", dstr)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"style_forecast_{datetime.now().strftime('%H%M')}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# 风格预判 — {dstr}\n\n")
        f.write(f"- 得分: " + " · ".join(f"{k}:{v}" for k, v in scores.items()) + "\n")
        f.write(f"- 预判: {top}\n")
    print(f"\n[已写入] {os.path.relpath(out, _PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
