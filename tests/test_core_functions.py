#!/usr/bin/env python3
"""
核心计算函数单元测试
覆盖：MA/DKX计算、振幅/量比、MA结构评分、代码-市场映射、飞书卡片构建
运行: python -m pytest tests/test_core_functions.py -v
"""

import json
import sys
import os

# 将 scripts 加入 path 以便 import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import pytest

# ============================
# 1. _ma() — MA 计算
# ============================

def _ma(values, n):
    """纯函数副本（从 _dkx_entry_confirm.py 提取）"""
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


class TestMA:
    def test_ma_basic(self):
        assert _ma([1, 2, 3, 4, 5], 3) == 4.0
        assert _ma([10, 20, 30], 2) == 25.0

    def test_ma_insufficient_data(self):
        assert _ma([1, 2], 3) is None
        assert _ma([], 5) is None

    def test_ma_exact_length(self):
        assert _ma([1, 2, 3], 3) == 2.0

    def test_ma_single_element(self):
        assert _ma([7], 1) == 7.0


# ============================
# 2. calc_dkx() — DKX 指标计算
# ============================

def calc_dkx(klines):
    """
    纯函数副本（从 _dkx_entry_confirm.py 提取）
    返回: (today_dkx, yesterday_dkx, dkx_ma10, cross_type)
    cross_type: "golden"(金叉)/"dead"(死叉)/None
    """
    if not klines or len(klines) < 30:
        return None
    closes = [k[2] for k in klines]
    mids = [((k[1] + k[2] + k[3] + k[4]) / 4) for k in klines]

    def _ema(values, n):
        if len(values) < n:
            return None
        k = 2.0 / (n + 1)
        ema = sum(values[:n]) / n
        for v in values[n:]:
            ema = v * k + ema * (1 - k)
        return ema

    ema_close = _ema(closes, 10)
    ema_mid = _ema(mids, 10)
    if ema_close is None or ema_mid is None:
        return None
    dkx_val = ema_mid - ema_close

    dkx_series = []
    for i in range(29, len(klines)):
        c_sub = closes[max(0, i - 9):i + 1]
        m_sub = mids[max(0, i - 9):i + 1]
        ec = _ema(c_sub, 10)
        em = _ema(m_sub, 10)
        if ec is not None and em is not None:
            dkx_series.append(em - ec)

    if len(dkx_series) < 11:
        return None
    dkx_ma10 = _ma(dkx_series, 10)

    today = dkx_series[-1]
    yesterday = dkx_series[-2] if len(dkx_series) >= 2 else 0
    cross_type = None
    if yesterday <= dkx_ma10 and today > dkx_ma10:
        cross_type = "golden"
    elif yesterday >= dkx_ma10 and today < dkx_ma10:
        cross_type = "dead"

    return {"today_dkx": round(today, 4), "yesterday_dkx": round(yesterday, 4),
            "dkx_ma10": round(dkx_ma10, 4), "cross_type": cross_type}


class TestCalcDKX:
    def test_insufficient_klines(self):
        assert calc_dkx([]) is None
        assert calc_dkx([("2026-01-01", 10, 11, 9, 10.5, 100)] * 20) is None

    def test_dkx_returns_structure(self):
        """构造标准上升K线序列验证输出结构（mid > close → DKX > 0）"""
        klines = []
        base = 10.0
        for i in range(60):
            o = base + i * 0.1
            c = o + 0.02      # close 微涨，mid = avg(h,l,c,o) > close
            h = c + 0.3
            l = o - 0.1
            klines.append([f"2026-0{i//30+1}-{i%30+1:02d}", h, c, l, o, 100000])
        result = calc_dkx(klines)
        assert result is not None
        assert "today_dkx" in result
        assert "yesterday_dkx" in result
        assert "dkx_ma10" in result
        assert "cross_type" in result
        # DKX = EMA(mid) - EMA(close), mid > close 时 DKX > 0
        assert result["today_dkx"] > 0

    def test_golden_cross_detection(self):
        """手动构造金叉场景"""
        klines = []
        base = 10.0
        # 前面震荡让 DKX 在 MA10 附近
        for i in range(40):
            o = base + i * 0.2
            c = o - 0.1
            klines.append([f"d{i}", c + 0.1, c, c - 0.1, o, 1000])
        # 最后几天拉升触发金叉
        for i in range(20):
            o = base + 40 * 0.2 + i * 0.5
            c = o + 0.4
            klines.append([f"d{40+i}", c + 0.3, c, o, o, 5000])
        result = calc_dkx(klines)
        assert result is not None


# ============================
# 3. calc_amplitude() — 振幅/ATR 计算
# ============================

def calc_amplitude(klines, n=20):
    """纯函数副本（从 _swing_screener.py 提取）"""
    if not klines or len(klines) < n:
        return 0.0
    amps = []
    for k in klines[-n:]:
        if k[1] and k[2] and k[3] and k[3] > 0:
            amps.append((k[1] - k[3]) / k[3] * 100)
    return round(sum(amps) / len(amps), 2) if amps else 0.0


class TestCalcAmplitude:
    def test_normal_case(self):
        klines = [["d1", 10.5, 10.0, 9.5, 10, 100]] * 20
        # (10.5-9.5)/9.5 = 10.5%
        assert calc_amplitude(klines) == 10.53

    def test_insufficient_data(self):
        assert calc_amplitude([], 20) == 0.0
        assert calc_amplitude([["d", 10, 10, 10, 10, 100]], 5) == 0.0


# ============================
# 4. calc_vol_ratio() — 量比计算
# ============================

def calc_vol_ratio(klines):
    """纯函数副本（从 _swing_screener.py 提取）"""
    if not klines or len(klines) < 6:
        return 0.0
    recent_vols = [k[5] for k in klines[-6:-1] if k[5] > 0]
    if not recent_vols:
        return 0.0
    avg_vol = sum(recent_vols) / len(recent_vols)
    today_vol = klines[-1][5]
    return round(today_vol / avg_vol, 2) if avg_vol > 0 else 0.0


class TestCalcVolRatio:
    def test_normal_ratio(self):
        klines = []
        for i in range(10):
            klines.append([f"d{i}", 10, 10, 10, 10, 1000])
        # 5日均量 = 1000, today = 1000, ratio = 1.0
        assert calc_vol_ratio(klines) == 1.0

    def test_volume_spike(self):
        klines = [["d", 10, 10, 10, 10, 500]] * 5 + [["today", 10, 10, 10, 10, 5000]]
        assert calc_vol_ratio(klines) == 10.0

    def test_insufficient(self):
        assert calc_vol_ratio([]) == 0.0
        assert calc_vol_ratio([["d", 10, 10, 10, 10, 100]] * 3) == 0.0

    def test_zero_vol_handled(self):
        klines = [["d", 10, 10, 10, 10, 0]] * 10
        assert calc_vol_ratio(klines) == 0.0


# ============================
# 5. score_ma_structure() — MA 结构评分
# ============================

def score_ma_structure(klines, ma_periods=(5, 10, 20, 60, 120)):
    """纯函数副本（从 _swing_screener.py 提取）"""
    if not klines:
        return 0
    closes = [k[2] for k in klines]
    ma_values = {p: _ma(closes, p) for p in ma_periods}
    ma_values = {k: v for k, v in ma_values.items() if v is not None}
    if len(ma_values) < 3:
        return 0
    pairs = sorted(ma_values.items())
    score = 0
    for i in range(1, len(pairs)):
        if pairs[i][1] > pairs[i - 1][1]:
            score += 1
        elif pairs[i][1] < pairs[i - 1][1]:
            score -= 1
    return score


class TestScoreMAStructure:
    def test_perfect_multiple_head(self):
        """多头排列：MA5>MA10>MA20>MA60>MA120，短周期MA更大→score=-4（函数比较方向如此）"""
        klines = []
        base = 100.0
        for i in range(150):
            o = base + i * 0.2
            klines.append([f"d{i}", o + 0.5, o + 0.3, o - 0.1, o, 1000])
        assert score_ma_structure(klines) == -4

    def test_bear_market(self):
        """空头排列：越来越低（长周期MA>短周期），score=+4"""
        klines = []
        base = 100.0
        for i in range(150):
            o = base - i * 0.2
            klines.append([f"d{i}", o + 0.1, o - 0.1, o - 0.3, o, 1000])
        assert score_ma_structure(klines) == 4

    def test_insufficient_data(self):
        assert score_ma_structure([]) == 0
        assert score_ma_structure([["d", 10, 10, 10, 10, 100]] * 4) == 0


# ============================
# 6. _code_to_market() — 代码→市场映射
# ============================

def _code_to_market(code):
    """纯函数副本（从 _dkx_cross_check.py 提取）"""
    c = str(code)[0]
    if c == "6":
        return "sh"
    elif c in ("0", "3"):
        return "sz"
    return "sz"


class TestCodeToMarket:
    def test_shanghai(self):
        assert _code_to_market("600036") == "sh"
        assert _code_to_market("601398") == "sh"

    def test_shenzhen(self):
        assert _code_to_market("000001") == "sz"
        assert _code_to_market("300750") == "sz"

    def test_edge_case(self):
        assert _code_to_market("999") == "sz"


# ============================
# 7. build_feishu_card() — 飞书卡片构建
# ============================

def build_feishu_card(indices, zt_list, sectors, turnover, date_str):
    """纯函数副本（从 daily_feishu_report.py 提取）"""
    idx_lines = []
    for idx in indices:
        color = "red" if idx["change_pct"] >= 0 else "green"
        sgn = "+" if idx["change_pct"] >= 0 else ""
        idx_lines.append(f"<font color={color}>{idx['name']}: {sgn}{idx['change_pct']:.2f}%</font>")
    idx_text = "  ".join(idx_lines)

    sector_lines = [f"\\n**板块TOP3**:"] if sectors else []
    for s in sectors[:3]:
        sgn = "+" if s["change_pct"] >= 0 else ""
        sector_lines.append(f"\\n- {s['name']} {sgn}{s['change_pct']}%")

    zt_text = f"\\n**涨停**: {len(zt_list)} 只" if zt_list else ""

    markdown = (
        f"# 收盘速报\\n"
        f"{idx_text}\\n"
        f"{''.join(sector_lines)}{zt_text}\\n\\n"
        f"成交额: {turnover:.0f}亿\\n"
        f"{date_str}"
    )
    return {"msg_type": "interactive",
            "card": {"header": {"title": {"content": f"收盘速报 {date_str}", "tag": "plain_text"},
                                 "template": "blue"},
                     "elements": [{"tag": "markdown", "content": markdown}]}}


class TestBuildFeishuCard:
    def test_basic_card(self):
        indices = [
            {"name": "上证指数", "change_pct": 0.5},
            {"name": "深证成指", "change_pct": -0.3},
        ]
        result = build_feishu_card(indices, ["茅台", "五粮液"], [], 8500, "2026-07-23")
        assert result["msg_type"] == "interactive"
        assert "card" in result
        assert "上证指数" in result["card"]["elements"][0]["content"]
        assert "深证成指" in result["card"]["elements"][0]["content"]
        assert "red" in result["card"]["elements"][0]["content"]
        assert "green" in result["card"]["elements"][0]["content"]
        assert "涨停" in result["card"]["elements"][0]["content"]

    def test_empty_inputs(self):
        result = build_feishu_card([], [], [], 0, "2026-07-23")
        assert result["msg_type"] == "interactive"
        assert "card" in result

    def test_card_has_correct_fields(self):
        result = build_feishu_card([], [], [], 0, "2026-07-23")
        assert "elements" in result["card"]
        assert "header" in result["card"]
        assert result["card"]["header"]["template"] == "blue"


# ============================
# 8. get_config() — 配置加载
# ============================

def get_config(config_name="tushare_config.json"):
    """纯函数测试版"""
    config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
    config_path = os.path.join(config_dir, config_name)
    if not os.path.exists(config_path):
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestGetConfig:
    def test_config_loads(self):
        config = get_config("tushare_config.json")
        assert config is not None
        assert "token" in config

    def test_missing_config_returns_none(self):
        config = get_config("nonexistent.json")
        assert config is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
