#!/usr/bin/env python3
"""东财信息层 — 个股信息 + 涨停四池 + 人气榜 + 概念命中 (SKILL.md §6.3/§8.1/§10.2)"""
import requests, time
from datetime import datetime
from scripts.eastmoney_api import UA, em_get

_session = requests.Session()
_session.trust_env = False

EM_HOT_BODY = {"appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38"}

def eastmoney_stock_info(code: str) -> dict:
    secid = f"{'1' if code.startswith('6') else '0'}.{code}"
    try:
        d = em_get("https://push2.eastmoney.com/api/qt/stock/get",
            params={"secid": secid, "invt": 2, "fltt": 2,
                    "fields": "f57,f58,f84,f100,f115,f116,f117,f167,f173",
                    "ut": "f057cbcbce2a86e2866ab8877db1d059"},
            headers={"Referer": "https://quote.eastmoney.com/"}, timeout=10)
        info = d.get("data") or {}
    except Exception as e:
        print(f"[stock_info] {code} err: {e}") ; return {}
    return {"code": info.get("f57",""),"name": info.get("f58",""),
            "industry": info.get("f100",""),"pe_ttm": info.get("f115"),
            "pb": info.get("f167"),"total_mcap_yi": round(float(info.get("f116",0) or 0)/1e8,2),
            "float_mcap_yi": round(float(info.get("f117",0) or 0)/1e8,2),
            "listing_date": info.get("f84","")}

def _em_pool(pool_type: str, date: str = None) -> list:
    """打板池统一入口（涨停/炸板/跌停/昨涨停）。

    降级链（2026-08-02 修复）：
      ① 东财 push2ex getTopicZTPool（官方端点，2026-07 起 rc=102 失效）
      ② 同花顺涨停揭秘 ths_limit_up_pool（V3.6.0 文档化替代源，仅 zt_pool 有明细；
         zb/dt/yzt 无逐条明细源，降级后返回空并在 stderr 提示）
    """
    type_map = {"zt_pool":"limitUp","zb_pool":"limitUpBroken","dt_pool":"limitDown","yzt_pool":"surgedLimitUp"}
    if date is None: date = datetime.now().strftime("%Y%m%d")
    try:
        resp = em_get("https://push2ex.eastmoney.com/getTopicZTPool",
            params={"ut":"7eea3edcaed734bea62c59f1c79e95a8","cb":"","sort":"fbt:asc",
                    "fdate":date,"type":type_map.get(pool_type,"limitUp"),"pagesize":2000,"page":1},
            headers={"Referer":"https://data.eastmoney.com/"},timeout=15)
        rc = resp.get("rc", 0)
        rows = (resp.get("data") or {}).get("pool") or []
        if rc == 0 and rows:
            out = []
            for it in rows:
                out.append({"code":it.get("c",""),"name":it.get("n",""),"pct":it.get("p",""),
                    "limit_days":it.get("lbc",0)>>16 if it.get("lbc") else 0,
                    "first_time":it.get("fbt",""),"last_time":it.get("lbt",""),
                    "reason":it.get("hybk",""),"turnover":it.get("ltsz","")})
            return out
        print(f"[em_pool] push2ex/{pool_type} rc={rc} date={date} — API已失效，降级同花顺")
    except Exception as e:
        print(f"[em_pool] push2ex/{pool_type} err: {e}")

    # ── 降级：同花顺涨停揭秘（仅 zt_pool 有逐条明细）──
    if pool_type == "zt_pool":
        try:
            from scripts.eastmoney_api import get_eastmoney
            data = get_eastmoney().ths_limit_up_pool(date, page=1, limit=200)
            zt = data.get("zt_list") or []
            return [{"code": r.get("code", ""), "name": r.get("name", ""),
                     "pct": r.get("change_rate", 0),
                     "limit_days": r.get("high_days_value", 0),
                     "first_time": r.get("first_time", ""), "last_time": "",
                     "reason": r.get("reason_type", ""),
                     "turnover": r.get("turnover_rate", 0)} for r in zt]
        except Exception as e:
            print(f"[em_pool] 同花顺降级失败: {e}")
    else:
        print(f"[em_pool] {pool_type} 无独立备胎源（同花顺仅提供计数），返回空")
    return []

def em_zt_pool(d=None): return _em_pool("zt_pool", d)
def em_zb_pool(d=None): return _em_pool("zb_pool", d)
def em_dt_pool(d=None): return _em_pool("dt_pool", d)
def em_yzt_pool(d=None): return _em_pool("yzt_pool", d)

def em_hot_rank(top: int = 50) -> list:
    try:
        d1 = em_get("https://emappdata.eastmoney.com/stockrank/getAllCurrentList",
            method="POST", json_body={**EM_HOT_BODY,"marketType":"","pageNo":1,"pageSize":top},
            timeout=10)
        data = d1.get("data") or []
        secids = [("0." if it["sc"].startswith("SZ") else "1.")+it["sc"][2:] for it in data]
        u = em_get("https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={"ut":"f057cbcbce2a86e2866ab8877db1d059","fltt":2,"invt":2,
                    "fields":"f14,f3,f12,f2","secids":",".join(secids)},
            headers={"Referer":"https://quote.eastmoney.com/"},timeout=10)
        diff = (u.get("data") or {}).get("diff") or []
        if isinstance(diff,dict): diff=list(diff.values())
        nm = {x["f12"]:(x.get("f14"),x.get("f2"),x.get("f3")) for x in diff}
    except Exception as e: return []
    return [{"rank":it["rk"],"code":it["sc"][2:],"name":nm.get(it["sc"][2:],("","",""))[0],
             "price":nm.get(it["sc"][2:],("","",""))[1],"pct":nm.get(it["sc"][2:],("","",""))[2],
             "rank_chg":it.get("hisRc")} for it in data]

def em_hot_concept(code: str) -> list:
    prefix="SH" if code.startswith("6") else "SZ"
    try:
        d = em_get("https://emappdata.eastmoney.com/stockrank/getHotStockRankList",
            method="POST", json_body={**EM_HOT_BODY,"srcSecurityCode":prefix+code},
            timeout=10)
        data = d.get("data") or []
    except Exception: return []
    return [{"concept":x.get("conceptName"),"bk":x.get("conceptId"),"hit":x.get("hitCount")} for x in data]
