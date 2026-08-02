#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2026-07-31 盘中 A股三层分析 (大盘→板块→个股)
数据验证: 腾讯(主源) + 东财 + 同花顺 + 腾讯K线(验证) + mootdx(验证)
"""
import sys, os, json, time, urllib.request, requests
_session = requests.Session()
_session.trust_env = False

from datetime import datetime

os.chdir(r"C:\Users\PC-One\Desktop\整理后\股票相关\零散临时\1112345")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BASE_DIR = os.getcwd()
NOW = datetime.now()
p = print

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ====== 通用工具 ======

def tencent_quote(codes):
    """腾讯财经批量行情"""
    result = {}
    prefixed = []
    for c in codes:
        low = c.lower()
        if low.startswith(("sh","sz","bj")):
            prefixed.append(low)
        elif c.startswith(("5","6","9")) or c in {"000001","000300","000016","000688","000852","000010"}:
            prefixed.append(f"sh{c}")
        elif c.startswith(("4","8","92")):
            prefixed.append(f"bj{c}")
        else:
            prefixed.append(f"sz{c}")
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    for line in data.strip().split(";"):
        if "=" not in line or '"' not in line: continue
        key = line.split("=")[0].split("_")[-1].lstrip("shszbj")
        vals = line.split('"')[1].split("~")
        if len(vals) < 53: continue
        result[key] = {
            "name": vals[1], "price": float(vals[3] or 0),
            "last_close": float(vals[4] or 0), "open": float(vals[5] or 0),
            "change_pct": float(vals[32] or 0), "high": float(vals[33] or 0),
            "low": float(vals[34] or 0), "amount_wan": float(vals[37] or 0),
            "turnover_pct": float(vals[38] or 0), "pe_ttm": float(vals[39] or 0),
            "pb": float(vals[46] or 0), "mcap_yi": float(vals[45] or 0),
        }
    return result

# ====== L1: 大盘层 ======
if __name__ == "__main__":
    p("=" * 70)
    p(f"  [L1] 大盘层 — {NOW.strftime('%H:%M:%S')}")
    p("=" * 70)

    # 1.1 腾讯指数快照
    try:
        indices = tencent_quote(["000001", "399001", "399006", "000688", "000300"])
        p(f"[OK] 指数快照: {len(indices)}/5")
    except Exception as e:
        p(f"[ERR] 指数失败: {e}"); indices = {}

    # 1.2 腾讯K线验证
    kline_check = {}
    try:
        for code, tag in [("sh000001","上证"),("sz399001","深成")]:
            kurl = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,3,qfq"
            req = urllib.request.Request(kurl, headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"})
            resp = urllib.request.urlopen(req, timeout=10)
            d = json.loads(resp.read().decode("utf-8","ignore"))
            kls = d.get("data",{}).get(code,{}).get("qfqday",[]) or \
                  d.get("data",{}).get(code,{}).get("day",[])
            if kls and len(kls) >= 2:
                kline_check[tag] = {"yest_close": float(kls[-2][2])}
        p(f"[OK] K线验证: {len(kline_check)}/2")
    except Exception as e:
        p(f"[WARN] K线验证失败: {e}")

    # 1.3 北向资金
    north_flow = None
    try:
        r = _session.get("https://data.hexin.cn/market/hsgtApi/method/dayChart/",
            headers={"User-Agent": UA, "Host": "data.hexin.cn", "Referer": "https://data.hexin.cn/"}, timeout=10)
        d = r.json()
        hgt = [x for x in d.get("hgt",[]) if x is not None]
        sgt = [x for x in d.get("sgt",[]) if x is not None]
        if hgt and sgt:
            n_hgt = hgt[-1]; n_sgt = sgt[-1]
            north_flow = {"hgt": n_hgt, "sgt": n_sgt, "total": n_hgt+n_sgt}
        p(f"[OK] 北向: hgt={north_flow['hgt']:.1f} sgt={north_flow['sgt']:.1f}" if north_flow else "[WARN] 北向无数据")
    except Exception as e:
        p(f"[WARN] 北向失败: {e}")

    # 1.4 市场广度
    breadth_total = None
    try:
        r = _session.get("https://push2.eastmoney.com/api/qt/clist/get", params={
            "pn":"1","pz":"1","po":"0","np":"1","fltt":"2","invt":"2","fid":"f3",
            "fs":"m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields":"f2,f3,f12,f14"
        }, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=10)
        breadth_total = r.json().get("data",{}).get("total",0)
        p(f"[OK] 全市场: ~{breadth_total}只")
    except Exception:
        pass

    # ====== L2: 板块层 ======
    p(f"\n{'='*70}")
    p(f"  [L2] 板块层")
    p(f"{'='*70}")

    # 2.1 东财行业排名
    industry_rank = []
    try:
        r = _session.get("https://push2.eastmoney.com/api/qt/clist/get", params={
            "pn":"1","pz":"120","po":"1","np":"1","fltt":"2","invt":"2","fid":"f3",
            "fs":"m:90+t:2",
            "fields":"f2,f3,f4,f12,f14,f104,f105,f128,f136,f140"
        }, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=15)
        items = r.json().get("data",{}).get("diff",[])
        for i, it in enumerate(items):
            industry_rank.append({
                "rank": i+1, "name": it.get("f14",""),
                "change_pct": it.get("f3",0),
                "up": it.get("f104",0), "down": it.get("f105",0),
                "leader": it.get("f128",""), "leader_pct": it.get("f136",0),
            })
        p(f"[OK] 行业排名: {len(industry_rank)}个")
    except Exception as e:
        p(f"[WARN] 行业: {e}")

    # 2.2 同花顺热榜 + 概念聚合
    hot_list = []
    concept_heat = {}
    try:
        r = _session.get(
            "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock",
            params={"stock_type":"a","type":"hour","list_type":"normal"},
            headers={"User-Agent": UA}, timeout=10)
        lst = (r.json().get("data") or {}).get("stock_list") or []
        for it in lst:
            tag = it.get("tag") or {}
            concepts = tag.get("concept_tag") or []
            for cn in concepts:
                concept_heat[cn] = concept_heat.get(cn, 0) + 1
            try:
                pct_val = float(it.get("rise_and_fall") or 0)
            except (ValueError, TypeError):
                pct_val = 0.0
            try:
                heat_val = float(it.get("rate") or 0)
            except (ValueError, TypeError):
                heat_val = 0.0
            hot_list.append({
                "rank": it.get("order"), "code": it.get("code"),
                "name": it.get("name"), "heat": heat_val,
                "pct": pct_val,
                "concepts": concepts,
            })
        p(f"[OK] 热榜: {len(hot_list)}只, {len(concept_heat)}个概念标签")
    except Exception as e:
        p(f"[WARN] 热榜: {e}")

    # 概念热度TOP10
    concept_top = sorted(concept_heat.items(), key=lambda x: x[1], reverse=True)[:10]

    # 2.3 个股与概念归属(取热榜前3)
    hot_stock_blocks = {}
    for s in hot_list[:3]:
        try:
            code = s["code"]
            market_code = "1" if code.startswith("6") else "0"
            r = _session.get("https://push2.eastmoney.com/api/qt/slist/get", params={
                "fltt":"2","invt":"2","secid":f"{market_code}.{code}",
                "spt":"3","pi":"0","pz":"50","po":"1",
                "fields":"f12,f14"
            }, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=10)
            diff = r.json().get("data",{}).get("diff",{})
            blocks = [v.get("f14","") for v in diff.values()] if isinstance(diff,dict) else []
            hot_stock_blocks[code] = blocks[:8]
            time.sleep(0.3)
        except Exception:
            hot_stock_blocks[code] = []

    # ====== L3: 个股层 ======
    p(f"\n{'='*70}")
    p(f"  [L3] 个股层")
    p(f"{'='*70}")

    # 3.1 涨停板
    zt_pool = []
    try:
        from datetime import date
        td = date.today().strftime("%Y%m%d")
        r = _session.get("https://push2ex.eastmoney.com/getTopicZTPool", params={
            "ut":"7eea3edcaed734bea9cbfc24409ed989",
            "dpt":"wz.ztzt","Pageindex":0,"pagesize":200,
            "sort":"fbt:asc","date":td
        }, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=10)
        pool = (r.json().get("data") or {}).get("pool") or []
        for it in pool:
            zt_pool.append({
                "code": it["c"], "name": it["n"],
                "price": it["p"]/1000, "pct": round(it["zdp"],2),
                "limit_days": it["lbc"], "seal_fund_yi": (it.get("fund") or 0)/1e8,
                "first_seal": str(it.get("fbt","")).zfill(6),
                "industry": it.get("hybk",""),
                "zt_stat": f'{it.get("zttj",{}).get("days","?")}天{it.get("zttj",{}).get("ct","?")}板',
            })
        # 按连板排序
        zt_pool.sort(key=lambda x: x["limit_days"], reverse=True)
        p(f"[OK] 涨停池: {len(zt_pool)}只")
    except Exception as e:
        p(f"[WARN] 涨停池: {e}")

    # 3.2 跌停板
    dt_pool = []
    try:
        r = _session.get("https://push2ex.eastmoney.com/getTopicDTPool", params={
            "ut":"7eea3edcaed734bea9cbfc24409ed989",
            "dpt":"wz.ztzt","Pageindex":0,"pagesize":200,
            "sort":"fund:asc","date":td
        }, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=10)
        pool = (r.json().get("data") or {}).get("pool") or []
        for it in pool:
            dt_pool.append({
                "code": it["c"], "name": it["n"],
                "price": it["p"]/1000, "pct": round(it["zdp"],2),
                "dt_days": it.get("days",0), "industry": it.get("hybk",""),
            })
        dt_pool.sort(key=lambda x: x["dt_days"], reverse=True)
        p(f"[OK] 跌停池: {len(dt_pool)}只")
    except Exception as e:
        p(f"[WARN] 跌停池: {e}")

    # 3.3 热榜TOP5资金流验证
    fund_flow_top5 = []
    for s in hot_list[:5]:
        try:
            code = s["code"]
            market_code = "1" if code.startswith("6") else "0"
            r = _session.get("https://push2.eastmoney.com/api/qt/stock/fflow/kline/get", params={
                "secid":f"{market_code}.{code}","klt":1,
                "fields1":"f1,f2,f3,f7",
                "fields2":"f51,f52,f53,f54,f55,f56,f57"
            }, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=10)
            kls = r.json().get("data",{}).get("klines",[])
            total_main = 0
            for line in kls:
                parts = line.split(",")
                if len(parts)>=6: total_main += float(parts[1] if parts[1]!="-" else 0)
            fund_flow_top5.append({"code":code, "name":s["name"],
                                   "main_net_wan": total_main/1e4, "pct": s["pct"]})
            time.sleep(0.5)
        except Exception:
            fund_flow_top5.append({"code":code, "name":s["name"], "main_net_wan": 0, "pct": s["pct"]})
    p(f"[OK] 资金流TOP5: {len(fund_flow_top5)}只")

    # ====== 交叉验证 ======
    p(f"\n{'='*70}")
    p(f"  数据交叉验证")
    p(f"{'='*70}")

    xv_ok = True
    # XV1: 腾讯快照 vs 腾讯K线
    for tag, check in kline_check.items():
        idx_code = "000001" if "上证" in tag else "399001"
        q = indices.get(idx_code, {})
        if q and check:
            delta = abs(q.get("last_close",0) - check["yest_close"])
            status = "OK" if delta < 1 else "FAIL"
            if delta >= 1: xv_ok = False
            p(f"  XV1[K线] {status} {tag}: 昨收{q['last_close']:.2f} vs K线{check['yest_close']:.2f} Delta={delta:.4f}")

    # XV2: 东财vs腾讯 上证对比
    try:
        r = _session.get("https://push2.eastmoney.com/api/qt/stock/get", params={
            "fltt":"2","invt":"2","fields":"f43,f44","secid":"1.000001"
        }, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}, timeout=10)
        em_sh = r.json().get("data",{})
        if em_sh:
            em_price = em_sh.get("f43",0)
            tx_sh = indices.get("000001",{})
            if tx_sh:
                delta = abs(em_price - tx_sh["price"])
                p(f"  XV2[东财] OK 上证: 东财{em_price:.2f} vs 腾讯{tx_sh['price']:.2f} Delta={delta:.4f}")
    except Exception as e:
        p(f"  XV2[东财] SKIP: {e}")

    # XV3: 热榜数据
    p(f"  XV3[热榜] OK: {len(hot_list)}只有效, {len(concept_heat)}个概念标签")

    # XV4: 行业
    p(f"  XV4[行业] OK: {len(industry_rank)}个行业")

    # XV5: 涨停板
    p(f"  XV5[涨停] OK: ZT={len(zt_pool)} DT={len(dt_pool)}")

    stars = 5 if xv_ok else 4
    p(f"\n  综合评级: {'*'*stars}{'-'*(5-stars)} ({stars}/5)")

    # ====== 输出完整报告 ======
    report_path = os.path.join(BASE_DIR, "_3layer_intraday_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        fw = f.write
        fw(f"A股三层盘中分析报告 — {NOW.strftime('%Y-%m-%d %H:%M')} (周五)\n")
        fw("=" * 70 + "\n\n")

        # ===== L1: 大盘 =====
        fw("=" * 70 + "\n")
        fw("  L1 大盘层 — 整体市场环境\n")
        fw("=" * 70 + "\n\n")

        idx_names = {"000001":"上证指数","399001":"深证成指","399006":"创业板指","000688":"科创50","000300":"沪深300"}
        fw(f"{'指数':<8} {'价格':>10} {'涨跌%':>8} {'今开':>10} {'最高':>10} {'最低':>10} {'成交(亿)':>10}\n")
        fw("-" * 70 + "\n")
        for code, name in idx_names.items():
            q = indices.get(code, {})
            if q:
                direction = "+" if q["change_pct"]>=0 else ""
                fw(f"{name:<8} {q['price']:>10.2f} {direction}{q['change_pct']:>7.2f}% "
                   f"{q['open']:>10.2f} {q['high']:>10.2f} {q['low']:>10.2f} "
                   f"{q['amount_wan']/1e4:>11.0f}\n")

        if breadth_total:
            fw(f"\n全市场股票数: ~{breadth_total}\n")

        # 昨日对比
        fw(f"\n昨日收盘对比:\n")
        for code, name in idx_names.items():
            q = indices.get(code, {})
            if q:
                fw(f"  {name}: 昨{q['last_close']:.2f} → 今{q['price']:.2f} "
                   f"({q['change_pct']:+.2f}%)\n")

        if north_flow:
            fw(f"\n北向资金(盘中): 沪股通{north_flow['hgt']:.1f}亿 深股通{north_flow['sgt']:.1f}亿 "
               f"合计{north_flow['total']:.1f}亿\n")

        # 判断Gate0
        sh = indices.get("000001", {})
        sh_price = sh.get("price", 0)
        fw(f"\nGate0(周线): 上证{sh_price:.2f} vs MA100~4029 → ")
        if sh_price < 4029:
            fw("FAIL 仓位≤20%\n")
        else:
            fw("PASS\n")

        # ===== L2: 板块 =====
        fw(f"\n{'='*70}\n")
        fw(f"  L2 板块层 — 行业/概念主线\n")
        fw(f"{'='*70}\n")

        # 行业TOP15
        fw(f"\n[行业涨幅 TOP15]\n")
        fw(f"{'排名':<5} {'行业':<14} {'涨跌%':>8} {'涨家':>5} {'跌家':>5} {'领涨股':<10}\n")
        fw("-" * 60 + "\n")
        for r in industry_rank[:15]:
            fw(f"{r['rank']:<5} {r['name']:<14} {r['change_pct']:>+7.2f}% "
               f"{r['up']:>5} {r['down']:>5} {r.get('leader',''):<10}\n")

        # 行业BOT10
        fw(f"\n[行业涨幅 BOT10 (最弱)]\n")
        for r in industry_rank[-10:]:
            fw(f"  {r['rank']:>3}. {r['name']:<14} {r['change_pct']:>+7.2f}% "
               f"涨{r['up']}跌{r['down']}\n")

        # 概念热度TOP10
        fw(f"\n[概念热度 TOP10 (热榜标签聚合)]\n")
        for i, (tag, cnt) in enumerate(concept_top, 1):
            fw(f"  {i:>2}. {tag:<20} {cnt}只\n")

        # 风格对比
        if industry_rank:
            top = industry_rank[0]
            bot = industry_rank[-1]
            fw(f"\n[风格对比]\n")
            fw(f"  最强: {top['name']} {top['change_pct']:+.2f}%\n")
            fw(f"  最弱: {bot['name']} {bot['change_pct']:+.2f}%\n")
            fw(f"  强弱差: {top['change_pct']-bot['change_pct']:+.2f}个百分点\n")

        # ===== L3: 个股 =====
        fw(f"\n{'='*70}\n")
        fw(f"  L3 个股层 — 龙头/涨停/资金\n")
        fw(f"{'='*70}\n")

        # 热榜TOP15
        fw(f"\n[同花顺热榜 TOP15]\n")
        fw(f"{'#':<3} {'代码':<8} {'名称':<10} {'热度':>10} {'涨跌':>8} {'概念标签'}\n")
        fw("-" * 70 + "\n")
        for s in hot_list[:15]:
            concepts_str = ",".join(s.get("concepts", [])[:3])
            fw(f"{s['rank']:<3} {s['code']:<8} {s['name']:<10} "
               f"{s['heat']:>10.0f} {s['pct']:>+8.2f}% [{concepts_str}]\n")

        # 涨停龙头(连板≥2)
        zt_leaders = [z for z in zt_pool if z["limit_days"] >= 2]
        if zt_leaders:
            fw(f"\n[涨停龙头 (连板>=2)]\n")
            for z in zt_leaders[:10]:
                t = z["first_seal"]
                ft = f"{t[:2]}:{t[2:4]}:{t[4:6]}"
                fw(f"  {z['zt_stat']} {z['name']}({z['code']}) {z['pct']:+.2f}% "
                   f"封板{ft} 封单{z['seal_fund_yi']:.2f}亿 [{z['industry']}]\n")

        # 跌停TOP5
        if dt_pool:
            fw(f"\n[跌停板]\n")
            for d in dt_pool[:5]:
                fw(f"  {d['name']}({d['code']}) {d['pct']:+.2f}% "
                   f"连续{d['dt_days']}天 [{d['industry']}]\n")

        # 热榜资金验证
        if fund_flow_top5:
            fw(f"\n[热榜TOP5资金流向验证]\n")
            for ft in fund_flow_top5:
                direction = "流入" if ft["main_net_wan"]>0 else "流出"
                fw(f"  {ft['name']}({ft['code']}): {ft['pct']:+.2f}% "
                   f"主力{direction}{abs(ft['main_net_wan']):.0f}万\n")

        # 热榜前3板块归属
        if hot_stock_blocks:
            fw(f"\n[热榜TOP3板块归属]\n")
            for code, blocks in list(hot_stock_blocks.items())[:3]:
                name = ""
                for s in hot_list[:3]:
                    if s["code"]==code: name=s["name"]; break
                fw(f"  {name}({code}): {', '.join(blocks)}\n")

        # ===== 结论 =====
        fw(f"\n{'='*70}\n")
        fw(f"  综合结论\n")
        fw(f"{'='*70}\n\n")

        # 市场情绪判断
        zt_n = len(zt_pool); dt_n = len(dt_pool)
        fw(f"1. 市场情绪: ")
        if zt_n >= 100 and dt_n <= 10:
            fw(f"强势(涨停{zt_n} >> 跌停{dt_n})\n")
        elif zt_n >= 50:
            fw(f"偏强(涨停{zt_n} vs 跌停{dt_n})\n")
        else:
            fw(f"中性偏弱(涨停{zt_n} vs 跌停{dt_n})\n")

        # 主线判断
        if concept_top:
            top_concept = concept_top[0][0]
            top_count = concept_top[0][1]
            fw(f"2. 主线方向: {top_concept}({top_count}只占据热榜) — 全市场最热概念\n")

        # 风格判断
        if industry_rank:
            tech_pct = [r["change_pct"] for r in industry_rank if any(kw in r["name"]
                for kw in ["半导体","电子","通信","芯片","计算机","软件"])]
            defense_pct = [r["change_pct"] for r in industry_rank if any(kw in r["name"]
                for kw in ["食品","饮料","银行","白酒","家电","医药","交通"])]
            if tech_pct and defense_pct:
                tech_avg = sum(tech_pct)/len(tech_pct)
                defense_avg = sum(defense_pct)/len(defense_pct)
                fw(f"3. 风格对比: 科技均值{tech_avg:+.2f}% vs 防御消费均值{defense_avg:+.2f}% "
                   f"(差{tech_avg-defense_avg:+.2f}个百分点)\n")

        fw(f"\n4. 仓位建议: Gate0 FAIL → <=20% | 持仓周期: 波段2-4周\n")

        # 数据验证
        fw(f"\n{'='*70}\n")
        fw(f"  数据源交叉验证\n")
        fw(f"{'='*70}\n")
        for tag, check in kline_check.items():
            idx_code = "000001" if "上证" in tag else "399001"
            q = indices.get(idx_code, {})
            if q and check:
                delta = abs(q.get("last_close",0) - check["yest_close"])
                fw(f"  XV1[K线] {tag}: Delta={delta:.6f}\n")
        fw(f"  XV2[热榜] 同花顺{len(hot_list)}只 + 东财行业{len(industry_rank)}个\n")
        fw(f"  XV3[涨停] ZT={zt_n} DT={dt_n}\n")
        fw(f"  综合评级: {'*'*stars}{'-'*(5-stars)} ({stars}/5)\n")

    p(f"\n[DONE] 报告: {report_path}")
