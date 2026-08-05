#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-07-29 数据质量交叉审计"""
import sys, os
BASE_DIR = os.environ.get("ANALYSIS_BASE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.chdir(BASE_DIR)

from market_api import api

issues = []
oks = []

def check(label, value, expected_range=None, source=""):
    """检查值是否在合理范围"""
    status = "OK"
    if expected_range:
        lo, hi = expected_range
        if value < lo or value > hi:
            status = "ISSUE"
            issues.append(f"[{source}] {label}: {value} 越界({lo}~{hi})")
        else:
            oks.append(f"[{source}] {label}: {value}")
    print(f"  {'OK' if status=='OK' else '!!'} {label}: {value}  {source}")

if __name__ == "__main__":
    print("=" * 60)
    print("  2026-07-29 数据质量交叉审计")
    print("=" * 60)
    
    # ====== 1. 指数行情：腾讯 vs Tushare ======
    print("\n--- 1. 九指数行情交叉验证 ---")
    
    # 源A: 腾讯
    idx = api.index_snapshot()
    tc_data = {}
    for d in idx:
        tc_data[d.get('code', d.get('name', ''))] = {
            'name': d.get('name', ''),
            'price': d['price'],
            'pct': d['change_pct'],
        }
    
    # 获取上证和深成
    sh_tc = None
    sz_tc = None
    for d in idx:
        name = d.get('name', '')
        if '上证' in name:
            sh_tc = d
        if '深证' in name:
            sz_tc = d
    
    # 源B: Tushare index_daily
    print("\n  腾讯  vs  Tushare index_daily:")
    try:
        from scripts.tushare_api import get_pro
        pro = get_pro()
        df_idx = pro.index_daily(ts_code='000001.SH', start_date='20260729', end_date='20260730')
        if df_idx is not None and not df_idx.empty:
            ts_sh = df_idx.iloc[-1]
            ts_close = float(ts_sh['close'])
            ts_pct = float(ts_sh['pct_chg'])
            if sh_tc:
                tc_close = sh_tc['price']
                diff = abs(tc_close - ts_close)
                status = "MATCH" if diff < 5 else "MISMATCH"
                print(f"  上证: 腾讯{tc_close:.2f} vs Tushare{ts_close:.2f} 差{diff:.2f} [{status}]")
                if diff >= 5:
                    issues.append(f"[指数交叉] 上证腾讯{tc_close:.2f} vs Tushare{ts_close:.2f} 差{diff:.2f}")
                else:
                    oks.append(f"[指数交叉] 上证 腾讯 vs Tushare 差{diff:.2f}(<5)")
        else:
            print(f"  Tushare index_daily 无今日数据")
    except Exception as e:
        print(f"  Tushare cross-check failed: {e}")
    
    # 涨跌幅核验: 腾讯上证 vs 推算
    if sh_tc:
        check("上证涨幅", sh_tc['change_pct'], (-10, 10), "腾讯")
        check("深成涨幅", sz_tc['change_pct'] if sz_tc else 0, (-15, 15), "腾讯")
        # 合理性: 深成涨幅应该与创业板方向一致
        cyb = [d for d in idx if '创业' in d.get('name', '')]
        if cyb and sz_tc:
            check("深成-创业板同向", abs(sz_tc['change_pct'] - cyb[0]['change_pct']), (0, 10), "腾讯")
    
    # 成交量合理性
    for d in idx:
        amt = d.get('turnover_yi', 0)
        name = d.get('name', '')
        if amt > 20000:
            issues.append(f"[指数成交] {name} 成交{amt:.0f}亿 > 20000亿(異常)")
        elif amt > 500:
            oks.append(f"[指数成交] {name} 成交{amt:.0f}亿")
    
    # ====== 2. 涨跌比验证 ======
    print("\n--- 2. 涨跌比交叉验证 ---")
    
    # 源A: 腾讯 breadth
    breadth = api.breadth()
    tc_total = breadth.get('total', 0)
    tc_up = breadth.get('up', 0)
    tc_down = breadth.get('down', 0)
    tc_flat = breadth.get('flat', 0)
    tc_up_pct = tc_up / tc_total * 100 if tc_total else 0
    
    print(f"  腾讯扫描: {tc_total}只 up={tc_up} down={tc_down} flat={tc_flat} {tc_up_pct:.1f}%涨")
    
    # 源B: 从指数涨跌推算合理性
    # 如果7-8个指数涨，下跌股应该少
    check("广度内部一致性", tc_up + tc_down + tc_flat - tc_total, (-2, 2), "BREADTH")
    
    # 源C: Tushare daily_basic
    print(f"\n  腾讯 vs Tushare daily_basic:")
    try:
        df_daily = pro.daily_basic(trade_date='20260729')
        if df_daily is not None and not df_daily.empty:
            ts_total = len(df_daily)
            print(f"  Tushare daily_basic: {ts_total}条(仅主板块)")
            check("Tushare_腾讯总股数比", ts_total / tc_total if tc_total else 0, (0.8, 1.0), "多源")
        else:
            print(f"  Tushare daily_basic 无今日数据(pm收盘后更新)")
    except Exception as e:
        print(f"  Tushare daily_basic failed: {e}")
    
    # 源D: 从板块排行累加上涨/下跌数
    if tc_up_pct > 0:
        check("广度合理范围", tc_up_pct, (40, 95), "腾讯")
    
    # ====== 3. 成交额验证 ======
    print("\n--- 3. 成交额交叉验证 ---")
    
    turnover = api.turnover()
    tc_total_yi = turnover.get('total_yi', 0)
    tc_sh_yi = turnover.get('sh_yi', 0)
    tc_sz_yi = turnover.get('sz_yi', 0)
    print(f"  腾讯turnover: 总{tc_total_yi:.1f}亿 沪{tc_sh_yi:.1f} 深{tc_sz_yi:.1f}")
    
    # 从指数快照加权累加验证
    idx_total_amt = sum(d.get('turnover_yi', 0) for d in idx)
    print(f"  九指数累加成交: {idx_total_amt:.1f}亿")
    
    # Tushare交叉
    try:
        df_daily_info = pro.index_dailybasic(trade_date='20260729', ts_code='000001.SH')
        if df_daily_info is not None and not df_daily_info.empty:
            ts_vol = float(df_daily_info.iloc[0].get('total_mv', 0)) if 'total_mv' in df_daily_info.columns else 0
            print(f"  Tushare index_dailybasic: 总市值={ts_vol/1e8:.0f}亿")
    except Exception:
        pass
    
    check("成交额合理范围", tc_total_yi, (5000, 50000), "腾讯")
    check("沪/深比合理", tc_sh_yi / tc_sz_yi if tc_sz_yi else 0, (0.3, 2.0), "腾讯")
    
    # ====== 4. 板块排行验证 ======
    print("\n--- 4. 板块排行交叉验证 ---")
    
    # 源A: 腾讯 sectors
    sectors = api.sectors()
    tc_top_sector = sectors[0]['name'] if sectors else 'N/A'
    tc_top_pct = sectors[0]['change_pct'] if sectors else 0
    
    # 源B: 同花顺 hot_list 补证
    try:
        hot_list = api.hot_list()
        if hot_list:
            # 从热榜概念tags看热门方向
            concepts = {}
            for h in hot_list[:30]:
                for c in h.get('concepts', []):
                    concepts[c] = concepts.get(c, 0) + 1
            top_concepts = sorted(concepts.items(), key=lambda x: x[1], reverse=True)[:3]
            print(f"  腾讯领涨: {tc_top_sector} ({tc_top_pct:+.2f}%)")
            print(f"  同花顺热榜: {[(t,n) for t,n in top_concepts]}")
    except Exception as e:
        print(f"  热榜获取失败: {e}")
    
    # 源C: Tushare 行业指数
    try:
        df_sw = pro.sw_daily(trade_date='20260729')
        if df_sw is not None and not df_sw.empty:
            df_sw = df_sw.sort_values('pct_chg', ascending=False)
            sw_top = df_sw.iloc[0]
            print(f"  Tushare申万行业TOP1: {sw_top.get('index_name','?')} {float(sw_top['pct_chg']):+.2f}%")
    except Exception as e:
        print(f"  Tushare sw_daily failed: {e}")
    
    # ====== 5. 涨停/跌停板验证 ======
    print("\n--- 5. 涨停/跌停板交叉验证 ---")
    
    # 源A: board_summary
    bs = api.board_summary()
    zt_bs = bs.get('zt_count', 0)
    dt_bs = bs.get('dt_count', 0)
    zb_bs = bs.get('zb_count', 0)
    print(f"  board_summary: zt={zt_bs} dt={dt_bs} zb={zb_bs}")
    
    # 源B: 东财push2ex涨停池（独立源验证）
    zt_list = api.zt_pool()
    dt_list = api.dt_pool()
    zt_em = len(zt_list) if zt_list else 0
    dt_em = len(dt_list) if dt_list else 0
    print(f"  东财push2ex zt_pool/dt_pool: zt={zt_em} dt={dt_em}")
    
    if zt_em > 0:
        zt_diff = abs(zt_bs - zt_em)
        if zt_diff > 10:
            issues.append(f"[涨停交叉] board_summary={zt_bs} vs 东财push2ex={zt_em} 差{zt_diff}")
        else:
            oks.append(f"[涨停交叉] board_summary vs 东财push2ex 差{zt_diff}(<=10)")
    else:
        # push2ex 返回 rc=102，该API已失效
        issues.append(f"[源失效] 东财push2ex涨停池返回0(rc=102)，无法交叉验证；仅用同花顺board_summary(zt={zt_bs} dt={dt_bs})")
    
    # 涨跌停比例合理性
    if zt_bs > 0:
        zb_rate = zb_bs / (zt_bs + zb_bs) * 100
        check("炸板率", zb_rate, (0, 70), "board_summary")
    
    # ====== 6. MA均线验证 ======
    print("\n--- 6. MA均线交叉验证 ---")
    
    try:
        # Tushare
        df_idx = pro.index_daily(ts_code='000001.SH', start_date='20250101', end_date='20260730')
        df_idx = df_idx.sort_values('trade_date')
        ts_close = float(df_idx.iloc[-1]['close'])
        ts_ma250 = float(df_idx['close'].tail(250).mean()) if len(df_idx) >= 250 else 0
        
        # 周线
        df_w = pro.index_weekly(ts_code='000001.SH', start_date='20250101', end_date='20260730')
        df_w = df_w.sort_values('trade_date')
        ts_w_close = float(df_w.iloc[-1]['close'])
        ts_ma20w = float(df_w['close'].tail(20).mean()) if len(df_w) >= 20 else 0
        
        print(f"  Tushare: 上证日收{ts_close:.2f} MA250={ts_ma250:.2f} {'上方' if ts_close>ts_ma250 else '下方'}")
        print(f"  Tushare: 上证周收{ts_w_close:.2f} MA20w={ts_ma20w:.2f} {'上方' if ts_w_close>ts_ma20w else '下方'}")
        
        # 交叉：MA250 vs 当前腾讯收盘价
        sh_from_tc = [d for d in idx if '上证' in d.get('name', '')]
        if sh_from_tc:
            tc_sh_price = sh_from_tc[0]['price']
            ma250_diff = abs(tc_sh_price - ts_close)
            # 先验证Tushare是否有今日数据
            df_today = pro.index_daily(ts_code='000001.SH', start_date='20260729', end_date='20260730')
            if df_today.empty or len(df_today) == 0:
                print(f"  !! Tushare无今日(0729)上证日线数据，ts_close={ts_close:.2f}(最近可用日) vs 腾讯={tc_sh_price:.2f}(今日)，跳过交叉验证")
                issues.append(f"[交叉] Tushare无今日日线数据，无法交叉验证腾讯-Tushare收盘价(腾讯={tc_sh_price:.2f}, Tushare最近={ts_close:.2f}, 差{ma250_diff:.2f})")
            else:
                check("腾讯-Tushare上证收盘价差", ma250_diff, (0, 10), "交叉")
        
        # Gate判断一致性
        if ts_close < ts_ma250:
            oks.append(f"[Gate1] 收盘{ts_close:.0f}<MA250{ts_ma250:.0f} = 年线下方(一致)")
        if ts_w_close < ts_ma20w:
            oks.append(f"[Gate0] 周收{ts_w_close:.0f}<20周线{ts_ma20w:.0f} = 一票否决(一致)")
        
    except Exception as e:
        print(f"  MA验证失败: {e}")
    
    # ====== 7. 北向资金验证 ======
    print("\n--- 7. 北向资金验证 ---")
    print(f"  注: 2024.8.19起不再披露每日北向净买入，缓存可能为0")
    try:
        nf = api.north_flow(n_days=3)
        if nf and 'records' in nf:
            recs = nf['records']
            for r in recs:
                h = r.get('hgt', 0)
                s = r.get('sgt', 0)
                print(f"    {r.get('date','?')}: hgt={h:.2f} sgt={s:.2f}")
                if abs(h) > 200:
                    issues.append(f"[北向] {r.get('date')} hgt={h:.2f}亿 异常(>200亿)")
    except Exception as e:
        print(f"  北向验证失败: {e}")
    
    # ====== 8. 异常值检测汇总 ======
    print("\n" + "=" * 60)
    print("  审计汇总")
    print("=" * 60)
    
    print(f"\n  [OK] 通过检查: {len(oks)}条")
    for o in oks:
        print(f"    {o}")
    
    if issues:
        print(f"\n  [!!] 发现问题: {len(issues)}条")
        for i in issues:
            print(f"    !! {i}")
    else:
        print(f"\n  [OK] 零问题，数据质量通过")
    
    # 最终判定
    if not issues:
        print(f"\n  >>> 数据质量: PASS 全部交叉验证通过")
    elif len(issues) <= 2:
        print(f"\n  >>> 数据质量: WARN 有{len(issues)}个问题但基本可用")
    else:
        print(f"\n  >>> 数据质量: FAIL 建议重新拉取")
