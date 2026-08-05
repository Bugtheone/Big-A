#!/usr/bin/env python3
"""东财资金面层 — 融资融券 + 大宗交易 + 股东户数 + 分红 + 120日资金流。
2026-07-24 从 SKILL.md §4.1~§4.5 融入。
"""

import time as _time
from datetime import datetime, timedelta

import requests

from scripts.eastmoney_api import UA, em_get, eastmoney_datacenter

_session = requests.Session()
_session.trust_env = False

# ========== 融资融券 (§4.1) ==========

def margin_trading(code: str = None, start_date: str = None, end_date: str = None) -> list[dict]:
    """个股/全市场融资融券数据。
    code: 6位代码，不传则返回全市场汇总(最近一日)。
    ⚠️ 2026-08 东财 datacenter 报表 RPTA_WEB_MTSS_MARGINTRADING 已失效（报表配置不存在），改用 Tushare margin 兜底。
    返回每行: {date, rzye(融资余额亿), rqye(融券余额亿), rzmr(融资买入亿), rqmc(融券卖出亿), ...}
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    try:
        from scripts.tushare_pro_data import ts_margin
        if code:
            ts_code = code + (".SH" if code.startswith(("6", "9")) else ".SZ")
            df = ts_margin(ts_code=ts_code, start=start_date, end=end_date)
        else:
            df = ts_margin(trade_date=end_date)
        rows = df.to_dict("records") if hasattr(df, "to_dict") else df
    except Exception as e:
        print(f"[margin] Tushare 失败: {e}")
        return []
    out = []
    for it in rows:
        out.append({
            "date": it.get("trade_date", "")[:10],
            "rzye": round(float(it.get("rzye", 0) or 0) / 1e8, 2),
            "rqye": round(float(it.get("rqye", 0) or 0) / 1e8, 2),
            "rzmr": round(float(it.get("rzmre", 0) or 0) / 1e8, 2),
            "rqmc": round(float(it.get("rqyl", 0) or 0) / 1e8, 2),
            "rzch": round(float(it.get("rzche", 0) or 0) / 1e8, 2),
            "rqch": round(float(it.get("rqche", 0) or 0) / 1e8, 2),
        })
    return out


# ========== 大宗交易 (§4.2) ==========

def block_trade(code: str, start_date: str = None, end_date: str = None) -> list[dict]:
    """个股大宗交易记录。
    code: 6位代码。start_date/end_date: YYYY-MM-DD。
    返回每笔: {date, price, volume(万股), amount(万元), buyer, seller, discount(折价率%)}
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    try:
        r = em_get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "sortColumns": "TRADE_DATE",
                "sortTypes": "-1",
                "pageSize": 500,
                "pageNumber": 1,
                "reportName": "RPT_DATA_BLOCKTRADE",
                "columns": "ALL",
                "source": "WEB", "client": "WEB",
                "filter": f'(TRADE_DATE>=\'{start_date}\')(TRADE_DATE<=\'{end_date}\')'
                          f'(SECURITY_CODE=\"{code}\")',
            },
            headers={"User-Agent": UA, "Referer": "https://data.eastmoney.com/"},
            timeout=15,
        )
        rows = (r.get("result") or {}).get("data") or []
    except Exception as e:
        print(f"[block_trade] {code} 失败: {e}")
        return []
    out = []
    for it in rows:
        close = float(it.get("CLOSE_PRICE", 0) or 0)
        price = float(it.get("DEAL_PRICE", 0) or 0)
        discount = round((price / close - 1) * 100, 2) if close else 0
        out.append({
            "date": it.get("TRADE_DATE", "")[:10],
            "price": price,
            "volume": it.get("DEAL_VOLUME"),
            "amount": it.get("DEAL_AMT"),
            "buyer": it.get("BUYER_NAME", ""),
            "seller": it.get("SELLER_NAME", ""),
            "discount": discount,
        })
    return out


# ========== 股东户数变化 (§4.3) ==========

def holder_num_change(code: str) -> list[dict]:
    """个股股东户数变化（反映筹码集中度）。
    code: 6位代码。
    返回每期: {end_date, holder_num(股东户数), avg_hold(人均持股), chg_pct(户数变化%)}
    """
    try:
        r = em_get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "sortColumns": "END_DATE",
                "sortTypes": "-1",
                "pageSize": 50,
                "pageNumber": 1,
                "reportName": "RPT_HOLDERNUMLATEST",
                "columns": "SECURITY_CODE,END_DATE,HOLDER_NUM,AVG_HOLD_NUM,HOLDER_NUM_CHANGE,HOLDER_NUM_RATIO",
                "source": "WEB", "client": "WEB",
                "filter": f'(SECURITY_CODE="{code}")',
            },
            headers={"User-Agent": UA, "Referer": "https://data.eastmoney.com/"},
            timeout=15,
        )
        rows = (r.get("result") or {}).get("data") or []
    except Exception as e:
        print(f"[holder_num] {code} 失败: {e}")
        return []
    out = []
    for it in rows:
        out.append({
            "end_date": it.get("END_DATE", "")[:10],
            "holder_num": it.get("HOLDER_NUM"),
            "avg_hold": it.get("AVG_HOLD_NUM"),
            "chg_pct": it.get("HOLDER_NUM_RATIO"),
        })
    return out


# ========== 分红历史 (§4.4) ==========

def dividend_history(code: str) -> list[dict]:
    """个股分红送转历史。
    code: 6位代码。
    返回每次: {year, ex_date, cash_div(每股分红元), bonus_share(送股), rights_issue(转增),
    plan_date(预案公告日), reg_date(股权登记日)}
    """
    try:
        r = em_get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "sortColumns": "EX_DIVIDEND_DATE",
                "sortTypes": "-1",
                "pageSize": 50,
                "pageNumber": 1,
                "reportName": "RPT_SHAREBONUS_DET",
                "columns": "ALL",
                "source": "WEB", "client": "WEB",
                "filter": f'(SECURITY_CODE="{code}")',
            },
            headers={"User-Agent": UA, "Referer": "https://data.eastmoney.com/"},
            timeout=15,
        )
        rows = (r.get("result") or {}).get("data") or []
    except Exception as e:
        print(f"[dividend] {code} 失败: {e}")
        return []
    out = []
    for it in rows:
        out.append({
            "year": str(it.get("REPORT_DATE") or "")[:4],
            "ex_date": (it.get("EX_DIVIDEND_DATE") or "")[:10],
            "cash_div": it.get("PRETAX_BONUS_RMB"),
            "bonus_share": it.get("BONUS_RATIO"),
            "rights_issue": it.get("IT_RATIO"),
            "plan_date": (it.get("PLAN_NOTICE_DATE") or "")[:10],
            "reg_date": (it.get("EQUITY_RECORD_DATE") or "")[:10],
        })
    return out


# ========== 120日资金流 (§4.5) ==========

def stock_fund_flow_120d(code: str) -> list[dict]:
    """个股120日主力资金流向（大/中/小单）。
    code: 6位代码。
    返回每日: {date, main_net(主力净流入万), big_net(超大单), mid_net(大单), small_net(小单),
    main_pct(主力净占比%)}
    """
    secid = f"{'1' if code.startswith('6') else '0'}.{code}"
    today = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")
    params = {
        "lmt": 0, "klt": 101,
        "secid": secid,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f174",
        "ut": "b2884a393a59ad640ee3e7d59f570b63",
        "beg": start, "end": today,
        "fqt": "1",
    }
    try:
        _time.sleep(0.5)
        resp = em_get("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get", params=params, timeout=15)
        # em_get 返回已解析 JSON dict（非 Response），无 raise_for_status
        lines = (resp.get("data") or {}).get("klines") or []
    except Exception as e:
        print(f"[fund_flow_120d] {code} 失败: {e}")
        return []
    out = []
    for line in lines:
        parts = line.split(",")
        if len(parts) < 4:
            continue
        out.append({
            "date": parts[0],
            "main_net": round(float(parts[1]) if parts[1] != "-" else 0, 2),
            "big_net": round(float(parts[2]) if parts[2] != "-" else 0, 2),
            "mid_net": round(float(parts[3]) if parts[3] != "-" else 0, 2),
            "small_net": round(float(parts[4]) if len(parts) > 4 and parts[4] != "-" else 0, 2),
            "main_pct": round(float(parts[5]) if len(parts) > 5 and parts[5] != "-" else 0, 2),
        })
    return out


if __name__ == "__main__":
    print("=== 融资融券(全市场) ===")
    items = margin_trading()
    for it in items[:3]:
        print(f"  {it['date']} 融资余额{it['rzye']}亿 融券{it['rqye']}亿 净买入{it['rzch']}亿")
    print(f"\n=== 分红(600519) ===")
    items = dividend_history("600519")
    for it in items[:3]:
        print(f"  {it['year']}年 每股{it['cash_div']}元")
