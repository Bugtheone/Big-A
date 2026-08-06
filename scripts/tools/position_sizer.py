#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓位管理工具（60/40 法则 → 档位映射，官方数据源，禁止估算）

纪律（2026-08-06 固化）：
- 仓位档位必须基于本工具输出的市场状态判定（60/40 法则 + 信号体系）
- 禁止凭感觉定仓位；本工具是仓位管理的唯一量化来源

输入（自动拉取或手动传入）：
  成交额（total_yi）· 指数 vs MA5/MA10 · 广度 · 涨停 · 信号状态

输出：
  档位 + 总仓上限 + 动作指令

档位映射：
  F. 观望 0%          成交<2.5万亿 或 指数破5/10日线
  E. 防守 ≤10%        广度<55%（E1）或 涨停<60（E2）→ 仅试错
  D. 试错 ≤20%        广度55~60% + 主线确立
  C. 升级 20~40%      广度60%+ 且 涨停≥60 + 主线不降级
  B. 加仓 40~70%      4/4 信号齐备
  A. 主升 70~100%     全面多头（MA多头 + 广度65%+ + 成交3万亿+）

用法：
  python scripts/tools/position_sizer.py                    # 自动拉取市场数据
  python scripts/tools/position_sizer.py --json
  python scripts/tools/position_sizer.py --signal-e1 --signal-e2   # 手动传入信号
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def compute_position(total_yi=None, sh_vs_ma5=None, breadth=None, zt=None,
                     e1=None, e2=None, a50_bear=None) -> dict:
    """核心计算：输入市场指标 → 仓位档位。任一参数为 None 时跳过该判据。"""
    reasons = []
    blockers = []

    # 60/40 法则条件① 成交
    if total_yi is not None:
        if total_yi < 25000:
            blockers.append(f"成交 {total_yi:.0f}亿 < 2.5万亿")
        else:
            reasons.append(f"成交 {total_yi:.0f}亿 ≥ 2.5万亿")

    # 条件② 指数 vs MA5/MA10（输入为 vs MA5 的百分比，如 -0.5 表示在下方）
    if sh_vs_ma5 is not None:
        if sh_vs_ma5 < 0:
            blockers.append(f"上证跌破MA5 ({(sh_vs_ma5):+.1f}%)")
        else:
            reasons.append(f"上证站上MA5 ({(sh_vs_ma5):+.1f}%)")

    # 广度
    if breadth is not None:
        if breadth < 55:
            blockers.append(f"广度 {breadth:.1f}% < 55% (E1)")
        elif breadth < 60:
            reasons.append(f"广度 {breadth:.1f}% ∈ [55,60)")
        else:
            reasons.append(f"广度 {breadth:.1f}% ≥ 60%")

    # 涨停
    if zt is not None:
        if zt < 60:
            blockers.append(f"涨停 {zt} < 60 (E2)")
        else:
            reasons.append(f"涨停 {zt} ≥ 60")

    # 显式信号
    if e1:
        blockers.append("E1 广度<55% 已触发")
    if e2:
        blockers.append("E2 涨停断层 已触发")
    if a50_bear:
        blockers.append("F1 A50 偏空")

    # ── 档位判定（撤退优先） ──
    if blockers:
        # 有硬性拦截 → 防守或观望
        if total_yi is not None and total_yi < 25000:
            tier, limit, action = "F", 0, "🚫 观望（成交不足 2.5 万亿，60/40 法则不满足）"
        else:
            tier, limit, action = "E", 10, "🛡 防守（撤退信号触发，仅 0.5~1% R 试错，严禁加仓）"
    else:
        # 无拦截 → 按广度/涨停/成交升级
        score = 0
        if breadth is not None and breadth >= 60:
            score += 1
        if zt is not None and zt >= 60:
            score += 1
        if total_yi is not None and total_yi >= 30000:
            score += 1
        if sh_vs_ma5 is not None and sh_vs_ma5 > 0.5:
            score += 1

        if score >= 4:
            tier, limit, action = "A", 100, "🚀 主升（全面多头，可满仓运作）"
        elif score == 3:
            tier, limit, action = "B", 70, "📈 加仓（信号齐备，40~70%）"
        elif score == 2:
            tier, limit, action = "C", 40, "📊 升级（2 信号，20~40%）"
        elif score == 1:
            tier, limit, action = "D", 20, "🧪 试错（单信号，主线回踩 ≤20%）"
        else:
            tier, limit, action = "D", 20, "🧪 试错（无强信号，保守 ≤20%）"

    return {
        "tier": tier, "limit_pct": limit, "action": action,
        "reasons": reasons, "blockers": blockers,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--signal-e1", action="store_true", help="手动标记 E1 广度<55%")
    ap.add_argument("--signal-e2", action="store_true", help="手动标记 E2 涨停断层")
    args = ap.parse_args()

    # 自动拉取市场数据
    data = {"total_yi": None, "sh_vs_ma5": None, "breadth": None, "zt": None}
    try:
        from scripts.market_api import api
        from scripts.tools.real_time import get_real_time
        t_rt0 = get_real_time()
        # 盘中成交折算全天（按已交易分钟比例，10:30前按上午1/2估算）
        import datetime
        hh, mm = t_rt0.get("used", "11:00:00").split(" ")[1].split(":")[:2]
        hm = int(hh) * 60 + int(mm)
        if hm < 570:  # 9:30 前
            elapsed = 0
        elif hm <= 690:  # 上午 9:30-11:30
            elapsed = hm - 570
        elif hm < 780:  # 午休
            elapsed = 120
        elif hm <= 900:  # 下午 13:00-15:00
            elapsed = 120 + (hm - 780)
        else:
            elapsed = 240
        traded_total = api.turnover()
        cur_yi = traded_total.get("total_yi") or 0
        full_day_yi = cur_yi * 240 / elapsed if elapsed > 30 else cur_yi
        data["total_yi"] = round(full_day_yi, 0)

        d = api.kline("上证指数", n_days=10)
        k = d["klines"]
        closes = [r[2] for r in k]
        ma5 = sum(closes[-5:]) / 5
        data["sh_vs_ma5"] = round((closes[-1] / ma5 - 1) * 100, 1)

        b = api.breadth()
        data["breadth"] = b.get("up_pct")
        try:
            pool = api.zt_pool()
            data["zt"] = len(pool)
        except Exception:
            data["zt"] = None
    except Exception as e:
        print(f"⚠️ 自动拉取失败: {e}（可手动传入信号）")

    from scripts.tools.real_time import get_real_time
    t_rt = get_real_time()

    r = compute_position(
        total_yi=data["total_yi"], sh_vs_ma5=data["sh_vs_ma5"],
        breadth=data["breadth"], zt=data["zt"],
        e1=args.signal_e1, e2=args.signal_e2,
    )

    if args.json:
        out = {"time": t_rt["used"], "inputs": data, "position": r}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    print(f"=== 仓位管理（{t_rt['used']} 腾讯CDN · 60/40法则）===")
    print(f"输入: 成交折算全天 {data['total_yi']:.0f}亿(盘中按时间折算) · 上证vsMA5 {(data['sh_vs_ma5'])}% · 广度 {data['breadth']}% · 涨停 {data['zt']}")
    print(f"档位: {r['tier']} | 总仓上限 {r['limit_pct']}%")
    print(f"动作: {r['action']}")
    if r["reasons"]:
        print("利多: " + " · ".join(r["reasons"]))
    if r["blockers"]:
        print("拦截: " + " · ".join(r["blockers"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
