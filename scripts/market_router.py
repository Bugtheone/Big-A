#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A股行情策略路由引擎（设计方案 v1.0 工程化落地，2026-08-06）

核心思想：先判天气、再选航道、最后才挑船。
  ① Gate 门控（0~3 档）→ ② 行情类型（12 种）→ ③ 策略路由（策略族）
  → ④ 板块方向 → ⑤ 仓位计算 → 每日决策报告

数据源（全部官方/实时，禁止估算）：
  腾讯（指数/广度/涨停）、东财 push2（板块资金）、market_api 聚合
  策略量化：position_sizer（档位）、entry_point（介入点）、trend_tracker（趋势）

用法：
  python scripts/market_router.py            # 完整决策报告
  python scripts/market_router.py --json     # JSON 输出
  python scripts/market_router.py --strategy-test   # 纯路由判定（不拉数据）
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ── 行情类型判定表（设计文档 §二.模块②） ──────────────
def classify_market(breadth, zt, down_cnt, mainline_ok, turnover_yi,
                    sh_pct, sh50_pct, board_top=None) -> list:
    """返回行情类型标签列表（可叠加）。参数来自实时拉取，禁止估算。"""
    tags = []
    board_top = board_top or []

    # ① 全面性普涨/普跌（第一优先级）
    if breadth > 60 and zt >= 60:
        tags.append("全面性普涨")
    if breadth < 40 and zt < 50:
        tags.append("全面性普跌")

    # ③ 结构性行情（第二优先级）
    if mainline_ok and (breadth < 55):
        tags.append("结构性行情")

    # ④ 存量博弈震荡
    if 40 <= breadth <= 60 and not mainline_ok:
        tags.append("存量博弈震荡")

    # ⑧ 超跌反弹（广度修复 + 放量 + 前期深跌）
    if sh_pct > 0 and breadth < 50 and turnover_yi and turnover_yi > 25000:
        tags.append("超跌反弹")

    # ⑨ 抱团行情（主线强但广度差）
    if mainline_ok and breadth < 45:
        tags.append("抱团行情")

    # ⑩ 防御性行情（涨幅前五全防御）
    defensive = ["银行", "煤炭", "石油", "公用事业", "电力", "钢铁", "食品"]
    if board_top and all(any(k in b for k in defensive) for b in board_top[:5]):
        tags.append("防御性行情")

    # ⑫ 反转/修复（指数翻红 + 广度回升趋势）
    if sh_pct > 0.5 and breadth > 45:
        tags.append("反转/修复")

    # ⑯ 权重行情（指数红但广度差）
    if sh_pct > 0 and breadth < 45 and sh50_pct > sh_pct:
        tags.append("权重行情")

    if not tags:
        tags.append("存量博弈震荡")
    return tags


# ── 策略路由（设计文档 §二.模块③） ─────────────────
def route_strategy(tags: list, gate_tier: str) -> list:
    """行情类型 → 策略族。返回 [策略族名, 买点规则, 仓位上限] 列表。"""
    strategies = []
    if "全面性普涨" in tags:
        strategies.append(("趋势跟踪", "突破买点正常执行；回踩MA20加仓", 50))
    if "结构性行情" in tags:
        strategies.append(("顺势波段", "主线内回踩MA10/MA20企稳买；分歧日低吸", 30))
    if "存量博弈震荡" in tags:
        strategies.append(("区间波段/均值回归", "箱体下沿缩量企稳买；不追突破", 20))
    if "抱团行情" in tags:
        strategies.append(("抱团核心", "龙头首次缩量回踩MA10（唯一买点），止损最快", 20))
    if "超跌反弹" in tags:
        strategies.append(("修复段轻仓", "止跌阳线/低开高走长下影后试仓，碰压力就走", 15))
    if "防御性行情" in tags:
        strategies.append(("配置/红利", "红利框架（股息率+估值分位），不用波段框架", 15))
    if "全面性普跌" in tags:
        strategies.append(("空仓观察", "不执行任何买点", 0))
    if "权重行情" in tags:
        strategies.append(("权重波段", "银行/保险/运营商自身波段，降低预期", 20))

    if not strategies:
        strategies.append(("观望", "数据不足，保守处理", 10))
    return strategies


# ── 板块路由（设计文档 §二.模块④） ─────────────────
def route_sectors(tags: list) -> dict:
    """行情类型 → 该做/禁止板块方向。"""
    do, avoid = [], []
    if "全面性普涨" in tags:
        do = ["主线 + 扩散板块（动量排名前5）"]
        avoid = ["无特别禁忌（别频繁换股）"]
    if "结构性行情" in tags:
        do = ["主线板块内龙头+中军（1~2条）"]
        avoid = ["非主线全部丢弃"]
    if "存量博弈震荡" in tags:
        do = ["最强方向回踩低吸"]
        avoid = ["追突破、弱势板块抄底"]
    if "抱团行情" in tags:
        do = ["抱团核心板块本身"]
        avoid = ["非抱团板块（资金不会扩散）"]
    if "超跌反弹" in tags:
        do = ["最先抗跌转强的板块"]
        avoid = ["还在地板上的弱势板块"]
    if "防御性行情" in tags:
        do = ["红利/银行/公用事业（配置框架）"]
        avoid = ["高弹性题材（胜率天然低）"]
    if "全面性普跌" in tags:
        do = ["无（只观察谁先抗跌）"]
        avoid = ["所有"]
    if "权重行情" in tags:
        do = ["银行/保险/运营商"]
        avoid = ["中小盘题材（权重涨时阴跌）"]
    if not do:
        do = ["主线方向（资金第一梯队）"]
        avoid = ["资金流出的弱势板块"]
    return {"do": do, "avoid": avoid}


# ── 仓位计算（设计文档 §二.模块⑤） ─────────────────
def compute_cap(tags: list, gate_tier: str) -> dict:
    """门控 × 行情类型 → 仓位上限。gate_tier: F/E/D/C/B/A（position_sizer 档位）"""
    base = {"F": 0, "E": 10, "D": 20, "C": 40, "B": 70, "A": 100}.get(gate_tier, 0)
    discount = 1.0
    if "全面性普跌" in tags:
        discount = 0
    elif "防御性行情" in tags:
        discount = 0.3
    elif "抱团行情" in tags or "存量博弈震荡" in tags:
        discount = 0.5
    elif "超跌反弹" in tags:
        discount = 0.6
    cap = int(base * discount)
    return {"base_pct": base, "discount": discount, "final_pct": cap}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strategy-test", action="store_true",
                    help="不拉数据，用示例参数测试路由逻辑")
    args = ap.parse_args()

    if args.strategy_test:
        # 用 08-06 11:17 上午尾盘真实数据测试
        tags = classify_market(breadth=28.9, zt=57, down_cnt=3429,
                               mainline_ok=True, turnover_yi=35000,
                               sh_pct=-0.02, sh50_pct=-0.41,
                               board_top=["印制电路板", "元件", "半导体", "电子", "通信设备"])
        strs = route_strategy(tags, "E")
        secs = route_sectors(tags)
        cap = compute_cap(tags, "E")
        print(json.dumps({"tags": tags, "strategies": strs,
                          "sectors": secs, "cap": cap}, ensure_ascii=False, indent=1))
        return 0

    # 实时拉取
    from scripts.market_api import api
    from scripts.tools.real_time import get_real_time
    from scripts.tools.position_sizer import compute_position

    t = get_real_time()
    try:
        snap = api.index_snapshot(["上证指数", "上证50"])
        sh = {s["name"]: s for s in snap}
        sh_pct = sh.get("上证指数", {}).get("change_pct", 0)
        sh50_pct = sh.get("上证50", {}).get("change_pct", 0)
    except Exception:
        sh_pct = sh50_pct = 0

    b = api.breadth()
    breadth, down_cnt = b.get("up_pct", 0), b.get("down", 0)
    try:
        pool = api.zt_pool()
        zt = len(pool)
    except Exception:
        zt = 0

    # 成交折算全天（与 position_sizer 一致逻辑）
    import datetime
    hm = datetime.datetime.now().hour * 60 + datetime.datetime.now().minute
    elapsed = 0
    if hm <= 690:
        elapsed = max(hm - 570, 0)
    elif hm < 780:
        elapsed = 120
    elif hm <= 900:
        elapsed = 120 + (hm - 780)
    else:
        elapsed = 240
    turnover_yi = api.turnover().get("total_yi", 0)
    if elapsed > 30:
        turnover_yi = turnover_yi * 240 / elapsed

    # 主线判定（资金第一梯队是否电子链）
    mainline_ok = False
    try:
        rows = api.board_fund_flow(board_type="行业")
        top_names = [r["name"] for r in rows[:5]]
        if any(k in n for n in top_names for k in ["电子", "半导体", "元件", "印制", "通信"]):
            mainline_ok = True
    except Exception:
        top_names = []

    pos = compute_position(total_yi=turnover_yi, breadth=breadth, zt=zt,
                           sh_vs_ma5=None)
    gate_tier = pos["tier"]

    tags = classify_market(breadth, zt, down_cnt, mainline_ok,
                           turnover_yi, sh_pct, sh50_pct, top_names)
    strs = route_strategy(tags, gate_tier)
    secs = route_sectors(tags)
    cap = compute_cap(tags, gate_tier)

    out = {
        "time": t["used"],
        "inputs": {"成交折算": round(turnover_yi), "广度": breadth,
                   "涨停": zt, "上证": sh_pct, "上证50": sh50_pct,
                   "板块TOP5": top_names, "主线确认": mainline_ok},
        "gate": {"档位": pos["tier"], "仓位上限": pos["limit_pct"],
                 "拦截": pos["blockers"]},
        "行情类型": tags,
        "策略路由": [{"策略": s[0], "买点": s[1], "仓位上限": s[2]} for s in strs],
        "板块方向": secs,
        "仓位": cap,
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    print(f"╔══ A股行情策略路由 — 每日决策报告 ══ {t['used']} ══╗")
    print(f"【输入】成交折算 {round(turnover_yi)}亿 · 广度 {breadth}% · 涨停 {zt} · 上证 {sh_pct:+.2f}% · 上证50 {sh50_pct:+.2f}%")
    print(f"【门控】档位 {pos['tier']} → 仓位上限 {pos['limit_pct']}%")
    for blk in pos["blockers"]:
        print(f"   拦截: {blk}")
    print(f"【行情类型】{' + '.join(tags)}")
    print(f"【策略路由】")
    for s in strs:
        print(f"   → {s[0]}: {s[1]}（仓位≤{s[2]}%）")
    print(f"【板块方向】")
    for d in secs["do"]:
        print(f"   该做: {d}")
    for a in secs["avoid"]:
        print(f"   禁止: {a}")
    print(f"【仓位】基础 {cap['base_pct']}% × 折扣 {cap['discount']} → 最终 {cap['final_pct']}%")
    print("╚" + "═" * 60 + "╝")
    return 0


if __name__ == "__main__":
    sys.exit(main())
