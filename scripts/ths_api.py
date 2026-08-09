#!/usr/bin/env python3
"""同花顺接口层 — 一致预期EPS + 热点原因 + 热榜 + 北向分钟流 (SKILL.md §2.2/§3.1/§3.2/§10.2-ths)"""
import requests
from datetime import datetime
from pathlib import Path
from scripts.eastmoney_api import UA

_session = requests.Session()
_session.trust_env = False

HSGT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "Chrome/117.0.0.0 Safari/537.36"
    ),
    "Host": "data.hexin.cn",
    "Referer": "https://data.hexin.cn/",
}

def ths_eps_forecast(code: str) -> list:
    """同花顺机构一致预期EPS。

    ⚠️ 2026-08-09 实测：旧端点 data.10jqka.com.cn/financial/yjyg/op/code/{code}/
    页面结构已改版（myTable02 表不存在），改用 SKILL.md §2.2 文档端点
    basic.10jqka.com.cn/new/{code}/worth.html（read_html 解析）。
    code 支持 688017 / SH688017 / 688017.SH（内部归一化为纯 6 位）。
    返回 [{年度, 预测机构数, 最小值, 均值, 最大值}, ...]（空表 = 无机构覆盖）
    """
    import pandas as pd
    from io import StringIO
    c = code[-6:] if len(code) > 6 else code
    url = f"https://basic.10jqka.com.cn/new/{c}/worth.html"
    headers = {
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36"),
        "Referer": "https://basic.10jqka.com.cn/",
    }
    try:
        r = _session.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        dfs = pd.read_html(StringIO(r.text))
    except Exception as e:
        return []
    for df in dfs:
        cols = [str(x) for x in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            return df.to_dict("records")
    return dfs[0].to_dict("records") if dfs else []

def ths_hot_reason(date: str = None) -> list:
    """同花顺当日强势股+涨停原因。返回 [{code,name,pct,reason,turnover,pe,market_cap}, ...]

    端点：zx.10jqka.com.cn/event/api/getharden（V3.6.0 文档化端点）。
    旧端点 data.10jqka.com.cn/dataapi/rank/hot_reason 已 404 失效（2026-08-02 实测）。
    date 为 None 时自动取最近交易日（跳过周末，最多回退 7 天）。
    """
    from datetime import date as _date, timedelta

    if date is None:
        date = _date.today()
        for _ in range(7):
            if date.weekday() < 5:
                break
            date -= timedelta(days=1)
        date = date.strftime("%Y-%m-%d")

    url = (f"http://zx.10jqka.com.cn/event/api/getharden/"
           f"date/{date}/orderby/date/orderway/desc/charset/GBK/")
    try:
        r = _session.get(url, headers={"User-Agent": UA}, timeout=10)
        d = r.json()
    except Exception as e:
        return []
    if d.get("errocode", 0) != 0:
        return []
    rows = d.get("data") or []
    return [{"code": it.get("code"), "name": it.get("name"), "pct": it.get("zhangfu"),
             "reason": it.get("reason", ""), "turnover": it.get("huanshou"),
             "pe": None, "market_cap": None} for it in rows]

def ths_hot_list(period: str = "hour") -> list:
    """同花顺热榜。period: hour/day。返回 [{rank,code,name,heat,pct,rank_chg,concepts,tag}, ...]"""
    try:
        r = _session.get("https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock",
            params={"stock_type":"a","type":period,"list_type":"normal"},
            headers={"User-Agent":UA},timeout=10)
        lst = (r.json().get("data") or {}).get("stock_list") or []
    except Exception as e: return []
    out=[]
    for it in lst:
        tag=it.get("tag") or {}
        out.append({"rank":it.get("order"),"code":it.get("code"),"name":it.get("name"),
            "heat":it.get("rate"),"pct":it.get("rise_and_fall"),"rank_chg":it.get("hot_rank_chg"),
            "concepts":tag.get("concept_tag") or [],"tag":tag.get("popularity_tag","")})
    return out


# ========== 北向资金分钟级快照 + 缓存（§3.2）===========================

def hsgt_realtime() -> dict:
    """同花顺北向资金当日分钟级快照。
    返回: {times: [...], hgt_yi: [...], sgt_yi: [...]}"""
    url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
    try:
        r = _session.get(url, headers=HSGT_HEADERS, timeout=10)
        d = r.json()
        times = d.get("time", [])
        hgt = d.get("hgt", [])
        sgt = d.get("sgt", [])
        return {"times": times, "hgt_yi": hgt, "sgt_yi": sgt}
    except Exception as e:
        return {"times": [], "hgt_yi": [], "sgt_yi": [], "error": str(e)}


def _northbound_cache_path() -> Path:
    return Path(__file__).parent.parent / "data" / "northbound_snapshots.csv"


def _save_northbound_snapshot(data: dict) -> None:
    """将分钟快照追加到本地CSV缓存（去重）"""
    import csv
    cache = _northbound_cache_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if cache.exists():
        with open(cache, "r", encoding="utf-8") as f:
            existing = {r.split(",")[0] for r in f if r and "," in r}
    with open(cache, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if cache.stat().st_size == 0:
            w.writerow(["datetime", "hgt_yi", "sgt_yi"])
        for i, t in enumerate(data.get("times", [])):
            key = t[:16]
            if key in existing:
                continue
            h = data["hgt_yi"][i] if i < len(data.get("hgt_yi") or []) else ""
            s = data["sgt_yi"][i] if i < len(data.get("sgt_yi") or []) else ""
            w.writerow([key, h, s])
            existing.add(key)


def _load_northbound_history(days: int = 5) -> list:
    """从本地缓存加载最近N天的分钟级数据"""
    import csv
    from datetime import datetime, timedelta
    cache = _northbound_cache_path()
    if not cache.exists():
        return []
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = []
    with open(cache, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("datetime", "")[:10] >= cutoff:
                rows.append(r)
    return rows


if __name__ == '__main__':
    data = hsgt_realtime()
    print(f"北向分钟流: {len(data.get('times', []))} 个数据点")
    if data.get("times"):
        print(f"  时间范围: {data['times'][0]} ~ {data['times'][-1]}")
        latest_hgt = data.get("hgt_yi", [])
        latest_sgt = data.get("sgt_yi", [])
        if latest_hgt:
            print(f"  最新沪股通: {latest_hgt[-1]:.2f} 亿")
        if latest_sgt:
            print(f"  最新深股通: {latest_sgt[-1]:.2f} 亿")
    else:
        print("  (无数据或请求失败)")
