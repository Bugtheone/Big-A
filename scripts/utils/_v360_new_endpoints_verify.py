#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""V3.6.0 新端点验证：em_stock_monitor() + em_price_anomaly()/em_price_anomaly_count()"""

import time
import random
import requests
from datetime import datetime, timedelta, timezone

# ============================================================
# 前置共享 helper（来自 SKILL.md）
# ============================================================
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

EM_SESSION = requests.Session()
EM_SESSION.trust_env = False
EM_SESSION.headers.update({"User-Agent": UA})
try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    _em_adapter = HTTPAdapter(max_retries=Retry(
        total=3, connect=3, backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"]))
    EM_SESSION.mount("https://", _em_adapter)
    EM_SESSION.mount("http://", _em_adapter)
except Exception:
    pass

EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]

def em_get(url: str, params: dict | None = None, headers: dict | None = None,
           timeout: int = 15, **kwargs):
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()

# ============================================================
# §8.4 em_stock_monitor() — 东财重点监控池
# ============================================================
CN_TZ = timezone(timedelta(hours=8))

def cn_today() -> str:
    return datetime.now(CN_TZ).date().isoformat()

MONITOR_URL = "https://mobappconfig.securities.eastmoney.com/emcfg/stock_monitor.json"
_MONITOR_MARKET = {"1": "SH", "0": "SZ", "B": "BJ"}

def em_stock_monitor(only_active: bool = True) -> list[dict]:
    """东财重点监控池。only_active=True 只留今天仍在监控窗口内的。"""
    r = em_get(MONITOR_URL, headers={"Referer": "https://vipmoney.eastmoney.com/"}, timeout=20)
    rows = r.json() or []
    today = cn_today()
    out = []
    for x in rows:
        start, end = x.get("VALIDATESTARTDATE", ""), x.get("VALIDATEENDDATE", "")
        if only_active and not (start <= today <= end):
            continue
        raw_mkt = str(x.get("MARKET", "")).upper()
        out.append({
            "code":   x.get("STKCODE", ""),
            "name":   x.get("STKNAME", ""),
            "market": _MONITOR_MARKET.get(raw_mkt, f"?{raw_mkt}"),
            "start":  start, "end": end,
            "link":   x.get("LINK_URL", ""),
        })
    return out

# ============================================================
# §8.5 em_price_anomaly() / em_price_anomaly_count() — 日内异动
# ============================================================
ANOMALY_BASE = "https://dycalchis.eastmoney.com/price-anomaly"
HQ_PARAMS = {"team": "h5", "product": "EastMoney", "client": "WAP",
             "version": "9001", "name": "WAP", "user": "123"}

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
    c = str(code or "")
    if c.startswith("920") or c[:2] in ("43", "83", "87") or board == 8:
        return "BJ"
    return "SH" if m == 1 else "SZ"

def _anomaly_get(path: str, page_size: int, page_no: int, **extra) -> dict:
    params = {**HQ_PARAMS, "pageSize": str(page_size), "pageNo": str(page_no), **extra}
    r = em_get(f"{ANOMALY_BASE}/{path}", params=params,
               headers={"Referer": "https://vipmoney.eastmoney.com/"}, timeout=20)
    d = r.json()
    if d.get("result") != 0:
        raise RuntimeError(f"东财异动接口拒绝: result={d.get('result')} msg={d.get('msg')!r}")
    return d

def em_price_anomaly(page_size: int = 200, page_no: int = 1) -> dict:
    """日内异动明细（price-anomaly/list）。"""
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
    """异动统计（price-anomaly/count）：按标的聚合的异动次数。"""
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


# ============================================================
# 主验证流程
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  V3.6.0 新端点验证报告")
    print(f"  执行时间: {datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    print("=" * 70)

    # ---- Test 1: 重点监控池 ----
    print("\n[Test 1] §8.4 em_stock_monitor() — 东财重点监控池")
    print("-" * 50)
    try:
        pool = em_stock_monitor(only_active=True)
        print(f"  [OK] 接口调用成功！当前在监控窗口: {len(pool)} 只")
        for s in pool:
            print(f"    {s['code']} {s['name']}({s['market']}) 监控期 {s['start']}~{s['end']}")
        if len(pool) == 0:
            print(f"    (今天可能没有活跃监控标的，或监控池全部已过期)")
    except Exception as e:
        print(f"  [FAIL] {e}")

    # ---- Test 2: 日内异动明细 ----
    print("\n[Test 2] §8.5 em_price_anomaly() — 日内异动明细")
    print("-" * 50)
    try:
        a = em_price_anomaly(page_size=200)
        print(f"  [OK] 接口调用成功！日期 {a['date']} | 页数 {a.get('pages',0)} | 异动 {len(a['items'])} 条")
        if a['items']:
            for s in a['items'][:10]:
                print(f"    {s['code']} {s['name']}({s['market']}) 涨跌{s['change_pct']}% "
                      f"偏离{s['deviation']}%/{s['days']}日 | {s['rule']}")
        else:
            print(f"    (今天无严重异常波动记录)")
    except Exception as e:
        print(f"  [FAIL] {e}")

    # ---- Test 3: 异动聚合统计 ----
    print("\n[Test 3] §8.5 em_price_anomaly_count() — 异动聚合统计")
    print("-" * 50)
    try:
        c = em_price_anomaly_count(page_size=50)
        print(f"  [OK] 接口调用成功！日期 {c['date']} | 页数 {c.get('pages',0)} | 标的 {len(c['items'])} 个")
        if c['items']:
            for s in c['items'][:10]:
                print(f"    {s['code']} {s['name']}({s['market']}) "
                      f"价格{s['price']} 涨跌{s['change_pct']}% 异动{s['times']}次 偏离{s['deviation']}%/{s['days']}日")
        else:
            print(f"    (今天无聚合异动数据)")
    except Exception as e:
        print(f"  [FAIL] {e}")

    # ---- Test 4: 交叉验证（异动 ∩ 监控池）----
    print("\n[Test 4] 交叉验证 — 异动 且 在监控池 = 最高风险")
    print("-" * 50)
    try:
        monitor_codes = {x["code"] for x in pool}
        if 'a' in dir():
            hot = [s for s in a['items'] if s['code'] in monitor_codes]
            if hot:
                print(f"  !! 高风险交集 {len(hot)} 只:")
                for s in hot:
                    print(f"    {s['code']} {s['name']} | {s['rule']}")
            else:
                print(f"  [OK] 无交叉风险（异动标的均不在监控池中）")
    except Exception as e:
        print(f"  [-] 跳过交叉验证: {e}")

    print("\n" + "=" * 70)
    print("  验证完成 — 三个新端点（§8.4 + §8.5 × 2）全部测试")
    print("=" * 70)
