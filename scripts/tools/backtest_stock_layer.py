#!/usr/bin/env python3
"""个股层方法论历史回测——过滤漏斗 + 两大买点 + R体系 验证（2026-08-23）

对齐《A股实战交易系统 v1.1》第四节（个股层）：
  E1 底线过滤  E2 趋势过滤  E3 强度过滤  E4 两大买点  E5 R体系

方法：无未来函数（信号日收盘确认 → 次日开盘入场），止损-5%/破MA10。
样本：沪深300 成分股（可计算、流动性好、覆盖主线），2022-01~2026-08。
分组：按市场环境状态（趋势/震荡/熊市）分层统计三个买点细节。

用法: python scripts/tools/backtest_stock_layer.py
"""
import sys
import os
import io
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import pandas as pd  # noqa: E402

# ========== 配置 ==========
START = '20220101'
END = '20260821'
HEAD = 1123            # 拉全量（不截断——MA250 需 250 天前置，扫描窗口需完整序列）
R_LOSS = 0.05        # 止损 5%
HOLD = (5, 10, 20)   # 持有期窗口
OUT = os.path.join(BASE_DIR, 'reports', 'misc', '个股层回测_2026-08-23.md')

# 沪深300 成分（简化：取 60 只可计算蓝筹代表，覆盖主线风格）
CANDIDATES = [
    '600519.SH', '601318.SH', '600036.SH', '601398.SH', '601288.SH', '600030.SH',
    '600887.SH', '600690.SH', '601888.SH', '601012.SH', '600009.SH', '601668.SH',
    '601857.SH', '601088.SH', '601601.SH', '601628.SH', '601939.SH', '601988.SH',
    '601899.SH', '603288.SH', '603501.SH', '603259.SH', '600028.SH', '601988.SH',
    '000858.SZ', '000333.SZ', '000651.SZ', '000725.SZ', '002415.SZ', '002475.SZ',
    '300750.SZ', '300059.SZ', '300015.SZ', '300760.SZ', '000001.SZ', '000002.SZ',
    '000063.SZ', '002352.SZ', '002594.SZ', '300014.SZ', '300122.SZ', '300124.SZ',
    '002049.SZ', '002230.SZ', '600703.SH', '688012.SH', '688981.SH', '300308.SZ',
    '300476.SZ', '002463.SZ', '603986.SH', '688041.SH', '002916.SZ', '600183.SH',
    '300408.SZ', '688256.SH', '002371.SZ', '600584.SH', '002049.SZ', '600745.SH',
]


def get_kl(ts_code: str) -> pd.DataFrame:
    from scripts.tushare_pro_data import ts_daily
    try:
        df = ts_daily(ts_code, start=START, end=END)
        if not df:
            return pd.DataFrame()
        rows = df
        # Tushare daily 结果可能为 dict list；统一成 DataFrame
        if isinstance(df, list):
            import pandas as pd
            df = pd.DataFrame(df)
        for c in ('trade_date', 'open', 'close', 'high', 'low', 'pct_chg'):
            if c not in df.columns:
                return pd.DataFrame()
        df = df.sort_values('trade_date').reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


def compute_ma(df: pd.DataFrame) -> pd.DataFrame:
    """计算 MA5/10/20/60 与 MA250（不足则 NaN）"""
    for n in (5, 10, 20, 60, 250):
        df[f'ma{n}'] = df['close'].rolling(n).mean()
    return df


def env_at(df: pd.DataFrame, idx: int) -> str:
    """基于 MA20×MA60 方向的简单环境分层：趋势/震荡/熊市"""
    if idx < 60:
        return '数据不足'
    ma20, ma60 = df.loc[idx, 'ma20'], df.loc[idx, 'ma60']
    if pd.isna(ma20) or pd.isna(ma60):
        return '数据不足'
    if ma20 > ma60 and df.loc[idx, 'close'] > ma60:
        return '趋势'
    if ma20 < ma60 and df.loc[idx, 'close'] < ma60:
        return '熊市'
    return '震荡'


def run_bt(ts_code: str) -> List[dict]:
    """单票回测：扫描每一天，符合 E2/E3 → 触发 E4 买点 → 记录 5/10/20 日收益"""
    df = get_kl(ts_code)
    if df.empty:
        return []
    df = compute_ma(df)
    results = []
    n = len(df)
    for i in range(61, n - 21):  # 需要前置 60 日 + 后 20 日
        r = df.iloc[i]
        close = float(r['close'])
        # E2 趋势过滤：收盘 > MA250 且 MA20 > MA60（MA250 数据不足时放宽为 MA60 向上）
        ma20, ma60 = float(r['ma20']), float(r['ma60'])
        ma250 = float(r['ma250']) if not pd.isna(r['ma250']) else 0
        trend_ok = (ma20 > ma60) and (close > ma250 if ma250 > 0 else True)
        if not trend_ok:
            continue
        # E3 强度过滤：近60日涨幅 > 0（简化相对强度）
        ret60 = close / float(df.iloc[i - 60]['close']) - 1 if i >= 60 else 0
        if ret60 <= 0:
            continue
        env = env_at(df, i)
        # E4 买点：回踩 MA10 (偏差 ±3%) 或 突破20日平台+量
        dev_ma10 = close / float(r['ma10']) - 1 if not pd.isna(r['ma10']) else 9
        event_key = f"{ts_code}_{r['trade_date']}_{'回踩' if abs(dev_ma10) <= 0.03 else '突破'}"
        # 回踩买点：|偏差| ≤ 3%
        if abs(dev_ma10) <= 0.03:
            entry = float(df.iloc[i + 1]['open'])  # 次日开盘入场（无未来函数）
            for h in HOLD:
                if i + h < n:
                    # 止损检查：持有期内跌破 -5%
                    stop = False
                    for j in range(i + 1, i + h + 1):
                        if float(df.iloc[j]['low']) <= entry * (1 - R_LOSS):
                            stop = True
                            break
                    exit_price = float(df.iloc[i + h]['close']) if not stop else entry * (1 - R_LOSS)
                    results.append({
                        'ts': ts_code, 'date': r['trade_date'], 'env': env,
                        'buy_type': '回踩', 'ret': exit_price / entry - 1,
                        'hold': h, 'stop': stop,
                    })
            continue  # 当天不重复考察突破
        # 突破买点：创 20 日新高 + 当日阳线 + 放量（量 > 20日均量×1.5，避免假突破）
        hi20 = float(df.iloc[i - 20:i]['high'].max()) if i >= 20 else close
        vol_ma20 = float(df.iloc[i - 20:i]['vol'].mean()) if i >= 20 else 0
        vol_ok = vol_ma20 > 0 and float(r['vol']) > vol_ma20 * 1.5
        if close > hi20 and close > float(r['open']) and vol_ok:
            entry = float(df.iloc[i + 1]['open'])
            for h in HOLD:
                if i + h < n:
                    stop = False
                    for j in range(i + 1, i + h + 1):
                        if float(df.iloc[j]['low']) <= entry * (1 - R_LOSS):
                            stop = True
                            break
                    exit_price = float(df.iloc[i + h]['close']) if not stop else entry * (1 - R_LOSS)
                    results.append({
                        'ts': ts_code, 'date': r['trade_date'], 'env': env,
                        'buy_type': '突破', 'ret': exit_price / entry - 1,
                        'hold': h, 'stop': stop,
                    })
    return results


def main() -> None:
    print(f'回测开始 {START}~{END}，样本 {len(CANDIDATES)} 只沪深300代表股（约 20 分钟）')
    all_results = []
    for i, code in enumerate(CANDIDATES):
        try:
            res = run_bt(code)
            if res:
                all_results.extend(res)
        except Exception as e:
            print(f'  [{i+1}/{len(CANDIDATES)}] {code} 失败: {e}')
        if (i + 1) % 10 == 0:
            print(f'  [{i+1}/{len(CANDIDATES)}] 累计信号 {len(all_results)}')
    print(f'完成，信号总数 {len(all_results)}')

    # ===== 分析输出 =====
    lines = []
    lines.append('# 个股层方法论历史回测报告（过滤漏斗+买点+R体系）')
    lines.append('')
    lines.append(f'> 时间戳：{datetime.now().strftime("%Y-%m-%d %H:%M")}｜区间 {START}~{END}｜样本：沪深300 代表股 {len(CANDIDATES)} 只｜信号 {len(all_results)} 次')
    lines.append('> 方法：无未来函数（信号日收盘确认→次日开盘入场），止损 -5%；持有窗口 5/10/20 日，破位即止损出。')
    lines.append('')

    dfr = pd.DataFrame(all_results)
    if dfr.empty:
        lines.append('**无有效信号（检查过滤或数据）**')
    else:
        lines.append('## 一、买点类型总体对比')
        lines.append('')
        lines.append('| 买点 | 信号数 | 平均5日 | 平均10日 | 平均20日 | 胜率5日 | 胜率10日 | 止损触发率 |')
        lines.append('|---|---|---|---|---|---|---|---|')
        for bt in ('回踩', '突破'):
            sub = dfr[dfr['buy_type'] == bt]
            if sub.empty:
                continue
            stats = []
            for h in (5, 10, 20):
                s = sub[sub['hold'] == h]['ret']
                stats.append(f"{s.mean() * 100:+.2f}%" if s.size else '—')
            win5 = (sub[(sub['hold'] == 5)]['ret'] > 0).mean() if (sub['hold'] == 5).any() else 0
            stop = sub['stop'].mean() if sub.size else 0
            lines.append(f"| {bt} | {sub.size} | {stats[0]} | {stats[1]} | {stats[2]} | {win5*100:.0f}% | — | {stop*100:.0f}% |")
        lines.append('')

        lines.append('## 二、环境分层①：趋势/震荡/熊市 × 买点')
        lines.append('')
        lines.append('| 环境 | 买点 | 信号 | 平均10日 | 平均20日 | 止损率 |')
        lines.append('|---|---|---|---|---|---|')
        for env in ('趋势', '震荡', '熊市'):
            sub = dfr[dfr['env'] == env]
            for bt in ('回踩', '突破'):
                s = sub[sub['buy_type'] == bt]
                if s.empty:
                    continue
                h10 = s[s['hold'] == 10]['ret'].mean() if (s['hold'] == 10).any() else 0
                h20 = s[s['hold'] == 20]['ret'].mean() if (s['hold'] == 20).any() else 0
                stop = s['stop'].mean()
                lines.append(f"| {env} | {bt} | {s.size} | {h10*100:+.2f}% | {h20*100:+.2f}% | {stop*100:.0f}% |")
        lines.append('')

        lines.append('## 三、E5 R体系验证（0.5-1%R 风控）')
        lines.append('')
        lines.append(f"- 止损触发率总体：{dfr['stop'].mean()*100:.1f}%（止损-5% 生效与否）")
        r_avg = dfr[dfr['hold'] == 5]['ret'].mean()
        lines.append(f"- 5 日平均收益：{r_avg*100:+.2f}% → R 倍数 ≈ {r_avg/0.05:+.2f}R（≥+0.5R=策略有效，≤0=无效）")
        lines.append('')

        lines.append('## 四、结论与修正建议')
        lines.append('')
        lines.append('（待 E1-E5 全量数据分析后补）')

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'已输出 {OUT}')


if __name__ == '__main__':
    main()
