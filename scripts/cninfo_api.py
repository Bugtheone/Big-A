#!/usr/bin/env python3
"""巨潮资讯层 — 公告检索 + 互动易问答 (SKILL.md §7.1/§10.1)"""
import requests
from datetime import datetime
from scripts.eastmoney_api import UA

_session = requests.Session()
_session.trust_env = False

# 巨潮 股票→orgId 映射（模块级缓存，首次调用拉取一次，全程复用）
_CNINFO_ORGID_MAP = {}

def _cninfo_orgid(code: str) -> str:
    """查股票真实 orgId。巨潮 orgId 并非统一 `gssx0{code}` 格式（如 601318→9900002221、
    601398→jjxt0000019、688017→9900041602），硬编码会导致大量股票（尤其 601xxx 段）
    返回 totalAnnouncement=0、查不到公告。优先动态查官方映射表，查不到再回退硬编码。"""
    global _CNINFO_ORGID_MAP
    if not _CNINFO_ORGID_MAP:
        try:
            r = _session.get("http://www.cninfo.com.cn/new/data/szse_stock.json",
                              headers={"User-Agent": UA}, timeout=15)
            _CNINFO_ORGID_MAP = {s["code"]: s["orgId"]
                                 for s in r.json().get("stockList", [])}
        except Exception as e:
            # 映射表拉取失败不致命：回退硬编码规则（仅部分老股票适用）
            pass
    org = _CNINFO_ORGID_MAP.get(code)
    if org:
        return org
    # fallback：老格式（仅部分老股票如 600519/600036 适用）
    if code.startswith("6"):
        return f"gssh0{code}"
    elif code.startswith("8") or code.startswith("4"):
        return f"gsbj0{code}"
    return f"gssz0{code}"


def cninfo_announcements(code: str, page_size: int = 20, page_num: int = 1, keyword: str = "") -> list:
    """巨潮公告检索。code: 6位代码。返回 [{title,url,ann_date,sec_code,sec_name}, ...]

    端点：POST /new/hisAnnouncement/query（SKILL.md §7.1 实测可用）；
    orgId 动态查官方映射表，杜绝 `{code},orgId` 字面量导致 601xxx 段查空。"""
    try:
        org_id = _cninfo_orgid(code)
        r = _session.post("https://www.cninfo.com.cn/new/hisAnnouncement/query",
            data={"stock": f"{code},{org_id}",
                  "tabName": "fulltext",
                  "pageSize": str(page_size), "pageNum": str(page_num),
                  "column": "szse", "category": "", "plate": "",
                  "seDate": "", "searchkey": keyword,
                  "secid": "", "sortName": "", "sortType": "", "isHLtitle": "true"},
            headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
                     "Referer": "https://www.cninfo.com.cn/new/disclosure",
                     "Origin": "https://www.cninfo.com.cn"},
            timeout=15)
        d = r.json()
        rows = d.get("announcements") or []
    except Exception as e:
        return []
    out = []
    for it in rows:
        # 公告日期用 announcementTime（Unix 毫秒）转换；adjunctUrl 末段是公告ID非日期
        ts = it.get("announcementTime")
        ann_date = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if isinstance(ts, (int, float)) else ""
        out.append({
            "title": it.get("announcementTitle", ""),
            "url": f"https://www.cninfo.com.cn/new/disclosure/detail?announceId={it.get('announcementId', '')}",
            "ann_date": ann_date,
            "sec_code": it.get("secCode", ""),
            "sec_name": it.get("secName", ""),
        })
    return out


def cninfo_irm(code: str, page_size: int = 30, page_num: int = 1) -> list:
    """互动易问答。code: 6位代码。返回 [{code,company,question,answer,answerer,ask_time}, ...]"""
    try:
        r1=_session.post("https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo",
            data={"keyWord":code},headers={"User-Agent":UA},timeout=10)
        d1=r1.json().get("data") or []
        if not d1: return []
        org_id=d1[0].get("secid")
        r2=_session.post("https://irm.cninfo.com.cn/newircs/company/question",
            params={"_t":1,"stockcode":code,"orgId":org_id,"pageSize":page_size,
                    "pageNum":page_num,"keyWord":"","startDay":"","endDay":""},
            headers={"User-Agent":UA},timeout=10)
        rows=r2.json().get("rows") or []
    except Exception as e: return []
    out=[]
    for it in rows:
        pd=it.get("pubDate")
        out.append({"code":it.get("stockCode"),"company":it.get("companyShortName"),
            "question":it.get("mainContent"),"answer":it.get("attachedContent"),
            "answerer":it.get("attachedAuthor"),
            "ask_time":datetime.fromtimestamp(pd/1000).strftime("%Y-%m-%d %H:%M") if pd else ""})
    return out
