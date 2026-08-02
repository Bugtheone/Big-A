#!/usr/bin/env python3
"""
Universal Data Gateway -- 全项目数据守门员。
**所有数据访问必须经此守门员**，自动验证每个数值的真实性和准确性。

设计原则:
  1. 返回格式与底层 API 完全一致，不破坏现有代码
  2. 每次调用自动验证，结果累积到审计轨迹
  3. 支持字段级 + 跨源双重验证
  4. 单例模式: `from scripts.data_gate import gate`

用法:
  from scripts.data_gate import gate
  indices = gate.tc_fetch_indices()          # 自动验证价格/涨跌幅
  north   = gate.em_fetch_north_flow_latest() # 自动验证北向资金
  board   = gate.em_fetch_board_summary()     # 自动验证涨停统计
  bf      = gate.em_board_fund_flow()         # 板块资金流向(行业/概念/地域)
  news    = gate.em_cls_telegraph("股市")     # 财联社电报(非交易时段备选)
  gate.print_audit()                          # 打印验证报告
"""

from __future__ import annotations
import os, sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ==================== 审计系统 ====================

class AuditLevel(Enum):
    OK = "OK"; INFO = "INFO"; WARN = "WARN"; FAIL = "FAIL"; CROSS = "CROSS"

@dataclass
class AuditEntry:
    level: AuditLevel; source: str; method: str; field: str
    value: Any; expected: str; message: str
    detail: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))


# ==================== 验证规则常量 ====================

# noqa: E402
from scripts.index_constants import INDEX_PRICE_BOUNDS  # 收敛九指数定义，原此处复制

BOARD_LIMITS = {"主板": 11.0, "创业板": 22.0, "科创板": 22.0, "北交所": 33.0}

# 全市场合理范围
PRICE_MIN, PRICE_MAX = 0.01, 10000.0
TURNOVER_MIN_YI, TURNOVER_MAX_YI = 500, 50000
NORTH_FLOW_MIN_YI, NORTH_FLOW_MAX_YI = -500.0, 500.0
PE_MIN, PE_MAX = 0.0, 10000.0
ZT_COUNT_MIN, ZT_COUNT_MAX = 10, 500
DT_COUNT_NORMAL, DT_COUNT_CRASH = 300, 2000
ZR_RATE_MIN, ZR_RATE_MAX = 0.0, 80.0


def _infer_board(code: str) -> str:
    pure = code.replace("sh","").replace("sz","")
    if pure.startswith("688"): return "科创板"
    if pure.startswith("300") or pure.startswith("301"): return "创业板"
    if pure.startswith(("4","8","92")): return "北交所"
    return "主板"


# ==================== DataGate ====================

class DataGate:
    def __init__(self, strict: bool = False):
        self.strict = strict
        self._tc = self._em = self._pro = self._dv = None
        self.audit: List[AuditEntry] = []
        self._fields: int = 0

    # ---- 懒加载 ----
    @property
    def tc(self):
        if not self._tc:
            from scripts.tencent_api import get_tencent
            self._tc = get_tencent()
        return self._tc
    @property
    def em(self):
        if not self._em:
            from scripts.eastmoney_api import get_eastmoney
            self._em = get_eastmoney()
        return self._em
    @property
    def pro(self):
        if not self._pro:
            from scripts.tushare_api import get_pro
            self._pro = get_pro()
        return self._pro
    @property
    def dv(self):
        if not self._dv:
            from scripts.data_validator import DataValidator
            self._dv = DataValidator()
        return self._dv

    # ---- 审计记录 ----
    def _log(self, level, src, mtd, fld, val, exp, msg, **dtl):
        e = AuditEntry(level, src, mtd, fld, val, exp, msg, dtl)
        self.audit.append(e)
        if self.strict and level == AuditLevel.FAIL:
            raise ValueError(f"[DataGate] {msg}")
        return e

    def _to_num(self, v, lab, src, mtd):
        try:
            return float(v)
        except (ValueError, TypeError):
            self._log(AuditLevel.FAIL, src, mtd, lab, v, "numeric", f"{lab}非数字:{v}")
            return None

    # ========== 字段级验证 ==========

    def _v_price(self, p, lab, code="", src="", mtd=""):
        v = self._to_num(p, lab, src, mtd)
        if v is None: return
        self._fields += 1
        if v <= 0:
            self._log(AuditLevel.FAIL, src, mtd, lab, v, ">0", f"{lab}价格={v}不可能<=0"); return
        if code in INDEX_PRICE_BOUNDS:
            lo, hi = INDEX_PRICE_BOUNDS[code]
            if v < lo*0.5: self._log(AuditLevel.FAIL, src, mtd, lab, v, f">={lo*0.5}", f"{lab}价格{v}<下限{lo}")
            elif v < lo*0.8: self._log(AuditLevel.WARN, src, mtd, lab, v, f"[{lo},{hi}]", f"{lab}价格{v}偏低")
            elif v > hi*1.5: self._log(AuditLevel.FAIL, src, mtd, lab, v, f"<={hi*1.5}", f"{lab}价格{v}>上限{hi}")
            elif v > hi*1.2: self._log(AuditLevel.WARN, src, mtd, lab, v, f"[{lo},{hi}]", f"{lab}价格{v}偏高")

    def _v_chg(self, c, lab, code="", src="", mtd=""):
        v = self._to_num(c, lab, src, mtd)
        if v is None: return
        self._fields += 1
        limit = BOARD_LIMITS.get(_infer_board(code), 11.0)
        if abs(v) > limit:
            self._log(AuditLevel.FAIL, src, mtd, lab, v, f"+/-{limit}%", f"{lab}涨跌幅{v}%超{_infer_board(code)}限制")

    def _v_vol(self, v, lab, src="", mtd=""):
        n = self._to_num(v, lab, src, mtd)
        if n is None: return
        self._fields += 1
        if n == 0: self._log(AuditLevel.INFO, src, mtd, lab, n, ">0?", f"{lab}成交量=0(可能停牌)")
        elif n < 0: self._log(AuditLevel.WARN, src, mtd, lab, n, ">=0", f"{lab}成交量为负")

    def _v_turnover(self, t, lab, src="", mtd=""):
        v = self._to_num(t, lab, src, mtd)
        if v is None: return
        self._fields += 1
        if v == 0: self._log(AuditLevel.WARN, src, mtd, lab, v, ">0", f"{lab}成交额=0(盘后未发布)")
        elif v < TURNOVER_MIN_YI: self._log(AuditLevel.WARN, src, mtd, lab, v, f">={TURNOVER_MIN_YI}", f"{lab}成交额{v}亿严重缩量")
        elif v > TURNOVER_MAX_YI: self._log(AuditLevel.WARN, src, mtd, lab, v, f"<={TURNOVER_MAX_YI}", f"{lab}成交额{v}亿异常放量")

    def _v_ohlc(self, o, h, l, c, lab, src="", mtd=""):
        self._fields += 1
        if o==0 and h==0 and l==0 and c==0:
            self._log(AuditLevel.WARN, src, mtd, lab, "全0", "非全零", f"{lab}OHLC全零")
            return
        if h < max(o, c): self._log(AuditLevel.FAIL, src, mtd, lab, f"O{o}H{h}L{l}C{c}", "H>=max(O,C)", f"{lab}最高价<max")
        if l > min(o, c): self._log(AuditLevel.FAIL, src, mtd, lab, f"O{o}H{h}L{l}C{c}", "L<=min(O,C)", f"{lab}最低价>min")

    def _v_north(self, f, lab, src="", mtd=""):
        v = self._to_num(f, lab, src, mtd)
        if v is None: return
        self._fields += 1
        if v == 0: self._log(AuditLevel.INFO, src, mtd, lab, v, "!=0?", f"{lab}北向=0(需判延迟)")
        elif v < NORTH_FLOW_MIN_YI: self._log(AuditLevel.WARN, src, mtd, lab, v, f">={NORTH_FLOW_MIN_YI}", f"{lab}北向流出异常大")
        elif v > NORTH_FLOW_MAX_YI: self._log(AuditLevel.WARN, src, mtd, lab, v, f"<={NORTH_FLOW_MAX_YI}", f"{lab}北向流入异常大")

    def _v_zt_dt(self, zt, dt, zrr, lab="", src="", mtd=""):
        zt_v = self._to_num(zt, f"{lab}涨停数", src, mtd)
        dt_v = self._to_num(dt, f"{lab}跌停数", src, mtd)
        zrr_v = self._to_num(zrr, f"{lab}炸板率", src, mtd)
        self._fields += 3
        if zt_v is not None:
            if zt_v == 0:
                self._log(AuditLevel.WARN, src, mtd, f"{lab}涨停数", 0, ">0", "涨停=0(非交易日/API异常)")
            elif zt_v < ZT_COUNT_MIN:
                self._log(AuditLevel.WARN, src, mtd, f"{lab}涨停数", zt_v, f">={ZT_COUNT_MIN}", f"涨停{zt_v}家极端弱市")
            elif zt_v > ZT_COUNT_MAX:
                self._log(AuditLevel.WARN, src, mtd, f"{lab}涨停数", zt_v, f"<={ZT_COUNT_MAX}", f"涨停{zt_v}家数据可疑")
        if dt_v is not None:
            if dt_v > DT_COUNT_CRASH:
                self._log(AuditLevel.WARN, src, mtd, f"{lab}跌停数", dt_v, f"<={DT_COUNT_CRASH}", f"跌停{dt_v}家熔断级")
            elif dt_v > DT_COUNT_NORMAL:
                self._log(AuditLevel.WARN, src, mtd, f"{lab}跌停数", dt_v, f"<={DT_COUNT_NORMAL}", f"跌停{dt_v}家恐慌")
        if zrr_v is not None and (zrr_v < ZR_RATE_MIN or zrr_v > ZR_RATE_MAX):
            self._log(AuditLevel.WARN, src, mtd, f"{lab}炸板率", zrr_v, f"[{ZR_RATE_MIN},{ZR_RATE_MAX}]", f"炸板率{zrr_v}%异常")

    # ========== 腾讯数据源 ==========

    def tc_fetch_realtime(self, codes: list) -> dict:
        data = self.tc.fetch_realtime(codes)
        for code, item in data.items():
            nm = item.get("name", code)
            self._v_price(item.get("price"), nm, code, "Tencent", "fetch_realtime")
            self._v_chg(item.get("change_pct"), nm, code, "Tencent", "fetch_realtime")
            self._v_vol(item.get("volume"), f"{nm}成交量", "Tencent", "fetch_realtime")
            self._v_turnover(item.get("turnover",0)/10000, f"{nm}成交额", "Tencent", "fetch_realtime")
        return data

    def tc_fetch_indices(self, codes=None, names=None) -> list:
        data = self.tc.fetch_indices(codes, names)
        for it in data:
            code = it.get("code",""); nm = it.get("name","") or code
            self._v_price(it.get("price"), nm, code, "Tencent", "fetch_indices")
            self._v_chg(it.get("change_pct"), nm, code, "Tencent", "fetch_indices")
        return data

    def tc_fetch_index_snapshot(self) -> list:
        return self.tc_fetch_indices()

    def tc_fetch_kline(self, code: str, n_days: int = 120, market: str = None) -> list:
        data = self.tc.fetch_kline(code, n_days, market)
        for row in data:
            if len(row) < 6: continue
            try:
                o, h, l, c = float(row[4]), float(row[1]), float(row[3]), float(row[2])
                self._v_ohlc(o, h, l, c, f"{code}@{row[0]}", "Tencent", "fetch_kline")
            except (ValueError, TypeError): pass
        return data

    def tc_fetch_kline_batch(self, codes: list, n_days: int = 120) -> dict:
        data = self.tc.fetch_kline_batch(codes, n_days)
        for code, kls in data.items():
            for row in kls:
                if len(row) < 6: continue
                try:
                    o, h, l, c = float(row[4]), float(row[1]), float(row[3]), float(row[2])
                    self._v_ohlc(o, h, l, c, f"{code}@{row[0]}", "Tencent", "fetch_kline_batch")
                except (ValueError, TypeError): pass
        return data

    def tc_fetch_turnover_simple(self) -> float:
        t = self.tc.fetch_turnover_simple()
        self._v_turnover(t, "全市场成交额", "Tencent", "fetch_turnover_simple")
        return t

    def tc_fetch_sectors(self, top_n: int = 5) -> list:
        data = self.tc.fetch_sectors(top_n)
        for it in data:
            self._v_chg(it.get("change_pct"), it.get("name","?"), "", "Tencent", "fetch_sectors")
        return data

    # ========== 东财数据源 ==========

    def em_fetch_north_flow(self, lmt: int = 1) -> list:
        data = self.em.fetch_north_flow(lmt)
        for it in data:
            self._v_north(it.get("total_yi"), f"北向{it.get('date','')}", "EastMoney", "fetch_north_flow")
        return data

    def em_fetch_north_flow_latest(self) -> Optional[dict]:
        data = self.em.fetch_north_flow_latest()
        if data:
            self._v_north(data.get("total_yi"), f"北向{data.get('date','')}", "EastMoney", "fetch_north_flow_latest")
        return data

    def em_ths_limit_up_pool(self, date: str, page: int = 1, limit: int = 200) -> dict:
        data = self.em.ths_limit_up_pool(date, page, limit)
        self._v_zt_dt(data.get("total",0), data.get("dt_count",0), data.get("zr_rate",0.0),
                      f"涨停@{date}", "EastMoney", "ths_limit_up_pool")
        return data

    def em_ths_limit_up_all(self, date: str) -> dict:
        data = self.em.ths_limit_up_all(date)
        self._v_zt_dt(data.get("total",0), data.get("dt_count",0), data.get("zr_rate",0.0),
                      f"涨停全量@{date}", "EastMoney", "ths_limit_up_all")
        return data

    def em_fetch_board_summary(self, date: str = None) -> dict:
        data = self.em.fetch_board_summary(date)
        self._v_zt_dt(data.get("zt_count",0), data.get("dt_count",0), data.get("zr_rate",0.0),
                      "打板汇总", "EastMoney", "fetch_board_summary")
        return data

    def em_board_fund_flow(self, board_type: str = "行业",
                           period: str = "今日", top_n: int = 10) -> list:
        """板块资金流向 — 行业/概念/地域 × 今日/5日/10日。经守门员验证主力净流入合理性。"""
        data = self.em.board_fund_flow(board_type, period, top_n)
        for it in data:
            nm = it.get("name", "?")
            main_net = it.get("main_net_yi", 0)
            self._v_vol(main_net, f"{board_type}·{nm}·主力净流入", "EastMoney", "board_fund_flow")
            self._v_chg(it.get("change_pct"), f"{board_type}·{nm}", "", "EastMoney", "board_fund_flow")
        return data

    def em_cls_telegraph(self, limit: int = 20) -> list:
        """财联社电报 — 7x24小时实时财经快讯。轻量验证（非空）。"""
        from scripts.cls_telegraph import get_cls
        self._fields += 1
        try:
            data = get_cls().fetch_telegraph(limit)
            if not data:
                self._log(AuditLevel.INFO, "CLS", "fetch_telegraph", "财联社电报",
                          0, ">0", "财联社电报返回空(非交易时段/网络问题)")
            return data
        except Exception as e:
            self._log(AuditLevel.WARN, "CLS", "fetch_telegraph", "财联社电报",
                      "error", "正常", f"财联社电报获取失败: {e}")
            return []

    # ========== Tushare数据源 ==========

    def ts_fetch_moneyflow_hsgt(self, start_date: str = None, end_date: str = None) -> list:
        from scripts.tushare_api import fetch_moneyflow_hsgt
        data = fetch_moneyflow_hsgt(start_date, end_date)
        for it in data:
            self._v_north(it.get("north_flow_yi"), f"TS北向{it.get('date','')}", "Tushare", "moneyflow_hsgt")
        return data

    # === Tushare Pro 行情 ===
    def ts_daily(self, ts_code=None, start=None, end=None, trade_date=None):
        from scripts.tushare_pro_data import ts_daily as _fn
        return _fn(ts_code=ts_code, start=start, end=end, trade_date=trade_date)

    def ts_index_daily(self, ts_code=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_index_daily as _fn
        return _fn(ts_code=ts_code, start=start, end=end)

    def ts_weekly(self, ts_code=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_weekly as _fn
        return _fn(ts_code=ts_code, start=start, end=end)

    def ts_monthly(self, ts_code=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_monthly as _fn
        return _fn(ts_code=ts_code, start=start, end=end)

    def ts_adj_factor(self, ts_code=None, trade_date=None):
        from scripts.tushare_pro_data import ts_adj_factor as _fn
        return _fn(ts_code=ts_code, trade_date=trade_date)

    def ts_suspend(self, ts_code=None, suspend_date=None):
        from scripts.tushare_pro_data import ts_suspend as _fn
        return _fn(ts_code=ts_code, suspend_date=suspend_date)

    # === Tushare Pro 基本面 ===
    def ts_daily_basic(self, trade_date=None, ts_code=None):
        from scripts.tushare_pro_data import ts_daily_basic as _fn
        return _fn(trade_date=trade_date, ts_code=ts_code)

    def ts_income(self, ts_code=None, start=None, end=None, period=None, report_type="1"):
        from scripts.tushare_pro_data import ts_income as _fn
        return _fn(ts_code=ts_code, start=start, end=end, period=period, report_type=report_type)

    def ts_balancesheet(self, ts_code=None, start=None, end=None, period=None, report_type="1"):
        from scripts.tushare_pro_data import ts_balancesheet as _fn
        return _fn(ts_code=ts_code, start=start, end=end, period=period, report_type=report_type)

    def ts_cashflow(self, ts_code=None, start=None, end=None, period=None, report_type="1"):
        from scripts.tushare_pro_data import ts_cashflow as _fn
        return _fn(ts_code=ts_code, start=start, end=end, period=period, report_type=report_type)

    def ts_forecast(self, ts_code=None, ann_date=None, start=None, end=None, period=None):
        from scripts.tushare_pro_data import ts_forecast as _fn
        return _fn(ts_code=ts_code, ann_date=ann_date, start=start, end=end, period=period)

    def ts_dividend(self, ts_code=None, ex_date=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_dividend as _fn
        return _fn(ts_code=ts_code, ex_date=ex_date, start=start, end=end)

    def ts_stk_holdernumber(self, ts_code=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_stk_holdernumber as _fn
        return _fn(ts_code=ts_code, start=start, end=end)

    def ts_disclosure_date(self, ts_code=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_disclosure_date as _fn
        return _fn(ts_code=ts_code, start=start, end=end)

    # === Tushare Pro 融资融券 ===
    def ts_margin(self, ts_code=None, trade_date=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_margin as _fn
        return _fn(ts_code=ts_code, trade_date=trade_date, start=start, end=end)

    def ts_margin_detail(self, ts_code=None, trade_date=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_margin_detail as _fn
        return _fn(ts_code=ts_code, trade_date=trade_date, start=start, end=end)

    # === Tushare Pro 股东 ===
    def ts_top10_holders(self, ts_code, start=None, end=None, period=None):
        from scripts.tushare_pro_data import ts_top10_holders as _fn
        return _fn(ts_code=ts_code, start=start, end=end, period=period)

    def ts_top10_floatholders(self, ts_code, start=None, end=None, period=None):
        from scripts.tushare_pro_data import ts_top10_floatholders as _fn
        return _fn(ts_code=ts_code, start=start, end=end, period=period)

    # === Tushare Pro 交易信号 ===
    def ts_moneyflow(self, ts_code=None, trade_date=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_moneyflow as _fn
        return _fn(ts_code=ts_code, trade_date=trade_date, start=start, end=end)

    def ts_daily_info(self, ts_code=None, trade_date=None, exchange=""):
        from scripts.tushare_pro_data import ts_daily_info as _fn
        return _fn(ts_code=ts_code, trade_date=trade_date, exchange=exchange)

    # === Tushare Pro 公司信息 ===
    def ts_stock_company(self, ts_code=None, exchange=None):
        from scripts.tushare_pro_data import ts_stock_company as _fn
        return _fn(ts_code=ts_code, exchange=exchange)

    def ts_namechange(self, ts_code=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_namechange as _fn
        return _fn(ts_code=ts_code, start=start, end=end)

    # === Tushare Pro 指数 ===
    def ts_index_weekly(self, ts_code=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_index_weekly as _fn
        return _fn(ts_code=ts_code, start=start, end=end)

    def ts_index_monthly(self, ts_code=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_index_monthly as _fn
        return _fn(ts_code=ts_code, start=start, end=end)

    def ts_index_dailybasic(self, ts_code=None, trade_date=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_index_dailybasic as _fn
        return _fn(ts_code=ts_code, trade_date=trade_date, start=start, end=end)

    # === Tushare Pro 因子 ===
    def ts_stk_factor(self, ts_code=None, trade_date=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_stk_factor as _fn
        return _fn(ts_code=ts_code, trade_date=trade_date, start=start, end=end)

    def ts_stk_factor_pro(self, ts_code=None, trade_date=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_stk_factor_pro as _fn
        return _fn(ts_code=ts_code, trade_date=trade_date, start=start, end=end)

    # === Tushare Pro 其他 ===
    def ts_fund_daily(self, ts_code=None, trade_date=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_fund_daily as _fn
        return _fn(ts_code=ts_code, trade_date=trade_date, start=start, end=end)

    def ts_ths_index(self, ts_code=None, exchange=None, type_=None):
        from scripts.tushare_pro_data import ts_ths_index as _fn
        return _fn(ts_code=ts_code, exchange=exchange, type_=type_)

    def ts_ths_daily(self, ts_code=None, trade_date=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_ths_daily as _fn
        return _fn(ts_code=ts_code, trade_date=trade_date, start=start, end=end)

    def ts_major_news(self, ts_code=None, start=None, end=None, src=""):
        from scripts.tushare_pro_data import ts_major_news as _fn
        return _fn(ts_code=ts_code, start=start, end=end, src=src)

    def ts_ggt_daily(self, ts_code=None, trade_date=None, start=None, end=None):
        from scripts.tushare_pro_data import ts_ggt_daily as _fn
        return _fn(ts_code=ts_code, trade_date=trade_date, start=start, end=end)

    # ========== 跨源交叉验证 ==========

    def cross_validate_north_flow(self, date: str = None):
        if not date: date = datetime.now().strftime("%Y%m%d")
        from scripts.data_validator import VStatus
        r = self.dv.validate_north_flow(date)
        if r.status == VStatus.PASS:
            self._log(AuditLevel.OK, "CrossSource", "north_flow", "北向资金·亿",
                      r.consensus, "双源一致", f"东财={r.sources.get('东财kamt')} Tushare={r.sources.get('Tushare')} 共识={r.consensus}亿",
                      em=r.sources.get("东财kamt"), ts=r.sources.get("Tushare"), consensus=r.consensus)
        else:
            for m in r.messages:
                self._log(AuditLevel.CROSS, "CrossSource", "north_flow", "北向资金·亿",
                          r.consensus, "双源一致/偏差", m,
                          em=r.sources.get("东财kamt"), ts=r.sources.get("Tushare"), consensus=r.consensus)
        return r

    def cross_validate_all(self, date: str = None):
        if not date: date = datetime.now().strftime("%Y%m%d")
        results = self.dv.validate_all(date)
        for r in results:
            for m in r.messages:
                self._log(AuditLevel.CROSS, "CrossSource", r.item, r.item, r.consensus, "合理/一致", m, consensus=r.consensus)
        return results

    # ========== 零值陷阱诊断 ==========

    def diagnose_zero_traps(self, turnover_yi=None, north_flow_yi=None, zt_count=None):
        if turnover_yi is None:
            try: turnover_yi = self.tc.fetch_turnover_simple()
            except Exception: pass
        if north_flow_yi is not None and north_flow_yi == 0 and (turnover_yi or 0) > 1000:
            self._log(AuditLevel.WARN, "ZeroTrap", "diagnose", "北向", 0.0, "!=0",
                      "ZERO_TRAP: 北向=0但全市场成交额正常→盘后数据未发布，非真实零值")
        if zt_count is not None and zt_count == 0 and (turnover_yi or 0) > 1000:
            self._log(AuditLevel.WARN, "ZeroTrap", "diagnose", "涨停数", 0, ">0",
                      "ZERO_TRAP: 涨停=0但有成交额→API异常或非交易日")

    # ========== 审计报告 ==========

    def audit_summary(self) -> Dict[str, int]:
        s = {"OK":0,"INFO":0,"WARN":0,"FAIL":0,"CROSS":0}
        for e in self.audit:
            k = e.level.value
            s[k] = s.get(k, 0) + 1
        return s

    def audit_markdown(self) -> str:
        s = self.audit_summary()
        total = sum(s.values())
        lines = [
            "## 数据验证审计报告\n",
            f"> 已验证字段: {self._fields} | 审计记录: {total}",
            f"> OK:{s['OK']} WARN:{s['WARN']} FAIL:{s['FAIL']} CROSS:{s['CROSS']} INFO:{s['INFO']}\n",
        ]

        groups: Dict[str, list] = {"FAIL":[],"WARN":[],"CROSS":[],"INFO":[],"OK":[]}
        for e in self.audit:
            k = e.level.value
            if k not in groups: k = "INFO"
            groups[k].append(e)

        for level in ["FAIL","WARN","CROSS","INFO"]:
            if not groups[level]: continue
            lv_label = {"FAIL":"[FAIL] 失败","WARN":"[WARN] 警告","CROSS":"[CROSS] 跨源","INFO":"[INFO] 信息"}
            lines.append(f"\n### {lv_label.get(level,level)} ({len(groups[level])}条)")
            for e in groups[level][:20]:  # 最多显示20条
                dtl = ""
                if e.detail.get("consensus") is not None:
                    dtl = f" (共识:{e.detail['consensus']:.2f})"
                if e.detail.get("em") is not None:
                    dtl += f" [东财:{e.detail['em']}, Tushare:{e.detail['ts']}]"
                lines.append(f"- `{e.timestamp}` {e.source}.{e.method}: **{e.field}**={e.value} | {e.message}{dtl}")
            if len(groups[level]) > 20:
                lines.append(f"- ... 还有 {len(groups[level])-20} 条")

        if total == 0:
            lines.append("\n*（无数据调用记录 — 可能尚无数据经过守门员）*")
        return "".join(lines) + "\n"

    # ========== 龙虎榜 + 资金流 + 解禁（来自 eastmoney_signals）==========
    def em_dragon_tiger_board(self, date: str = None) -> list:
        from scripts.eastmoney_signals import dragon_tiger_board
        return dragon_tiger_board(date)

    def em_lockup_expiry(self, days: int = 7) -> list:
        from scripts.eastmoney_signals import lockup_expiry
        return lockup_expiry(days)

    def em_industry_board(self, board_type: str = "行业") -> list:
        from scripts.eastmoney_signals import em_industry_board
        return em_industry_board(board_type)

    def em_fund_flow_minute(self, code: str) -> list:
        from scripts.eastmoney_signals import eastmoney_fund_flow_minute
        return eastmoney_fund_flow_minute(code)

    # ========== 融资融券 + 大宗 + 股东 + 分红 + 资金流120日 ==========
    def em_margin_trading(self, code: str = None, start: str = None, end: str = None) -> list:
        from scripts.eastmoney_fundamentals import margin_trading
        return margin_trading(code, start, end)

    def em_block_trade(self, code: str, start: str = None, end: str = None) -> list:
        from scripts.eastmoney_fundamentals import block_trade
        return block_trade(code, start, end)

    def em_holder_num_change(self, code: str) -> list:
        from scripts.eastmoney_fundamentals import holder_num_change
        return holder_num_change(code)

    def em_dividend_history(self, code: str) -> list:
        from scripts.eastmoney_fundamentals import dividend_history
        return dividend_history(code)

    def em_stock_fund_flow_120d(self, code: str) -> list:
        from scripts.eastmoney_fundamentals import stock_fund_flow_120d
        return stock_fund_flow_120d(code)

    # ========== 个股新闻 + 全球新闻 ==========
    def em_stock_news(self, code: str, page_size: int = 20) -> list:
        from scripts.eastmoney_news import eastmoney_stock_news
        return eastmoney_stock_news(code, page_size=page_size)

    def em_global_news(self, page_size: int = 20) -> list:
        from scripts.eastmoney_news import eastmoney_global_news
        return eastmoney_global_news(page_size=page_size)

    # ========== 个股信息 + 涨停四池 + 人气榜 ==========
    def em_stock_info(self, code: str) -> dict:
        from scripts.eastmoney_info import eastmoney_stock_info
        return eastmoney_stock_info(code)

    def em_zt_pool(self, date: str = None) -> list:
        from scripts.eastmoney_info import em_zt_pool
        return em_zt_pool(date)

    def em_zb_pool(self, date: str = None) -> list:
        from scripts.eastmoney_info import em_zb_pool
        return em_zb_pool(date)

    def em_dt_pool(self, date: str = None) -> list:
        from scripts.eastmoney_info import em_dt_pool
        return em_dt_pool(date)

    def em_hot_rank(self, top: int = 50) -> list:
        from scripts.eastmoney_info import em_hot_rank
        return em_hot_rank(top)

    def em_hot_concept(self, code: str) -> list:
        from scripts.eastmoney_info import em_hot_concept
        return em_hot_concept(code)

    # ========== 同花顺热榜 + 一致预期 ==========
    def ths_eps_forecast(self, code: str) -> list:
        from scripts.ths_api import ths_eps_forecast
        return ths_eps_forecast(code)

    def ths_hot_reason(self) -> list:
        from scripts.ths_api import ths_hot_reason
        return ths_hot_reason()

    def ths_hot_list(self, period: str = "hour") -> list:
        from scripts.ths_api import ths_hot_list
        return ths_hot_list(period)

    # ========== 新浪期权 + 财报 ==========
    def sina_option_codes(self, underlying: str = "510050", call: bool = True) -> dict:
        from scripts.sina_api import sina_option_codes
        return sina_option_codes(underlying, call)

    def sina_option_tquote(self, code: str) -> dict:
        from scripts.sina_api import sina_option_tquote
        return sina_option_tquote(code)

    def sina_option_greeks(self, code: str) -> dict:
        from scripts.sina_api import sina_option_greeks
        return sina_option_greeks(code)

    def sina_financial_report(self, code: str) -> dict:
        from scripts.sina_api import sina_financial_report
        return sina_financial_report(code)

    # ========== 巨潮公告 + 互动易 ==========
    def cninfo_announcements(self, code: str, page_size: int = 20, keyword: str = "") -> list:
        from scripts.cninfo_api import cninfo_announcements
        return cninfo_announcements(code, page_size=page_size, keyword=keyword)

    def cninfo_irm(self, code: str, page_size: int = 30) -> list:
        from scripts.cninfo_api import cninfo_irm
        return cninfo_irm(code, page_size=page_size)

    # ========== 通达信mootdx ==========
    def tdx_bars(self, code: str, freq: int = 9, count: int = 100) -> list:
        from scripts.mootdx_api import get_mootdx
        return get_mootdx().bars(code, freq=freq, count=count)

    def tdx_quotes(self, codes: list) -> list:
        from scripts.mootdx_api import get_mootdx
        return get_mootdx().quotes(codes)

    def tdx_finance(self, code: str) -> dict:
        from scripts.mootdx_api import get_mootdx
        return get_mootdx().finance(code)

    def tdx_available(self) -> bool:
        """判断 mootdx TCP 7709 端口在当前时段是否可能连通。

        只有盘中连续竞价(9:30-11:30, 13:00-15:00)返回 True。
        午休/盘前/收盘后/周末/节假日 → 自动降级到 Tushare.pro。
        
        用法: 调用方先 if gate.tdx_available(): do_mootdx() else: fallback()
        """
        from datetime import datetime, time as dtime
        now = datetime.now()
        t = now.time()
        wd = now.weekday()  # 0=Mon ~ 6=Sun
        
        # 周末
        if wd >= 5:
            return False
        # 盘中上午: 9:30-11:30
        if dtime(9, 30) <= t < dtime(11, 30):
            return True
        # 盘中下午: 13:00-15:00
        if dtime(13, 0) <= t < dtime(15, 0):
            return True
        # 其他: 盘前/午休/收盘后
        return False

    # ========== 估值 ==========
    def val_full_valuation(self, code: str) -> dict:
        from scripts.valuation import full_valuation
        return full_valuation(code)

    # ========== 百度K线（§1.3）==========
    def em_baidu_kline_with_ma(self, code: str, start_time: str = "") -> dict:
        from scripts.eastmoney_api import baidu_kline_with_ma
        return baidu_kline_with_ma(code, start_time)

    # ========== 东财研报 + PDF（§2.1）==========
    def em_eastmoney_reports(self, code: str, max_pages: int = 5) -> list:
        from scripts.eastmoney_api import eastmoney_reports
        return eastmoney_reports(code, max_pages)

    def em_download_pdf(self, record: dict, target_dir: str = None) -> str:
        from scripts.eastmoney_api import download_pdf
        return download_pdf(record, target_dir)

    def em_industry_reports(self, industry_code: str = "*", max_pages: int = 5,
                            begin: str = "2024-01-01") -> list:
        from scripts.eastmoney_api import eastmoney_industry_reports
        return eastmoney_industry_reports(industry_code, max_pages, begin)

    # ========== 同花顺北向分钟流（§3.2）==========
    def ths_hsgt_realtime(self) -> dict:
        from scripts.ths_api import hsgt_realtime
        return hsgt_realtime()

    # ========== 打板情绪（§8.3）==========
    def em_limit_up_sentiment(self, date: str) -> dict:
        zt = self.em_zt_pool(date)
        zb = self.em_zb_pool(date)
        dt = self.em_dt_pool(date)
        ladder = {}
        for s in zt:
            days = s.get("limit_days", 0) or 0
            ladder[days] = ladder.get(days, 0) + 1
        zt_n, zb_n = len(zt), len(zb)
        return {
            "date": date, "zt_count": zt_n, "zb_count": zb_n, "dt_count": len(dt),
            "break_rate": round(zb_n / (zt_n + zb_n) * 100, 1) if (zt_n + zb_n) else 0,
            "max_height": max((s.get("limit_days", 0) or 0 for s in zt), default=0),
            "ladder": dict(sorted(ladder.items())),
        }

    def print_audit(self):
        """控制台打印审计报告"""
        output = self.audit_markdown()
        try:
            print(output)
        except UnicodeEncodeError:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
            print(output)

    def reset(self):
        """重置审计轨迹（新的一天/新任务开始时调用）"""
        self.audit.clear()
        self._fields = 0

    # ========== 完整性检查 ==========

    def health_check(self, date: str = None) -> dict:
        """返回数据健康度评分 (0-100)"""
        if not date: date = datetime.now().strftime("%Y%m%d")
        results = self.dv.validate_all(date)
        s = self.audit_summary()
        total = max(sum(s.values()), 1)
        # 公式: 100 - FAIL*20 - WARN*5 - INFO*1 (最低0)
        score = max(0, 100 - s["FAIL"] * 20 - s["WARN"] * 5 - s["INFO"] * 1)
        return {
            "score": score,
            "grade": "A" if score >= 90 else ("B" if score >= 70 else ("C" if score >= 50 else "D")),
            "fields_validated": self._fields,
            "cross_checks": len([e for e in self.audit if e.level == AuditLevel.CROSS]),
            "fails": s["FAIL"],
            "warns": s["WARN"],
            "cross_results": [{"item": r.item, "status": r.status.value, "consensus": r.consensus} for r in results],
        }


# ==================== 全局单例 ====================

gate = DataGate()


# ==================== 便捷函数 ====================

def validate_all_active(date: str = None) -> dict:
    """一键：通过守门员获取所有活跃数据 + 跨源验证 + 输出健康报告"""
    if not date: date = datetime.now().strftime("%Y%m%d")
    gate.reset()
    # 收集核心数据
    indices = gate.tc_fetch_indices()
    north = gate.em_fetch_north_flow_latest()
    board = gate.em_fetch_board_summary(date)
    turnover = gate.tc_fetch_turnover_simple()
    gate.cross_validate_all(date)
    gate.diagnose_zero_traps(turnover, north.get("total_yi") if north else None,
                             board.get("zt_count") if board else None)
    health = gate.health_check(date)
    return {
        "date": date, "health": health,
        "indices": indices, "north": north, "board": board, "turnover_yi": turnover,
        "audit": gate.audit_markdown(),
    }


if __name__ == "__main__":
    """DataGate 自检 — 快速验证全链条可通"""
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    gate.reset()
    print("【DataGate 守门员 — 全链条自检】\n")

    # 腾讯数据源
    idx = gate.tc_fetch_indices()
    print(f"[Tencent] 指数: {len(idx)} 个")
    turnover = gate.tc_fetch_turnover_simple()
    print(f"[Tencent] 全市场成交额: {turnover:.0f} 亿")
    sectors = gate.tc_fetch_sectors(5)
    print(f"[Tencent] 行业板块TOP5: {[s['name'] for s in sectors]}")

    # 东财数据源
    north = gate.em_fetch_north_flow_latest()
    print(f"[EastMoney] 北向最新: {north['total_yi']:.2f} 亿" if north and north.get("total_yi") else "[EastMoney] 北向数据为空(盘后)")
    board = gate.em_fetch_board_summary()
    print(f"[EastMoney] 涨停: {board['zt_count']} | 炸板率: {board['zr_rate']:.1f}% | 最高连板: {board['zt_high_lb']}")

    # 板块资金流向（push2限流时自动降级为空列表）
    bf = gate.em_board_fund_flow("概念", "今日", 5)
    if bf:
        top3 = [(r["name"], round(r["main_net_yi"], 1)) for r in bf[:3]]
        print(f"[EastMoney] 概念板块资金TOP3: {top3}")
    else:
        print("[EastMoney] 板块资金流向: push2限流，跳过(非关键)")

    # 跨源交叉验证
    gate.cross_validate_north_flow()
    gate.diagnose_zero_traps(turnover,
        north.get("total_yi") if north else None,
        board.get("zt_count") if board else None)

    # 输出审计报告
    gate.print_audit()
    health = gate.health_check()
    print(f"\n健康度评分: {health['score']}/100 ({health['grade']}级)")
