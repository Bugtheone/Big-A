#!/usr/bin/env python3
"""
market_api 纯函数单元测试（无网络依赖）

覆盖：_safe_float / _calc_ma / _is_weekend_date / _resolve_index / _ma_position。
运行: python -m pytest tests/test_market_api.py -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from scripts.market_api import MarketAPI  # noqa: E402


# ============ _safe_float ============

class TestSafeFloat:
    def test_float_string(self):
        assert MarketAPI._safe_float("12.5") == 12.5

    def test_int_input(self):
        assert MarketAPI._safe_float(8) == 8.0

    def test_invalid_string_defaults_zero(self):
        assert MarketAPI._safe_float("abc") == 0.0

    def test_none_defaults_zero(self):
        assert MarketAPI._safe_float(None) == 0.0

    def test_custom_default(self):
        assert MarketAPI._safe_float("--", default=-1.0) == -1.0

    def test_negative_number(self):
        assert MarketAPI._safe_float("-3.14") == -3.14


# ============ _calc_ma ============

class TestCalcMa:
    def test_basic(self):
        assert MarketAPI._calc_ma([1, 2, 3, 4, 5], 3) == 4.0

    def test_insufficient_data_returns_none(self):
        assert MarketAPI._calc_ma([1, 2], 3) is None

    def test_empty_list_returns_none(self):
        assert MarketAPI._calc_ma([], 5) is None

    def test_exact_length(self):
        assert MarketAPI._calc_ma([10, 20, 30], 3) == 20.0

    def test_single_element(self):
        assert MarketAPI._calc_ma([7], 1) == 7.0


# ============ _is_weekend_date ============

class TestIsWeekendDate:
    def test_saturday(self):
        assert MarketAPI._is_weekend_date("2026-08-01") is True

    def test_sunday(self):
        assert MarketAPI._is_weekend_date("2026-08-02") is True

    def test_friday(self):
        assert MarketAPI._is_weekend_date("2026-07-31") is False

    def test_monday(self):
        assert MarketAPI._is_weekend_date("2026-08-03") is False

    def test_invalid_format(self):
        assert MarketAPI._is_weekend_date("not-a-date") is False

    def test_empty_string(self):
        assert MarketAPI._is_weekend_date("") is False


# ============ _resolve_index ============

class TestResolveIndex:
    def test_chinese_name(self):
        assert MarketAPI._resolve_index("上证指数") == ("000001", "sh")

    def test_chinese_name_cyb(self):
        assert MarketAPI._resolve_index("创业板指") == ("399006", "sz")

    def test_bare_code(self):
        assert MarketAPI._resolve_index("000001") == ("000001", "sh")

    def test_code_sz399006(self):
        assert MarketAPI._resolve_index("399006") == ("399006", "sz")

    def test_unknown_defaults_sh(self):
        assert MarketAPI._resolve_index("999999") == ("999999", "sh")

    def test_empty_defaults_sh(self):
        assert MarketAPI._resolve_index("") == ("", "sh")


# ============ _ma_position ============

class TestMaPosition:
    def test_above_ma5_below_ma20(self):
        ind = {"latest_close": 100, "ma5": 98, "ma10": 99, "ma20": 105}
        out = MarketAPI._ma_position([], ind)
        assert "站上MA5" in out and "跌破MA20" in out

    def test_golden_cross_ma5_ma10(self):
        ind = {"latest_close": 100, "ma5": 99, "ma10": 98, "ma20": 97}
        out = MarketAPI._ma_position([], ind)
        assert "金叉" in out

    def test_death_cross_ma10_ma20(self):
        ind = {"latest_close": 90, "ma5": 92, "ma10": 94, "ma20": 93}
        out = MarketAPI._ma_position([], ind)
        assert "死叉" in out

    def test_insufficient_data(self):
        ind = {"latest_close": 100, "ma5": None, "ma10": None, "ma20": None}
        assert MarketAPI._ma_position([], ind) == "数据不足"

    def test_partial_ma_only_ma5(self):
        ind = {"latest_close": 100, "ma5": 95, "ma10": None, "ma20": None}
        out = MarketAPI._ma_position([], ind)
        assert "站上MA5" in out and "MA10" not in out

    def test_all_below(self):
        ind = {"latest_close": 50, "ma5": 60, "ma10": 70, "ma20": 80}
        out = MarketAPI._ma_position([], ind)
        assert "跌破MA5" in out and "跌破MA10" in out and "跌破MA20" in out
