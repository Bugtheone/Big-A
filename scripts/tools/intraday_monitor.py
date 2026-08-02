#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
盘中监控脚本 v1.0
===============
功能：实时拉取九大指数、黄白线、量能预估、涨停跌停、板块资金，输出大盘状态快照。
调用方式：
  1. 手动：python scripts/tools/intraday_monitor.py
  2. AI Agent触发：用户说"跑盘中监控"
  3. 自动化定时：CodeBuddy automation 每30分钟一次（9:30-11:30, 13:00-15:00）

输出：
  - 控制台实时面板
  - data/intraday_latest.json（最近一次快照）
  - data/intraday_log_YYYYMMDD.jsonl（追加日志）
"""

import sys, os, json, time
from datetime import datetime, date, timedelta
from pathlib import Path

# Windows GBK 终端兼容
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 项目根
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR / 'scripts'))

from market_api import api

# ─────────────────── 盘中阶段判断 ───────────────────
def trading_phase() -> dict:
    """
    返回当前所处的交易阶段。

    非交易日 → phase='closed'
    盘前 9:00-9:25 → 'pre_market'
    开盘前30分钟 9:30-10:00 → 'opening'
    盘中 10:00-11:30, 13:00-14:30 → 'mid_session'
    尾盘 14:30-15:00 → 'closing'
    盘后 15:00-次日9:00 → 'after_hours'
    """
    now = datetime.now()
    weekday = now.weekday()  # 0=Mon ... 6=Sun
    is_weekend = weekday >= 5

    if is_weekend or now.hour < 9:
        return {'phase': 'closed', 'label': '休市/盘前', 'action': 'skip'}

    t = now.hour * 100 + now.minute

    if 900 <= t < 925:
        return {'phase': 'pre_market', 'label': '集合竞价', 'action': 'check'}
    elif 925 <= t < 930:
        return {'phase': 'opening', 'label': '即将开盘', 'action': 'check'}
    elif 930 <= t < 1000:
        return {'phase': 'opening', 'label': '开盘30分钟', 'action': 'check'}
    elif 1000 <= t < 1130:
        return {'phase': 'mid_session', 'label': '上午盘中', 'action': 'check'}
    elif 1130 <= t < 1300:
        return {'phase': 'lunch', 'label': '午间休市', 'action': 'skip'}
    elif 1300 <= t < 1430:
        return {'phase': 'mid_session', 'label': '下午盘中', 'action': 'check'}
    elif 1430 <= t < 1500:
        return {'phase': 'closing', 'label': '尾盘30分钟', 'action': 'check'}
    else:
        return {'phase': 'after_hours', 'label': '已收盘', 'action': 'skip'}


# ─────────────────── 数据采集 ───────────────────
def collect_snapshot() -> dict:
    """一次性采集所有盘中数据，返回统一 dict。"""
    result = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'phase': trading_phase(),
        'indices': {},
        'volume': {},
        'sentiment': {},
        'sectors': {},
        'warnings': [],
        'signals': [],
    }

    # ── 1. 九大指数实时快照 ──
    try:
        snap = api.index_snapshot()
        # snap 预期格式: {code: {name, price, change_pct, ...}} 或 list of dict
        if isinstance(snap, list):
            for item in snap:
                code = item.get('code', '')
                result['indices'][code] = {
                    'name': item.get('name', ''),
                    'price': item.get('price', 0),
                    'change_pct': item.get('change_pct', 0),
                    'volume': item.get('volume', 0),
                }
        elif isinstance(snap, dict):
            result['indices'] = snap
    except Exception as e:
        result['warnings'].append(f'指数快照失败: {e}')

    # 指数涨跌统计
    up_count = sum(1 for v in result['indices'].values()
                   if isinstance(v, dict) and v.get('change_pct', 0) > 0)
    down_count = sum(1 for v in result['indices'].values()
                     if isinstance(v, dict) and v.get('change_pct', 0) < 0)
    total = len(result['indices'])
    result['breadth'] = {'up': up_count, 'down': down_count, 'total': total}

    if total > 0 and up_count == 0:
        result['warnings'].append('⚠️ 九指数全跌！')

    # ── 2. 黄白线检查（通过腾讯快照获取上证指数和上证领先） ──
    try:
        from market_api import tencent_quote
        # 上证指数 sh000001 + 上证领先 sh000002
        sh_data = tencent_quote(['sh000001', 'sh000002'])
        if isinstance(sh_data, dict) and 'sh000001' in sh_data:
            idx_price = float(sh_data['sh000001'].get('price', 0))
            lead_price = float(sh_data['sh000002'].get('price', 0))
            if idx_price and lead_price:
                diff_pct = (lead_price - idx_price) / idx_price * 100
                result['yellow_white'] = {
                    'idx_price': idx_price,
                    'lead_price': lead_price,
                    'diff_pct': round(diff_pct, 4),
                }
                if abs(diff_pct) > 1.0:
                    result['warnings'].append(
                        f'⚠️ 黄白线偏离 {diff_pct:+.2f}%：'
                        f'{"黄线在上≈小盘强于大盘" if diff_pct > 0 else "白线在上≈权重护盘"}'
                    )
    except Exception as e:
        result['yellow_white'] = {'error': str(e)}

    # ── 3. 量能预估 ──
    try:
        turnover = api.turnover()
        if isinstance(turnover, dict):
            total_yi = turnover.get('total_yi', 0)
            result['volume'] = {
                'current_yi': total_yi,
                'sh_yi': turnover.get('sh_yi', 0),
                'sz_yi': turnover.get('sz_yi', 0),
            }

            # 与最近几日收盘量对比（从数据文件读取）
            vol_file = BASE_DIR / 'data' / '30d_performance.json'
            # 简化：用 MEMORY.md 中记录的成交额对比
            prev_volume = 20257  # 7/28 成交额
            if total_yi > 0:
                ratio = total_yi / prev_volume if prev_volume else 1
                phase = result['phase']['phase']
                if phase == 'opening':
                    # 开盘30分钟预估全天量 ≈ 当前量 × 开盘倍率（通常前30分钟占全天15-20%）
                    estimated_full = total_yi * 5  # 粗略估算
                    result['volume']['estimated_full'] = round(estimated_full, 0)
                    result['volume']['vs_prev'] = round(estimated_full / prev_volume * 100, 1)

                    if estimated_full < prev_volume * 0.7:
                        result['signals'].append('🔻 预估全天缩量，不追高')
                    elif estimated_full > prev_volume * 1.3:
                        result['signals'].append('🔺 预估放量，关注方向')
    except Exception as e:
        result['volume'] = {'error': str(e)}

    # ── 4. 涨停/跌停情绪 ──
    try:
        zt = api.zt_pool()
        dt = api.dt_pool()
        zt_count = len(zt) if isinstance(zt, list) else (len(zt.get('data', [])) if isinstance(zt, dict) else 0)
        dt_count = len(dt) if isinstance(dt, list) else (len(dt.get('data', [])) if isinstance(dt, dict) else 0)
        result['sentiment'] = {
            'zt_count': zt_count,
            'dt_count': dt_count,
        }

        if dt_count >= 10:
            result['warnings'].append(f'⚠️ 跌停{dt_count}只（阈值10），情绪冰点')
        if zt_count >= 100:
            result['warnings'].append(f'⚠️ 涨停{zt_count}只（阈值100），情绪可能过热')
    except Exception as e:
        result['sentiment'] = {'error': str(e)}

    # ── 5. 板块资金流向 ──
    try:
        sectors = api.sectors()
        if isinstance(sectors, dict):
            # 提取涨幅前5和后5
            sector_list = []
            for k, v in sectors.items():
                if isinstance(v, dict):
                    sector_list.append({
                        'name': v.get('name', k),
                        'change_pct': v.get('change_pct', 0),
                    })
            sector_list.sort(key=lambda x: x['change_pct'], reverse=True)
            result['sectors'] = {
                'top5': sector_list[:5],
                'bottom5': sector_list[-5:],
                'up_count': sum(1 for s in sector_list if s['change_pct'] > 0),
                'total': len(sector_list),
            }
    except Exception as e:
        result['sectors'] = {'error': str(e)}

    # ── 6. 北向资金（实时） ──
    try:
        north = api.north_flow()
        if isinstance(north, dict):
            result['northbound'] = {
                'net_flow_yi': north.get('net_flow', north.get('net_yi', 0)),
            }
        elif isinstance(north, list) and north:
            result['northbound'] = {'data': north[:3]}
    except Exception as e:
        result['northbound'] = {'error': str(e)}

    return result


# ─────────────────── 面板输出 ───────────────────
def print_panel(data: dict):
    """控制台面板输出"""
    phase = data['phase']
    ts = data['timestamp']

    print()
    print('=' * 72)
    print(f'  盘中监控面板  |  {ts}  |  {phase["label"]}')
    print('=' * 72)

    if phase['phase'] == 'closed':
        print('  ⏸️  当前处于休市/周末状态，无需监控。')
        return

    # ── 指数概览 ──
    indices = data.get('indices', {})
    breadth = data.get('breadth', {})
    print(f'  📊 指数 {breadth.get("up", 0)}涨{breadth.get("down", 0)}跌')
    print(f'  {"指数":<10} {"点位":>10} {"涨跌幅":>8}')
    print(f'  {"-"*28}')
    key_indices = ['sh000001', 'sz399001', 'sz399006', 'sh000688',
                   'sh000016', 'sh000300', 'sh000852', 'sh000905']
    for code in key_indices:
        if code in indices:
            v = indices[code]
            if isinstance(v, dict):
                pct = v.get('change_pct', v.get('pct_chg', 0))
                price = v.get('price', v.get('close', 0))
                name = v.get('name', code)
                sign = '+' if pct > 0 else ''
                print(f'  {name:<10} {price:>10.2f} {sign}{pct:>7.2f}%')
    print()

    # ── 黄白线 ──
    yw = data.get('yellow_white', {})
    if yw and 'diff_pct' in yw:
        diff = yw['diff_pct']
        flag = '🟡黄线在上(小盘强)' if diff > 0.05 else ('⚪白线在上(权重护盘)' if diff < -0.05 else '🟢粘合')
        print(f'  📏 黄白线偏离: {diff:+.2f}% {flag}')
        if abs(diff) > 1.0:
            print(f'     ⚠️  鳄鱼口警告：不碰题材股！')
        print()

    # ── 量能 ──
    vol = data.get('volume', {})
    if vol and vol.get('current_yi'):
        cur = vol.get('current_yi', 0)
        est = vol.get('estimated_full', 0)
        ratio = vol.get('vs_prev', 0)
        print(f'  💰 当前成交额: {cur:.0f}亿')
        if est:
            print(f'     预估全天量: {est:.0f}亿 (vs昨日 {ratio}%)')
            if ratio < 70:
                print(f'     🔻 缩量明显 → 不追高，10:30仍缩全天不开新仓')
        print()

    # ── 涨停跌停 ──
    sent = data.get('sentiment', {})
    if sent:
        zt = sent.get('zt_count', '?')
        dt = sent.get('dt_count', '?')
        flag = ''
        if isinstance(dt, int) and dt >= 10:
            flag = ' ⚠️冰点'
        elif isinstance(zt, int) and zt >= 100:
            flag = ' ⚠️过热'
        print(f'  🔥 涨停: {zt}  |  ❄️ 跌停: {dt}{flag}')
        print()

    # ── 信号汇总 ──
    warnings = data.get('warnings', [])
    signals = data.get('signals', [])

    if warnings:
        print(f'  ┌─ ⚠️  警告 ──────────────────────')
        for w in warnings:
            print(f'  │ {w}')
        print(f'  └{"─"*34}')

    if signals:
        print(f'  ┌─ 💡 信号 ──────────────────────')
        for s in signals:
            print(f'  │ {s}')
        print(f'  └{"─"*34}')

    print()
    print(f'  📋 当前仓位建议：参考昨日盘后报告 data/daily_report_*.md')
    print('=' * 72)


# ─────────────────── 保存 ───────────────────
def save_results(data: dict):
    """保存快照 + 追加日志"""
    data_dir = BASE_DIR / 'data'
    data_dir.mkdir(exist_ok=True)

    ts = datetime.now()
    # 最新快照（覆盖）
    snap_file = data_dir / 'intraday_latest.json'
    with open(snap_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 追加日志
    log_file = data_dir / f'intraday_log_{ts.strftime("%Y%m%d")}.jsonl'
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + '\n')


# ─────────────────── 主入口 ───────────────────
def main():
    phase = trading_phase()

    if phase['action'] == 'skip':
        print_panel({'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                      'phase': phase})
        print(f'\n✅ 盘中监控结束（{phase["label"]}，无需操作）')
        return

    print('🔄 正在采集盘中数据...')
    data = collect_snapshot()
    print_panel(data)
    save_results(data)
    print(f'💾 快照已保存: data/intraday_latest.json')


if __name__ == '__main__':
    main()
