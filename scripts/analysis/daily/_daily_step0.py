#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""7/29 盘后日报 Step0：多源数据拉取"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.market_api import api

results = {}

# ========== 1. 九指数快照（腾讯源） ==========
print("=" * 60)
print("九指数快照")
print("=" * 60)
try:
    snap = api.index_snapshot()
    indexes = {}
    for s in snap:
        name = s.get('name', '')
        price = s.get('price', 'N/A')
        chg_pct = s.get('change_pct', 'N/A')
        chg_val = s.get('change', 'N/A')
        idx_map = {
            '上证指数': '000001.SH', '深证成指': '399001.SZ', '创业板指': '399006.SZ',
            '科创50': '000688.SH', '上证50': '000016.SH', '沪深300': '000300.SH',
            '中证500': '000905.SH', '中证1000': '000852.SH', '中证2000': '932000.CSI'
        }
        code = idx_map.get(name, name)
        indexes[code] = {'name': name, 'price': price, 'chg_pct': chg_pct, 'chg_val': chg_val}
        print(f"  {name}: {price} ({chg_pct}%)")
    results['indexes'] = indexes
except Exception as e:
    print(f"  失败: {e}")

# ========== 2. 成交额 ==========
print("\n" + "=" * 60)
print("成交额")
print("=" * 60)
try:
    t = api.turnover()
    print(f"  上证:{t.get('sh','N/A')}亿 深证:{t.get('sz','N/A')}亿 合计:{t.get('total','N/A')}亿")
    results['turnover'] = t
except Exception as e:
    print(f"  失败: {e}")

# ========== 3. 板块涨跌 ==========
print("\n" + "=" * 60)
print("板块涨跌 TOP5")
print("=" * 60)
try:
    sectors = api.sectors()
    sorted_all = sorted(sectors, key=lambda x: x.get('change_pct', 0) or 0, reverse=True)
    up5 = sorted_all[:8]
    down5 = sorted_all[-8:]
    print("  涨幅TOP8:")
    for s in up5:
        print(f"    {s.get('name','')}: {s.get('change_pct','N/A')}%")
    print("  跌幅TOP8:")
    for s in reversed(down5):
        print(f"    {s.get('name','')}: {s.get('change_pct','N/A')}%")
    results['sectors'] = {'up': [{'name': s.get('name'), 'pct': s.get('change_pct')} for s in up5],
                         'down': [{'name': s.get('name'), 'pct': s.get('change_pct')} for s in down5]}
except Exception as e:
    print(f"  失败: {e}")

# ========== 4. 涨停池 ==========
print("\n" + "=" * 60)
print("涨停池")
print("=" * 60)
try:
    zt = api.zt_pool()
    print(f"  涨停数量: {len(zt) if zt else 0}")
    if zt:
        zt_sorted = sorted(zt, key=lambda x: x.get('high_days', 0) or 0, reverse=True)
        for z in zt_sorted[:5]:
            print(f"  {z.get('name','')}: {z.get('close','N/A')} 连板:{z.get('high_days','N/A')}")
    results['zt_count'] = len(zt) if zt else 0
    results['zt_top'] = [{'name': z.get('name'), 'high_days': z.get('high_days')} for z in (zt_sorted[:5] if zt else [])]
except Exception as e:
    print(f"  失败: {e}")

# ========== 5. 跌停池 ==========
print("\n" + "=" * 60)
print("跌停池")
print("=" * 60)
try:
    zb = api.zb_pool()
    print(f"  跌停数量: {len(zb) if zb else 0}")
    results['zb_count'] = len(zb) if zb else 0
except Exception as e:
    print(f"  失败: {e}")

# ========== 6. 板块概览 ==========
print("\n" + "=" * 60)
print("板块概览")
print("=" * 60)
try:
    bs = api.board_summary()
    print(f"  领涨板块: {bs.get('up', [])[:5]}")
    print(f"  领跌板块: {bs.get('down', [])[:5]}")
    results['board_summary'] = bs
except Exception as e:
    print(f"  失败: {e}")

# ========== 7. 北向资金 ==========
print("\n" + "=" * 60)
print("北向资金（同花顺hexin）")
print("=" * 60)
try:
    nf = api.north_flow(n_days=5)
    for d in (nf if isinstance(nf, list) else [nf])[-5:]:
        print(f"  {d}")
    results['north_flow'] = nf
except Exception as e:
    print(f"  失败: {e}")

# 保存
with open("data/step0_data_0729.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print("\n保存到 data/step0_data_0729.json")

# ========== 10. 概念板块补充 (Tushare ths_daily) — 2026-07-29 新增 ==========
print("\n" + "=" * 60)
print("概念板块补充 (消费类)")
print("=" * 60)

CONCEPT_NAME_MAP = {
    "885462.TI": "乳业", "884127.TI": "乳品",
    "884031.TI": "食品加工", "884109.TI": "饮料制造",
    "884009.TI": "白酒", "884011.TI": "啤酒",
    "884073.TI": "调味品", "884088.TI": "预制菜",
    "884103.TI": "新零售", "885461.TI": "猪肉",
    "884059.TI": "医美", "884015.TI": "CRO",
    "885678.TI": "免税", "884079.TI": "社区团购",
}

concept_data = []
try:
    from scripts.tushare_api import get_pro
    pro = get_pro()
    codes = list(CONCEPT_NAME_MAP.keys())
    df = pro.ths_daily(ts_code=",".join(codes),
                       start_date="20260729", end_date="20260729")
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            code = row["ts_code"]
            name = CONCEPT_NAME_MAP.get(code, code)
            close = row.get("close", 0)
            pre_close = row.get("pre_close", 0)
            if close and pre_close and pre_close != 0:
                pct = round((close / pre_close - 1) * 100, 2)
                concept_data.append({"name": name, "pct": pct})
        
        # 排序打印
        concept_sorted = sorted(concept_data, key=lambda x: x["pct"], reverse=True)
        print(f"  共 {len(concept_sorted)} 个消费类概念板块:")
        for c in concept_sorted:
            mark = " ★" if abs(c["pct"]) >= 5 else ""
            print(f"    {c['name']:<8s} {c['pct']:+.2f}%{mark}")
    else:
        print("  Tushare ths_daily 返回空")
except ImportError:
    print("  [SKIP] tushare 未安装")
except Exception as e:
    print(f"  [WARN] {e}")

if concept_data:
    results['concept_sectors'] = concept_data
    # 补充保存
    with open("data/step0_data_0729.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
