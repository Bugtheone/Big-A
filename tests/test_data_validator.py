#!/usr/bin/env python3
"""
数据验证模块单元测试
覆盖：零值陷阱诊断、验证结果结构、验证报告格式化、九指数常量完整性
运行: python -m pytest tests/test_data_validator.py -v
"""

import os
import sys

# 项目根加入 sys.path（data_validator 内部以 scripts. 前缀导入）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from scripts.data_validator import DataValidator, VResult, VStatus  # noqa: E402
from scripts.index_constants import INDEX_CODE_MAP, INDEX_PRICE_BOUNDS, INDEX_KEYS  # noqa: E402


class TestZeroTrap:
    """零值陷阱诊断 — 区分"真实零"与"数据缺失"。"""

    def test_north_flow_zero_with_normal_turnover(self):
        dv = DataValidator()
        warns = dv.diagnose_zero_trap(0.0, 5000, 50)
        assert any("北向=0.00但成交额正常" in w for w in warns)

    def test_north_flow_zero_low_turnover(self):
        dv = DataValidator()
        # 成交额极低 → 更可能本来就是非交易日，不告警
        assert dv.diagnose_zero_trap(0.0, 500, 50) == []

    def test_zt_zero_with_turnover(self):
        dv = DataValidator()
        warns = dv.diagnose_zero_trap(20.0, 5000, 0)
        assert any("涨停=0但有成交" in w for w in warns)

    def test_zt_zero_with_zero_turnover(self):
        dv = DataValidator()
        # 全部为零 → 非交易日，不告警
        assert dv.diagnose_zero_trap(0.0, 0, 0) == []

    def test_normal_values_no_warn(self):
        dv = DataValidator()
        assert dv.diagnose_zero_trap(25.0, 8000, 80) == []


class TestVResult:
    """VResult 数据结构默认值。"""

    def test_default_status_pass(self):
        r = VResult(item="测试")
        assert r.status == VStatus.PASS
        assert r.messages == []
        assert r.consensus is None

    def test_enum_values(self):
        assert VStatus.PASS.value == "PASS"
        assert VStatus.WARN.value == "WARN"
        assert VStatus.FAIL.value == "FAIL"
        assert VStatus.ONLY_ONE.value == "ONLY_ONE"


class TestFormatReport:
    """验证报告 Markdown 格式化。"""

    def test_basic_report(self):
        r1 = VResult(item="北向资金", status=VStatus.PASS, consensus=12.34)
        r2 = VResult(item="板块数据", status=VStatus.WARN, messages=["注意"])
        text = DataValidator.format_report([r1, r2])
        assert "## 数据验证报告" in text
        assert "PASS 1" in text
        assert "WARN 1" in text
        assert "[OK] 北向资金" in text
        assert "[WARN] 板块数据" in text
        assert "12.34" in text

    def test_empty_report(self):
        text = DataValidator.format_report([])
        assert "总览" in text
        assert "0项" in text

    def test_fail_status_icon(self):
        r = VResult(item="成交额", status=VStatus.FAIL)
        assert "[FAIL] 成交额" in DataValidator.format_report([r])


class TestIndexConstants:
    """九大指数常量完整性。"""

    def test_nine_indexes(self):
        assert len(INDEX_KEYS) == 9
        assert len(INDEX_CODE_MAP) == 9

    def test_all_keys_have_bounds(self):
        for k in INDEX_KEYS:
            assert k in INDEX_PRICE_BOUNDS, f"{k} 缺少价格区间"

    def test_code_map_consistency(self):
        # 名称 → (代码, 前缀) → 拼接 key 必须在 INDEX_KEYS 中
        for name, (code, prefix) in INDEX_CODE_MAP.items():
            key = f"{prefix}{code}"
            assert key in INDEX_KEYS, f"{name} 的 key {key} 不在 INDEX_KEYS"

    def test_bounds_reasonable(self):
        for k, (lo, hi) in INDEX_PRICE_BOUNDS.items():
            assert lo < hi, f"{k} 区间下限应小于上限"
            assert lo > 0
