#!/usr/bin/env python3
"""新浪数据层 — 财报三表 + ETF期权T型报价+希腊字母 (SKILL.md §6.4/§9.1)"""
import requests, re, time
from datetime import datetime
from scripts.eastmoney_api import UA

_session = requests.Session()
_session.trust_env = False

SINA_OPT_HDR = {"Referer":"https://stock.finance.sina.com.cn/","User-Agent":UA}

def _opt_f(x):
    try: return float(x)
    except (ValueError, TypeError): return x

def _sina_hq(param: str) -> list:
    r = _session.get(f"https://hq.sinajs.cn/list={param}",headers=SINA_OPT_HDR,timeout=10)
    r.encoding="gbk"; t=r.text
    return t.split('"')[1].split(",") if '"' in t else []

def sina_option_codes(underlying: str = "510050", call: bool = True) -> dict:
    cate={"510050":"50ETF","510300":"300ETF","588000":"科创50ETF","510500":"500ETF"}.get(underlying,"50ETF")
    try:
        months=_session.get(f"https://stock.finance.sina.com.cn/futures/api/openapi.php/StockOptionService.getStockName?exchange=null&cate={cate}",
            headers=SINA_OPT_HDR,timeout=10).json()["result"]["data"]["contractMonth"]
    except Exception: return {}
    months=[m.replace("-","")[2:] for m in months[1:]]
    flag="OP_UP_" if call else "OP_DOWN_"
    out={}
    for m in months:
        codes=[c.replace("CON_OP_","") for c in _sina_hq(f"{flag}{underlying}{m}") if c.startswith("CON_OP_")]
        if codes: out[m]=codes
    return out

def sina_option_tquote(code: str) -> dict:
    v=_sina_hq(f"CON_OP_{code}")
    if len(v)<43: return {}
    return {"bid_vol":_opt_f(v[0]),"bid":_opt_f(v[1]),"last":_opt_f(v[2]),"ask":_opt_f(v[3]),
        "ask_vol":_opt_f(v[4]),"open_interest":_opt_f(v[5]),"pct":_opt_f(v[6]),"strike":_opt_f(v[7]),
        "prev_close":_opt_f(v[8]),"open":_opt_f(v[9]),"limit_up":_opt_f(v[10]),
        "limit_down":_opt_f(v[11]),"name":v[37],"amplitude":_opt_f(v[38]),
        "high":_opt_f(v[39]),"low":_opt_f(v[40]),"volume":_opt_f(v[41]),"amount":_opt_f(v[42])}

def sina_option_greeks(code: str) -> dict:
    raw=_sina_hq(f"CON_SO_{code}")
    if len(raw)<16: return {}
    v=[raw[0]]+raw[4:]
    return {"name":v[0],"volume":_opt_f(v[1]),"delta":_opt_f(v[2]),"gamma":_opt_f(v[3]),
        "theta":_opt_f(v[4]),"vega":_opt_f(v[5]),"iv":_opt_f(v[6]),"high":_opt_f(v[7]),
        "low":_opt_f(v[8]),"trade_code":v[9],"strike":_opt_f(v[10]),"last":_opt_f(v[11]),
        "theory":_opt_f(v[12])}

def sina_financial_report(code: str) -> dict:
    """新浪财报三表（资产负债表/利润表/现金流量表）。
    code: 6位代码。返回 {balance,income,cashflow} 每表 list of {item_name,amount}"""
    prefix="sh" if code.startswith(("6","9")) else "sz"
    out={}
    for rtype,name in [("BalanceSheet","balance"),("ProfitStatement","income"),("CashFlow","cashflow")]:
        try:
            url=f"https://vip.stock.finance.sina.com.cn/corp/go.php/vFD_{rtype}/stockid/{code}/ctrl/part/displaytype/4.phtml"
            r=_session.get(url,headers={"User-Agent":UA},timeout=15)
            r.encoding="gbk"
            rows=re.findall(r'<tr[^>]*>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?</tr>',r.text,re.S)
            out[name]=[{"item":re.sub(r'<[^>]+>','',r[0]).strip(),"amount":re.sub(r'<[^>]+>','',r[1]).strip()} for r in rows]
        except Exception as e:
            out[name]=[]
    return out
