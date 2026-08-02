#!/usr/bin/env python3
"""
data_gate 字段级验证逻辑单元测试（无网络依赖）

覆盖：板块推断、数值转换、价格/涨跌幅/量/成交额/OHLC/北向/涨跌停 字段校验、
      audit 记录结构、strict 模式抛错。
运行: python -m pytest tests/test_data_gate.py -v
"""

import os
import sys

# 项目根加入 sys.path（data_gate 内部以 scripts. 前缀导入）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from scripts.data_gate import (  # noqa: E402
    DataGate,
    AuditEntry,
    AuditLevel,
    _infer_board,
)


# ============ _infer_board 板块推断 ============

class TestInferBoard:
    def test_sh_main_board(self):
        assert _infer_board("sh600000") == "主板"

    def test_sz_main_board(self):
        assert _infer_board("sz000001") == "主板"

    def test_kechuang(self):
        assert _infer_board("sh688981") == "科创板"

    def test_chuangye_300(self):
        assert _infer_board("sz300750") == "创业板"

    def test_chuangye_301(self):
        assert _infer_board("sz301236") == "创业板"

    def test_beijiao_old_segment(self):
        # 北交所老号段 43/83/87 与 920 新号段统一归北交所
        assert _infer_board("bj430047") == "北交所"
        assert _infer_board("920001") == "北交所"

    def test_empty_code_defaults_main(self):
        assert _infer_board("") == "主板"


# ============ _to_num 数值转换 ============

class TestToNum:
    def test_float_string(self):
        g = DataGate()
        assert g._to_num("12.5", "价格", "T", "m") == 12.5

    def test_int_input(self):
        g = DataGate()
        assert g._to_num(8, "成交额", "T", "m") == 8.0

    def test_non_numeric_logs_fail(self):
        g = DataGate()
        assert g._to_num("abc", "价格", "T", "m") is None
        fails = [e for e in g.audit if e.level == AuditLevel.FAIL]
        assert len(fails) == 1
        assert "非数字" in fails[0].message

    def test_none_input(self):
        g = DataGate()
        assert g._to_num(None, "价格", "T", "m") is None


# ============ _v_price 价格校验 ============

class TestVPrice:
    def test_positive_price_ok(self):
        g = DataGate()
        g._v_price(10.5, "平安银行", "sz000001", "T", "t")
        assert g.audit == []

    def test_zero_price_fail(self):
        g = DataGate()
        g._v_price(0, "平安银行", "sz000001", "T", "t")
        assert g.audit[-1].level == AuditLevel.FAIL
        assert "不可能<=0" in g.audit[-1].message

    def test_negative_price_fail(self):
        g = DataGate()
        g._v_price(-3, "平安银行", "sz000001", "T", "t")
        assert g.audit[-1].level == AuditLevel.FAIL

    def test_index_below_lower_bound_fail(self):
        # 上证指数 (sh000001) 区间 [2000,7000]，<lo*0.5=1000 → FAIL
        g = DataGate()
        g._v_price(800, "上证指数", "sh000001", "T", "t")
        assert g.audit[-1].level == AuditLevel.FAIL

    def test_index_slightly_low_warn(self):
        # 1500 ∈ [1000,1600) → WARN 偏低
        g = DataGate()
        g._v_price(1500, "上证指数", "sh000001", "T", "t")
        assert g.audit[-1].level == AuditLevel.WARN

    def test_index_above_upper_bound_fail(self):
        # >hi*1.5=10500 → FAIL
        g = DataGate()
        g._v_price(20000, "上证指数", "sh000001", "T", "t")
        assert g.audit[-1].level == AuditLevel.FAIL

    def test_index_slightly_high_warn(self):
        # 9000 ∈ (8400,10500] → WARN 偏高
        g = DataGate()
        g._v_price(9000, "上证指数", "sh000001", "T", "t")
        assert g.audit[-1].level == AuditLevel.WARN

    def test_index_in_range_ok(self):
        g = DataGate()
        g._v_price(3200, "上证指数", "sh000001", "T", "t")
        assert g.audit == []

    def test_non_numeric_price(self):
        g = DataGate()
        g._v_price("--", "平安银行", "sz000001", "T", "t")
        assert g.audit[-1].level == AuditLevel.FAIL


# ============ _v_chg 涨跌幅校验 ============

class TestVChg:
    def test_normal_pct_ok(self):
        g = DataGate()
        g._v_chg(3.5, "平安银行", "sz000001", "T", "t")
        assert g.audit == []

    def test_exceeds_main_limit(self):
        # 主板 ±11%
        g = DataGate()
        g._v_chg(12.0, "平安银行", "sz000001", "T", "t")
        assert g.audit[-1].level == AuditLevel.FAIL
        assert "涨跌幅" in g.audit[-1].message

    def test_chuangye_within_22(self):
        g = DataGate()
        g._v_chg(21.0, "宁德时代", "sz300750", "T", "t")
        assert g.audit == []

    def test_chuangye_exceeds_22(self):
        g = DataGate()
        g._v_chg(23.0, "宁德时代", "sz300750", "T", "t")
        assert g.audit[-1].level == AuditLevel.FAIL

    def test_kechuang_exceeds_22(self):
        g = DataGate()
        g._v_chg(25.0, "中芯国际", "sh688981", "T", "t")
        assert g.audit[-1].level == AuditLevel.FAIL

    def test_negative_pct_ok(self):
        g = DataGate()
        g._v_chg(-9.9, "平安银行", "sz000001", "T", "t")
        assert g.audit == []


# ============ _v_vol 成交量校验 ============

class TestVVol:
    def test_normal_ok(self):
        g = DataGate()
        g._v_vol(500000, "平安银行成交量", "T", "t")
        assert g.audit == []

    def test_zero_info(self):
        g = DataGate()
        g._v_vol(0, "平安银行成交量", "T", "t")
        assert g.audit[-1].level == AuditLevel.INFO
        assert "停牌" in g.audit[-1].message

    def test_negative_warn(self):
        g = DataGate()
        g._v_vol(-100, "平安银行成交量", "T", "t")
        assert g.audit[-1].level == AuditLevel.WARN


# ============ _v_turnover 成交额校验 ============

class TestVTurnover:
    def test_normal_ok(self):
        g = DataGate()
        g._v_turnover(8000, "全市场成交额", "T", "t")
        assert g.audit == []

    def test_zero_warn(self):
        g = DataGate()
        g._v_turnover(0, "全市场成交额", "T", "t")
        assert g.audit[-1].level == AuditLevel.WARN

    def test_low_turnover_warn(self):
        # <500 亿
        g = DataGate()
        g._v_turnover(200, "全市场成交额", "T", "t")
        assert g.audit[-1].level == AuditLevel.WARN
        assert "缩量" in g.audit[-1].message

    def test_high_turnover_warn(self):
        # >50000 亿
        g = DataGate()
        g._v_turnover(60000, "全市场成交额", "T", "t")
        assert g.audit[-1].level == AuditLevel.WARN
        assert "放量" in g.audit[-1].message


# ============ _v_ohlc OHLC 一致性 ============

class TestVOhlc:
    def test_all_zero_warn(self):
        g = DataGate()
        g._v_ohlc(0, 0, 0, 0, "sh000001@2026-08-01", "T", "t")
        assert g.audit[-1].level == AuditLevel.WARN
        assert "全零" in g.audit[-1].message

    def test_high_less_than_max_fail(self):
        # H < max(O,C)
        g = DataGate()
        g._v_ohlc(10, 9, 8, 11, "sh000001@2026-08-01", "T", "t")
        assert g.audit[-1].level == AuditLevel.FAIL

    def test_low_greater_than_min_fail(self):
        # L > min(O,C)
        g = DataGate()
        g._v_ohlc(10, 12, 11, 9, "sh000001@2026-08-01", "T", "t")
        assert g.audit[-1].level == AuditLevel.FAIL

    def test_valid_ohlc_ok(self):
        g = DataGate()
        g._v_ohlc(10, 12, 8, 11, "sh000001@2026-08-01", "T", "t")
        assert g.audit == []


# ============ _v_north 北向资金校验 ============

class TestVNorth:
    def test_normal_ok(self):
        g = DataGate()
        g._v_north(30.5, "北向2026-08-01", "EM", "t")
        assert g.audit == []

    def test_zero_info(self):
        g = DataGate()
        g._v_north(0, "北向2026-08-01", "EM", "t")
        assert g.audit[-1].level == AuditLevel.INFO

    def test_outflow_too_large_warn(self):
        # <-500 亿
        g = DataGate()
        g._v_north(-600, "北向2026-08-01", "EM", "t")
        assert g.audit[-1].level == AuditLevel.WARN

    def test_inflow_too_large_warn(self):
        # >500 亿
        g = DataGate()
        g._v_north(600, "北向2026-08-01", "EM", "t")
        assert g.audit[-1].level == AuditLevel.WARN


# ============ _v_zt_dt 涨跌停/炸板率校验 ============

class TestVZtDt:
    def test_normal_ok(self):
        g = DataGate()
        g._v_zt_dt(50, 5, 20.0, "涨停@2026-08-01", "EM", "t")
        assert g.audit == []

    def test_zt_zero_warn(self):
        g = DataGate()
        g._v_zt_dt(0, 5, 20.0, "涨停@2026-08-01", "EM", "t")
        warns = [e for e in g.audit if e.level == AuditLevel.WARN]
        assert any("涨停=0" in e.message for e in warns)

    def test_zt_too_few_warn(self):
        g = DataGate()
        g._v_zt_dt(3, 5, 20.0, "涨停@2026-08-01", "EM", "t")
        warns = [e for e in g.audit if e.level == AuditLevel.WARN]
        assert any("极端弱市" in e.message for e in warns)

    def test_zt_too_many_warn(self):
        g = DataGate()
        g._v_zt_dt(600, 5, 20.0, "涨停@2026-08-01", "EM", "t")
        warns = [e for e in g.audit if e.level == AuditLevel.WARN]
        assert any("数据可疑" in e.message for e in warns)

    def test_dt_crash_warn(self):
        g = DataGate()
        g._v_zt_dt(50, 2500, 20.0, "涨停@2026-08-01", "EM", "t")
        warns = [e for e in g.audit if e.level == AuditLevel.WARN]
        assert any("熔断级" in e.message for e in warns)

    def test_dt_panic_warn(self):
        g = DataGate()
        g._v_zt_dt(50, 500, 20.0, "涨停@2026-08-01", "EM", "t")
        warns = [e for e in g.audit if e.level == AuditLevel.WARN]
        assert any("恐慌" in e.message for e in warns)

    def test_zrr_out_of_range_warn(self):
        g = DataGate()
        g._v_zt_dt(50, 5, 95.0, "涨停@2026-08-01", "EM", "t")
        warns = [e for e in g.audit if e.level == AuditLevel.WARN]
        assert any("炸板率" in e.message for e in warns)


# ============ 审计记录结构与 strict 模式 ============

class TestAuditAndStrict:
    def test_audit_entry_defaults(self):
        e = AuditEntry(AuditLevel.WARN, "T", "m", "f", 1, ">0", "msg")
        assert e.level == AuditLevel.WARN
        assert e.detail == {}
        assert e.timestamp  # 自动生成时间戳

    def test_strict_raises_on_fail(self):
        g = DataGate(strict=True)
        with pytest.raises(ValueError):
            g._v_price(0, "平安银行", "sz000001", "T", "t")

    def test_strict_no_raise_on_valid(self):
        g = DataGate(strict=True)
        g._v_price(10.5, "平安银行", "sz000001", "T", "t")  # 不抛错
        assert g.audit == []

    def test_strict_ignores_warn(self):
        g = DataGate(strict=True)
        g._v_turnover(200, "全市场成交额", "T", "t")  # WARN 不抛错
        assert g.audit[-1].level == AuditLevel.WARN

    def test_fields_counter_increments(self):
        g = DataGate()
        g._v_price(10.5, "平安银行", "sz000001", "T", "t")
        g._v_chg(2.0, "平安银行", "sz000001", "T", "t")
        assert g._fields == 2


# ============ audit_summary 审计统计 ============

class TestAuditSummary:
    def test_empty_audit(self):
        g = DataGate()
        assert g.audit_summary() == {"OK": 0, "INFO": 0, "WARN": 0, "FAIL": 0, "CROSS": 0}

    def test_mixed_levels_counted(self):
        g = DataGate()
        g._v_price(0, "平安银行", "sz000001", "T", "t")      # FAIL
        g._v_vol(0, "成交量", "T", "t")                        # INFO
        g._v_turnover(200, "成交额", "T", "t")                 # WARN
        s = g.audit_summary()
        assert s["FAIL"] == 1 and s["INFO"] == 1 and s["WARN"] == 1

    def test_multiple_same_level(self):
        g = DataGate()
        g._v_price(-1, "平安银行", "sz000001", "T", "t")
        g._v_price(-2, "平安银行", "sz000001", "T", "t")
        assert g.audit_summary()["FAIL"] == 2


# ============ audit_markdown 审计报告格式化 ============

class TestAuditMarkdown:
    def test_empty_note(self):
        g = DataGate()
        out = g.audit_markdown()
        assert "无数据调用记录" in out
        assert "## 数据验证审计报告" in out

    def test_header_counts(self):
        g = DataGate()
        g._v_price(0, "平安银行", "sz000001", "T", "t")   # FAIL
        g._v_vol(0, "成交量", "T", "t")                     # INFO
        out = g.audit_markdown()
        assert "FAIL:1" in out and "INFO:1" in out

    def test_fail_section_with_field(self):
        g = DataGate()
        g._v_price(0, "平安银行", "sz000001", "T", "t")
        out = g.audit_markdown()
        assert "[FAIL] 失败" in out
        assert "平安银行" in out

    def test_consensus_detail_rendered(self):
        g = DataGate()
        g._log(AuditLevel.CROSS, "CrossSource", "north_flow", "北向资金·亿",
               10.5, "双源一致", "msg", em=9.8, ts=11.2, consensus=10.5)
        out = g.audit_markdown()
        assert "共识:10.50" in out
        assert "东财:9.8" in out

    def test_truncation_at_20(self):
        g = DataGate()
        for i in range(25):
            g._log(AuditLevel.INFO, "T", "m", f"f{i}", i, ">0", "批量占位")
        out = g.audit_markdown()
        assert "还有 5 条" in out  # 25 - 20 = 5


# ============ diagnose_zero_traps 零值陷阱诊断 ============

class TestDiagnoseZeroTraps:
    def test_north_zero_with_turnover_warns(self):
        g = DataGate()
        g.diagnose_zero_traps(turnover_yi=8000, north_flow_yi=0.0, zt_count=None)
        warns = [e for e in g.audit if e.level == AuditLevel.WARN]
        assert any("ZERO_TRAP" in e.message and "北向" in e.message for e in warns)

    def test_north_zero_low_turnover_no_warn(self):
        g = DataGate()
        g.diagnose_zero_traps(turnover_yi=200, north_flow_yi=0.0, zt_count=None)
        assert g.audit == []

    def test_zt_zero_with_turnover_warns(self):
        g = DataGate()
        g.diagnose_zero_traps(turnover_yi=8000, north_flow_yi=None, zt_count=0)
        warns = [e for e in g.audit if e.level == AuditLevel.WARN]
        assert any("ZERO_TRAP" in e.message and "涨停" in e.message for e in warns)

    def test_normal_values_no_warn(self):
        g = DataGate()
        g.diagnose_zero_traps(turnover_yi=8000, north_flow_yi=25.0, zt_count=50)
        assert g.audit == []

    def test_both_traps_together(self):
        g = DataGate()
        g.diagnose_zero_traps(turnover_yi=8000, north_flow_yi=0.0, zt_count=0)
        warns = [e for e in g.audit if e.level == AuditLevel.WARN]
        assert len(warns) == 2
