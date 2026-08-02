#!/usr/bin/env python3
"""
2026-07-29 大盘→板块→个股 三层分析 + 多源交叉验证
"""
import sys, os, json, time
from datetime import datetime
from collections import Counter

if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'scripts'))
    from market_api import api

    TODAY = "20260729"
    print("=" * 70)
    print(f"  A股 大盘→板块→个股 分析报告 — {TODAY[:4]}-{TODAY[4:6]}-{TODAY[6:8]}")
    print("=" * 70)

    # ============================================================
    #  LAYER 1: 大盘
    # ============================================================
    print("\n" + "─" * 60)
    print("  【第一层：大盘】")
    print("─" * 60)

    # --- 1.1 九指数快照 (腾讯，不封IP) ---
    print("\n  ■ 1.1 九指数行情 (腾讯财经)")
    idx = api.index_snapshot()
    index_names = ['上证指数','深证成指','创业板指','科创50','上证50','沪深300','中证500','中证1000','上证全指']
    index_data = {}
    for d in idx:
        nm = d.get('name', '')
        index_data[nm] = d

    for nm in index_names:
        d = index_data.get(nm, {})
        if d:
            print(f"    {nm:8s}: {d['price']:>10.2f}  {d['change_pct']:>+.2f}%  成交{d.get('amount_wan',0)/10000:.0f}亿")
        else:
            print(f"    {nm:8s}: 无数据")

    # 涨跌比
    up_count = sum(1 for d in index_data.values() if d.get('change_pct', 0) > 0)
    dn_count = sum(1 for d in index_data.values() if d.get('change_pct', 0) < 0)
    print(f"    -> {up_count}涨{dn_count}跌")

    # --- 1.2 全市场广度 (腾讯) ---
    print("\n  ■ 1.2 涨跌广度 (腾讯全市场扫描)")
    try:
        br = api.breadth()
        total_s = br.get('total', 0)
        up_s = br.get('up', 0)
        dn_s = br.get('down', 0)
        flat_s = br.get('flat', 0)
        up_pct = up_s / total_s * 100 if total_s else 0
        bj_data_status = "ok" if not br.get('bj_data_status') else br.get('bj_data_status')
        print(f"    全市场 {total_s}只: 涨{up_s} ({up_pct:.1f}%) 跌{dn_s} 平{flat_s}")
        print(f"    北交所数据状态: {bj_data_status}")
    except Exception as e:
        print(f"    广度获取失败: {e}")

    # --- 1.3 成交额 (腾讯) ---
    print("\n  ■ 1.3 成交额 (腾讯 turnover)")
    try:
        t = api.turnover()
        total_amt = t.get('total_yi', 0)
        sh_amt = t.get('sh_yi', 0)
        sz_amt = t.get('sz_yi', 0)
        print(f"    总成交: {total_amt:.0f}亿  沪: {sh_amt:.0f}亿  深: {sz_amt:.0f}亿")

        # 交叉验证：各指数成交额累加
        idx_vol = sum(d.get('amount_wan', 0) / 10000 for d in index_data.values())
        print(f"    九指数累加: {idx_vol:.0f}亿  (注: 含重复统计)")
    except Exception as e:
        print(f"    成交额获取失败: {e}")

    # --- 1.4 北向资金 ---
    print("\n  ■ 1.4 北向资金 (5级降级链)")
    try:
        nf = api.north_flow(n_days=5)
        if nf and 'records' in nf:
            for r in nf['records'][-5:]:
                print(f"    {r.get('date','?')}: hgt={r.get('hgt',0):.2f} sgt={r.get('sgt',0):.2f}")
    except Exception as e:
        print(f"    北向获取失败: {e}")

    # --- 1.5 门控判定 ---
    print("\n  ■ 1.5 门控系统判定")
    # Gate0 周线：用 Tushare 周线（最近可用日）
    try:
        import tushare as ts
        pro = ts.pro_api()

        # 日线MA
        df_idx = pro.index_daily(ts_code='000001.SH', start_date='20250101', end_date=TODAY)
        df_idx = df_idx.sort_values('trade_date')
        latest = df_idx.iloc[-1]
        ts_close = float(latest['close'])
        ts_date = latest['trade_date']
        ts_ma250 = float(df_idx['close'].tail(250).mean()) if len(df_idx) >= 250 else 0
        ts_ma60 = float(df_idx['close'].tail(60).mean()) if len(df_idx) >= 60 else 0

        # 周线
        df_w = pro.index_weekly(ts_code='000001.SH', start_date='20250101', end_date=TODAY)
        df_w = df_w.sort_values('trade_date')
        w_latest = df_w.iloc[-1]
        ts_w_close = float(w_latest['close'])
        ts_w_date = w_latest['trade_date']
        ts_ma20w = float(df_w['close'].tail(20).mean()) if len(df_w) >= 20 else 0

        print(f"    Tushare 日线: {ts_date} 收{ts_close:.2f}  MA60={ts_ma60:.2f}  MA250={ts_ma250:.2f}")
        print(f"    Tushare 周线: {ts_w_date} 收{ts_w_close:.2f}  MA20w={ts_ma20w:.2f}")

        # Gate0: 20周线一票否决
        if ts_w_close < ts_ma20w:
            is_above_ma20w = ts_w_close > ts_ma20w
            print(f"    Gate0: 周收{ts_w_close:.0f} < 20周线{ts_ma20w:.0f}")
            print(f"    >>> 一票否决！不开新仓")
        else:
            print(f"    Gate0: 周收{ts_w_close:.0f} >= 20周线{ts_ma20w:.0f}  -> 通过")

        # Gate1: MA60/250 仓位上限
        above_ma250 = ts_close > ts_ma250
        above_ma60 = ts_close > ts_ma60
        ma60_direction = "UP" if ts_ma60 > float(df_idx['close'].tail(60).iloc[0]) else "DOWN"  # simplified

        print(f"    Gate1: 收{ts_close:.0f}")
        if above_ma250 and above_ma60 and ma60_direction == "UP":
            print(f"    >>> MA250上方+MA60向上 → 仓位上限 80~100%")
        elif above_ma250:
            print(f"    >>> MA250上方 → 仓位上限 ≤50%")
        elif above_ma60:
            print(f"    >>> MA60~250之间 → 仓位上限 ≤30%")
        else:
            print(f"    >>> MA60下方 → 仓位上限 0~20%")

        # Gate2: 量能广度
        up_ok = up_s > 2500 if 'up_s' in dir() else False
        print(f"    Gate2: 上涨{up_s}只 {'>2500 OK' if up_ok else '<2500 WARN'}")

        # Gate3: 情绪 (在后面涨停分析后补充)

    except Exception as e:
        print(f"    Tushare数据异常: {e}")

    # ============================================================
    #  LAYER 2: 板块
    # ============================================================
    print("\n" + "─" * 60)
    print("  【第二层：板块】")
    print("─" * 60)

    # --- 2.1 行业涨跌排名 ---
    print("\n  ■ 2.1 行业涨跌排名 (东财)")
    try:
        sectors = api.sectors()
        if sectors:
            # 按涨跌幅排序
            sorted_s = sorted(sectors, key=lambda x: x.get('change_pct', 0), reverse=True)
            print("    === TOP 10 涨幅行业 ===")
            for s in sorted_s[:10]:
                print(f"      {s.get('name',''):>12s}: {s.get('change_pct',0):>+6.2f}%  涨{s.get('up_count','?')}/跌{s.get('down_count','?')}")
            print("    === BOTTOM 5 跌幅行业 ===")
            for s in sorted_s[-5:]:
                print(f"      {s.get('name',''):>12s}: {s.get('change_pct',0):>+6.2f}%  涨{s.get('up_count','?')}/跌{s.get('down_count','?')}")
    except Exception as e:
        print(f"    行业排名获取失败: {e}")

    # --- 2.2 热点题材归因 ---
    print("\n  ■ 2.2 热点题材归因 (同花顺)")
    try:
        hot = api.hot_reason()
        if hot:
            # hot_reason returns list: [{code, name, pct, concepts, ...}, ...]
            all_tags = []
            for item in hot:
                concepts = item.get('concepts', '') or ''
                tags = [t.strip() for t in concepts.replace('+', ',').replace(';', ',').split(',') if t.strip()]
                all_tags.extend(tags)
            cnt = Counter(all_tags)
            if cnt:
                print("    TOP 10 热门题材:")
                for tag, n in cnt.most_common(10):
                    print(f"      {tag}: {n}只")

            # 最强个股
            sorted_hot = sorted(hot, key=lambda x: float(x.get('pct', 0) or 0), reverse=True)
            print("    涨幅 TOP5:")
            for r in sorted_hot[:5]:
                print(f"      {r.get('code','')} {r.get('name','')}: {r.get('pct',0)}%  {r.get('concepts','')}")
        else:
            print("    同花顺热点: 无数据")
    except Exception as e:
        print(f"    热点获取失败: {e}")

    # --- 2.3 同花顺热榜 ---
    print("\n  ■ 2.3 同花顺热榜")
    try:
        hot_list = api.hot_list()
        if hot_list:
            concepts = {}
            for h in hot_list[:30]:
                for c in h.get('concepts', []):
                    concepts[c] = concepts.get(c, 0) + 1
            top_concepts = sorted(concepts.items(), key=lambda x: x[1], reverse=True)[:5]
            print(f"    热榜概念热度: {top_concepts}")
            print(f"    热榜 TOP5:")
            for h in hot_list[:5]:
                print(f"      #{h.get('rank','?')} {h.get('name','')} 热度{h.get('heat','?')} {h.get('pct',0):+.1f}%")
    except Exception as e:
        print(f"    热榜获取失败: {e}")

    # ============================================================
    #  LAYER 3: 个股 (打板情绪)
    # ============================================================
    print("\n" + "─" * 60)
    print("  【第三层：个股 (打板情绪)】")
    print("─" * 60)

    # --- 3.1 涨停/跌停/炸板 ---
    print("\n  ■ 3.1 涨停/跌停/炸板 (同花顺 board_summary)")
    try:
        bs = api.board_summary()
        zt_bs = bs.get('zt_count', 0)
        dt_bs = bs.get('dt_count', 0)
        zb_bs = bs.get('zb_count', 0)
        zt_open = bs.get('zt_open', 0)
        zt_yesterday = bs.get('zt_yesterday', 0)
        zt_high_lb = bs.get('zt_high_lb', 0)
        zt_high_name = bs.get('zt_high_name', '')

        zb_rate = zb_bs / (zt_bs + zb_bs) * 100 if (zt_bs + zb_bs) > 0 else 0
        jj_rate = zt_open / zt_yesterday * 100 if zt_yesterday > 0 else 0

        print(f"    涨停: {zt_bs}只  炸板: {zb_bs}只  跌停: {dt_bs}只")
        print(f"    炸板率: {zb_rate:.1f}%  晋级率: {jj_rate:.1f}%")
        print(f"    最高连板: {zt_high_lb}连板 ({zt_high_name})")
        print(f"    昨涨停今表现: 涨停{zt_open}/昨{zt_yesterday}")

        # Gate3 情绪判定
        if zt_bs >= 100:
            print(f"    Gate3情绪: 涨停{zt_bs}>=100 → 不开新仓")
        elif dt_bs > 10:
            print(f"    Gate3情绪: 跌停{dt_bs}>10 → 减半仓")
        else:
            print(f"    Gate3情绪: 涨停{zt_bs}<100 跌停{dt_bs}<=10 → 正常")

        # 涨停原因分布
        zt_reasons = bs.get('zt_top_reasons', [])
        if zt_reasons:
            print("    涨停原因 TOP5:")
            for r, n in zt_reasons[:5]:
                print(f"      {r}: {n}只")

    except Exception as e:
        print(f"    打板数据获取失败: {e}")

    # ============================================================
    #  综合判定
    # ============================================================
    print("\n" + "=" * 70)
    print("  【综合判定】")
    print("=" * 70)

    issues_found = []

    # Gate0
    gate0_pass = ts_w_close >= ts_ma20w if 'ts_w_close' in dir() else False
    if not gate0_pass:
        print("  Gate0: [FAIL] 一票否决 (周线在20周线下方)")
        issues_found.append("Gate0一票否决")
    else:
        print("  Gate0: [PASS] 通过")

    # Gate1
    gate1_status = "归零"
    if above_ma250 and above_ma60:
        gate1_status = "80~100%"
    elif above_ma250:
        gate1_status = "<=50%"
    elif above_ma60:
        gate1_status = "<=30%"
    else:
        gate1_status = "<=20%"
    print(f"  Gate1: [{'PASS' if gate1_status not in ('<=20%','归零') else 'WARN'}] 仓位上限 {gate1_status}")

    # Gate2
    print(f"  Gate2: [{'PASS' if up_ok else 'WARN'}] 上涨家数 {up_s}")

    # Gate3
    if zt_bs >= 100:
        print(f"  Gate3: [FAIL] 涨停{zt_bs}>=100 不开新仓")
        issues_found.append("涨停过热")
    elif dt_bs > 10:
        print(f"  Gate3: [WARN] 跌停{dt_bs}>10 减半仓")
        issues_found.append("跌停超标")
    else:
        print(f"  Gate3: [PASS] 涨停{zt_bs} 跌停{dt_bs}")

    # 综合打分卡
    score = 0
    # 1. 指数结构
    if up_count >= 6:
        score += 1
        print(f"  指数结构: +1 ({up_count}涨)")

    else:
        score -= 1
        print(f"  指数结构: -1 ({up_count}涨)")

    # 2. 市场广度
    if up_s > 2500:
        score += 1
        print(f"  市场广度: +1 (上涨{up_s}>2500)")
    elif up_s > 1000:
        score += 0
        print(f"  市场广度: 0 (上涨{up_s})")
    else:
        score -= 1
        print(f"  市场广度: -1 (上涨{up_s}<1000)")

    # 3. 量价关系 (简化: 用当日成交额判断)
    if total_amt > 15000:
        score += 1
        print(f"  量价关系: +1 (成交{total_amt:.0f}亿>15000)")
    else:
        score -= 1
        print(f"  量价关系: -1 (成交{total_amt:.0f}亿)")

    # 4. 主线持续性 (涨停>50且有明确原因)
    if zt_bs > 50:
        score += 1
        print(f"  主线持续性: +1 (涨停{zt_bs}>50)")
    else:
        score -= 1
        print(f"  主线持续性: -1 (涨停{zt_bs}<=50)")

    # 5. 亏钱效应 (跌停+炸板)
    total_bad = dt_bs + zb_bs
    if total_bad <= 20:
        score += 1
        print(f"  亏钱效应: +1 (跌停+炸板={total_bad}<=20)")
    else:
        score -= 1
        print(f"  亏钱效应: -1 (跌停+炸板={total_bad}>20)")

    print(f"\n  打分: {score}/5")
    if score >= 4:
        print(f"  >>> 进攻 (80~100%仓位)")
    elif score >= 2:
        print(f"  >>> 试错 (30~50%仓位)")
    elif score >= 0:
        print(f"  >>> 收缩 (≤20%仓位)")
    else:
        print(f"  >>> 空仓 (0%)")

    # Gate0 一票否决后强制空仓
    if not gate0_pass:
        print(f"  >>> Gate0一票否决 → 强制空仓！")

    # ============================================================
    #  数据质量备注
    # ============================================================
    print("\n" + "─" * 60)
    print("  【数据源交叉验证备注】")
    print("─" * 60)
    print(f"  行情: 腾讯财经 (不封IP) — 九指数实时快照")
    print(f"  广度: 腾讯全市场扫描 — {total_s}只 (含沪深京)")
    print(f"  门控: Tushare日线/周线 — 最近可用日 {ts_date} (今日数据可能未更新)")
    print(f"  行业: 东财 push2 (m:90+t:2)")
    print(f"  热点: 同花顺 hot_reason (零鉴权)")
    print(f"  热榜: 同花顺 hot_list")
    print(f"  打板: 同花顺 board_summary (zt={zt_bs} dt={dt_bs} zb={zb_bs})")
    print(f"  北向: 5级降级链 (2024.8.19起日度数据已停更)")
    print(f"  东财push2ex: rc=102 已失效，涨停池改用同花顺")
    print(f"  腾讯-Tushare交叉: Tushare{ts_date} vs 腾讯今日 — 日期不同时不交叉对比")
    print()
    print("=" * 70)
    print(f"  报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
