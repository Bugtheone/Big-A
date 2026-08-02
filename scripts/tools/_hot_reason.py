#!/usr/bin/env python3
"""今日A股强势股 + 题材归因

数据源：同花顺热点接口（zx.10jqka.com.cn）+ 腾讯行情（qt.gtimg.cn）
用法：python _hot_reason.py [YYYY-MM-DD]   # 默认今天
"""

import sys
import requests
import pandas as pd
from collections import Counter, defaultdict

# 企业代理环境：绕过系统代理
s = requests.Session()
s.trust_env = False
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36'


def ths_hot_reason(date=None):
    """拉取同花顺当日热点股 + 题材归因（仅基础信息，不含价格）"""
    from datetime import date as _date
    if date is None:
        date = _date.today().strftime('%Y-%m-%d')

    url = (
        f'http://zx.10jqka.com.cn/event/api/getharden/'
        f'date/{date}/orderby/date/orderway/desc/charset/GBK/'
    )

    try:
        r = s.get(url, headers={'User-Agent': UA}, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"同花顺热点请求失败: {e}")

    try:
        data = r.json()
    except ValueError as e:
        raise RuntimeError(f"同花顺热点 JSON 解析失败: {e}")

    if data.get('errocode', 0) != 0:
        raise RuntimeError(f"同花顺热点错误: {data.get('errormsg', 'N/A')}")

    rows = data.get('data') or []
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # API 返回字段：id, name, code, reason, date, market
    df = df.rename(columns={
        'name': '名称', 'code': '代码', 'reason': '题材归因', 'market': '市场',
    })
    return df


def fetch_prices_single_batch(codes, s):
    """腾讯行情批量子集拉取：返回 {code: {name, price, chg_pct, turnover}} """
    url = 'http://qt.gtimg.cn/q=' + ','.join(codes)
    try:
        r = s.get(url, timeout=15)
        r.encoding = 'gbk'
    except requests.RequestException:
        return {}

    import re
    result = {}
    for m in re.finditer(r'v_(\w+?)="([^"]*)"', r.text):
        code = m.group(1)
        f = m.group(2).split('~')
        if len(f) < 40:
            continue
        try:
            result[code] = {
                'name': f[1],
                'price': float(f[3]) if f[3] else 0,
                'chg_pct': float(f[32]) if f[32] else 0,
                'turnover': float(f[38]) if f[38] else 0,
            }
        except (ValueError, IndexError):
            continue
    return result


def main(date_str=None):
    # ── 1. 拉取热点股 ──
    try:
        df = ths_hot_reason(date_str)
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        return

    if df.empty:
        print("[WARN] 当日无热点数据")
        return

    display_date = date_str or pd.Timestamp.today().strftime('%Y-%m-%d')
    print(f"\n{'='*60}")
    print(f"  {display_date}  A股强势股题材归因")
    print(f"{'='*60}")
    print(f"  热点个股: {len(df)} 只\n")

    # ── 2. 题材热度统计 ──
    all_tags = []
    for r in df['题材归因'].dropna():
        tags = [t.strip() for t in str(r).split('+') if t.strip()]
        all_tags.extend(tags)
    cnt = Counter(all_tags)

    print(f"  {'题材热度 TOP 15':-^40}")
    for tag, n in cnt.most_common(15):
        bar = '#' * min(n // 2, 30)
        print(f'  {tag:<14} {n:>3}只 {bar}')

    # ── 3. 题材 → 个股分组 ──
    topic_stocks = defaultdict(list)
    for _, r in df.iterrows():
        reason = str(r.get('题材归因', ''))
        if not reason or reason == 'nan':
            continue
        for tag in reason.split('+'):
            tag = tag.strip()
            if tag:
                topic_stocks[tag].append({
                    'code': r['代码'],
                    'name': r['名称'],
                    'market': r.get('市场', ''),
                })

    # ── 4. 拉取行情数据（代码需要加交易所前缀） ──
    def add_prefix(code):
        """THS代码 → 腾讯行情代码（sh/sz 前缀）"""
        code = str(code)
        if code.startswith(('60', '68')):
            return f"sh{code}"
        return f"sz{code}"

    top_topics = [t for t, _ in cnt.most_common(15)]
    hot_codes_map = {}  # raw_code → tencent_code
    for topic in top_topics:
        for item in topic_stocks.get(topic, []):
            raw = item['code']
            if raw not in hot_codes_map:
                hot_codes_map[raw] = add_prefix(raw)

    tencent_codes = list(hot_codes_map.values())
    prices_raw = {}
    code_list = tencent_codes
    batch_size = 80
    print(f"\n  [拉取 {len(code_list)} 只个股行情中...]")
    for i in range(0, len(code_list), batch_size):
        batch = code_list[i:i + batch_size]
        prices_raw.update(fetch_prices_single_batch(batch, s))

    # 腾讯代码 → 原始代码 的反向映射
    tcode_to_raw = {v: k for k, v in hot_codes_map.items()}
    prices = {tcode_to_raw.get(k, k): v for k, v in prices_raw.items()}

    # ── 5. 按题材展示个股（带行情） ──
    print(f"\n  {'题材领涨个股':-^40}")
    for topic in top_topics:
        stocks = topic_stocks.get(topic, [])
        # 过滤有行情的个股，按涨幅排序
        ranked = []
        for st in stocks:
            p = prices.get(st['code'])
            if p and p['chg_pct'] != 0:
                ranked.append((p['chg_pct'], st, p))
        ranked.sort(key=lambda x: x[0], reverse=True)

        if not ranked:
            continue

        print(f"\n  [{topic}]  ({sum(1 for _, _, p in ranked if p['chg_pct'] > 0)}/{len(ranked)} 上涨)")
        for i, (chg, st, p) in enumerate(ranked[:8]):  # 每题材最多 8 只
            flag = '+' if chg > 0 else ''
            print(f"    {st['code']} {st['name']:<6} {flag}{chg:>6.2f}%  "
                  f"换手{p['turnover']:.1f}%")


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(date_arg)
