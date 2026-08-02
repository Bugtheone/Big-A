# -*- coding: utf-8 -*-
"""AI Agent 全数据源自检脚本 — 验证 7 大源可用性"""
import sys, os, subprocess, json, time
sys.path.insert(0, r'c:\Users\PC-One\Desktop\整理后\股票相关\零散临时\1112345')
from scripts.market_api import api

results = {}
start = time.time()

# 1. 腾讯快照 — 返回 list of dict
try:
    r = api.index_snapshot()
    ok = isinstance(r, list) and len(r) >= 4
    if ok and len(r) > 0:
        first = r[0]
        results['1_tencent_snapshot'] = f'OK ({len(r)} indices, sh={first.get("price","?")})'
    else:
        results['1_tencent_snapshot'] = f'FAIL: type={type(r).__name__}'
except Exception as e:
    results['1_tencent_snapshot'] = f'FAIL: {e}'

# 2. 腾讯K线
try:
    r = api.kline('上证指数', 3)
    results['2_tencent_kline'] = f'OK ({len(r) if r else 0} bars)' if r else 'FAIL: empty'
except Exception as e:
    results['2_tencent_kline'] = f'FAIL: {e}'

# 3. Tushare.pro K线 — 返回 {summary, date_range, data}
try:
    r = api.ts_daily_kline(ts_code='000001.SZ', n_days=3)
    summary = r.get('summary', {}) if isinstance(r, dict) else {}
    ok = summary.get('count', 0) > 0
    results['3_tushare_kline'] = f'OK ({summary.get("count","?")} bars, last_close={summary.get("last_close","?")})' if ok else f'FAIL: summary={summary}'
except Exception as e:
    results['3_tushare_kline'] = f'FAIL: {e}'

# 4. Westock CLI (修复: 去掉 --raw, 用 _westock_helper)
try:
    from scripts.utils._westock_helper import kline
    rows = kline("sh000001", limit=3)
    ok = len(rows) > 0 and 'last' in rows[0]
    results['4_westock_kline'] = f'OK ({len(rows)} bars, last={rows[0].get("last","?")})' if ok else 'FAIL: empty'
except Exception as e:
    results['4_westock_kline'] = f'FAIL: {e}'

# 5. 同花顺热榜
try:
    r = api.hot_rank(5)
    ok = isinstance(r, list) and len(r) > 0
    top_name = r[0].get('name','?') if ok else '?'
    results['5_ths_hot'] = f'OK ({len(r)} entries, top={top_name})' if ok else f'FAIL: type={type(r).__name__} len={len(r) if isinstance(r,list) else "?"}'
except Exception as e:
    results['5_ths_hot'] = f'FAIL: {e}'

# 6. 北向资金
try:
    r = api.north_flow(3)
    records = r.get('records', []) if isinstance(r, dict) else []
    ok = len(records) > 0
    latest = records[0] if records else {}
    results['6_north_flow'] = f'OK ({len(records)}d, latest_net={latest.get("net_flow_yi","?")}yi)' if ok else f'FAIL: {r}'
except Exception as e:
    results['6_north_flow'] = f'FAIL: {e}'

# 7. 问财 SkillHub
try:
    r = api.iwencai_query('市盈率小于30倍且ROE大于10%的银行股', limit=5)
    ok = r.get('success') if isinstance(r, dict) else False
    count = r.get('code_count', '?') if isinstance(r, dict) else '?'
    results['7_iwencai'] = f'OK ({count} hits)' if ok else f'WARN: {r.get("message","empty") if isinstance(r,dict) else r}'
except Exception as e:
    results['7_iwencai'] = f'FAIL: {e}'

# 8. 腾讯板块排名
try:
    r = api.sectors(5)
    ok = isinstance(r, list) and len(r) > 0
    top_name = r[0].get('name','?') if ok else '?'
    results['8_tencent_sectors'] = f'OK ({len(r) if ok else 0} sectors, top={top_name})' if ok else 'FAIL: empty'
except Exception as e:
    results['8_tencent_sectors'] = f'FAIL: {e}'

elapsed = time.time() - start
pass_count = sum(1 for v in results.values() if v.startswith('OK'))
warn_count = sum(1 for v in results.values() if v.startswith('WARN'))
fail_count = sum(1 for v in results.values() if v.startswith('FAIL'))

print('=== AI Agent Self-Check (V3.6.0) ===')
for k, v in results.items():
    flag = 'PASS' if v.startswith('OK') else ('WARN' if v.startswith('WARN') else 'FAIL')
    print(f'  [{flag}] {k}: {v}')
print(f'\nPASS: {pass_count}/{len(results)} WARN: {warn_count} FAIL: {fail_count} | Time: {elapsed:.1f}s')
