#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""entry_point 工具测试：验证介入点计算使用官方K线源且输出可追溯

测试项：
1. 计算可运行（返回 dict 结构完整）
2. 输出含 MA5/MA10/MA20 与偏离度
3. source 字段 = tencent_fqkline（官方前复权源）
4. 对已知标的（工业富联 601138）偏离度与腾讯官方接口直接计算一致
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def test_calc_entry_structure():
    from scripts.tools.entry_point import calc_entry
    r = calc_entry("601138")
    assert "error" not in r, f"计算失败: {r}"
    for k in ["close", "ma5", "ma10", "ma20", "dev_ma5_pct", "dev_ma10_pct",
              "dev_ma20_pct", "state", "entry_zone", "stop"]:
        assert k in r, f"缺少字段 {k}"
    assert r["source"] == "tencent_fqkline", "必须使用腾讯官方前复权K线源"
    assert r["ma5"] > 0 and r["ma10"] > 0
    print("PASS test_calc_entry_structure")


def test_matches_direct_tencent():
    """与直接调用腾讯官方接口计算的 MA 完全一致（防估算）"""
    from scripts.tools.entry_point import calc_entry, _norm
    import requests

    r = calc_entry("601138")
    pref = _norm("601138")
    S = requests.Session()
    S.trust_env = False
    S.headers.update({"User-Agent": "Mozilla/5.0"})
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    resp = S.get(url, params={"param": f"{pref},day,,,30,qfq"}, timeout=10)
    d = resp.json()["data"][pref]
    kl = d.get("qfqday") or d.get("day") or []
    closes = [float(x[2]) for x in kl]
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    assert abs(r["ma5"] - round(ma5, 2)) < 0.02, f"MA5 不一致: {r['ma5']} vs {round(ma5,2)}"
    assert abs(r["ma10"] - round(ma10, 2)) < 0.02, f"MA10 不一致: {r['ma10']} vs {round(ma10,2)}"
    print("PASS test_matches_direct_tencent")


def test_state_classification():
    from scripts.tools.entry_point import calc_entry
    # 工业富联今日 +4.6%，5日 +30%，应判定急拉超买
    r = calc_entry("601138")
    assert "超买" in r["state"] or "急拉" in r["state"], f"状态判定错误: {r['state']}"
    print("PASS test_state_classification")


def test_unknown_code():
    from scripts.tools.entry_point import calc_entry
    r = calc_entry("999999")
    assert "error" in r, "无效代码应返回 error"
    print("PASS test_unknown_code")


def test_qscore_present_and_bounded():
    """Q-score 应存在且 ∈ [0,100]，分级为 A/B/C/D 之一"""
    from scripts.tools.entry_point import calc_entry
    r = calc_entry("000977")
    assert "q_score" in r, "缺少 q_score"
    assert 0 <= r["q_score"] <= 100, f"q_score 越界: {r['q_score']}"
    assert r["q_grade"] in ("A", "B", "C", "D"), f"分级错误: {r['q_grade']}"
    assert len(r["q_factors"]) == 6, "应含六因子"
    assert isinstance(r["vol_ratio_5d"], float)
    assert isinstance(r["pullback_days"], int)
    print(f"PASS test_qscore_present_and_bounded (score={r['q_score']} grade={r['q_grade']})")


def test_qscore_overbought_is_low():
    """急拉超买标的（胜宏 300476，偏离 MA10 >8%）Q-score 应 <60（C/D 级）"""
    from scripts.tools.entry_point import calc_entry
    r = calc_entry("300476")
    if "error" in r:
        print("SKIP test_qscore_overbought_is_low（标的无数据）")
        return
    assert r["q_score"] < 60, f"超买标的评分应<60: {r['q_score']} {r['q_factors']}"
    print(f"PASS test_qscore_overbought_is_low (score={r['q_score']})")


def test_qscore_consistency():
    """Q-score 因子分应等于六因子之和（防拆分不一致）"""
    from scripts.tools.entry_point import calc_entry
    r = calc_entry("603019")
    s = sum(r["q_factors"].values())
    assert s == r["q_score"], f"因子和({s}) != Q-score({r['q_score']})"
    print(f"PASS test_qscore_consistency (sum={s})")


if __name__ == "__main__":
    test_calc_entry_structure()
    test_matches_direct_tencent()
    test_state_classification()
    test_unknown_code()
    test_qscore_present_and_bounded()
    test_qscore_overbought_is_low()
    test_qscore_consistency()
    print("\n✅ 全部通过：entry_point 使用官方K线源，Q-score 六因子可追溯")
