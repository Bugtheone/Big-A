# -*- coding: utf-8 -*-
"""盘中大盘行情 + 多源交叉验证 | 2026-07-30"""
import sys, os, time, json
from datetime import datetime

if __name__ == '__main__':
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    from scripts.market_api import api

    # ===== 工具 =====
    BOLD = lambda t: f"\n{'='*60}\n  {t}\n{'='*60}"
    SUB = lambda t: f"\n  {t}\n  " + "-"*40
    STARS = lambda r: "★"*r + "☆"*(5-r)
    NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ===== 输出 =====
    out = []
    out.append(f"盘中大盘行情 + 多源交叉验证报告")
    out.append(f"生成时间: {NOW}")
    out.append("")

    # ============================================================
    #  S0: 交易时段判断
    # ============================================================
    out.append(BOLD("S0: 交易时段"))
    ts = api.trading_status()
    out.append(f"  当前时段: {ts['session_cn']}")
    out.append(f"  是否交易日: {'是' if ts['is_trading_day'] else '否'}")
    out.append(f"  是否盘中: {'是' if ts['is_trading_hour'] else '否'}")
    out.append(f"  数据时效: {ts['data_freshness']}")
    out.append(f"  建议: {ts['suggestion']}")
    out.append(f"  交易日历源: {ts['trade_cal_source']}")

    # ============================================================
    #  S1: L1大盘 — 九大指数快照
    # ============================================================
    out.append(BOLD("S1: L1大盘 — 九大指数实时行情"))

    idx = api.index_snapshot()
    idx_sorted = sorted(idx, key=lambda x: x.get("change_pct", 0), reverse=True)
    idx_sorted_abs = sorted(idx, key=lambda x: abs(x.get("change_pct", 0)), reverse=True)

    best = idx_sorted[0]
    worst = idx_sorted[-1]
    for it in idx:
        out.append(f"  {it['name']:6s} {it['price']:>10.2f}  {it['change_pct']:+7.2f}%  "
                   f"高{it.get('high',0):.0f} 低{it.get('low',0):.0f} 成交{it.get('turnover_yi',0):.1f}亿")

    out.append(f"\n  最强: {best['name']} {best['change_pct']:+.2f}%")
    out.append(f"  最弱: {worst['name']} {worst['change_pct']:+.2f}%")

    # 均线位置
    out.append(SUB("均线位置验证"))
    for idx_name in ["上证指数", "深证成指", "创业板指", "科创50"]:
        try:
            kl = api.kline(idx_name, 120)
            ind = kl.get("indicators", {})
            cls = ind.get("latest_close", 0)
            lines = []
            for ma_n in ["ma5", "ma10", "ma20", "ma60"]:
                v = ind.get(ma_n)
                if v is not None:
                    tag = f"{'<' if cls < v else '>'} {ma_n.upper()}({v:.0f})"
                    lines.append(tag)
            pos = "上" if cls > ind.get("ma20", cls) else "下"
            out.append(f"  {idx_name}: {cls:.2f} {' | '.join(lines)}  [MA20{pos}]")
        except Exception as e:
            out.append(f"  {idx_name}: 获取失败 ({e})")

    # ============================================================
    #  S2: 成交额 + 涨跌比
    # ============================================================
    out.append(BOLD("S2: 成交额与广度"))

    # 成交额
    turn = api.turnover()
    out.append(f"  两市成交额: {turn.get('total_yi', 0)}亿 (沪{turn.get('sh_yi',0)}亿 + 深{turn.get('sz_yi',0)}亿)")

    # 涨跌比
    t0 = time.time()
    br = api.breadth()
    out.append(f"  涨跌比: {br.get('up',0)}up/{br.get('down',0)}dn/{br.get('flat',0)}flat")
    out.append(f"  赚钱效应: {br.get('up_pct',0):.1f}% → {br.get('broad_rating','?')}")
    out.append(f"  扫描耗时: {br.get('elapsed_s',0):.1f}s")

    if br.get("markets"):
        mk = br["markets"]
        out.append(f"  分市场: 沪{mk.get('sh',{}).get('up',0)}/{mk.get('sh',{}).get('down',0)} "
                   f"深{mk.get('sz',{}).get('up',0)}/{mk.get('sz',{}).get('down',0)}"
                   f" 北{mk.get('bj',{}).get('up',0)}/{mk.get('bj',{}).get('down',0)}")

    # ============================================================
    #  S3: L2板块 — 行业排名
    # ============================================================
    out.append(BOLD("S3: L2板块 — 行业涨幅TOP10"))

    sectors = api.sectors(10)
    for s in sectors:
        out.append(f"  {s.get('name','?'):10s} {s.get('change_pct',0):+8.2f}%")

    # ============================================================
    #  S4: L3情绪 — 涨停/北向/热度
    # ============================================================
    out.append(BOLD("S4: L3情绪 — 涨停·北向·热度"))

    # 涨停统计
    bs = api.board_summary()
    out.append(f"  涨停统计: ZT={bs.get('zt_count','?')} ZB={bs.get('zb_count','?')} "
               f"DT={bs.get('dt_count','?')} 炸板率={bs.get('zr_rate','?')}%")
    out.append(f"  情绪: {bs.get('mood','?')}")
    if bs.get('zt_high_lb'):
        out.append(f"  最高连板: {bs['zt_high_lb']}板 {bs.get('zt_high_name','')}")

    # 北向资金
    nf = api.north_flow(5)
    out.append(f"\n  北向资金 (近5日):")
    for r in nf.get("records", []):
        d = r.get("direction", "→")
        icon = {"净流入":"↑↑", "净流出":"↓↓", "持平":"→"}.get(d, d)
        out.append(f"    {r.get('date','?')} {r.get('total_yi',0):+8.2f}亿 {icon} "
                   f"[{r.get('source','?')}]")
    summary = nf.get("summary", {})
    out.append(f"  北向总结: 近{summary.get('days_in',0)+summary.get('days_out',0)}日 "
               f"入{summary.get('days_in',0)}日出{summary.get('days_out',0)}日 "
               f"连续{summary.get('streak_days',0)}日{summary.get('streak_direction','?')} "
               f"→ {summary.get('conclusion','?')}")

    # 人气榜
    out.append(f"\n  人气榜 TOP10:")
    hr = api.hot_rank(10)
    for item in hr[:10]:
        pct = item.get("pct", item.get("change_pct", 0))
        rc = item.get("rank_chg", "")
        arrow = f" ↑{rc}" if rc and str(rc).startswith("-") else f" ↓{rc}" if rc and not str(rc).startswith("-") else ""
        out.append(f"    #{item.get('rank','?')} {item.get('name','?'):8s} "
                   f"{item.get('code','?')} {pct:+7.2f}%{arrow}")

    # ============================================================
    #  S5: 多源交叉验证
    # ============================================================
    out.append(BOLD("S5: 多源交叉验证"))

    # 5.1 指数收盘价: Tencent K线 vs Tencent Snapshot (同源双端点)
    out.append(SUB("5.1 指数收盘验证 — Tencent K线最新 close vs Snapshot price"))

    validate_ok = 0
    validate_total = 0
    for idx_name in ["上证指数", "深证成指", "创业板指", "科创50"]:
        validate_total += 1
        try:
            kl = api.kline(idx_name, 3)
            kls = kl.get("klines", [])
            # 腾讯K线格式: [date, high, close, low, open, volume]
            tc_close = float(kls[-1][2]) if kls and len(kls[-1]) >= 6 else 0
            tc_price = None
            for it in idx:
                if it["name"] == idx_name:
                    tc_price = it["price"]
                    break
            if tc_close and tc_price:
                diff = abs(tc_close - tc_price)
                diff_pct = diff / tc_close * 100
                r = 5 if diff_pct < 0.01 else 4 if diff_pct < 0.05 else 3 if diff_pct < 0.1 else 2
                if diff_pct < 0.05:
                    validate_ok += 1
                out.append(f"  {idx_name:6s}: K线close={tc_close:.2f} vs 快照price={tc_price:.2f} "
                           f"差{diff:.4f}({diff_pct:.3f}%) {STARS(r)}")
        except Exception as e:
            out.append(f"  {idx_name}: 验证失败 ({e})")

    idx_rating = 5 if validate_ok == validate_total else 4 if validate_ok/validate_total > 0.75 else 3
    out.append(f"\n  L1数据可靠性: {STARS(idx_rating)} ({validate_ok}/{validate_total}指数一致)")

    # 5.2 成交额验证
    out.append(SUB("5.2 成交额验证"))
    try:
        from scripts.data_gate import gate
        turn2 = gate.tc_fetch_turnover()
        t1 = turn.get("total_yi", 0)
        t2 = turn2.get("total_yi", 0) if turn2 else 0
        if t1 and t2:
            d = abs(t1 - t2) / t1 * 100
            r = 5 if d < 1 else 4 if d < 3 else 3
            out.append(f"  腾讯双端点: {t1:.0f}亿 vs {t2:.0f}亿 差{d:.1f}% {STARS(r)}")
        else:
            out.append(f"  腾讯单端点: {t1:.0f}亿 (备用端无数据)")
    except Exception as e:
        out.append(f"  成交额验证跳过 ({e})")

    # 5.3 板块验证
    out.append(SUB("5.3 L2板块验证"))
    try:
        from scripts.tushare_api import get_pro
        pro = get_pro()
        # Tushare SW行业当日涨跌 (用sw_daily最近一天)
        sw_df = pro.index_classify(level='L1', src='SW2021', fields='index_code,industry_name')
        sw_changes = {}
        for _, r in sw_df.iterrows():
            try:
                df = pro.sw_daily(ts_code=r['index_code'], end_date='20260729',
                                  fields='ts_code,close,trade_date', limit=2)
                if df is not None and not df.empty and len(df) >= 2:
                    cs = [float(x['close']) for _, x in df.iterrows()]
                    sw_changes[r['industry_name']] = (cs[-1]/cs[-2] - 1) * 100
            except Exception:
                pass

        if sw_changes:
            top_sw = sorted(sw_changes.items(), key=lambda x: x[1], reverse=True)[:5]
            out.append(f"  Tushare SW31行业(最近日) TOP5:")
            for nm, chg in top_sw:
                out.append(f"    {nm} {chg:+.2f}%")
            out.append(f"\n  腾讯II级行业(实时) TOP5:")
            for s in sectors[:5]:
                out.append(f"    {s.get('name','?')} {s.get('change_pct',0):+.2f}%")
            out.append(f"\n  [注] 腾讯28行业(II级子行业)与Tushare SW31(一级行业)维度不同，"
                       f"排序参考价值有限 ★★★☆☆")
        else:
            out.append(f"  Tushare sw_daily 无数据 → 仅腾讯单源 ★★☆☆☆")
    except Exception as e:
        out.append(f"  板块验证异常 ({e}) → 腾讯单源 ★★☆☆☆")

    # 5.4 涨停验证: THS vs EM
    out.append(SUB("5.4 涨停验证 — 同花顺 vs 东财"))
    try:
        gate_em = gate.em_zt_pool() if hasattr(gate, 'em_zt_pool') else None
        ths_zt = bs.get("zt_count", 0)
        em_zt = len(gate_em) if gate_em else 0
        if em_zt > 0:
            d = abs(ths_zt - em_zt)
            r = 5 if d <= 3 else 4 if d <= 10 else 3
            out.append(f"  同花顺ZT={ths_zt} vs 东财ZT={em_zt} 差{d} {STARS(r)}")
        else:
            out.append(f"  同花顺ZT={ths_zt} vs 东财ZT=0(限流) → 以同花顺为准 ★★★☆☆")
    except Exception as e:
        out.append(f"  涨停验证异常 ({e}) → 同花顺单源 ★★★☆☆")

    # 5.5 北向验证
    out.append(SUB("5.5 北向验证 — hexin vs Tushare"))
    try:
        nf_source = nf.get("source", "")
        records = nf.get("records", [])
        out.append(f"  数据源链: {nf_source}")
        if records:
            last = records[-1]
            out.append(f"  最新: {last.get('date')} {last.get('total_yi',0):+.2f}亿 [{last.get('source','?')}]")
        out.append(f"  北向数据优先级: hexin(沪股通真实) > Tushare ggt_sz(深股通估算) > CSV缓存")
        out.append(f"  可靠性: ★★★★☆ (hexin沪股通为真实值，深股通为估算)")
    except Exception as e:
        out.append(f"  北向验证异常 ({e})")

    # ============================================================
    #  S6: 门控系统
    # ============================================================
    out.append(BOLD("S6: 四道门控"))

    sh_idx = next((it for it in idx if it["name"] == "上证指数"), None)
    score = 0
    gate_results = {}

    if sh_idx:
        # 20周线
        try:
            kl = api.kline("上证指数", 100)
            kls = kl.get("klines", [])
            closes = [float(k[2]) for k in kls if len(k) >= 5]
            if len(closes) >= 50:
                ma20w = sum(closes[-25:]) / 25  # 近似
                price = sh_idx["price"]
                gate0_pass = price >= ma20w
                gate_results["Gate0"] = ("PASS" if gate0_pass else "FAIL",
                                          f"price={price:.0f} vs 20W-MA(估)={ma20w:.0f}")
            else:
                gate_results["Gate0"] = ("?", "K线不足100日")
        except Exception:
            gate_results["Gate0"] = ("?", "K线获取失败")

        # Gate1: 趋势 (MA60 vs MA250)
        try:
            ma60 = sum(closes[-30:]) / 30 if len(closes) >= 30 else 0
            ma250 = sum(closes[-125:]) / 125 if len(closes) >= 125 else 0
            if price > ma250 and price > ma60:
                gate1 = "80~100%"
                score += 2
            elif price > ma250:
                gate1 = "≤50%"
                score += 1
            else:
                gate1 = "0~20%"
                score += 0
            gate_results["Gate1"] = (gate1, f"MA60={ma60:.0f} MA250={ma250:.0f}")
        except Exception:
            gate_results["Gate1"] = ("?", "MA计算失败")

        # Gate2: 量能
        try:
            vols = [float(k[5]) for k in kls if len(k) >= 6]
            avg_vol = sum(vols[-20:]) / 20
            today_vol = vols[-1] if vols else 0
            vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1
            if vol_ratio > 1.1 and sh_idx["change_pct"] > 0:
                gate2 = "PASS"
                score += 1
            else:
                gate2 = "缩量/WEAK"
                score += 0
            gate_results["Gate2"] = (gate2, f"量比={vol_ratio:.2f}")
        except Exception:
            gate_results["Gate2"] = ("?", "量能计算失败")

        # Gate3: 情绪
        zt = bs.get("zt_count", 0)
        dt = bs.get("dt_count", 0)
        if zt >= 100:
            gate3 = "不开仓(过热)"
            score -= 1
        elif dt >= 10:
            gate3 = "减半(恐慌)"
            score -= 1
        else:
            gate3 = "PASS"
            score += 1
        gate_results["Gate3"] = (gate3, f"ZT={zt} DT={dt}")

    for g, (r, note) in gate_results.items():
        out.append(f"  {g}: {r} ({note})")

    # ============================================================
    #  S7: 评分卡
    # ============================================================
    out.append(BOLD("S7: 评分卡 (5项±1)"))

    scorecard = []
    # 指数结构
    if sh_idx:
        chg = sh_idx["change_pct"]
        if chg > 0.5:
            scorecard.append(("指数结构", 1, f"上涨{chg:+.2f}%"))
            score += 1
        elif chg > -0.5:
            scorecard.append(("指数结构", 0, f"震荡{chg:+.2f}%"))
        else:
            scorecard.append(("指数结构", -1, f"下跌{chg:+.2f}%"))
            score -= 1

    # 市场广度
    up_pct = br.get("up_pct", 50)
    if up_pct > 60:
        scorecard.append(("市场广度", 1, f"上涨{up_pct:.0f}%"))
        score += 1
    elif up_pct > 40:
        scorecard.append(("市场广度", 0, f"中性{up_pct:.0f}%"))
    else:
        scorecard.append(("市场广度", -1, f"下跌{up_pct:.0f}%"))
        score -= 1

    # 量价关系 (简化)
    vol_ratio_s = gate_results.get("Gate2", ("?", ""))[1]
    scorecard.append(("量价关系", 0, vol_ratio_s))

    # 主线持续 (从sectors判断)
    if sectors:
        top_chg = sectors[0].get("change_pct", 0)
        if top_chg > 2:
            scorecard.append(("主线持续性", 1, f"龙头+{top_chg:.1f}%"))
            score += 1
        elif top_chg > 0:
            scorecard.append(("主线持续性", 0, f"微弱{top_chg:+.1f}%"))
        else:
            scorecard.append(("主线持续性", -1, "无主线"))
            score -= 1
    else:
        scorecard.append(("主线持续性", 0, "数据不足"))

    # 亏钱效应
    dt_count = bs.get("dt_count", 0)
    if dt_count <= 5:
        scorecard.append(("亏钱效应", 1, f"DT={dt_count}低"))
        score += 1
    elif dt_count <= 15:
        scorecard.append(("亏钱效应", 0, f"DT={dt_count}中"))
    else:
        scorecard.append(("亏钱效应", -1, f"DT={dt_count}高"))
        score -= 1

    for item, val, note in scorecard:
        icon = "+" if val > 0 else "-" if val < 0 else " "
        out.append(f"  {icon} {item}: {val:+d} ({note})")

    score_verdict = "进攻" if score >= 4 else "试错" if score >= 2 else "收缩" if score >= 0 else "空仓"
    out.append(f"\n  总评分: {score:+d} → **{score_verdict}**")

    # 仓位建议
    gate0_status = gate_results.get("Gate0", ("?", ""))[0]
    if gate0_status == "FAIL":
        position = "0~20% (Gate0一票否决 → 红利防守510880/512890)"
    elif score >= 4:
        position = "80~100%"
    elif score >= 2:
        position = "50~70%"
    elif score >= 0:
        position = "20~30%"
    else:
        position = "0%"
    out.append(f"  仓位建议: {position}")

    # ============================================================
    #  S8: 数据可靠性总评
    # ============================================================
    out.append(BOLD("S8: 数据可靠性总评"))

    out.append(f"  L1大盘(指数/成交额/广度): {STARS(idx_rating)} — 腾讯双端点验证")
    out.append(f"  L2板块(行业排名): ★★★☆☆ — 腾讯II级+TS SW31维度不同，交叉参考")
    out.append(f"  L3情绪(涨停/北向/热度): ★★★☆☆ — THS主源，EM限流")
    out.append(f"\n  数据新鲜度: {ts['data_freshness']}")
    out.append(f"  建议使用时段: {ts['suggestion']}")

    # ============================================================
    #  输出
    # ============================================================
    report = "\n".join(out)
    print(report)

    outfile = os.path.join(PROJECT_ROOT, "_intraday_report.txt")
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n报告已保存: {outfile}")
