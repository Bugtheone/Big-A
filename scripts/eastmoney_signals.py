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
    """个股分钟级主力资金流向（主力/小单/中单/大单/超大单净流入）。

    ⚠️ 2026-08-09 实测：旧端点 push2his.eastmoney.com/api/qt/stock/fflow/minute/get
    已 404（4 主机全失效），改用 SKILL.md §3.4 文档端点
    push2.eastmoney.com/api/qt/stock/fflow/kline/get（klt=1 分钟）。
    金额单位：元（非万元）。

    返回每条: {time, main_net, small_net, mid_net, large_net, super_net}
    """
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    params = {
        "secid": secid, "klt": 1,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/",
               "Origin": "https://quote.eastmoney.com"}
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
    except Exception as e:
        print(f"[fund_flow_minute] {code} 请求失败: {e}")
        return []
    out = []
    for line in (r.get("data") or {}).get("klines") or []:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        out.append({
            "time": parts[0],
            "main_net": float(parts[1]),
            "small_net": float(parts[2]),
            "mid_net": float(parts[3]),
            "large_net": float(parts[4]),
            "super_net": float(parts[5]),
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
                "sortColumns": "SECURITY_CODE",
                "sortTypes": "1",
                "pageSize": 200,
                "pageNumber": 1,
                "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
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
                "sortColumns": "FREE_DATE",
                "sortTypes": "1",
                "pageSize": 500,
                "pageNumber": 1,
                "reportName": "RPT_LIFT_STAGE",
                "columns": "ALL",
                "source": "WEB", "client": "WEB",
                "filter": f'(FREE_DATE>=\'{start}\')(FREE_DATE<=\'{end}\')',
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
        unlock_dt = str(it.get("FREE_DATE", ""))[:10]
        days_left = 0
        if unlock_dt:
            days_left = (datetime.strptime(unlock_dt, "%Y-%m-%d") - datetime.now()).days
        # RPT_LIFT_STAGE: CURRENT_FREE_SHARES(万股) / LIFT_MARKET_CAP(万元)
        cap_yi = None
        try:
            cap_yi = round(float(it.get("LIFT_MARKET_CAP", 0) or 0) / 1e4, 2)
        except (TypeError, ValueError):
            cap_yi = None
        out.append({
            "code": it.get("SECURITY_CODE"),
            "name": it.get("SECURITY_NAME_ABBR"),
            "unlock_date": unlock_dt,
            "unlock_shares": it.get("CURRENT_FREE_SHARES"),
            "unlock_ratio": None,
            "float_mcap": cap_yi,
            "days_left": days_left,
        })
    return out


# ========== 行业对比 (§3.7 东财版) ==========

def em_industry_board(board_type: str = "行业", date: str = None) -> list[dict]:
    """东财行业/概念板块榜单（push2 clist，V3.6.1 对齐 SKILL.md §3.7）。

    2026-08-09 修复：旧实现用 datacenter RPTA_WEB_THEME_DETAIL + `m:90+t2`（缺冒号笔误）
    恒返回空；改走 push2 clist（m:90+t:2 / m:90+t:3，fid=f3 按涨幅排序）。

    返回每板块: code/name/pct/up_count/down_count/lead_stock/lead_pct
    """
    fs = {"行业": "m:90+t:2", "概念": "m:90+t:3"}.get(board_type, "m:90+t:2")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "200", "po": "1", "np": "1",
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": fs,
        "fields": "f12,f14,f3,f104,f105,f128,f136,f140",
    }
    d = em_get(url, params=params, headers={"Referer": "https://quote.eastmoney.com/"}, timeout=15)
    diff = (d.get("data") or {}).get("diff") or []
    if isinstance(diff, dict):
        diff = list(diff.values())
    out = []
    for it in diff:
        out.append({
            "code": it.get("f12", ""),
            "name": it.get("f14", ""),
            "pct": it.get("f3", 0),
            "up_count": it.get("f104", 0),
            "down_count": it.get("f105", 0),
            "lead_stock": it.get("f140", ""),
            "lead_pct": it.get("f136", 0),
        })
    return out


# ========== 个股板块归属 (§3.3 东财 slist) ==========

def eastmoney_concept_blocks(code: str) -> dict:
    """个股所属板块/概念归属（东财 slist，一次请求拿全，2026-08-09 融入）。
    返回: {total, boards: [{name, code(BK码), change_pct, lead_stock}], concept_tags: [板块名...]}
    """
    market_code = 1 if code.startswith("6") else 0
    params = {
        "fltt": "2", "invt": "2",
        "secid": f"{market_code}.{code}",
        "spt": "3", "pi": "0", "pz": "200", "po": "1",
        "fields": "f12,f14,f3,f128",
    }
    try:
        d = em_get("https://push2.eastmoney.com/api/qt/slist/get",
                   params=params, headers={"Referer": "https://quote.eastmoney.com/"}, timeout=15)
    except Exception as e:
        print(f"[WARN] 东财板块归属请求失败: {e}")
        return {"total": 0, "boards": [], "concept_tags": []}
    diff = (d.get("data") or {}).get("diff") or {}
    items = diff.values() if isinstance(diff, dict) else diff
    boards = []
    for it in items:
        boards.append({
            "name": it.get("f14", ""),
            "code": it.get("f12", ""),
            "change_pct": it.get("f3", ""),
            "lead_stock": it.get("f128", ""),
        })
    return {"total": len(boards), "boards": boards,
            "concept_tags": [b["name"] for b in boards]}


# ========== 连板股龙虎榜 (§3.9) ==========

def daily_dragon_tiger(board_type: str = "daily_billboard", date: str = None) -> list[dict]:
    """东财每日龙虎榜连板股统计。board_type: daily_billboard/weekly_billboard。
    返回每只: code/name/pct/days(连板天数)/reason/net_buy_yi
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    # ⚠️ reportName 必须连写且带 _DETAILSNEW 后缀（2026-08-09 实测）：
    # RPT_DAILY_BILLBOARD_DETAILSNEW / RPT_DAILYBILLBOARDDETAILS 均返回 0 条，
    # 正确为 RPT_DAILYBILLBOARD_DETAILSNEW（board 名去下划线连写 + _DETAILSNEW）
    report_name = f"RPT_{board_type.replace('_', '').upper()}_DETAILSNEW"
    try:
        r = em_get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "sortColumns": "TRADE_DATE,SECURITY_CODE",
                "sortTypes": "-1,1",
                "pageSize": 500,
                "pageNumber": 1,
                "reportName": report_name,
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


# ============================================================
# §8.5 东财日内异动池（V3.6.1 · SKILL.md 8.5，2026-08-09 融入）
# ============================================================

ANOMALY_BASE = "https://dycalchis.eastmoney.com/price-anomaly"
# 东财 H5 固定公共参数，缺 team 会被拒（unknow team）
HQ_PARAMS = {"team": "h5", "product": "EastMoney", "client": "WAP",
             "version": "9001", "name": "WAP", "user": "123"}

# 异动规则码（e 字段）→ 文字说明；s==6 且 e∈{4,5,6,7} 时按 e*10 取更严阈值那档
ANOMALY_RULES = {
    1:  "主板连续10个交易日内4次出现同向异常波动",
    2:  "创业板连续10个交易日内3次出现同向异常波动",
    3:  "科创板连续10个交易日内3次出现同向异常波动",
    4:  "连续十个交易日内日收盘价涨跌幅偏离值累计达到+100%",
    5:  "连续十个交易日内日收盘价涨跌幅偏离值累计达到-50%",
    6:  "连续三十个交易日内日收盘价涨跌幅偏离值累计达到+200%",
    7:  "连续三十个交易日内日收盘价涨跌幅偏离值累计达到-70%",
    8:  "北交所连续10个交易日内3次出现同向异常波动",
    40: "连续十个交易日内日收盘价涨跌幅偏离值累计达到+150%",
    50: "连续十个交易日内日收盘价涨跌幅偏离值累计达到-60%",
    60: "连续30个交易日内日收盘价涨跌幅偏离值累计达到+300%",
    70: "连续30个交易日内日收盘价涨跌幅偏离值累计达到-75%",
}


def _anomaly_market(code, m, board=None) -> str:
    """异动记录 → 交易所。北交所与深市同为 m=0，按代码号段判（920/43/83/87 或规则码 8）。"""
    c = str(code or "")
    if c.startswith("920") or c[:2] in ("43", "83", "87") or board == 8:
        return "BJ"
    return "SH" if m == 1 else "SZ"


def _anomaly_get(path: str, page_size: int, page_no: int, **extra) -> dict:
    params = {**HQ_PARAMS, "pageSize": str(page_size), "pageNo": str(page_no), **extra}
    d = em_get(f"{ANOMALY_BASE}/{path}", params=params,
               headers={"Referer": "https://vipmoney.eastmoney.com/"}, timeout=20)
    if d.get("result") != 0:
        raise RuntimeError(f"东财异动接口拒绝: result={d.get('result')} msg={d.get('msg')!r}")
    return d


def em_price_anomaly(page_size: int = 200, page_no: int = 1) -> dict:
    """日内异动明细（price-anomaly/list）。返回 {date, items:[...]}"""
    d = _anomaly_get("list", page_size, page_no)
    items = []
    for x in d.get("data") or []:
        e = x.get("e")
        key = e * 10 if (x.get("s") == 6 and e in (4, 5, 6, 7)) else e
        items.append({
            "code": x.get("c"), "name": x.get("n"),
            "market": _anomaly_market(x.get("c"), x.get("m"), x.get("s")),
            "change_pct": x.get("a"),
            "deviation": x.get("x"),
            "days": x.get("d"),
            "board": x.get("s"),
            "rule_code": key,
            "rule": ANOMALY_RULES.get(key, f"未知规则码 {key}"),
            "is_today": x.get("o") != 2,
        })
    return {"date": str(d.get("date", "")), "pages": d.get("pages", 0), "items": items}


def em_price_anomaly_count(page_size: int = 50, page_no: int = 1,
                           sort_key: str = "", sort_dir: str = "") -> dict:
    """异动统计（price-anomaly/count）：按标的聚合的异动次数 + 现价。"""
    d = _anomaly_get("count", page_size, page_no, sortKey=sort_key, sortDir=sort_dir)
    items = [{
        "code": x.get("c"), "name": x.get("n"),
        "market": _anomaly_market(x.get("c"), x.get("m"), x.get("s")),
        "price": x.get("p"),
        "change_pct": x.get("a"),
        "times": x.get("t"),
        "deviation": x.get("x"),
        "days": x.get("d"),
        "board": x.get("s"),
    } for x in d.get("data") or []]
    return {"date": str(d.get("date", "")), "pages": d.get("pages", 0), "items": items}
