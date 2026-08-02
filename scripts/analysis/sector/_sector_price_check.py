# -*- coding: utf-8 -*-
"""板块价格检查 (修复2026-07-31: --raw不再支持, 使用_helper解析MD表格)"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from scripts.utils._westock_helper import sector_industry_ranking

data = sector_industry_ranking()
if not data:
    print("parse failed (no sector data)")
    exit(1)

# 找消费板块: 白酒、银行、食品、汽车、家电等
consumer_kw = ['白酒','银行','食品','饮料','乳品','汽车','厨卫','乘用','电器','保险','煤炭','电力']
tech_kw = ['半导体','通信','元件','IT','软件','光伏','军工','自动化','芯片','AI','机器']

print("=== 行业板块周涨幅排名(消费vs科技) ===\n")
# 按5日涨跌排序 (Westock sector字段: changePct5d)
by_week = sorted(data, key=lambda x: abs(float(x.get('changePct5d', '0') or 0)), reverse=True)
for item in by_week[:30]:
    name = item.get('name','?')
    dp = item.get('changePct','?')    # 当日涨跌幅
    wp = item.get('changePct5d','?')  # 5日(周)涨跌幅
    mp = item.get('changePct20d','?') # 20日(月)涨跌幅
    tag = ''
    if any(k in name for k in consumer_kw):
        tag = ' << 消费'
    elif any(k in name for k in tech_kw):
        tag = ' << 科技'
    if tag:
        print(f'{name:<14s} 日:{dp:>8s}  5日:{wp:>8s}  20日:{mp:>8s}{tag}')
