# -*- coding: utf-8 -*-
"""饮料制造 — 腾讯行情交叉验证 (同花顺 884109.TI +0.55%)"""
import requests, time, json, os
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
session.trust_env = False
retry = Retry(total=2, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)

# 饮料制造概念板块常见成分股
STOCKS = {
    # 白酒
    'sh600519': '贵州茅台', 'sz000858': '五粮液', 'sz000568': '泸州老窖',
    'sz002304': '洋河股份', 'sh600809': '山西汾酒', 'sz000596': '古井贡酒',
    'sh603369': '今世缘', 'sz000799': '酒鬼酒', 'sh600702': '舍得酒业',
    'sh600779': '水井坊', 'sh600559': '老白干酒', 'sh603589': '口子窖',
    'sh600197': '伊力特', 'sh603919': '金徽酒', 'sz000860': '顺鑫农业',
    'sh600059': '古越龙山', 'sz000995': '皇台酒业',
    # 啤酒
    'sz000729': '燕京啤酒', 'sh600600': '青岛啤酒', 'sh600132': '重庆啤酒',
    'sz002461': '珠江啤酒', 'sh603076': '乐惠国际',
    # 葡萄酒  
    'sz000869': '张裕A', 'sh600084': '中葡股份', 'sh600365': '通葡股份',
    'sh600543': '莫高股份',
    # 黄酒
    'sh600616': '金枫酒业',
    # 软饮料/其他
    'sz000848': '承德露露', 'sz002568': '百润股份', 'sh600189': '泉阳泉',
    'sh600300': '维维股份', 'sh600238': '海南椰岛', 'sh605388': '均瑶健康',
    'sz002946': '新乳业', 'sh600882': '妙可蓝多',
}

THS_PCT = 0.55  # 第一次成功拉取ths_daily的结果
TOTAL_MEMBER = 48  # ths_member返回48只

print('=' * 70)
print('饮料制造概念板块 (884109.TI) — 腾讯行情交叉验证')
print(f'Tushare ths_daily: +{THS_PCT}% (第一次成功拉取)')
print(f'Tushare ths_member: {TOTAL_MEMBER}只 (第一次成功拉取)')
print('=' * 70)

# 批量拉取腾讯行情
batch_size = 50
codes = list(STOCKS.keys())
qt_results = []

for i in range(0, len(codes), batch_size):
    batch = codes[i:i+batch_size]
    url = 'http://qt.gtimg.cn/q=' + ','.join(batch)
    try:
        resp = session.get(url, timeout=10)
        resp.encoding = 'gbk'
        for line in resp.text.strip().split('\n'):
            if '="' not in line: 
                continue
            code_name, data = line.split('="', 1)
            code = code_name.split('_')[-1]
            data = data.rstrip('";\n')
            fields = data.split('~')
            if len(fields) >= 33:
                name = fields[1]
                price = float(fields[3]) if fields[3] else 0
                pre_close = float(fields[4]) if fields[4] else 0
                change_pct = float(fields[32]) if fields[32] else 0
                qt_results.append({
                    'code': code, 'name': name, 'price': price,
                    'pre_close': pre_close, 'change_pct': change_pct
                })
    except Exception as e:
        print(f'  [WARN] batch failed: {e}')
    time.sleep(0.3)

# 排序并展示
qt_results.sort(key=lambda x: x['change_pct'], reverse=True)
up = sum(1 for r in qt_results if r['change_pct'] > 0)
down = sum(1 for r in qt_results if r['change_pct'] < 0)
flat_sum = sum(1 for r in qt_results if r['change_pct'] == 0)
avg = sum(r['change_pct'] for r in qt_results) / len(qt_results) if qt_results else 0

print(f'\n获取: {len(qt_results)}/{len(STOCKS)}只成分股行情 (期望48只)')
print(f'腾讯等权均价涨跌: {avg:+.2f}%')
print(f'同花顺板块指数涨跌: +{THS_PCT}% (ths_daily)')
print(f'差值: {avg - THS_PCT:+.2f}%')

# 方向一致性
dir_ok = (avg > 0 and THS_PCT > 0) or (avg < 0 and THS_PCT < 0)
print(f'方向一致性: {"[PASS] 同向" if dir_ok else "[FAIL] 反向"}')

print(f'\n涨跌统计: 涨{up} / 跌{down} / 平{flat_sum}')
print(f'上涨占比: {up/len(qt_results)*100:.1f}%')

# 分品类
print(f'\n分品类涨跌幅:')
categories = {
    '白酒': ['茅台','五粮液','泸州老窖','洋河','汾酒','古井贡酒','今世缘','酒鬼酒',
             '舍得','水井坊','老白干','口子窖','伊力特','金徽酒','顺鑫','古越龙山','皇台'],
    '啤酒': ['燕京','青岛','重庆','珠江','乐惠'],
    '葡萄酒': ['张裕','中葡','通葡','莫高'],
    '黄酒': ['金枫'],
    '饮料/其他': ['承德露露','百润','泉阳泉','维维','海南椰岛','均瑶','新乳业','妙可蓝多'],
}
for cat, kws in categories.items():
    cat_pcts = [r['change_pct'] for r in qt_results if any(kw in r['name'] for kw in kws)]
    if cat_pcts:
        cat_avg = sum(cat_pcts) / len(cat_pcts)
        print(f'  {cat}: {cat_avg:+.2f}% ({len(cat_pcts)}只)')

print(f'\n成分股涨跌详情:')
for i, r in enumerate(qt_results):
    flag = '++' if r['change_pct'] > 3 else ('+' if r['change_pct'] > 0 else ('0' if r['change_pct'] == 0 else '-'))
    print(f'  {i+1:2d}. [{flag}] {r["name"]:8s} {r["code"]:10s} {r["price"]:8.2f} {r["change_pct"]:+8.2f}%')

# 验证结论
print(f'\n{"=" * 70}')
print('验证结论')
print('=' * 70)
diff = abs(avg - THS_PCT)
coverage = len(qt_results) / TOTAL_MEMBER * 100

print(f'  成分股覆盖: {len(qt_results)}/{TOTAL_MEMBER} ({coverage:.1f}%)')
print(f'  腾讯等权均价: {avg:+.2f}%')
print(f'  同花顺板块指数(流通市值加权): +{THS_PCT}%')
print(f'  差值: {diff:.2f}%')

if diff < 0.5 and dir_ok:
    rating = 4
    note = '高度一致 — 双源同向，差值在0.5%以内'
    trust = '高'
elif diff < 1.5 and dir_ok:
    rating = 3
    note = '基本一致 — 方向一致，差值偏大(可能成分股覆盖不全)'
    trust = '中'
elif diff < 3.0:
    rating = 2
    note = '偏离明显 — 可能需要更多成分股数据'
    trust = '低'
else:
    rating = 1
    note = '严重偏离 — 数据源不可靠或成分股差异大'
    trust = '极低'

print(f'  综合评级: [{rating}/5] {note}')
print(f'  数据可信度: {trust}')
print()

# 额外分析
print('补充分析:')
print(f'  - 同花顺板块指数用流通市值加权，大票涨得多会拉高指数')
print(f'  - 腾讯等权均价用小票拉高上限参考')
print(f'  - 正常情况下: 腾讯等权(小票偏多) >= 同花顺(大票权重)')
if avg > THS_PCT:
    print(f'  - 当前: 腾讯{avg:+.2f}% > 同花顺+{THS_PCT}%  — 符合预期(小票涨幅>大票)')
else:
    print(f'  - 当前: 腾讯{avg:+.2f}% < 同花顺+{THS_PCT}%  — 大票领涨，小票拖后腿')

# 保存
result = {
    "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    "concept": "饮料制造 (884109.TI)",
    "ths_daily_pct": THS_PCT,
    "tencent_count": len(qt_results),
    "tencent_avg_pct": round(avg, 4),
    "diff": round(diff, 4),
    "direction_ok": dir_ok,
    "rating": f"{rating}/5",
    "trust": trust
}
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'drink_verify_2026-07-29.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f'结果已保存: {out}')
