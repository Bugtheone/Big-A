#!/usr/bin/env python3
"""东财信号层 — 龙虎榜 + 资金流分钟 + 解禁 + 行业对比 + 连板股龙虎榜。
2026-07-24 从 SKILL.md §3.4~§3.9 融入。
"""

import time
from datetime import datetime, timedelta

import requests

from scripts.eastmoney_api import UA, em_get, eastmoney_datacenter

_session = requests.Session()
_session.trust_env = False

# ========== 分钟级资金流向 (§3.4) ==========

def eastmoney_fund_flow_minute(code: str, date: str = None) -> list[dict]:
    """个股分钟级主力资金流向（大/中/小单净流入）。
    code: 6位代码。date: YYYY-MM-DD（默认当日）。
    返回每条: {time, main_in(主力净流入万元), big_in(大单), mid_in(中单), small_in(小单)}
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        r = em_get(
            "https://push2his.eastmoney.com/api/qt/stock/fflow/minute/get",
            params={
                "lmt": 0, "klt": 1, "fields1": "f1,f2,f3,f4",
                "fields2": "f51,f52,f53,f54,f55",
                "secid": f"{'1' if code.startswith('6') else '0'}.{code}",
                "ut": "b2884a393a59ad640ee3e7d59f570b63",
            },
            headers={"User-Agent": UA, "Referer": "https://data.eastmoney.com/"},
            timeout=10,
        )
        js = r
        lines = (js.get("data") or {}).get("data") or []
    except Exception as e:
        print(f"[fund_flow_minute] {code} 失败: {e}")
        return []
    out = []
    for line in lines:
        parts = line.split(",")
        if len(parts) < 4:
            continue
        out.append({
            "time": parts[0],
            "main_in": float(parts[1]) if parts[1] != "-" else 0,
            "big_in": float(parts[2]) if parts[2] != "-" else 0,
            "mid_in": float(parts[3]) if parts[3] != "-" else 0,
            "small_in": float(parts[4]) if len(parts) > 4 and parts[4] != "-" else 0,
        })
    return out


# ========== 龙虎榜日榜 (§3.5) ==========

def dragon_tiger_board(date: str = None) -> list[dict]:
    """东财龙虎榜每日上榜个股。
    date: YYYY-MM-DD（默认当日）。返回每只: code/name/pct/close/reason/turnover/
    net_buy_yi(净买额亿元)/buy_seats(买方席位列表)/sell_seats(卖方席位列表)
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        r = em_get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "sortColumns": "NET_BUY_AMT",
                "sortTypes": "-1",
                "pageSize": 200,
                "pageNumber": 1,
                "reportName": "RPT_DAILYBILLBOARD_DAILY",
                "columns": "ALL",
                "source": "WEB", "client": "WEB",
                "filter": f'(TRADE_DATE=\'{date}\')',
            },
            headers={"User-Agent": UA, "Referer": "https://data.eastmoney.com/"},
            timeout=15,
        )
        rows = (r.get("result") or {}).get("data") or []
    except Exception as e:
        print(f"[dragon_tiger] 请求失败: {e}")
        return []
    out = []
    for it in rows:
        buy_seats = []
        sell_seats = []
        for i in range(1, 6):
            b = it.get(f"BUY_TRADER_{i}", "")
            s = it.get(f"SELL_TRADER_{i}", "")
            if b:
                buy_seats.append({"name": b, "amount": it.get(f"BUY_TRADER_AMT_{i}", 0)})
            if s:
                sell_seats.append({"name": s, "amount": it.get(f"SELL_TRADER_AMT_{i}", 0)})
        out.append({
            "code": it.get("SECURITY_CODE"),
            "name": it.get("SECURITY_NAME_ABBR"),
            "pct": it.get("CHANGE_RATE"),
            "close": it.get("CLOSE_PRICE"),
            "reason": it.get("EXPLANATION", ""),
            "net_buy_yi": round(float(it.get("NET_BUY_AMT", 0) or 0) / 1e8, 2),
            "turnover": it.get("TURNOVERRATE"),
            "buy_seats": buy_seats,
            "sell_seats": sell_seats,
        })
    return out


# ========== 解禁提醒 (§3.6) ==========

def lockup_expiry(days: int = 7) -> list[dict]:
    """近期限售解禁提醒。days: 未来N天。
    返回每只: code/name/unlock_date(解禁日)/unlock_shares(解禁股数万)/unlock_ratio(解禁占总股本%)/
    float_mcap(解禁市值亿)/days_left(距今天数)
    """
    start = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        r = em_get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "sortColumns": "UNLOCK_DATE",
                "sortTypes": "1",
                "pageSize": 500,
                "pageNumber": 1,
                "reportName": "RPT_LIFT_STATISTICS",
                "columns": "ALL",
                "source": "WEB", "client": "WEB",
                "filter": f'(UNLOCK_DATE>=\'{start}\')(UNLOCK_DATE<=\'{end}\')',
            },
            headers={"User-Agent": UA, "Referer": "https://data.eastmoney.com/"},
            timeout=15,
        )
        rows = (r.get("result") or {}).get("data") or []
    except Exception as e:
        print(f"[lockup] 请求失败: {e}")
        return []
    out = []
    for it in rows:
        unlock_dt = it.get("UNLOCK_DATE", "")[:10]
        days_left = 0
        if unlock_dt:
            days_left = (datetime.strptime(unlock_dt, "%Y-%m-%d") - datetime.now()).days
        out.append({
            "code": it.get("SECURITY_CODE"),
            "name": it.get("SECURITY_NAME_ABBR"),
            "unlock_date": unlock_dt,
            "unlock_shares": it.get("UNLOCK_SHARES"),
            "unlock_ratio": it.get("UNLOCK_RATIO"),
            "float_mcap": round(float(it.get("UNLOCK_SHARES", 0) or 0) * float(it.get("CLOSE_PRICE", 0) or 0) / 1e8, 2),
            "days_left": days_left,
        })
    return out


# ========== 行业对比 (§3.7 东财版) ==========

def em_industry_board(board_type: str = "行业", date: str = None) -> list[dict]:
    """东财行业/概念板块榜单。board_type: "行业"/"概念"。
    返回每板块: code/name/pct/lead_stock/lead_pct/total_mcap/up_count/down_count
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    mt = {"行业": "m:90+t2", "概念": "m:90+t3"}.get(board_type, "m:90+t2")
    data = eastmoney_datacenter({
        "type": "RPTA_WEB_THEME_DETAIL",
        "sty": "ALL",
        "sr": "-1", "st": "12",
        "filter": "(MARKET=ALL)",
        "p": "1", "ps": "200",
    }, m=mt)
    rows = (data.get("data") or []) if isinstance(data, dict) else (data or [])
    out = []
    for it in rows:
        out.append({
            "code": it.get("SECUCODE", ""),
            "name": it.get("BOARD_NAME", ""),
            "pct": it.get("CHANGE_RATE"),
            "lead_stock": it.get("LEAD_STOCK_NAME", ""),
            "lead_pct": it.get("LEAD_STOCK_CHANGE_RATE"),
            "up_count": it.get("UP_COUNT"),
            "down_count": it.get("DOWN_COUNT"),
        })
    return out


# ========== 连板股龙虎榜 (§3.9) ==========

def daily_dragon_tiger(board_type: str = "daily_billboard", date: str = None) -> list[dict]:
    """东财每日龙虎榜连板股统计。board_type: daily_billboard/weekly_billboard。
    返回每只: code/name/pct/days(连板天数)/reason/net_buy_yi
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        r = em_get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "sortColumns": "TRADE_DATE,SECURITY_CODE",
                "sortTypes": "-1,1",
                "pageSize": 500,
                "pageNumber": 1,
                "reportName": f"RPT_{board_type.upper()}DETAILS",
                "columns": "ALL",
                "source": "WEB", "client": "WEB",
                "filter": f'(TRADE_DATE>=\'{date}\')',
            },
            headers={"User-Agent": UA, "Referer": "https://data.eastmoney.com/"},
            timeout=15,
        )
        rows = (r.get("result") or {}).get("data") or []
    except Exception as e:
        print(f"[daily_dragon_tiger] 请求失败: {e}")
        return []
    out = []
    for it in rows:
        out.append({
            "code": it.get("SECURITY_CODE"),
            "name": it.get("SECURITY_NAME_ABBR"),
            "pct": it.get("CHANGE_RATE"),
            "days": it.get("ACCUMULATE_DAYS"),
            "reason": it.get("EXPLANATION", ""),
            "net_buy_yi": round(float(it.get("NET_BUY_AMT", 0) or 0) / 1e8, 2),
        })
    return out


if __name__ == "__main__":
    print("=== 龙虎榜测试 ===")
    items = dragon_tiger_board()
    for it in items[:3]:
        print(f"  {it['name']} {it['pct']}% 净买{it['net_buy_yi']}亿 {it['reason'][:20]}")
    print(f"\n=== 限售解禁(近7日) ===")
    items = lockup_expiry(7)
    for it in items[:3]:
        print(f"  {it['name']} {it['unlock_date']} 市值{it['float_mcap']}亿")
