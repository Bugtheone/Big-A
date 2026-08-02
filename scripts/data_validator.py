#!/usr/bin/env python3
"""数据验证审查模块 — 跨源交叉验证 + 数值合理性检查。"""

from __future__ import annotations
import os, sys, time

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
import io
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# 收敛九指数定义（原此处复制了一份 INDEX_PRICE_RANGES，现统一引用公共常量）
from scripts.index_constants import INDEX_PRICE_BOUNDS

# ---- 阈值常量 ----
NORTH_FLOW_MAX_DIFF_YI = 20.0
LIMIT_UP_MIN, LIMIT_UP_MAX = 10, 500
LIMIT_DOWN_NORMAL, LIMIT_DOWN_CRASH = 300, 2000
ZR_RATE_MIN, ZR_RATE_MAX = 0.0, 80.0
TURNOVER_MIN, TURNOVER_MAX = 1000, 50000
INDEX_PCT_RANGE = (-12.0, 12.0)

INDEX_PRICE_RANGES: Dict[str, Tuple[float, float]] = dict(INDEX_PRICE_BOUNDS)  # noqa: F821（收敛九指数定义，见下方导入）

class VStatus(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    ONLY_ONE = "ONLY_ONE"

@dataclass
class VResult:
    item: str
    status: VStatus = VStatus.PASS
    sources: Dict[str, Any] = field(default_factory=dict)
    consensus: Any = None
    messages: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)


class DataValidator:
    """数据验证审查器 — 跨源交叉验证 + 数值合理性检查。"""

    def __init__(self):
        self._em = self._tc = None

    @property
    def em(self):
        if self._em is None:
            from scripts.eastmoney_api import get_eastmoney
            self._em = get_eastmoney()
        return self._em

    @property
    def tc(self):
        if self._tc is None:
            from scripts.tencent_api import get_tencent
            self._tc = get_tencent()
        return self._tc

    # ==================== 北向资金交叉验证 ====================

    def validate_north_flow(self, date: str) -> VResult:
        """交叉验证：东财kamt v2 vs Tushare moneyflow_hsgt。自动检测单源延迟。"""
        r = VResult(item="北向资金(净买入·亿元)")
        sources: Dict[str, Any] = {}

        # 源1: 东财 kamt.kline v2
        try:
            em_data = self.em.fetch_north_flow(lmt=1)
            if em_data:
                sources["东财kamt"] = em_data[0]["total_yi"]
                r.detail["em_date"] = em_data[0].get("date", "?")
        except Exception as e:
            sources["东财kamt"] = None
            r.detail["em_error"] = str(e)

        # 源2: Tushare
        try:
            from scripts.tushare_api import fetch_moneyflow_hsgt
            ts_data = fetch_moneyflow_hsgt(end_date=date)
            if ts_data:
                match = next((row for row in ts_data if row.get("date") == date), ts_data[-1])
                if match:
                    sources["Tushare"] = match["north_flow_yi"]
                    r.detail["ts_date"] = match.get("date", "?")
                    r.detail["ts_sh"] = match.get("sh_north_yi", 0)
                    r.detail["ts_sz"] = match.get("sz_north_yi", 0)
        except Exception as e:
            sources["Tushare"] = None
            r.detail["ts_error"] = str(e)

        r.sources = sources
        em_v, ts_v = sources.get("东财kamt"), sources.get("Tushare")

        if em_v is None and ts_v is None:
            r.status, r.consensus = VStatus.FAIL, None
            r.messages.append("FAIL: 两个数据源均无数据")
            return r

        # 单源可用
        if em_v is None or ts_v is None:
            val = em_v if ts_v is None else ts_v
            source = "东财kamt" if em_v is not None else "Tushare"
            r.status = VStatus.ONLY_ONE
            r.consensus = val
            if val == 0.0:
                r.status = VStatus.WARN
                r.messages.append(f"WARN: {source} 返回 0.00亿，可能是盘后数据尚未发布")
            else:
                r.messages.append(f"ONLY_ONE: 仅{source}可用 ({val:+.2f}亿)")
            return r

        # 双源可用 → 交叉比对
        diff = abs(em_v - ts_v)
        r.detail["diff_yi"] = round(diff, 2)

        if diff < 5.0:
            r.status = VStatus.PASS
            r.consensus = round((em_v + ts_v) / 2, 2)
            r.messages.append(f"PASS: 两源一致 东财={em_v}亿 Tushare={ts_v}亿 diff={diff:.2f}亿")
        elif em_v == 0.0 and ts_v != 0.0:
            r.status, r.consensus = VStatus.WARN, ts_v
            r.messages.append(f"WARN: 东财0.00 vs Tushare{ts_v:+.2f}亿 → 东财盘后延迟，以Tushare为准")
        elif ts_v == 0.0 and em_v != 0.0:
            r.status, r.consensus = VStatus.WARN, em_v
            r.messages.append(f"WARN: Tushare0.00 vs 东财{em_v:+.2f}亿 → Tushare延迟，以东财为准")
        elif diff > NORTH_FLOW_MAX_DIFF_YI:
            r.status = VStatus.FAIL
            r.consensus = em_v if em_v != 0 else ts_v
            r.messages.append(f"FAIL: 两源差异过大 东财={em_v}亿 Tushare={ts_v}亿 diff={diff:.2f}亿")
        else:
            r.status, r.consensus = VStatus.WARN, round((em_v + ts_v) / 2, 2)
            r.messages.append(f"WARN: 有差异 东财={em_v}亿 Tushare={ts_v}亿 diff={diff:.2f}亿")

        return r

    # ==================== 打板数据验证 ====================

    def validate_board_data(self, date: str) -> VResult:
        """验证：涨停/跌停/炸板率 数值合理性。"""
        r = VResult(item="打板数据(同花顺)")
        try:
            data = self.em.ths_limit_up_pool(date, page=1, limit=200)
        except Exception as e:
            r.messages.append(f"FAIL: 获取失败: {e}")
            return r

        zt, zb, dt, zrr = data.get("total", 0), data.get("zb_count", 0), data.get("dt_count", 0), data.get("zr_rate", 0.0)
        ztl = len(data.get("zt_list", []))

        r.sources = {"涨停": zt, "炸板": zb, "跌停": dt, "炸板率%": zrr, "列表长度": ztl}
        msgs = []

        if zt == 0:
            msgs.append("FAIL: 涨停数=0，数据不可用")
            r.status = VStatus.FAIL
        elif zt < LIMIT_UP_MIN:
            msgs.append(f"WARN: 涨停{zt}<{LIMIT_UP_MIN}，极端弱市或数据不完整")
        elif zt > LIMIT_UP_MAX:
            msgs.append(f"WARN: 涨停{zt}>{LIMIT_UP_MAX}，数据可疑")

        if dt > LIMIT_DOWN_CRASH:
            msgs.append(f"WARN: 跌停{dt}>{LIMIT_DOWN_CRASH}，数据可疑")
        elif dt > LIMIT_DOWN_NORMAL:
            msgs.append(f"WARN: 跌停{dt}>{LIMIT_DOWN_NORMAL}，市场恐慌")

        if zrr < ZR_RATE_MIN or zrr > ZR_RATE_MAX:
            msgs.append(f"WARN: 炸板率{zrr}%异常")

        if ztl != zt and zt <= 200:
            msgs.append(f"WARN: 列表长度{ztl}≠total{zt}，需分页")

        if r.status != VStatus.FAIL:
            has_fail = any("FAIL" in m for m in msgs)
            has_warn = any("WARN" in m for m in msgs)
            r.status = VStatus.FAIL if has_fail else VStatus.WARN if has_warn else VStatus.PASS
            if not has_fail and not has_warn:
                msgs.append(f"PASS: 涨停{zt} 炸板{zb} 跌停{dt} 炸板率{zrr}%")

        r.messages = msgs
        r.consensus = {"zt_count": zt, "zb_count": zb, "dt_count": dt, "zr_rate": zrr}
        return r

    # ==================== 指数快照验证 ====================

    def validate_index_snapshot(self, index_data: Optional[List[dict]] = None) -> VResult:
        """验证：九大指数价格/涨跌幅 合理性。"""
        r = VResult(item="指数快照")
        if index_data is None:
            try:
                index_data = self.tc.fetch_index_snapshot()
            except Exception as e:
                r.messages.append(f"FAIL: 获取失败: {e}")
                return r

        if not index_data:
            r.messages.append("FAIL: 数据为空"); return r

        msgs, anomalies = [], 0
        for idx in index_data:
            code, name = idx.get("code", "?"), idx.get("name", "?")
            price, pct = idx.get("price", 0), idx.get("change_pct", 0)
            # None 值防御：价格/涨跌幅为 None 时按 0 处理，避免 f-string 格式化抛 TypeError
            if price is None:
                price = 0
            if pct is None:
                pct = 0
            r.sources[name or code] = f"{price:.2f} ({pct:+.2f}%)"

            if code in INDEX_PRICE_RANGES:
                lo, hi = INDEX_PRICE_RANGES[code]
                if price <= 0:
                    msgs.append(f"FAIL: {name} 价格=0 数据缺失"); anomalies += 1
                elif price < lo * 0.8 or price > hi * 1.2:
                    msgs.append(f"WARN: {name} 价格{price}超出[{lo},{hi}]"); anomalies += 1

            if pct == 0 and price > 0 and name not in ("科创50", "创业板指"):
                msgs.append(f"WARN: {name} 涨幅0.00%，可能延迟")

            limit = 22.0 if code in ("sh000688", "sz399006") else 11.0
            if abs(pct) > limit:
                msgs.append(f"FAIL: {name} 涨跌幅{pct:+.2f}%超±{limit}%"); anomalies += 1

        if anomalies:
            has_fail = any("FAIL" in m for m in msgs)
            r.status = VStatus.FAIL if has_fail else VStatus.WARN
        else:
            r.status = VStatus.PASS
            msgs.insert(0, f"PASS: {len(index_data)}指数正常")
        r.messages = msgs
        return r

    # ==================== 成交额验证 ====================

    def validate_turnover(self) -> VResult:
        """验证：全市场成交额合理性。"""
        r = VResult(item="成交额(亿元)")
        try:
            t = self.tc.fetch_turnover_simple()
            r.sources["腾讯"] = t
        except Exception as e:
            r.messages.append(f"FAIL: {e}"); return r

        t = float(t or 0)
        if t == 0:
            r.status, r.messages = VStatus.WARN, ["WARN: 成交额=0，数据未发布"]
        elif t < TURNOVER_MIN:
            r.status, r.messages = VStatus.WARN, [f"WARN: {t}亿<{TURNOVER_MIN}亿 极度缩量"]
        elif t > TURNOVER_MAX:
            r.status, r.messages = VStatus.WARN, [f"WARN: {t}亿>{TURNOVER_MAX}亿 异常放量"]
        else:
            r.status, r.messages = VStatus.PASS, [f"PASS: {t}亿 合理范围"]
        r.consensus = t
        return r

    # ==================== 零值陷阱诊断 ====================

    def diagnose_zero_trap(self, north_flow_yi: float, turnover_yi: float, zt_count: int = -1) -> List[str]:
        """诊断零值：区分"真实零"和"数据缺失"。"""
        w = []
        if north_flow_yi is not None and north_flow_yi == 0 and (turnover_yi or 0) > 1000:
            w.append("ZERO_TRAP: 北向=0.00但成交额正常 → 盘后数据未发布，非真实零值")
        if zt_count == 0 and (turnover_yi or 0) > 0:
            w.append("ZERO_TRAP: 涨停=0但有成交 → API异常或非交易日")
        return w

    # ==================== 一键全量审查 ====================

    def validate_all(self, date: str = None) -> List[VResult]:
        """一键全量审查。返回所有VResult列表，直接打印或消费。"""
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        results = []

        t0 = time.time()
        nf = self.validate_north_flow(date)
        nf.detail["elapsed_s"] = round(time.time() - t0, 2)
        results.append(nf)

        t0 = time.time()
        bd = self.validate_board_data(date)
        bd.detail["elapsed_s"] = round(time.time() - t0, 2)
        results.append(bd)

        t0 = time.time()
        idx = self.validate_index_snapshot()
        idx.detail["elapsed_s"] = round(time.time() - t0, 2)
        results.append(idx)

        t0 = time.time()
        to = self.validate_turnover()
        to.detail["elapsed_s"] = round(time.time() - t0, 2)
        results.append(to)

        # 追加零值陷阱诊断
        turnover_yi = to.consensus
        if nf.consensus is not None and bd.consensus is not None:
            zt = bd.consensus["zt_count"] if isinstance(bd.consensus, dict) else -1
            zero_warns = self.diagnose_zero_trap(nf.consensus, turnover_yi, zt)
            if zero_warns:
                zr = VResult(item="零值陷阱诊断", status=VStatus.WARN,
                             messages=zero_warns, consensus={"north_flow": nf.consensus})
                results.append(zr)

        return results

    # ==================== 验证报告格式化 ====================

    @staticmethod
    def format_report(results: List[VResult]) -> str:
        """将验证结果格式化为 Markdown 报告文本。"""
        lines = ["## 数据验证报告\n"]
        total = len(results)
        pass_n = sum(1 for r in results if r.status == VStatus.PASS)
        warn_n = sum(1 for r in results if r.status == VStatus.WARN)
        fail_n = sum(1 for r in results if r.status == VStatus.FAIL)
        only_n = sum(1 for r in results if r.status == VStatus.ONLY_ONE)

        lines.append(f"**总览**: {total}项 | PASS {pass_n} | WARN {warn_n} | ONLY_ONE {only_n} | FAIL {fail_n}\n")

        for r in results:
            icon = {"PASS": "[OK]", "WARN": "[WARN]", "FAIL": "[FAIL]", "ONLY_ONE": "[1SRC]"}[r.status.value]
            lines.append(f"### {icon} {r.item}")
            for m in r.messages:
                lines.append(f"- {m}")
            if r.consensus is not None:
                if isinstance(r.consensus, dict):
                    lines.append(f"- 共识值: {r.consensus}")
                else:
                    lines.append(f"- 共识值: **{r.consensus}**")
            lines.append("")
        return "\n".join(lines)

    def print_report(self, date: str = None):
        """直接打印验证报告到控制台。"""
        results = self.validate_all(date)
        output = self.format_report(results)
        try:
            print(output)
        except UnicodeEncodeError:
            # GBK fallback
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
            print(output)
        return results


# ==================== 自测 ====================

if __name__ == "__main__":
    dv = DataValidator()
    dv.print_report("20260723")
