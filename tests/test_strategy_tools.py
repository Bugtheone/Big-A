#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""趋势/突破/仓位三策略工具测试（官方K线源，禁止估算）

覆盖：
  ① trend_tracker: T-score 边界/状态机分级/因子和一致
  ② breakout_detector: B-score 边界/深跌标的低分（防守正确）
  ③ position_sizer: 档位映射/撤退优先/边界输入
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_trend_score_bounded():
    from scripts.tools.trend_tracker import calc_trend
    r = calc_trend("601138")
    assert "error" not in r, f"计算失败: {r}"
    assert 0 <= r["t_score"] <= 100
    assert r["t_grade"] in ("A", "B", "C", "D", "E")
    assert len(r["factors"]) == 6
    assert sum(r["factors"].values()) == r["t_score"], "因子和必须等于 T-score"
    assert r["source"] == "tencent_fqkline"
    print(f"PASS test_trend_score_bounded (score={r['t_score']} {r['state']})")


def test_trend_structure():
    from scripts.tools.trend_tracker import calc_trend
    r = calc_trend("000977")
    for k in ["ma5", "ma10", "ma20", "ma60", "slope20_pct",
              "drawdown_60d_pct", "roc10_pct"]:
        assert k in r, f"缺少字段 {k}"
    print("PASS test_trend_structure")


def test_breakout_bounded():
    from scripts.tools.breakout_detector import calc_breakout
    r = calc_breakout("300476")
    assert "error" not in r, f"计算失败: {r}"
    assert 0 <= r["b_score"] <= 100
    assert r["b_grade"] in ("A", "B", "C", "D")
    assert len(r["factors"]) == 6
    assert sum(r["factors"].values()) == r["b_score"]
    assert r["source"] == "tencent_fqkline"
    print(f"PASS test_breakout_bounded (score={r['b_score']} {r['b_grade']})")


def test_breakout_deep_drawdown_is_low():
    """深跌标的（回撤大）不应判真突破——防守正确性"""
    from scripts.tools.breakout_detector import calc_breakout
    r = calc_breakout("300476")  # 08-06 回撤 17.7%，非突破
    assert r["b_score"] < 60, f"深跌反弹不应判真突破: {r['b_score']}"
    print(f"PASS test_breakout_deep_drawdown_is_low (score={r['b_score']})")


def test_position_retreat_priority():
    """E1/E2 触发 → 防守档（≤10%），撤退优先"""
    from scripts.tools.position_sizer import compute_position
    r = compute_position(total_yi=35000, sh_vs_ma5=0.9, breadth=28.4, zt=58)
    assert r["tier"] == "E", f"E1+E2 应防守: {r['tier']}"
    assert r["limit_pct"] <= 10
    print("PASS test_position_retreat_priority")


def test_position_full_bull():
    """全面多头 → A 档（100%）"""
    from scripts.tools.position_sizer import compute_position
    r = compute_position(total_yi=32000, sh_vs_ma5=1.2, breadth=65.0, zt=75)
    assert r["tier"] == "A", f"全面多头应主升: {r['tier']}"
    assert r["limit_pct"] == 100
    print("PASS test_position_full_bull")


def test_position_watch_no_turnover():
    """成交 <2.5万亿 → F 观望（0%）"""
    from scripts.tools.position_sizer import compute_position
    r = compute_position(total_yi=18000, sh_vs_ma5=0.5, breadth=60.0, zt=70)
    assert r["tier"] == "F", f"成交不足应观望: {r['tier']}"
    assert r["limit_pct"] == 0
    print("PASS test_position_watch_no_turnover")


def test_position_edge_none():
    """全空输入（手动模式）→ 保守试错"""
    from scripts.tools.position_sizer import compute_position
    r = compute_position()
    assert r["tier"] in ("D", "E"), f"空输入应保守: {r['tier']}"
    print(f"PASS test_position_edge_none ({r['tier']})")


if __name__ == "__main__":
    test_trend_score_bounded()
    test_trend_structure()
    test_breakout_bounded()
    test_breakout_deep_drawdown_is_low()
    test_position_retreat_priority()
    test_position_full_bull()
    test_position_watch_no_turnover()
    test_position_edge_none()
    print("\n✅ 全部通过：三策略工具官方K线源 + 档位映射可追溯")
