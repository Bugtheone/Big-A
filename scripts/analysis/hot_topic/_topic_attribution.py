#!/usr/bin/env python3
"""题材归因 v3 — 东财底层直调 + 同花顺热榜交叉验证"""

if __name__ == '__main__':
    import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from scripts.data_gate import gate
    from scripts.market_api import api
    from collections import Counter
    import json

    print("=" * 65)
    print("  2026-07-28 题材归因 v3（东财底层+同花顺）")
    print("=" * 65)

    # ── 1. 东财涨停池(直接调 gate) ──
    print("\n" + "─" * 50)
    print("【涨停池 — 东财直调】")
    print("─" * 50)
    try:
        zt = gate.em_zt_pool()
        if zt:
            print(f"涨停: {len(zt)}只")
            # 按行业/题材归因
            ind_counter = Counter()
            for s in zt:
                ind_counter[s.get('industry','其他')] += 1
            print(f"涨停行业分布:")
            for ind, cnt in ind_counter.most_common():
                print(f"  {ind}: {cnt}只")
            print(f"\n涨停TOP15:")
            for i, s in enumerate(zt[:15], 1):
                stat = f"{s.get('limit_days','')}连" if s.get('limit_days', 0) >= 2 else "首板"
                print(f"  {i}. {s['name']}({s['code']}) +{s.get('pct','')}% {stat} {s.get('industry','')}")
        else:
            print("(无涨停数据)")
    except Exception as e:
        print(f"失败: {e}")

    # ── 2. 东财跌停池 ──
    print("\n" + "─" * 50)
    print("【跌停池 — 东财直调】")
    print("─" * 50)
    try:
        dt = gate.em_dt_pool()
        if dt:
            ind_counter = Counter()
            for s in dt:
                ind_counter[s.get('industry','其他')] += 1
            print(f"跌停: {len(dt)}只")
            print(f"跌停行业分布:")
            for ind, cnt in ind_counter.most_common(10):
                print(f"  {ind}: {cnt}只")
        else:
            print("(无跌停数据)")
    except Exception as e:
        print(f"失败: {e}")

    # ── 3. 东财行业板块(全量) ──
    print("\n" + "─" * 50)
    print("【东财行业板块 涨跌排行】")
    print("─" * 50)
    try:
        hy = gate.em_industry_board("行业")
        if hy:
            sorted_hy = sorted(hy, key=lambda x: float(x.get('change_pct', 0) or 0), reverse=True)
            up = [b for b in sorted_hy if float(b.get('change_pct', 0) or 0) > 0]
            down = [b for b in sorted_hy if float(b.get('change_pct', 0) or 0) <= 0]
            print(f"共 {len(sorted_hy)} 行业 | 上涨: {len(up)} | 下跌: {len(down)} | 涨跌比: {len(up)}:{len(down)}")
            if up:
                print(f"\n上涨行业:")
                for b in up:
                    print(f"  {b['name']}: +{b['change_pct']}% 领涨:{b.get('lead_stock','')}")
            print(f"\n跌幅最深 TOP10:")
            for i, b in enumerate(down[:10], 1):
                print(f"  {i}. {b['name']}: {b['change_pct']}%")
        else:
            print("(无数据)")
    except Exception as e:
        print(f"失败: {e}")

    # ── 4. 东财概念板块(全量) ──
    print("\n" + "─" * 50)
    print("【东财概念板块 涨跌排行】")
    print("─" * 50)
    try:
        gn = gate.em_industry_board("概念")
        if gn:
            sorted_gn = sorted(gn, key=lambda x: float(x.get('change_pct', 0) or 0), reverse=True)
            up = [b for b in sorted_gn if float(b.get('change_pct', 0) or 0) > 0]
            down = [b for b in sorted_gn if float(b.get('change_pct', 0) or 0) <= 0]
            print(f"共 {len(sorted_gn)} 概念 | 上涨: {len(up)} | 下跌: {len(down)} | 涨跌比: {len(up)}:{len(down)}")
            if up:
                print(f"\n涨幅TOP15:")
                for i, b in enumerate(up[:15], 1):
                    main_yi = b.get('fund_flow_main_yi', 0) or 0
                    flow = f"主力{'入' if main_yi>0 else '出'}{abs(main_yi):.1f}亿" if main_yi else ""
                    print(f"  {i}. {b['name']}: +{b['change_pct']}% {flow} 领涨:{b.get('lead_stock','')}")
            print(f"\n跌幅TOP10:")
            for i, b in enumerate(sorted_gn[-10:], 1):
                print(f"  {i}. {b['name']}: {b['change_pct']}%")
        else:
            print("(无数据)")
    except Exception as e:
        print(f"失败: {e}")

    # ── 5. 同花顺热榜(已验证可用) ──
    print("\n" + "─" * 50)
    print("【同花顺热榜 TOP30 — 全市场关注焦点】")
    print("─" * 50)
    try:
        hl = api.hot_list("day")
        if hl:
            concept_counter = Counter()
            for s in hl[:50]:
                for c in s.get('concepts', []) or []:
                    concept_counter[c] += 1
            print(f"关注概念 TOP15:")
            for c, cnt in concept_counter.most_common(15):
                bar = "█" * min(cnt, 10)
                print(f"  {c}: {cnt}只 {bar}")
            print(f"\n全榜 TOP30:")
            for s in hl[:30]:
                rank_chg = s.get('rank_chg', 0) or 0
                arrow = "↑" if rank_chg > 0 else ("↓" if rank_chg < 0 else "→")
                concepts = ", ".join(s.get('concepts', [])[:3]) if s.get('concepts') else ""
                print(f"  #{s['rank']:>2} {s['name']:<8} {arrow}{abs(rank_chg):<3}| {concepts}")
        else:
            print("(无数据)")
    except Exception as e:
        print(f"失败: {e}")

    print("\n" + "=" * 65)
    print("  分析完毕")
    print("=" * 65)
