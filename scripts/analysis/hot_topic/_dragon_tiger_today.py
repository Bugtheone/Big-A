#!/usr/bin/env python3
"""2026-07-28 全市场龙虎榜 — 净买入排名TOP"""
import time, random, requests, json

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# 东财防封
EM_SESSION = requests.Session()
EM_SESSION.trust_env = False
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]

def em_get(url, params=None, headers=None, timeout=15):
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout)
    finally:
        _em_last_call[0] = time.time()

def eastmoney_datacenter(report_name, columns="ALL", filter_str="", page_size=50,
                          sort_columns="", sort_types="-1"):
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get(DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get("success") and d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []

def daily_dragon_tiger(trade_date, min_net_buy=None):
    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')",
        page_size=500,
        sort_columns="BILLBOARD_NET_AMT", sort_types="-1",
    )
    if not data:
        return {"date": trade_date, "total_records": 0, "stocks": [], "note": "无数据"}

    stocks = []
    for row in data:
        net_buy = (row.get("BILLBOARD_NET_AMT") or 0) / 10000
        if min_net_buy is not None and net_buy < min_net_buy:
            continue
        stocks.append({
            "code": row.get("SECURITY_CODE", ""),
            "name": row.get("SECURITY_NAME_ABBR", ""),
            "reason": row.get("EXPLANATION", ""),
            "close": row.get("CLOSE_PRICE") or 0,
            "change_pct": round(float(row.get("CHANGE_RATE") or 0), 2),
            "net_buy_wan": round(net_buy, 1),
            "buy_wan": round((row.get("BILLBOARD_BUY_AMT") or 0) / 10000, 1),
            "sell_wan": round((row.get("BILLBOARD_SELL_AMT") or 0) / 10000, 1),
            "turnover_pct": round(float(row.get("TURNOVERRATE") or 0), 2),
        })
    return {"date": trade_date, "total_records": len(stocks), "stocks": stocks}

if __name__ == "__main__":
    # 执行查询
    data = daily_dragon_tiger("2026-07-28")
    print(f"=== 全市场龙虎榜 · {data['date']} ===\n")
    if data["total_records"] == 0:
        print("今日暂无龙虎榜数据（可能非交易日，或盘后尚未更新）")
    else:
        print(f"上榜股票总数: {data['total_records']} 条记录")

        # 净买入 TOP20
        top_buy = sorted(data["stocks"], key=lambda x: x["net_buy_wan"], reverse=True)
        print(f"\n--- 净买入 TOP{min(20, len(top_buy))} ---")
        print(f"{'排名':<4} {'代码':<8} {'名称':<10} {'净买入(万)':<12} {'涨跌幅':<8} {'上榜原因'}")
        print("-" * 100)
        for i, s in enumerate(top_buy[:20], 1):
            print(f"{i:<4} {s['code']:<8} {s['name']:<10} {s['net_buy_wan']:>+.1f}万{'':>4} {s['change_pct']:>+6.2f}%{'':>3} {s['reason'][:45]}")

        # 净卖出 TOP10
        top_sell = sorted(data["stocks"], key=lambda x: x["net_buy_wan"])
        print(f"\n--- 净卖出 TOP10 ---")
        print(f"{'排名':<4} {'代码':<8} {'名称':<10} {'净买入(万)':<12} {'涨跌幅':<8} {'上榜原因'}")
        print("-" * 100)
        for i, s in enumerate(top_sell[:10], 1):
            print(f"{i:<4} {s['code']:<8} {s['name']:<10} {s['net_buy_wan']:>+.1f}万{'':>4} {s['change_pct']:>+6.2f}%{'':>3} {s['reason'][:45]}")

        # 统计
        net_in = sum(s["net_buy_wan"] for s in data["stocks"] if s["net_buy_wan"] > 0)
        net_out = sum(s["net_buy_wan"] for s in data["stocks"] if s["net_buy_wan"] < 0)
        print(f"\n--- 全市场汇总 ---")
        print(f"净买入票数: {sum(1 for s in data['stocks'] if s['net_buy_wan'] > 0)} 只  累计净买: {net_in:.0f}万")
        print(f"净卖出票数: {sum(1 for s in data['stocks'] if s['net_buy_wan'] < 0)} 只  累计净卖: {net_out:.0f}万")
        print(f"总净差额: {net_in + net_out:.0f}万")
