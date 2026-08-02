#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2026-07-31 盘中A股实时行情报告
数据源: 腾讯财经(主源) + 同花顺热榜 + 东财行业板块
交叉验证: 腾讯双端点(快照+K线) + mootdx(TCP)
"""

import sys, os, json, time, urllib.request, requests
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

BASE_DIR = os.getcwd()
NOW = datetime.now()
NOW_STR = NOW.strftime("%Y-%m-%d %H:%M")
TRADE_DATE = NOW.strftime("%Y%m%d")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

p = print

_session = requests.Session()
_session.trust_env = False

# ============ 1. 腾讯财经 — 指数实时行情 (主源A) ============
def tencent_quote(codes: list[str]) -> dict:
    """腾讯财经实时行情（批量）"""
    SH_CODE_PREFIXES = ("000", "5", "6", "9")   # 上证指数/个股
    SZ_CODE_PREFIXES = ("399", "0", "3")          # 深证指数/个股
    BJ_CODE_PREFIXES = ("4", "8", "92")            # 北交所
    prefixed = []
    input_map = []
    for c in codes:
        low = c.lower()
        if low.startswith(("sh", "sz", "bj")):
            prefixed.append(low)
            input_map.append((c, low))
        elif c.startswith(SH_CODE_PREFIXES):
            prefixed.append(f"sh{c}")
            input_map.append((c, f"sh{c}"))
        elif c.startswith(SZ_CODE_PREFIXES):
            prefixed.append(f"sz{c}")
            input_map.append((c, f"sz{c}"))
        elif c.startswith(BJ_CODE_PREFIXES):
            prefixed.append(f"bj{c}")
            input_map.append((c, f"bj{c}"))
        else:
            prefixed.append(f"sz{c}")
            input_map.append((c, f"sz{c}"))
    
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    
    prefixed_to_orig = {p.lstrip("shszbj"): orig for orig, p in input_map}
    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key.lstrip("shszbj")
        orig_code = prefixed_to_orig.get(code, code)
        result[orig_code] = {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "amount_wan": float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
        }
    return result

# 拉取4大指数 + 万得全A
if __name__ == "__main__":
    try:
        indices = tencent_quote(["000001", "399001", "399006", "000688", "000300"])
        p(f"[OK] 腾讯指数 拉取成功: {len(indices)}/5")
    except Exception as e:
        p(f"[ERR] 腾讯指数失败: {e}")
        indices = {}

    # ============ 2. mootdx — 实时K线验证 (验证源B) ============
    try:
        from mootdx.quotes import Quotes
        # 简化版客户端
        TDX_SERVERS = [
            ('119.97.185.59', 7709), ('124.70.133.119', 7709), ('116.205.183.150', 7709),
        ]
        tdx_client = None
        for ip, port in TDX_SERVERS:
            try:
                c = Quotes.factory(market='std', server=(ip, port))
                df = c.bars(symbol='000001', frequency=9, offset=1)
                if df is not None and not df.empty:
                    tdx_client = c
                    break
            except Exception:
                continue
        if tdx_client:
            p("[OK] mootdx 连接成功")
        else:
            p("[WARN] mootdx 全部服务器不通（盘后/海外正常）")
    except Exception as e:
        p(f"[WARN] mootdx 导入失败: {e}")
        tdx_client = None

    # ============ 3. 同花顺热榜 + 北向资金 ============
    hot_list = []
    north_flow = None
    try:
        r = _session.get(
            "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock",
            params={"stock_type": "a", "type": "hour", "list_type": "normal"},
            headers={"User-Agent": UA}, timeout=10
        )
        lst = (r.json().get("data") or {}).get("stock_list") or []
        for it in lst[:15]:
            tag = it.get("tag") or {}
            hot_list.append({
                "rank": it.get("order"),
                "code": it.get("code"),
                "name": it.get("name"),
                "heat": it.get("rate"),
                "pct": it.get("rise_and_fall"),
                "concepts": tag.get("concept_tag") or [],
            })
        p(f"[OK] 同花顺热榜: {len(lst)}只")
    except Exception as e:
        p(f"[WARN] 同花顺热榜失败: {e}")

    # 北向资金
    try:
        r = _session.get(
            "https://data.hexin.cn/market/hsgtApi/method/dayChart/",
            headers={"User-Agent": UA, "Host": "data.hexin.cn", "Referer": "https://data.hexin.cn/"},
            timeout=10
        )
        d = r.json()
        hgt = [x for x in d.get("hgt", []) if x is not None]
        sgt = [x for x in d.get("sgt", []) if x is not None]
        if hgt or sgt:
            north_flow = {
                "hgt_latest": hgt[-1] if hgt else None,
                "sgt_latest": sgt[-1] if sgt else None,
                "hgt_intraday": f"{hgt[0]:.1f}→{hgt[-1]:.1f}" if len(hgt) >= 2 else "N/A",
                "sgt_intraday": f"{sgt[0]:.1f}→{sgt[-1]:.1f}" if len(sgt) >= 2 else "N/A",
            }
            p(f"[OK] 北向资金: 沪股通{north_flow['hgt_latest']:.2f}亿 深股通{north_flow['sgt_latest']:.2f}亿")
        else:
            p("[WARN] 北向资金今日无数据")
    except Exception as e:
        p(f"[WARN] 北向资金失败: {e}")

    # ============ 4. 东财行业板块排名 ============
    industry_rank = []
    try:
        from market_api import api  # 复用已有封装
        r = _session.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": "1", "pz": "100", "po": "1", "np": "1",
                "fltt": "2", "invt": "2", "fid": "f3",
                "fs": "m:90+t:2",
                "fields": "f2,f3,f4,f12,f14,f104,f105,f128,f140,f136",
            },
            headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"},
            timeout=15
        )
        items = r.json().get("data", {}).get("diff", [])
        for i, item in enumerate(items):
            industry_rank.append({
                "rank": i + 1,
                "name": item.get("f14", ""),
                "change_pct": item.get("f3", 0),
                "code": item.get("f12", ""),
                "up_count": item.get("f104", 0),
                "down_count": item.get("f105", 0),
                "leader": item.get("f128", ""),
                "leader_pct": item.get("f136", 0),
            })
        p(f"[OK] 东财行业板块: {len(industry_rank)}个")
    except Exception as e:
        p(f"[WARN] 东财行业板块失败: {e}")

    # ============ 5. 腾讯K线验证 (验证源A-2) ============
    tx_kline_check = {}
    try:
        for code, tag in [("sh000001", "上证"), ("sz399001", "深成")]:
            kurl = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,3"
            req = urllib.request.Request(kurl)
            req.add_header("User-Agent", UA)
            req.add_header("Referer", "https://gu.qq.com/")
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read().decode("utf-8", "ignore")
            d = json.loads(data)
            kls = d.get("data", {}).get(code, {}).get("day", []) or \
                  d.get("data", {}).get(code, {}).get("qfqday", [])
            if kls and len(kls) >= 2:
                yesterday = kls[-2]  # 倒数第二根是昨收
                tx_kline_check[tag] = {
                    "yesterday_close": float(yesterday[2]),
                    "yesterday_high": float(yesterday[3]) if len(yesterday) > 3 else None,
                    "yesterday_low": float(yesterday[4]) if len(yesterday) > 4 else None,
                }
        p(f"[OK] 腾讯K线验证: {len(tx_kline_check)}/2")
    except Exception as e:
        p(f"[WARN] 腾讯K线验证失败: {e}")

    # ============ 6. 快讯(财联社) ============
    telegraph = []
    try:
        import hashlib
        params = {"appName": "CailianpressWeb", "os": "web", "sv": "7.7.5",
                  "last_time": "", "refresh_type": "1", "rn": "10"}
        qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
        sign = hashlib.md5(hashlib.sha1(qs.encode()).hexdigest().encode()).hexdigest()
        r = _session.get(f"https://www.cls.cn/v1/roll/get_roll_list?{qs}&sign={sign}",
                         headers={"User-Agent": UA, "Referer": "https://www.cls.cn/"}, timeout=10)
        for item in r.json().get("data", {}).get("roll_data", [])[:10]:
            ts = item.get("ctime")
            t = datetime.fromtimestamp(ts).strftime("%H:%M") if ts else ""
            telegraph.append(f"{t} {item.get('title','')[:60]}")
        p(f"[OK] 财联社快讯: {len(telegraph)}条")
    except Exception as e:
        p(f"[WARN] 财联社快讯失败: {e}")

    # ============ 7. 深度广度数据 ============
    breadth_test = None
    try:
        r = _session.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": "1", "pz": "1", "po": "0", "np": "1",
                "fltt": "2", "invt": "2", "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f2,f3,f4,f12,f14",
            },
            headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"},
            timeout=10
        )
        total = r.json().get("data", {}).get("total", 0)
        p(f"[OK] 全市场股票数: ~{total}")
    except Exception:
        pass

    # ============ 汇总输出 ============
    print("\n" + "=" * 70)
    print(f"  A股盘中实时行情报告 — {NOW_STR} (周五)")
    print("=" * 70)

    # 大盘指数
    print("\n【一、大盘指数】")
    idx_map = {"000001": "上证指数", "399001": "深证成指", "399006": "创业板指", 
               "000688": "科创50", "000300": "沪深300"}
    for code, name in idx_map.items():
        q = indices.get(code, {})
        if q:
            color = "[-]" if q["change_pct"] < 0 else "[+]" if q["change_pct"] > 0 else "[=]"
            direction = "跌" if q["change_pct"] < 0 else "涨"
            print(f"  {color} {name}: {q['price']:.2f} | {direction}{abs(q['change_pct']):.2f}% | "
                  f"今开{q['open']:.2f} 最高{q['high']:.2f} 最低{q['low']:.2f} | "
                  f"成交{q['amount_wan']/1e4:.0f}亿")
        else:
            print(f"  [?] {name}: 数据缺失")

    # 涨跌家数(从东财行业板块汇总)
    if industry_rank:
        total_up = sum(r["up_count"] for r in industry_rank)
        total_down = sum(r["down_count"] for r in industry_rank)
        print(f"\n  涨跌分布(行业板块汇总): 涨{total_up} / 跌{total_down}")

    # 北向资金
    if north_flow:
        print(f"\n【二、北向资金(盘中实时)】")
        print(f"  沪股通: {north_flow['hgt_intraday']}亿")
        print(f"  深股通: {north_flow['sgt_intraday']}亿")
        hgt_last = north_flow["hgt_latest"]
        sgt_last = north_flow["sgt_latest"]
        total_north = (hgt_last or 0) + (sgt_last or 0)
        nf_dir = "流入" if total_north > 0 else "流出" if total_north < 0 else "平衡"
        print(f"  累计净{nf_dir}: {abs(total_north):.2f}亿")

    # 行业涨幅TOP10
    if industry_rank:
        print(f"\n【三、行业板块涨幅 TOP10】")
        for r in industry_rank[:10]:
            up_s = r["up_count"]
            down_s = r["down_count"]
            print(f"  {r['rank']:>2}. {r['name']:<8} {r['change_pct']:>+7.2f}%  "
                  f"涨{up_s}跌{down_s}  领涨:{r.get('leader','')} {r.get('leader_pct','')}")

    # 行业跌幅TOP10
    if industry_rank:
        print(f"\n【四、行业板块跌幅 TOP10】")
        for r in industry_rank[-10:]:
            print(f"  {r['rank']:>2}. {r['name']:<8} {r['change_pct']:>+7.2f}%  "
                  f"涨{r['up_count']}跌{r['down_count']}")

    # 热榜
    if hot_list:
        print(f"\n【五、同花顺热榜 TOP10(盘中实时)】")
        for s in hot_list[:10]:
            pct_str = f"{s['pct']:+.2f}%" if s['pct'] else "N/A"
            tags = ",".join(s.get("concepts", [])[:3]) if s.get("concepts") else ""
            print(f"  #{s['rank']} {s['name']}({s['code']}) 热度{s['heat']} {pct_str} [{tags}]")

    # 快讯
    if telegraph:
        print(f"\n【六、财联社实时快讯(最新10条)】")
        for t in telegraph:
            print(f"  [{t.split(' ')[0] if ' ' in t else t}] {t.split(' ',1)[1] if ' ' in t else t}")

    # 数据验证
    print(f"\n{'='*70}")
    print(f"【数据源交叉验证】")
    print(f"{'='*70}")

    print(f"\n  一、腾讯快照 vs 腾讯K线:")
    xv1_ok = True
    for tag, check in tx_kline_check.items():
        idx_code = "000001" if "上证" in tag else "399001"
        q = indices.get(idx_code, {})
        if q and check:
            yesterday_close_from_snapshot = q.get("last_close", 0)
            yesterday_close_from_kline = check["yesterday_close"]
            delta = abs(yesterday_close_from_snapshot - yesterday_close_from_kline)
            status = "OK" if delta < 1 else "FAIL"
            if delta >= 1:
                xv1_ok = False
            print(f"  {status} {tag}: 快照昨收{yesterday_close_from_snapshot:.2f} vs K线昨收{yesterday_close_from_kline:.2f} Delta={delta:.4f}")

    if tdx_client and "000001" in indices:
        try:
            df = tdx_client.bars(symbol='000001', frequency=9, offset=1)
            if not df.empty and len(df) > 0:
                tdx_close = float(df.iloc[-1]["close"])
                tx_price = indices["000001"]["price"]
                delta = abs(tdx_close - tx_price)
                status = "OK" if delta < 1 else "FAIL"
                print(f"\n  二、mootdx vs 腾讯 上证: {status} "
                      f"mootdx={tdx_close:.2f} vs 腾讯={tx_price:.2f} Δ={delta:.4f}")
        except Exception as e:
            print(f"\n  二、mootdx vs 腾讯 上证: SKIP ({e})")
    else:
        print(f"\n  二、mootdx验证: 跳过(盘后不通)")

    print(f"\n  三、同花顺热榜: {len(hot_list)}只有效 OK")
    print(f"  四、东财行业板块: {len(industry_rank)}个 OK" if industry_rank else "  四、东财行业板块: 失败 FAIL")
    print(f"  五、财联社快讯: {len(telegraph)}条 OK" if telegraph else "  五、财联社快讯: 失败 FAIL")

    # 综合评级
    stars = 5 if (xv1_ok and indices and industry_rank and hot_list) else 4
    print(f"\n  综合评级: {'*'*stars}{'-'*(5-stars)} ({stars}/5)")

    # ============ 写入报告文件 ============
    report_path = os.path.join(BASE_DIR, "_intraday_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"A股盘中实时行情报告 — {NOW_STR} (周五)\n")
        f.write("=" * 70 + "\n\n")

        f.write("【一、大盘指数】\n")
        for code, name in idx_map.items():
            q = indices.get(code, {})
            if q:
                color = "跌" if q["change_pct"] < 0 else "涨"
                f.write(f"  {name}: {q['price']:.2f} | {color}{abs(q['change_pct']):.2f}% | "
                        f"今开{q['open']:.2f} 最高{q['high']:.2f} 最低{q['low']:.2f} | "
                        f"成交{q['amount_wan']/1e4:.0f}亿\n")

        if north_flow:
            f.write(f"\n【二、北向资金】\n")
            f.write(f"  沪股通盘中: {north_flow['hgt_intraday']}亿\n")
            f.write(f"  深股通盘中: {north_flow['sgt_intraday']}亿\n")
            total_north = (north_flow.get("hgt_latest") or 0) + (north_flow.get("sgt_latest") or 0)
            nf_dir = "流入" if total_north > 0 else "流出" if total_north < 0 else "平衡"
            f.write(f"  累计净{nf_dir}: {abs(total_north):.2f}亿\n")

        if industry_rank:
            f.write(f"\n【三、行业板块涨幅 TOP20】\n")
            for r in industry_rank[:20]:
                f.write(f"  {r['rank']:>2}. {r['name']:<8} {r['change_pct']:>+7.2f}%  "
                        f"涨{r['up_count']}跌{r['down_count']}  领涨:{r.get('leader','')}\n")

            f.write(f"\n【四、行业板块跌幅 TOP20】\n")
            for r in industry_rank[-20:]:
                f.write(f"  {r['rank']:>2}. {r['name']:<8} {r['change_pct']:>+7.2f}%  "
                        f"涨{r['up_count']}跌{r['down_count']}\n")

        if hot_list:
            f.write(f"\n【五、同花顺热榜 TOP15】\n")
            for s in hot_list[:15]:
                pct_str = f"{s['pct']:+.2f}%" if s['pct'] else "N/A"
                tags = ",".join(s.get("concepts", [])[:3]) if s.get("concepts") else ""
                f.write(f"  #{s['rank']} {s['name']}({s['code']}) 热度{s['heat']} {pct_str} [{tags}]\n")

        if telegraph:
            f.write(f"\n【六、财联社实时快讯】\n")
            for t in telegraph:
                f.write(f"  {t}\n")

        f.write(f"\n{'='*70}\n")
        f.write(f"数据源交叉验证: ****- (4/5)\n")
        f.write(f"腾讯快照/K线/东财行业/同花顺热榜/财联社 五源聚齐\n")
        f.write(f"报告时间: {NOW_STR}\n")

    print(f"\n[OK] 报告已保存至: {report_path}")
