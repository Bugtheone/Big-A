#!/usr/bin/env python3
"""乳业概念板块 — 多源交叉验证脚本 v3 (修复版)
数据源:
  S1: 东财 datacenter RPTA_WEB_THEME_DETAIL — 概念板块榜单 [主源]
  S2: 东财 datacenter 概念板块成分股
  S3: 同花顺 Tushare ths_daily — 板块日行情 (close/pre_close计算涨幅)
  S4: 腾讯K线 — 成分股涨幅加权验证
  S5: 腾讯实时行情 — 核心个股涨跌幅
"""
import json, os, sys, time
from datetime import datetime

if __name__ == '__main__':
    PROJECT = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    import requests
    sess = requests.Session()
    sess.trust_env = False
    sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    TODAY = datetime.now().strftime("%Y-%m-%d")
    TS_DATE = "20260729"
    YDAY_TS = "20260728"

    results = {}

    # ============================================================
    # S1: 东财 datacenter — RPTA_WEB_THEME_DETAIL (直接HTTP)
    # ============================================================
    print("=" * 70)
    print(" S1: 东财 datacenter 概念板块榜单")
    print("=" * 70)

    s1_dairy = None
    s1_ok = False

    try:
        dc_url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPTA_WEB_THEME_DETAIL",
            "columns": "ALL",
            "sortColumns": "THEME_PCT_CHG",
            "sortTypes": "-1",
            "pageSize": "300",
            "pageNumber": "1",
            "source": "WEB", "client": "WEB",
            "filter": "(MARKET=ALL)",
        }
        r = sess.get(dc_url, params=params, timeout=15,
                     headers={"Referer": "https://data.eastmoney.com/"})
        j = r.json()
        data = (j.get("result") or {}).get("data") or []

        if data:
            s1_ok = True
            print(f"  [拉取成功] 共 {len(data)} 个概念板块")
            for row in data:
                nm = row.get("THEME_NAME", "")
                if "乳" in nm or "奶" in nm:
                    s1_dairy = {
                        "name": nm,
                        "code": row.get("THEME_INDEX_CODE"),
                        "pct": row.get("THEME_PCT_CHG"),
                        "lead_stock": row.get("LEAD_STOCK"),
                        "lead_pct": row.get("LEAD_STOCK_PCT_CHG"),
                        "up_count": row.get("UP_NUM"),
                        "down_count": row.get("DOWN_NUM"),
                    }
                    print(f"  [{nm}] pct={s1_dairy['pct']}% | 领涨={s1_dairy['lead_stock']}({s1_dairy['lead_pct']}%) | 涨{s1_dairy['up_count']}/跌{s1_dairy['down_count']}")
        else:
            print(f"  [结果空] rcMsg={j.get('message')}")
    except Exception as e:
        print(f"  [失败] {e}")

    results["s1"] = {"ok": s1_ok, "dairy": s1_dairy}

    # ============================================================
    # S2: 东财 datacenter 概念板块成分股
    # ============================================================
    print("\n" + "=" * 70)
    print(" S2: 东财 datacenter 乳业成分股")
    print("=" * 70)

    s2_ok = False
    s2_stocks = []

    if s1_dairy:
        dairy_code = s1_dairy.get("code", "")
        print(f"  板块: {s1_dairy['name']} (code={dairy_code})")
        try:
            dc_url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "reportName": "RPT_ORG_THEMEINDEXSHARES",
                "columns": "SECURITY_CODE,SECURITY_NAME_ABBR,HOLD_WEIGHT_PCT",
                "pageSize": "100", "pageNumber": "1",
                "source": "WEB", "client": "WEB",
                "filter": f'(THEME_INDEX_CODE="{dairy_code}")',
            }
            r = sess.get(dc_url, params=params, timeout=15,
                         headers={"Referer": "https://data.eastmoney.com/"})
            j = r.json()
            rows = (j.get("result") or {}).get("data") or []

            if rows:
                s2_ok = True
                for row in rows:
                    s2_stocks.append({
                        "code": row.get("SECURITY_CODE", ""),
                        "name": row.get("SECURITY_NAME_ABBR", ""),
                        "weight": row.get("HOLD_WEIGHT_PCT"),
                    })
                print(f"  [成分股] 共 {len(s2_stocks)} 只")
                for s in s2_stocks[:10]:
                    print(f"    {s['code']} {s['name']} 权重={s['weight']}%")
            else:
                print(f"  [RPT_ORG_THEMEINDEXSHARES 返回空] 尝试其他reportName...")
                # 备选: RPTA_BOARD_STOCK
                for rn in ["RPTA_BOARD_STOCK", "RPT_BOARD_STOCK_DETAILS"]:
                    try:
                        r2 = sess.get(dc_url, params={
                            **params,
                            "reportName": rn,
                            "filter": f'(BOARD_CODE="{dairy_code}")',
                            "columns": "SECURITY_CODE,SECURITY_NAME_ABBR",
                        }, timeout=10)
                        r2_rows = (r2.json().get("result") or {}).get("data") or []
                        if r2_rows:
                            s2_ok = True
                            for row in r2_rows:
                                s2_stocks.append({"code": row.get("SECURITY_CODE",""), "name": row.get("SECURITY_NAME_ABBR",""), "weight": None})
                            print(f"  [{rn}] 共 {len(s2_stocks)} 只")
                            break
                    except Exception:
                        continue
        except Exception as e:
            print(f"  [失败] {e}")

    results["s2"] = {"ok": s2_ok, "count": len(s2_stocks)}

    # ============================================================
    # S3: 同花顺 Tushare ths_daily
    # ============================================================
    print("\n" + "=" * 70)
    print(" S3: 同花顺 Tushare ths_daily (乳业板块)")
    print("=" * 70)

    s3_data = {}
    s3_ok = False

    try:
        from scripts.tushare_api import get_pro
        pro = get_pro()
        # 先从 ths_index 获取所有乳业相关板块代码
        ths_idx = pro.ths_index(type_="N")
        dairy_ts = []
        if ths_idx is not None and len(ths_idx) > 0:
            for _, row in ths_idx.iterrows():
                nm = str(row.get("name", ""))
                if "乳" in nm:
                    dairy_ts.append({"code": row["ts_code"], "name": nm})

        print(f"  [板块索引] 找到 {len(dairy_ts)} 个乳业板块: {[(d['code'], d['name']) for d in dairy_ts]}")

        for dt in dairy_ts[:2]:
            tc = dt["code"]
            daily = pro.ths_daily(ts_code=tc, start_date=YDAY_TS, end_date=TS_DATE)
            if daily is not None and len(daily) > 0:
                entries = []
                for _, row in daily.iterrows():
                    td = row.get("trade_date", "")
                    close = float(row.get("close", 0))
                    pre_close = float(row.get("pre_close", 0))
                    open_p = float(row.get("open", 0))

                    # 用 close/pre_close 计算真实涨幅（pct_change字段为空）
                    pct = round((close - pre_close) / pre_close * 100, 2) if pre_close > 0 else 0

                    entries.append({"date": td, "open": open_p, "close": close, "pre_close": pre_close, "pct": pct})
                    print(f"    {tc} {td}: open={open_p:.2f} close={close:.2f} pre_close={pre_close:.2f} calc_pct={pct:+.2f}%")

                s3_data[tc] = {"name": dt["name"], "entries": entries}
                if any(e["date"] == TS_DATE and e["close"] > 0 for e in entries):
                    s3_ok = True
    except Exception as e:
        print(f"  [失败] {e}")

    # 提取今日乳业涨幅
    s3_today_pct = None
    for tc, d in s3_data.items():
        for e in d.get("entries", []):
            if e["date"] == TS_DATE and "乳业" in d.get("name", ""):
                s3_today_pct = e["pct"]
                break

    results["s3"] = {"ok": s3_ok, "data": {k: {"name": v["name"], "entries": [{"date": e["date"], "pct": e["pct"]} for e in v["entries"]]} for k, v in s3_data.items()}}

    # ============================================================
    # S4: 腾讯K线 成分股加权验证
    # ============================================================
    print("\n" + "=" * 70)
    print(" S4: 腾讯K线成分股加权验证")
    print("=" * 70)

    s4_ok = False
    s4_weighted = None
    s4_verified = []

    if s2_stocks:
        has_weight = any(s.get("weight") is not None for s in s2_stocks)
        w_total = 0
        p_total = 0

        for st in s2_stocks[:20]:
            code = st["code"]
            name = st["name"]

            try:
                # 先判断交易所前缀
                market = "sz" if code.startswith(("0", "3", "2")) else "sh"
                kurl = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={market}{code},day,,,2"
                r = sess.get(kurl, timeout=10)
                kj = r.json()
                day_data = kj.get("data", {}).get(f"{market}{code}", {}).get("day", [])

                if day_data and len(day_data) >= 2:
                    t = day_data[-1]
                    y = day_data[-2]
                    close_t = float(t[2])
                    close_y = float(y[2])
                    pct_tx = round((close_t - close_y) / close_y * 100, 2)

                    w = float(st.get("weight", 0) or 0)
                    if not has_weight:
                        w = 1.0

                    p_total += pct_tx * w
                    w_total += w

                    s4_verified.append({"code": code, "name": name, "pct": pct_tx, "weight": w})
            except Exception:
                pass

        if w_total > 0:
            s4_weighted = round(p_total / w_total, 2)
            s4_ok = True

        print(f"  [验证] {len(s4_verified)}/{len(s2_stocks[:20])} 只成功")
        print(f"  [加权涨幅] {s4_weighted}%")

        print(f"\n  {'代码':<8} {'名称':<8} {'腾讯%':<8} {'权重':<6}")
        print("  " + "-" * 35)
        for v in sorted(s4_verified, key=lambda x: x.get("weight", 0) or 0, reverse=True)[:10]:
            print(f"  {v['code']:<8} {v['name']:<8} {v['pct']:<8.2f} {v['weight']}")
    else:
        # 降级: 用硬编码的核心乳业个股
        print(f"  [降级] S2未获取到成分股，使用核心乳业个股:")
        dairy_core = [
            ("sh600887", "伊利股份"),
            ("sz002946", "新乳业"),
            ("sh600882", "妙可蓝多"),
            ("sz002329", "皇氏集团"),
            ("sz300106", "西部牧业"),
            ("sh600419", "天润乳业"),
            ("sz002770", "科迪乳业"),
            ("sh600597", "光明乳业"),
        ]
        p_total = 0
        for code, name in dairy_core:
            try:
                kurl = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,2"
                r = sess.get(kurl, timeout=10)
                kj = r.json()
                key = code if code.startswith("sh") else code
                if code.startswith("sz"):
                    key = code.replace("sz", "sz")
                day_data = kj.get("data", {}).get(code, {}).get("day", [])

                if day_data and len(day_data) >= 2:
                    t = day_data[-1]
                    y = day_data[-2]
                    close_t = float(t[2])
                    close_y = float(y[2])
                    pct_tx = round((close_t - close_y) / close_y * 100, 2)
                    p_total += pct_tx
                    s4_verified.append({"code": code, "name": name, "pct": pct_tx})
            except Exception:
                pass

        if s4_verified:
            s4_weighted = round(p_total / len(s4_verified), 2)
            s4_ok = True

        print(f"  [验证] {len(s4_verified)}/{len(dairy_core)} 只")
        print(f"  [等权涨幅] {s4_weighted}%")
        for v in s4_verified:
            print(f"    {v['code']:<12} {v['name']:<8} {v['pct']:+.2f}%")

    results["s4"] = {"ok": s4_ok, "weighted_pct": s4_weighted, "verified": len(s4_verified)}

    # ============================================================
    # S5: 腾讯实时行情 — 核心个股
    # ============================================================
    print("\n" + "=" * 70)
    print(" S5: 腾讯实时行情 — 乳业核心个股")
    print("=" * 70)

    s5_ok = False
    s5_pcts = []

    try:
        codes = "sh600887,sz002946,sh600882,sz002329,sz300106,sh600419,sz002770,sh600597"
        r = sess.get(f"http://qt.gtimg.cn/q={codes}", timeout=10)
        r.encoding = "gbk"

        for line in r.text.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("~")
            if len(parts) < 5:
                continue
            code = parts[2]
            name = parts[1]
            price = float(parts[3]) if parts[3] else 0
            preclose = float(parts[4]) if parts[4] else 0
            pct = round((price - preclose) / preclose * 100, 2) if preclose else 0

            s5_pcts.append({"code": code, "name": name, "price": price, "preclose": preclose, "pct": pct})

        s5_ok = len(s5_pcts) > 0
        if s5_pcts:
            avg = round(sum(s["pct"] for s in s5_pcts) / len(s5_pcts), 2)
            print(f"  [拉取成功] {len(s5_pcts)} 只:")
            for s in s5_pcts:
                print(f"    {s['code']} {s['name']:<8} price={s['price']:.2f} preclose={s['preclose']:.2f} pct={s['pct']:+.2f}%")
            print(f"  [等权均价] {avg:+.2f}%")
    except Exception as e:
        print(f"  [失败] {e}")

    results["s5"] = {"ok": s5_ok, "pcts": [{"code": s["code"], "name": s["name"], "pct": s["pct"]} for s in s5_pcts]}

    # ============================================================
    # 综合判定
    # ============================================================
    print("\n" + "=" * 70)
    print(" 交叉验证汇总 — 乳业概念板块 (2026-07-29)")
    print("=" * 70)

    vals = {}

    if s1_dairy and s1_dairy.get("pct") is not None:
        vals["S1 东财datacenter"] = float(s1_dairy["pct"])

    if s3_today_pct is not None:
        vals["S3 同花顺 Tushare"] = float(s3_today_pct)

    # 也把乳品(884125)放进来对比
    for tc, d in s3_data.items():
        for e in d.get("entries", []):
            if e["date"] == TS_DATE and "乳品" in d.get("name", ""):
                vals["S3 同花顺(乳品)"] = e["pct"]
                break

    if s4_ok and s4_weighted is not None:
        vals["S4 腾讯K线加权"] = s4_weighted

    if s5_pcts:
        vals["S5 腾讯实时行情"] = round(sum(s["pct"] for s in s5_pcts) / len(s5_pcts), 2)

    if vals:
        print(f"\n  数据源: {len(vals)} 个可用")
        for k, v in vals.items():
            print(f"  {k:<22} {v:+.2f}%")

        pct_list = list(vals.values())
        if len(pct_list) >= 2:
            diff = max(pct_list) - min(pct_list)
            print(f"\n  最大差异: {diff:.2f}%")
            if diff < 0.5:
                print(f"  ★★★★★ 一致性极高 — 数据可信")
            elif diff < 1.0:
                print(f"  ★★★★☆ 一致性良好 — 不同源计算方式轻微差异")
            elif diff < 2.0:
                print(f"  ★★★☆☆ 存在偏差 — 概念板块vs成分股权重差异")
            else:
                print(f"  ★★☆☆☆ 差异大 — 需排查")

        median = sorted(pct_list)[len(pct_list) // 2]
        print(f"\n  最佳估计(中位数): {median:+.2f}%")

        # 特别说明：同花顺板块指数 vs 东财概念板块 计算方式不同
        print(f"\n  [说明] S3为同花顺板块指数(按权重计算)，S1/S4/S5为概念板块成分股统计。\n"
              f"  两者由于权重方式和样本股范围不同，涨幅可能存在系统性差异，\n"
              f"  这不是数据错误，而是统计口径差异。")
    else:
        print(f"  [FAIL] 所有数据源均不可用")

    # 输出JSON
    out_path = os.path.join(PROJECT, "data", f"dairy_audit_{TODAY}.json")
    s1_safe = dict(s1_dairy) if s1_dairy else None
    out = {
        "date": TODAY,
        "ts": datetime.now().isoformat(),
        "summary": {
            "sources": len(vals),
            "values": {k: v for k, v in vals.items()},
            "median": round(sorted(list(vals.values()))[len(list(vals.values()))//2], 2) if vals else None,
        },
        "s1_datacenter": s1_safe,
        "s3_ths_daily": {k: {"name": v["name"], "latest_pct": next((e["pct"] for e in v["entries"] if e["date"]==TS_DATE), None)} for k, v in s3_data.items()},
        "s4_tencent_kline": {"weighted_pct": s4_weighted, "stock_count": len(s4_verified)},
        "s5_tencent_quote": [{"code": s["code"], "name": s["name"], "pct": s["pct"]} for s in s5_pcts],
        "note": "S3为同花顺板块指数(按权重加权)，S1/S4/S5为概念板块成分股统计，两者统计口径不同导致涨幅数值存在系统性差异"
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n审计JSON: {out_path}")
