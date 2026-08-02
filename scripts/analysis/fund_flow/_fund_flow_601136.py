#!/usr/bin/env python3
"""601136 首创证券 当日资金流向 — Tushare ts_moneyflow + 腾讯"""
import json, urllib.request, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# --- 腾讯行情 ---
try:
    qurl = 'https://qt.gtimg.cn/q=sh601136'
    req = urllib.request.Request(qurl)
    req.add_header('User-Agent', 'Mozilla/5.0')
    resp = urllib.request.urlopen(req, timeout=10)
    data_text = resp.read().decode('gbk')
    vals = data_text.split('"')[1].split('~')
    print(f'=== 601136 {vals[1]} 行情 ===')
    print(f'现价: {vals[3]}  涨跌幅: {vals[32]}%  涨跌额: {vals[31]}')
    print(f'今开/昨收: {vals[5]}/{vals[4]}  最高/最低: {vals[33]}/{vals[34]}')
    print(f'成交额: {float(vals[37])/1e4:.2f}亿  换手率: {vals[38]}%')
    print(f'量比: {vals[49]}  振幅: {vals[43]}%')
    print(f'PE(TTM): {vals[39]}  PB: {vals[46]}  总市值: {vals[45]}亿')
except Exception as e:
    print(f'腾讯行情失败: {e}')

# --- Tushare ts_moneyflow ---
try:
    from scripts.tushare_pro_data import ts_moneyflow
    df = ts_moneyflow(ts_code='601136.SH', trade_date='20260728')
    if df is not None and not df.empty:
        print('\n=== Tushare 资金流向 (2026-07-28) ===')
        row = df.iloc[0]
        # 主力 = 大单 + 超大单
        buy_elg_vol = row.get('buy_elg_vol', 0) or 0  # 超大单买入量(手)
        sell_elg_vol = row.get('sell_elg_vol', 0) or 0
        buy_lg_vol = row.get('buy_lg_vol', 0) or 0   # 大单买入量(手)
        sell_lg_vol = row.get('sell_lg_vol', 0) or 0
        buy_md_vol = row.get('buy_md_vol', 0) or 0   # 中单买入量
        sell_md_vol = row.get('sell_md_vol', 0) or 0
        buy_sm_vol = row.get('buy_sm_vol', 0) or 0   # 小单买入量
        sell_sm_vol = row.get('sell_sm_vol', 0) or 0
        
        buy_elg_amt = row.get('buy_elg_amount', 0) or 0  # 万元
        sell_elg_amt = row.get('sell_elg_amount', 0) or 0
        buy_lg_amt = row.get('buy_lg_amount', 0) or 0
        sell_lg_amt = row.get('sell_lg_amount', 0) or 0
        buy_md_amt = row.get('buy_md_amount', 0) or 0
        sell_md_amt = row.get('sell_md_amount', 0) or 0
        buy_sm_amt = row.get('buy_sm_amount', 0) or 0
        sell_sm_amt = row.get('sell_sm_amount', 0) or 0
        
        net_mf_vol = row.get('net_mf_vol', 0) or 0   # 主力净流入量(手)
        net_mf_amount = row.get('net_mf_amount', 0) or 0  # 主力净流入额(万元)
        
        elg_net = (buy_elg_amt or 0) - (sell_elg_amt or 0)
        lg_net = (buy_lg_amt or 0) - (sell_lg_amt or 0)
        md_net = (buy_md_amt or 0) - (sell_md_amt or 0)
        sm_net = (buy_sm_amt or 0) - (sell_sm_amt or 0)
        
        print(f'证券代码: {row.get("ts_code","")} 交易日期: {row.get("trade_date","")}')
        print(f'\n--- 按金额(万元) ---')
        print(f'超大单: 买入 {buy_elg_amt:.0f}万 / 卖出 {sell_elg_amt:.0f}万 → 净额 {elg_net:+.0f}万')
        print(f'大  单: 买入 {buy_lg_amt:.0f}万 / 卖出 {sell_lg_amt:.0f}万 → 净额 {lg_net:+.0f}万')
        print(f'中  单: 买入 {buy_md_amt:.0f}万 / 卖出 {sell_md_amt:.0f}万 → 净额 {md_net:+.0f}万')
        print(f'小  单: 买入 {buy_sm_amt:.0f}万 / 卖出 {sell_sm_amt:.0f}万 → 净额 {sm_net:+.0f}万')
        
        main_net = elg_net + lg_net
        total_net = main_net + md_net + sm_net
        
        print(f'\n主力合计(超大+大): {main_net:+.0f}万元')
        print(f'总净流入(含中+小): {total_net:+.0f}万元')
        
        direction = '↑ 主力资金净流入' if main_net > 0 else '↓ 主力资金净流出'
        print(f'\n结论: {direction} {abs(main_net):.0f}万元')
        
        if main_net != 0:
            if main_net > 0:
                ratio = main_net / (buy_elg_amt + buy_lg_amt + buy_md_amt + buy_sm_amt) * 100
                print(f'主力净买入额占总买入比例: {ratio:.1f}%')
            
        print(f'\n--- 按成交量(手) ---')
        print(f'主力净流入量: {net_mf_vol:+.0f}手')
        elg_vol_net = (buy_elg_vol or 0) - (sell_elg_vol or 0)
        lg_vol_net = (buy_lg_vol or 0) - (sell_lg_vol or 0)
        print(f'超大单净量: {elg_vol_net:+.0f}手  大单净量: {lg_vol_net:+.0f}手')
    else:
        print('Tushare moneyflow 今日暂无数据（收市后可能1-2小时延迟）')
except Exception as e:
    print(f'Tushare ts_moneyflow 失败: {e}')
