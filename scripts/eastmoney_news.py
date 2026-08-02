#!/usr/bin/env python3
"""东财新闻层 — 个股新闻 + 全球宏观新闻。
2026-07-24 从 SKILL.md §5.1、§5.3 融入。
"""

import time
from datetime import datetime

import requests

from scripts.eastmoney_api import UA, em_get

_session = requests.Session()
_session.trust_env = False

# ========== 个股新闻 (§5.1) ==========

def eastmoney_stock_news(code: str, page: int = 1, page_size: int = 20) -> list[dict]:
    """东财个股新闻列表。
    code: 6位代码。
    返回每条: {title, url, source, pub_time, summary}
    """
    try:
        # 契约对齐 SKILL.md §5.1（原 URL query 参数，合并 em_get 后改为 params dict）
        params = {"sr": -1, "page_size": page_size, "page_index": page,
                  "ann_type": "A", "client_source": "web", "stock_list": code,
                  "f_node": 0, "s_node": 0}
        r = em_get("https://np-anotice-stock.eastmoney.com/api/security/ann", params=params, timeout=10)
        rows = (r.get("data") or {}).get("list") or []
    except Exception as e:
        print(f"[stock_news] {code} err: {e}")
        return []
    out = []
    for it in rows:
        out.append({
            "title": it.get("title_ch", ""),
            "url": f"https://data.eastmoney.com/notices/detail/{code}/{it.get('notice_date','')[:10].replace('-','')}/{it.get('art_code','')}.html",
            "source": "东财公告",
            "pub_time": it.get("notice_date", ""),
            "summary": it.get("summary", "") if isinstance(it.get("summary"), str) else "",
        })
    return out


# ========== 全球宏观新闻 (§5.3) ==========

def eastmoney_global_news(page: int = 1, page_size: int = 20) -> list[dict]:
    """东财全球宏观新闻（国际市场）。
    返回每条: {title, url, source, pub_time, summary}
    """
    try:
        # 东财宏观新闻接口：page_index/page_size 分页契约
        params = {"page_index": page, "page_size": page_size}
        r = em_get("https://finance.eastmoney.com/api/caijingyaowen/global", params=params, timeout=10)
        js = r
        rows = (js.get("Data") or {}).get("List") or js.get("data", {}).get("list") or []
    except Exception as e:
        print(f"[global_news] err: {e}")
        return []
    out = []
    for it in rows:
        out.append({
            "title": it.get("title", "") or it.get("Title", ""),
            "url": it.get("url", "") or it.get("Url", ""),
            "source": it.get("source", "东财"),
            "pub_time": it.get("showTime", "") or it.get("ShowTime", ""),
            "summary": it.get("summary", "") or it.get("Summary", ""),
        })
    return out


if __name__ == "__main__":
    print("=== 个股新闻(600519) ===")
    items = eastmoney_stock_news("600519", page_size=5)
    for it in items:
        print(f"  [{it['pub_time']}] {it['title'][:40]}")
    print(f"\n=== 全球新闻 ===")
    items = eastmoney_global_news(page_size=3)
    for it in items:
        print(f"  [{it['pub_time']}] {it['title'][:40]}")
