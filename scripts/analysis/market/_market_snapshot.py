#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""大盘指数 + 成交额 + 涨停统计 + 涨跌家数"""
import sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import date
from scripts.market_api import api

today = date.today()

# ============ 1. 九大指数 ============
print("=" * 50)
print(f"  {today} 大盘指数")
print("=" * 50)
try:
    snap = api.index_snapshot()
    idx_order = [
        '上证指数', '深证成指', '创业板指', '科创50',
        '上证50', '沪深300', '中小100', '中证1000', '国证2000'
    ]
    printed = set()
    for name in idx_order:
        for s in snap:
            if s.get('name') == name and name not in printed:
                printed.add(name)
                pct = s.get('change_pct', 'N/A')
                arrow = "+" if isinstance(pct, (int, float)) and pct > 0 else ""
                print(f"  {name:<8} {str(s.get('price','N/A')):>8}  {arrow}{str(pct)}%")
    # count
    up = sum(1 for s in snap if isinstance(s.get('change_pct'), (int, float)) and s['change_pct'] > 0)
    down = sum(1 for s in snap if isinstance(s.get('change_pct'), (int, float)) and s['change_pct'] < 0)
    print(f"\n  红盘: {up}/{len(snap)}  |  绿盘: {down}/{len(snap)}")
except Exception as e:
    print(f"  失败: {e}")

# ============ 2. 成交额 ============
print(f"\n{'=' * 50}")
print("  成交额")
print("=" * 50)
try:
    t = api.turnover()
    print(f"  上证: {t.get('sh', 'N/A')}亿 | 深证: {t.get('sz', 'N/A')}亿 | 合计: {t.get('total', 'N/A')}亿")
except Exception as e:
    print(f"  失败: {e}")

# ============ 3. 涨停/跌停池 ============
print(f"\n{'=' * 50}")
print("  涨停跌停统计")
print("=" * 50)
try:
    board = api.ths_limit_up_pool()
    zt = sum(1 for b in board if isinstance(b.get('limit_up'), (int, float)) and b['limit_up'] >= 9.8)
    print(f"  同花顺涨停池: {len(board)}只 (>=9.8%: {zt}只)")
except Exception as e:
    print(f"  同花顺涨停池失败: {e}")

# Tushare as cross-check
try:
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'tushare_config.json')
    with open(cfg_path) as f:
        cfg = json.load(f)
    import tushare as ts
    pro = ts.pro_api(cfg['token'])
    df = pro.limit_list_d(trade_date=today.strftime('%Y%m%d'))
    lu = len(df[df['limit'] == 'U'])
    ld = len(df[df['limit'] == 'D'])
    print(f"  Tushare验证: 涨停{lu}只 | 跌停{ld}只")
except Exception as e:
    print(f"  Tushare验证失败: {e}")

# ============ 4. 板块涨跌 TOP5 ============
print(f"\n{'=' * 50}")
print("  板块涨跌 TOP5")
print("=" * 50)
try:
    sectors = api.sectors()
    sorted_s = sorted(sectors, key=lambda x: x.get('change_pct', 0) or 0, reverse=True)
    print("  涨幅前5:")
    for s in sorted_s[:5]:
        print(f"    {s.get('name',''):<16s} {str(s.get('change_pct','N/A')):>8}%")
    print("  跌幅前5:")
    for s in sorted_s[-5:]:
        print(f"    {s.get('name',''):<16s} {str(s.get('change_pct','N/A')):>8}%")
except Exception as e:
    print(f"  失败: {e}")

# ============ 5. 昨日对比 ============
print(f"\n{'=' * 50}")
print("  昨日(7/28) vs 今日对比")
print("=" * 50)
try:
    for s in snap:
        name = s.get('name', '')
        if name in ['上证指数', '深证成指', '创业板指', '科创50']:
            price = s.get('price', 'N/A')
            prev = s.get('prev_close', s.get('yesterday_close', 'N/A'))
            if isinstance(price, (int, float)) and isinstance(prev, (int, float)):
                gap = price - prev
                print(f"  {name}: 昨收{prev:.2f} -> 今{price:.2f} ({gap:+.2f})")
except Exception as e:
    print(f"  失败: {e}")

print(f"\n{'=' * 50}")
print("  数据源: 腾讯(指数) + 同花顺(涨停池) + Tushare(验证)")
print("=" * 50)
