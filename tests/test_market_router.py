#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行情策略路由引擎测试（设计方案 v1.0 工程化验证）

场景覆盖：
  ① 全面性普跌 → 空仓观察（仓位 0）
  ② 全面性普涨 → 趋势跟踪（仓位 100）
  ③ 抱团行情 → 抱团核心策略（唯一买点=龙头回踩）
  ④ E 档（防守）基础仓位 = 10
  ⑤ 板块路由：结构性行情只做主线，禁止非主线
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))


def test_crash_empty():
    from market_router import classify_market, compute_cap
    tags = classify_market(breadth=20, zt=30, down_cnt=4000, mainline_ok=False,
                           turnover_yi=20000, sh_pct=-1.5, sh50_pct=-1.2)
    assert "全面性普跌" in tags
    cap = compute_cap(tags, "E")
    assert cap["final_pct"] == 0, "普跌应空仓"
    print("PASS test_crash_empty")


def test_bull_trend():
    from market_router import classify_market, route_strategy, compute_cap
    tags = classify_market(breadth=70, zt=80, down_cnt=500, mainline_ok=True,
                           turnover_yi=32000, sh_pct=2.0, sh50_pct=1.0)
    assert "全面性普涨" in tags
    strs = route_strategy(tags, "A")
    assert any("趋势跟踪" in s[0] for s in strs)
    cap = compute_cap(tags, "A")
    assert cap["final_pct"] == 100, "全面普涨应满仓"
    print("PASS test_bull_trend")


def test_herding():
    from market_router import classify_market, route_strategy
    tags = classify_market(breadth=35, zt=60, down_cnt=3000, mainline_ok=True,
                           turnover_yi=35000, sh_pct=0.3, sh50_pct=-0.2)
    assert "抱团行情" in tags
    strs = route_strategy(tags, "E")
    assert any("抱团" in s[0] for s in strs)
    print("PASS test_herding")


def test_defense_tier_base():
    from market_router import compute_cap
    cap = compute_cap(["结构性行情"], "E")
    assert cap["base_pct"] == 10, f"E档基础应10: {cap}"
    print("PASS test_defense_tier_base")


def test_sector_route_structural():
    from market_router import route_sectors
    secs = route_sectors(["结构性行情"])
    assert any("主线" in d for d in secs["do"]), f"结构性行情应做主线: {secs}"
    assert any("非主线" in a for a in secs["avoid"])
    print("PASS test_sector_route_structural")


def test_gate_tier_mapping():
    """F/E/D/C/B/A 全部档位映射正确"""
    from market_router import compute_cap
    for tier, expect in [("F", 0), ("E", 10), ("D", 20), ("C", 40), ("B", 70), ("A", 100)]:
        cap = compute_cap([], tier)
        assert cap["base_pct"] == expect, f"{tier} 应 {expect}: {cap}"
    print("PASS test_gate_tier_mapping")


if __name__ == "__main__":
    test_crash_empty()
    test_bull_trend()
    test_herding()
    test_defense_tier_base()
    test_sector_route_structural()
    test_gate_tier_mapping()
    print("\n✅ 全部通过：路由引擎（行情→策略→板块→仓位）可追溯")
