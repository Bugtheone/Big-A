#!/usr/bin/env python3
"""
Tushare Pro 全量数据封装（500元/5000积分档）。
覆盖: 行情(4) | 基本面(8) | 融资融券(2) | 股东(3) | 信号(4) |
       公司(2) | 指数(3) | 因子(2) | 基金(1) | 概念(3) | 新闻(1) | 港股通(1) | 市场总览(1)
所有函数返回 list[dict]，统一异常处理，自动分页。
"""

from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ========== 工具 ==========

def _df_to_dicts(df) -> List[Dict[str, Any]]:
    """DataFrame -> list[dict]，处理 NaN/None"""
    if df is None or len(df) == 0:
        return []
    import pandas as pd
    result = []
    for _, row in df.iterrows():
        d = {}
        for k, v in row.items():
            if pd.isna(v):
                d[k] = None
            elif isinstance(v, pd.Timestamp):
                d[k] = v.strftime("%Y%m%d")
            else:
                d[k] = v
        result.append(d)
    return result

def _default_dates(start, end, lookback=365):
    if not end:
        end = datetime.now().strftime("%Y%m%d")
    if not start:
        start = (datetime.now() - timedelta(days=lookback)).strftime("%Y%m%d")
    return start, end

def _fetch(pro, method, chunk=3000, **kw) -> List[Dict]:
    """通用获取器（Tushare 单次最多约 6000 行）。
    全市场区间查询（有 start_date/end_date 但无 ts_code/trade_date）按日分段，
    避免多日数据被静默截断；单股/单日查询走原路径。"""
    fn = getattr(pro, method)
    start, end = kw.get("start_date"), kw.get("end_date")
    if start and end and not kw.get("ts_code") and not kw.get("trade_date"):
        from datetime import datetime, timedelta
        cur = datetime.strptime(start, "%Y%m%d")
        last = datetime.strptime(end, "%Y%m%d")
        out: List[Dict] = []
        while cur <= last:
            day_kw = dict(kw)
            day_kw["start_date"] = cur.strftime("%Y%m%d")
            day_kw["end_date"] = cur.strftime("%Y%m%d")
            try:
                df = fn(**day_kw)
                out.extend(_df_to_dicts(df))
            except Exception as e:
                logger.warning(f"Tushare.{method} {cur:%Y%m%d} 失败: {e}")
            cur += timedelta(days=1)
        return out
    try:
        df = fn(**kw)
        return _df_to_dicts(df)
    except Exception as e:
        logger.warning(f"Tushare.{method} 失败: {e}")
        return []

# ========== I. 行情 ==========

def ts_daily(ts_code=None, start=None, end=None, trade_date=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if ts_code: kw["ts_code"] = ts_code
    if trade_date: kw["trade_date"] = trade_date
    else:
        s, e = _default_dates(start, end, 10)
        kw["start_date"] = s; kw["end_date"] = e
    return _fetch(pro, "daily", **kw)

def ts_weekly(ts_code=None, start=None, end=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    s, e = _default_dates(start, end, 365)
    kw = {"start_date": s, "end_date": e}
    if ts_code: kw["ts_code"] = ts_code
    return _fetch(pro, "weekly", **kw)

def ts_monthly(ts_code=None, start=None, end=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    s, e = _default_dates(start, end, 730)
    kw = {"start_date": s, "end_date": e}
    if ts_code: kw["ts_code"] = ts_code
    return _fetch(pro, "monthly", **kw)

def ts_adj_factor(ts_code=None, trade_date=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if ts_code: kw["ts_code"] = ts_code
    if trade_date: kw["trade_date"] = trade_date
    return _fetch(pro, "adj_factor", **kw)

def ts_suspend(ts_code=None, suspend_date=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"suspend_date": suspend_date or datetime.now().strftime("%Y%m%d")}
    if ts_code: kw["ts_code"] = ts_code
    return _fetch(pro, "suspend", **kw)

# ========== II. 基本面 ==========

def ts_daily_basic(trade_date=None, ts_code=None):
    """PE/PB/市值/换手率/量比——波段选股核心"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"trade_date": trade_date or datetime.now().strftime("%Y%m%d")}
    if ts_code: kw["ts_code"] = ts_code
    return _fetch(pro, "daily_basic", **kw)

def ts_income(ts_code=None, start=None, end=None, period=None, report_type="1"):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"report_type": report_type}
    if ts_code: kw["ts_code"] = ts_code
    if period: kw["period"] = period
    else:
        s, e = _default_dates(start, end, 730)
        kw["start_date"] = s; kw["end_date"] = e
    return _fetch(pro, "income", **kw)

def ts_balancesheet(ts_code=None, start=None, end=None, period=None, report_type="1"):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"report_type": report_type}
    if ts_code: kw["ts_code"] = ts_code
    if period: kw["period"] = period
    else:
        s, e = _default_dates(start, end, 730)
        kw["start_date"] = s; kw["end_date"] = e
    return _fetch(pro, "balancesheet", **kw)

def ts_cashflow(ts_code=None, start=None, end=None, period=None, report_type="1"):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"report_type": report_type}
    if ts_code: kw["ts_code"] = ts_code
    if period: kw["period"] = period
    else:
        s, e = _default_dates(start, end, 730)
        kw["start_date"] = s; kw["end_date"] = e
    return _fetch(pro, "cashflow", **kw)

def ts_forecast(ts_code=None, ann_date=None, start=None, end=None, period=None):
    """业绩预告。需要 ts_code 或 ann_date（Tushare要求至少一个）。"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if ts_code: kw["ts_code"] = ts_code
    if ann_date: kw["ann_date"] = ann_date
    if period: kw["period"] = period
    if start: kw["start_date"] = start
    if end: kw["end_date"] = end
    return _fetch(pro, "forecast", **kw)

def ts_dividend(ts_code=None, ex_date=None, start=None, end=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if ts_code: kw["ts_code"] = ts_code
    if ex_date: kw["ex_date"] = ex_date
    if start: kw["start_date"] = start
    if end: kw["end_date"] = end
    return _fetch(pro, "dividend", **kw)

def ts_stk_holdernumber(ts_code=None, start=None, end=None):
    """股东户数变化（筹码集中度）"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    s, e = _default_dates(start, end, 730)
    kw = {"start_date": s, "end_date": e}
    if ts_code: kw["ts_code"] = ts_code
    return _fetch(pro, "stk_holdernumber", **kw)

def ts_disclosure_date(ts_code=None, start=None, end=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"end_date": end or datetime.now().strftime("%Y%m%d")}
    if ts_code: kw["ts_code"] = ts_code
    if start: kw["start_date"] = start
    return _fetch(pro, "disclosure_date", **kw)

# ========== III. 融资融券 ==========

def ts_margin(ts_code=None, trade_date=None, start=None, end=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if ts_code: kw["ts_code"] = ts_code
    if trade_date: kw["trade_date"] = trade_date
    else:
        s, e = _default_dates(start, end, 30)
        kw["start_date"] = s; kw["end_date"] = e
    return _fetch(pro, "margin", **kw)

def ts_margin_detail(ts_code=None, trade_date=None, start=None, end=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if ts_code: kw["ts_code"] = ts_code
    if trade_date: kw["trade_date"] = trade_date
    else:
        s, e = _default_dates(start, end, 3)
        kw["start_date"] = s; kw["end_date"] = e
    return _fetch(pro, "margin_detail", **kw)

# ========== IV. 股东 ==========

def ts_top10_holders(ts_code, start=None, end=None, period=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"ts_code": ts_code}
    if period: kw["period"] = period
    if start: kw["start_date"] = start
    if end: kw["end_date"] = end
    return _fetch(pro, "top10_holders", **kw)

def ts_top10_floatholders(ts_code, start=None, end=None, period=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"ts_code": ts_code}
    if period: kw["period"] = period
    if start: kw["start_date"] = start
    if end: kw["end_date"] = end
    return _fetch(pro, "top10_floatholders", **kw)

# ========== V. 交易信号 ==========

def ts_moneyflow(ts_code=None, trade_date=None, start=None, end=None):
    """个股资金流向（主力净流入额）。
    注意: trade_date 与 start/end 互斥, 传了 start/end 时不得再传 trade_date, 否则 API 返回空。"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if start or end:
        # 日期区间查询: 不能带 trade_date
        if ts_code: kw["ts_code"] = ts_code
        if start: kw["start_date"] = start
        if end: kw["end_date"] = end
    else:
        kw = {"trade_date": trade_date or datetime.now().strftime("%Y%m%d")}
        if ts_code: kw["ts_code"] = ts_code
    return _fetch(pro, "moneyflow", **kw)

def ts_daily_info(ts_code=None, trade_date=None, exchange=""):
    """市场总览每日指标（需要5000积分）"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"trade_date": trade_date or datetime.now().strftime("%Y%m%d")}
    if ts_code: kw["ts_code"] = ts_code
    if exchange: kw["exchange"] = exchange
    return _fetch(pro, "daily_info", **kw)

# ========== VI. 公司信息 ==========

def ts_stock_company(ts_code=None, exchange=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if ts_code: kw["ts_code"] = ts_code
    if exchange: kw["exchange"] = exchange
    return _fetch(pro, "stock_company", **kw)

def ts_namechange(ts_code=None, start=None, end=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if ts_code: kw["ts_code"] = ts_code
    if start: kw["start_date"] = start
    if end: kw["end_date"] = end
    return _fetch(pro, "namechange", **kw)

# ========== VII. 指数 ==========

def ts_index_daily(ts_code=None, start=None, end=None):
    """指数日线行情 (pro.index_daily)"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    s, e = _default_dates(start, end, 730)
    kw = {"start_date": s, "end_date": e}
    if ts_code: kw["ts_code"] = ts_code
    return _fetch(pro, "index_daily", **kw)

def ts_index_weekly(ts_code=None, start=None, end=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    s, e = _default_dates(start, end, 730)
    kw = {"start_date": s, "end_date": e}
    if ts_code: kw["ts_code"] = ts_code
    return _fetch(pro, "index_weekly", **kw)

def ts_index_monthly(ts_code=None, start=None, end=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    s, e = _default_dates(start, end, 1825)
    kw = {"start_date": s, "end_date": e}
    if ts_code: kw["ts_code"] = ts_code
    return _fetch(pro, "index_monthly", **kw)

def ts_index_dailybasic(ts_code=None, trade_date=None, start=None, end=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"trade_date": trade_date or datetime.now().strftime("%Y%m%d")}
    if ts_code: kw["ts_code"] = ts_code
    if start: kw["start_date"] = start
    if end: kw["end_date"] = end
    return _fetch(pro, "index_dailybasic", **kw)

# ========== VIII. 因子 ==========

def ts_stk_factor(ts_code=None, trade_date=None, start=None, end=None):
    """复权因子 + 前/后复权价（2000积分）"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if ts_code: kw["ts_code"] = ts_code
    if trade_date: kw["trade_date"] = trade_date
    else:
        s, e = _default_dates(start, end, 365)
        kw["start_date"] = s; kw["end_date"] = e
    return _fetch(pro, "stk_factor", **kw)

def ts_stk_factor_pro(ts_code=None, trade_date=None, start=None, end=None):
    """专业股票因子（5000积分，更完整）"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if ts_code: kw["ts_code"] = ts_code
    if trade_date: kw["trade_date"] = trade_date
    else:
        s, e = _default_dates(start, end, 365)
        kw["start_date"] = s; kw["end_date"] = e
    return _fetch(pro, "stk_factor_pro", **kw)

# ========== IX. 基金 ==========

def ts_fund_daily(ts_code=None, trade_date=None, start=None, end=None):
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"trade_date": trade_date or datetime.now().strftime("%Y%m%d")}
    if ts_code: kw["ts_code"] = ts_code
    if start: kw["start_date"] = start
    if end: kw["end_date"] = end
    return _fetch(pro, "fund_daily", **kw)

# ========== X. 概念板块（同花顺） ==========

def ts_ths_index(ts_code=None, exchange=None, type_=None):
    """同花顺概念板块指数。返回: ts_code,name,count,exchange,list_date,type"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if ts_code: kw["ts_code"] = ts_code
    if exchange: kw["exchange"] = exchange
    if type_: kw["type"] = type_
    return _fetch(pro, "ths_index", **kw)

def ts_ths_daily(ts_code=None, trade_date=None, start=None, end=None):
    """同花顺板块日行情。ts_code 如 883001.TI"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"trade_date": trade_date or datetime.now().strftime("%Y%m%d")}
    if ts_code: kw["ts_code"] = ts_code
    if start: kw["start_date"] = start
    if end: kw["end_date"] = end
    return _fetch(pro, "ths_daily", **kw)

# ========== XI. 新闻公告 ==========

def ts_major_news(ts_code=None, start=None, end=None, src=""):
    """新闻公告"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {}
    if ts_code: kw["ts_code"] = ts_code
    if start: kw["start_date"] = start
    if end: kw["end_date"] = end
    if src: kw["src"] = src
    return _fetch(pro, "major_news", **kw)

# ========== XII. 港股通 ==========

def ts_ggt_daily(ts_code=None, trade_date=None, start=None, end=None):
    """港股通日行情"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kw = {"trade_date": trade_date or datetime.now().strftime("%Y%m%d")}
    if ts_code: kw["ts_code"] = ts_code
    if start: kw["start_date"] = start
    if end: kw["end_date"] = end
    return _fetch(pro, "ggt_daily", **kw)
