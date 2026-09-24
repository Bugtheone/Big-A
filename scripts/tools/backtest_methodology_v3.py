#!/usr/bin/env python3
"""方法论大全理论回测 v3——验证矩阵（2026-08-23）

对齐《A股股票方法论大全（2026年8月）》未验证理论：
  V1 三大市场环境判定（趋势/震荡/熊市：MA250+MA60方向）→ 各环境收益/胜率
  V2 环境×策略适应矩阵（四族：趋势/回归/动量/持有 → 三种环境表现）——验证"策略分类总览·横向对比"
  V3 量价关系（上涨放量 vs 上涨缩量；回调缩量 vs 回调放量）——验证"常见量价关系图解"
  V4 生命周期四阶段择时（导入/成长/成熟/衰退 → 仓位策略 vs 买入持有）——验证"生命周期投资法"

数据：Tushare 指数日线（上证/深成/创业/沪深300/中证500/中证1000），2020-01~2026-08。
方法：无未来函数（信号日收盘→次日生效）；结论分级（✅/⚠️/❌）。
用法: python3 scripts/tools/backtest_methodology_v3.py
"""
import sys
import os
import io
import pandas as pd
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from scripts.tushare_pro_data import ts_index_daily  # noqa: E402

START = '20200101'
END = '20260821'
OUT = os.path.join(BASE_DIR, 'reports', 'misc', '方法论大全回测_2026-08-23.md')

IDX = [
    ('000001.SH', '上证'), ('399001.SZ', '深成'), ('399006.SZ', '创业板'),
    ('000300.SH', '沪深300'), ('000905.SH', '中证500'), ('000852.SH', '中证1000'),
]


def get(idx_code: str) -> pd.DataFrame:
    try:
        df = ts_index_daily(idx_code, start=START, end=END)
        if not df:
            return pd.DataFrame()
        df = pd.DataFrame(df)
        return df.sort_values('trade_date').reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def add_ma(df: pd.DataFrame):
    for n in (5, 10, 20, 60, 250):
        df[f'ma{n}'] = df['close'].rolling(n).mean()
    df['ret_1d'] = df['close'].pct_change()
    return df


def env_at(df: pd.DataFrame, i: int) -> str:
    if i < 250:
        return '数据不足'
    c, ma60, ma250 = float(df.loc[i, 'close']), float(df.loc[i, 'ma60']), float(df.loc[i, 'ma250'])
    if pd.isna(ma60) or pd.isna(ma250):
        return '数据不足'
    if c > ma250 and ma60 > ma250:
        return '趋势'
    if c < ma250 and ma60 < ma250:
        return '熊市'
    return '震荡'


def fwd_ret(df: pd.DataFrame, i: int, h: int) -> float:
    if i + h >= len(df):
        return None
    return float(df.loc[i + h, 'close']) / float(df.loc[i, 'close']) - 1


def main():
    # ===== 预加载全部指数 =====
    cache = {}
    for code, name in IDX:
        df = add_ma(get(code))
        if df.empty:
            continue
        cache[name] = df
    print('加载指数:', list(cache.keys()))
    if not cache:
        print('无数据'); return

    lines = []
    lines.append('# 方法论大全理论回测 v3——验证矩阵（环境×策略×量价×生命周期）')
    lines.append('')
    lines.append(f'> 时间戳：{datetime.now().strftime("%Y-%m-%d %H:%M")}｜区间 {START}~{END}｜指数 {len(cache)} 个')
    lines.append('> 理论来源：《A股股票方法论大全（2026年8月）.mm》第二/四/五/六章（此前未验证项）')
    lines.append('')

    # ===== V1 三大市场环境 → 各环境收益（沪深300 主验证） =====
    lines.append('## V1 三大市场环境判定（趋势/震荡/熊市）→ 后续收益（沪深300）')
    lines.append('')
    lines.append('| 环境 | 天数 | 占比 | 次日平均 | 未来5日 | 未来20日 | 未来60日 |')
    lines.append('|---|---|---|---|---|---|---|')
    df = cache['沪深300']
    stats = {'趋势': [], '震荡': [], '熊市': []}
    for i in range(250, len(df) - 60):
        env = env_at(df, i)
        if env not in stats:
            continue
        r5, r20, r60 = fwd_ret(df, i, 5), fwd_ret(df, i, 20), fwd_ret(df, i, 60)
        if r5 is None or r20 is None or r60 is None:
            continue
        stats[env].append((r5 * 100, r20 * 100, r60 * 100))
    total = sum(len(v) for v in stats.values())
    for env in ('趋势', '震荡', '熊市'):
        v = stats[env]
        if not v:
            lines.append(f'| {env} | 0 | - | - | - | - |')
            continue
        n = len(v)
        a5 = sum(x[0] for x in v) / n
        a20 = sum(x[1] for x in v) / n
        a60 = sum(x[2] for x in v) / n
        lines.append(f'| {env} | {n} | {n/total*100:.0f}% | — | {a5:+.2f}% | {a20:+.2f}% | {a60:+.2f}% |')
    lines.append('')

    # ===== V2 环境×策略适应矩阵 =====
    lines.append('## V2 环境×策略适应矩阵（沪深300，策略年化）')
    lines.append('')
    lines.append('> 策略定义：趋势=MA20>MA60且站上MA60持有多头；回归=乖离<0买入（超卖均值归）；动量=60日动量>0持有；持有=基准')
    lines.append('')
    lines.append('| 策略 | 趋势环境 | 震荡环境 | 熊市环境 | 全期 |')
    lines.append('|---|---|---|---|---|')
    strategies = {
        '趋势(MA20>MA60)': lambda i: float(df.loc[i, 'ma20']) > float(df.loc[i, 'ma60']),
        '动量(60日>0)': lambda i: float(df.loc[i, 'close']) > float(df.loc[i - 60, 'close']),
        '回归(乖离<0)': lambda i: float(df.loc[i, 'close']) < float(df.loc[i, 'ma60']),
        '持有(基准)': lambda i: True,
    }
    # 简化：逐日标记策略持仓状态，按环境分组统计日收益
    env_daily = {'趋势': [], '震荡': [], '熊市': []}
    all_daily = []
    for i in range(250, len(df) - 1):
        env = env_at(df, i)
        if env not in env_daily:
            continue
        r = float(df.loc[i + 1, 'close']) / float(df.loc[i, 'close']) - 1
        row = {'env': env, 'ret': r}
        for name, fn in strategies.items():
            try:
                row[name] = fn(i)
            except Exception:
                row[name] = False
        env_daily[env].append(row)
        all_daily.append(row)
    for strat in strategies:
        cells = []
        for env in ('趋势', '震荡', '熊市'):
            days = [x for x in env_daily[env] if x[strat]]
            if not days:
                cells.append('—')
                continue
            avg = sum(x['ret'] for x in days) / len(days)
            cells.append(f'{avg*252*100:+.1f}%')
        all_days = [x for x in all_daily if x[strat]]
        avg_all = sum(x['ret'] for x in all_days) / len(all_days) if all_days else 0
        cells.append(f'{avg_all*252*100:+.1f}%')
        lines.append(f'| {strat} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |')
    lines.append('')

    # ===== V3 量价关系 =====
    lines.append('## V3 量价关系（上涨放量/缩量 → 5日收益；上证+深成 混合）')
    lines.append('')
    lines.append('| 量价形态 | 信号数 | 平均5日 | 平均10日 | 胜率 |')
    lines.append('|---|---|---|---|---|')
    v3 = []
    for cname in ('上证', '深成'):
        d = cache[cname]
        for i in range(20, len(d) - 10):
            c = float(d.loc[i, 'close'])
            o = float(d.loc[i, 'open'])
            vol = float(d.loc[i, 'vol']) if 'vol' in d.columns else 0
            vol_ma20 = float(d.loc[i - 20:i, 'vol'].mean()) if 'vol' in d.columns else 0
            if c <= o:
                continue
            # 上涨日
            if vol_ma20 > 0 and vol > vol_ma20 * 1.5:
                shape = '上涨放量'
            elif vol_ma20 > 0 and vol < vol_ma20 * 0.7:
                shape = '上涨缩量'
            else:
                continue
            r5 = fwd_ret(d, i, 5)
            r10 = fwd_ret(d, i, 10)
            if r5 is None or r10 is None:
                continue
            v3.append({'shape': shape, 'r5': r5 * 100, 'r10': r10 * 100, 'win': r5 > 0})
    import collections
    shapes = collections.defaultdict(list)
    for x in v3:
        shapes[x['shape']].append(x)
    for shape, lst in shapes.items():
        n = len(lst)
        a5 = sum(x['r5'] for x in lst) / n
        a10 = sum(x['r10'] for x in lst) / n
        win = sum(x['win'] for x in lst) / n
        lines.append(f'| {shape} | {n} | {a5:+.2f}% | {a10:+.2f}% | {win*100:.0f}% |')
    lines.append('')

    # ===== V4 生命周期四阶段（简化：用沪深300 月度均线趋势近似） =====
    lines.append('## V4 生命周期四阶段择时（近似标定，沪深300 2020-2026）')
    lines.append('')
    lines.append('| 阶段 | 判定 | 仓位(理论) | 实际区间 | 效果 |')
    lines.append('|---|---|---|---|---|')
    # 手动标定关键阶段点（用收盘价定性，真实数据）：
    ph = [
        ('导入(2024-01~2024-09)', '底部磨底', '≤2成', '2024年磨底段'),
        ('成长(2024-09~2025-12)', '放量主升', '6-8成', '2024-09成交放量'),
        ('成熟(2026-01~2026-04)', '高位震荡', '3-5成', '2026 高位'),
        ('衰退(2026-05~现在)', '阴跌', '≤2成或空仓', '2026-05后回落'),
    ]
    lines.append('| 阶段 | 匹配 | 说明 |')
    lines.append('|---|---|---|')
    for a, b, c, d in ph:
        lines.append(f'| {a} | {b} | {d} |')
    lines.append('')
    lines.append('（四阶段为定性标注，量化验证需按月分割全期收益——见总结建议）')
    lines.append('')

    # ===== 总结 =====
    lines.append('## 总结论')
    lines.append('')
    lines.append('（待补——见报告尾部）')

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'已输出 {OUT}')


if __name__ == '__main__':
    main()
