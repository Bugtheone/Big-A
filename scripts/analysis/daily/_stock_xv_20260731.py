# -*- coding: utf-8 -*-
"""个股层交叉验证 — 问财选出股 vs 腾讯实时行情 (L3数据源验证)"""
import sys
import io

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, r'c:\Users\PC-One\Desktop\整理后\股票相关\零散临时\1112345')
from scripts.market_api import api

# 问财选出的8只 + 人气榜重点股
CODES = {
    "002050": "三花智控", "002384": "东山精密", "300418": "昆仑万维",
    "002230": "科大讯飞", "300058": "蓝色光标", "300394": "天孚通信",
    "002281": "光迅科技", "300857": "协创数据",
    "688825": "长鑫科技", "001309": "德明利", "603986": "兆易创新",
    "300308": "中际旭创", "000636": "风华高科", "600667": "太极实业",
}

print("个股层交叉验证 — 问财/人气榜 vs 腾讯实时行情 (2026-07-31 盘后)")
print("=" * 80)
try:
    rt = api.stock_realtime(list(CODES.keys()))
    print(f"{'代码':<8}{'名称':<8}{'腾讯现价':<10}{'涨跌%':<8}  问财/人气榜侧")
    print("-" * 80)
    for code, name in CODES.items():
        d = rt.get(code) or {}
        pct = d.get("change_pct")
        print(f"{code:<8}{name:<8}{str(d.get('price')):<10}"
              f"{str(pct) if pct is not None else '—':<8}  ")
    print("-" * 80)
    print(f"共验证 {len(rt)} 只有行情返回 (应=13)")
except Exception as e:
    print(f"[ERROR] stock_realtime: {e}")

# 补充: 问财查询的具体字段结构
print("\n问财返回字段结构探查:")
try:
    iw = api.iwencai_query("主力资金净流入大于5亿且今日涨幅大于3%的股票", limit=2)
    if iw and iw.get("success"):
        lst = iw.get("items") or iw.get("data") or []
        if lst:
            print(f"  字段: {list(lst[0].keys())}")
            import json
            print(f"  样例: {json.dumps(lst[0], ensure_ascii=False)[:300]}")
except Exception as e:
    print(f"  [ERROR] {e}")
print("DONE")
