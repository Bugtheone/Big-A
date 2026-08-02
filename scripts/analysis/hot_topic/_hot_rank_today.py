import requests
_session = requests.Session()
_session.trust_env = False

import json

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# ===== 同花顺热榜 =====
print("=" * 60)
print("【同花顺热榜 — 今日最热门股票 + 概念标签】")
print("=" * 60)
try:
    r = _session.get(
        "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock",
        params={"stock_type": "a", "type": "day", "list_type": "normal"},
        headers={"User-Agent": UA}, timeout=10
    )
    lst = (r.json().get("data") or {}).get("stock_list") or []
    for i, it in enumerate(lst[:20]):
        rank = it.get("order", i+1)
        code = it.get("code", "")
        name = it.get("name", "")
        heat = it.get("rate", "")
        pct = it.get("rise_and_fall", "")
        rank_chg = it.get("hot_rank_chg", "")
        tag = it.get("tag") or {}
        concepts = tag.get("concept_tag", [])
        pop_tag = tag.get("popularity_tag", "")
        chg_str = f"{rank_chg:+d}" if rank_chg else ""
        print(f"  #{rank} {name}({code}) 热度{heat} | {pct}% | 排名变化{chg_str}")
        if pop_tag:
            print(f"       人气标签: {pop_tag}")
        if concepts:
            print(f"       概念: {' / '.join(concepts[:5])}")
        print()
except Exception as e:
    print(f"  同花顺热榜失败: {e}")

# ===== 东财人气榜 =====
print("=" * 60)
print("【东财人气榜 TOP20】")
print("=" * 60)
EM_HOT_BODY = {"appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38"}
try:
    r = _session.post(
        "https://emappdata.eastmoney.com/stockrank/getAllCurrentList",
        json={**EM_HOT_BODY, "marketType": "", "pageNo": 1, "pageSize": 20},
        headers={"User-Agent": UA}, timeout=10
    )
    data = r.json().get("data") or []
    if data:
        # 补名称/价格
        secids = [("0." if it["sc"].startswith("SZ") else "1.") + it["sc"][2:] for it in data]
        u = _session.get(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "ut": "f057cbcbce2a86e2866ab8877db1d059", "fltt": 2, "invt": 2,
                "fields": "f14,f3,f12,f2", "secids": ",".join(secids)
            },
            headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=10
        )
        diff = (u.json().get("data") or {}).get("diff") or []
        if isinstance(diff, dict):
            diff = list(diff.values())
        nm = {x["f12"]: (x.get("f14"), x.get("f2"), x.get("f3")) for x in diff}

        for it in data:
            code = it["sc"][2:]
            name, price, pct = nm.get(code, ("", None, None))
            rank_chg = it.get("hisRc", "")
            chg_str = f"{rank_chg:+d}" if rank_chg else ""
            print(f"  #{it['rk']} {name}({code}) 价格{price} | {pct}% | 排名变化{chg_str}")
except Exception as e:
    print(f"  东财人气榜失败: {e}")

# ===== 热门股票概念命中（东财） =====
print()
print("=" * 60)
print("【东财热门概念命中 — TOP5热门股被归到什么概念在炒】")
print("=" * 60)
try:
    # 先再拉一次人气榜取TOP5
    r2 = _session.post(
        "https://emappdata.eastmoney.com/stockrank/getAllCurrentList",
        json={**EM_HOT_BODY, "marketType": "", "pageNo": 1, "pageSize": 5},
        headers={"User-Agent": UA}, timeout=10
    )
    top5 = r2.json().get("data") or []
    for it in top5[:5]:
        code = it["sc"][2:]
        prefix = it["sc"][:2]  # SH or SZ
        name = nm.get(code, ("?", None, None))[0]
        print(f"\n  {name}({code}) 的概念命中:")
        try:
            r3 = _session.post(
                "https://emappdata.eastmoney.com/stockrank/getHotStockRankList",
                json={**EM_HOT_BODY, "srcSecurityCode": prefix + code},
                headers={"User-Agent": UA}, timeout=10
            )
            concepts = r3.json().get("data") or []
            for c in concepts[:8]:
                hit = c.get("hitCount", "")
                cn = c.get("conceptName", "")
                print(f"    - {cn} (热度{hit})")
        except Exception as e:
            print(f"    概念查询失败: {e}")
except Exception as e:
    print(f"  概念命中查询失败: {e}")
