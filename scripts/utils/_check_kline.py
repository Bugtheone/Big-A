# -*- coding: utf-8 -*-
"""板块K线检查 (修复2026-07-31: --raw不再支持, 用_helper解析MD表格)"""
import sys, os, io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from scripts.utils._westock_helper import kline

sectors = {
    "白酒II": "pt01801125", "股份制银行II": "pt01801783",
    "乘用车": "pt01801095", "国有大型银行II": "pt01801782",
    "半导体": "pt01801081", "通信设备": "pt01801102"
}

for name, code in sectors.items():
    # 获取大量K线数据 (Westock kline 默认返回全量)
    klines = kline(code, limit=60)  # 请求60根日K线
    if not klines:
        print(f"{name}: no data")
        continue

    print(f"\n{name} ({code}): {len(klines)} K lines, last 15:")
    for k in klines[-15:]:
        d = k.get('date','')
        o = k.get('open','?')
        c = k.get('last','?')       # Westock字段名: last (=close)
        amt = k.get('amount','?')   # 成交额
        print(f"  {d} O={o} C={c} 成交额={amt}")
