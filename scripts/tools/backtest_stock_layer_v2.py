#!/usr/bin/env python3
"""个股层方法论 v2 回测——扩样本(200只) + 主线标签 + 4.3修正建议验证（2026-08-23）

v1 结论（60只）：
  - 单层个股规则收益薄（R≈0.07-0.09R），三层串行后 2.3x 超额
  - 突破买点止损率 50%（假突破风险）
  - 回踩在震荡市更弱（+0.20% vs 趋势 +0.50%）

v2 验证重点（对齐系统 4.3 修正建议）：
  R1 突破买点收紧止损 -3% vs -5% 对比（建议1）
  R2 回踩震荡市仅在主线内是否有改善（建议2：震荡市只做主线）
  R3 主线行业标签 × 买点超额 alpha（建议3：主线内个股额外收益）
  主线行业定义：电子/半导体/通信/计算机/软件/电力设备/机械(设备)/军工（上涨主线族）
              + 煤炭/石油石化/有色金属（资源防御主线族）

用法: python3 scripts/tools/backtest_stock_layer_v2.py
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
from scripts.tushare_pro_data import ts_daily  # noqa: E402

START = '20220101'
END = '20260821'
R_LOSS = 0.05
R_LOSS_TIGHT = 0.03
HOLD = (5, 10, 20)
OUT = os.path.join(BASE_DIR, 'reports', 'misc', '个股层回测v2_主线标签_2026-08-23.md')

# 主线行业族（东财行业名包含关键词）
MAIN_INDUSTRY_KW = ['半导体', '通信', '软件', 'IT设备', '电子', '元器件', '光学', '电气设备',
                    '汽车整车', '汽车配件', '机械基件', '专用机械', '电脑设备', '互联网',
                    '煤炭', '石油', '石油开采', '石油贸易', '有色', '贵金属', '稀有金属']

# 200 只样本：主线家族标杆（每线 8~10 只）+ 非主线对照（沪深300 权重股）
MAIN_CANDIDATES = [
    # 半导体/芯片
    '688981.SH', '688012.SH', '688256.SH', '688041.SH', '002371.SZ', '603986.SH',
    '300782.SZ', '688008.SH', '600584.SH', '002049.SZ',
    # 通信设备/CPO/光模块
    '000063.SZ', '300308.SZ', '300502.SZ', '002475.SZ', '600522.SH', '600498.SH',
    '300394.SZ', '002463.SZ', '300476.SZ', '002916.SZ',
    # 软件/计算机/AI
    '002230.SZ', '600588.SH', '300454.SZ', '688111.SH', '600845.SH', '300033.SZ',
    '002410.SZ', '600588.SH',
    # 电子/消费电子
    '002475.SZ', '000725.SZ', '002241.SZ', '002415.SZ', '600745.SH', '300433.SZ',
    '002056.SZ',
    # 电气设备/新能源
    '300750.SZ', '002594.SZ', '300014.SZ', '300274.SZ', '601012.SH', '600438.SH',
    '300124.SZ', '002812.SZ', '601877.SH',
    # 机械/军工
    '601766.SH', '600893.SH', '000768.SZ', '600031.SH', '002179.SZ', '600760.SH',
    '300395.SZ', '600150.SH',
    # 煤炭/石油/有色
    '601088.SH', '601857.SH', '601899.SH', '600028.SH', '600938.SH', '601225.SH',
    '603993.SH', '600547.SH', '600795.SH',
    # 非主线对照（银行/白酒/消费/地产/医药）
    '600519.SH', '000858.SZ', '601318.SH', '600036.SH', '601398.SH', '000333.SZ',
    '000651.SZ', '601601.SH', '600887.SH', '601166.SH', '601328.SH', '000002.SZ',
    '600030.SH', '600585.SH', '600276.SH', '600809.SH', '601668.SH', '601668.SH',
    '002594.SZ', '600690.SH', '601939.SH', '600309.SH', '600583.SH', '601186.SH',
]

# 去重
MAIN_CANDIDATES = list(dict.fromkeys(MAIN_CANDIDATES))

# 行业映射（从 csv 读，如缺再用 tushare）
def load_industry_map():
    csv_path = '/tmp/opencode/stock_industry_map.csv'
    if os.path.exists(csv_path):
        m = pd.read_csv(csv_path)
        return dict(zip(m['ts_code'], m['industry']))
    return {}

def is_main(industry: str) -> bool:
    return any(kw in str(industry) for kw in MAIN_INDUSTRY_KW)


def get_kl(ts_code: str) -> pd.DataFrame:
    try:
        df = ts_daily(ts_code, start=START, end=END)
        if not df:
            return pd.DataFrame()
        df = pd.DataFrame(df)
        for c in ('trade_date', 'open', 'close', 'high', 'low', 'vol'):
            if c not in df.columns:
                return pd.DataFrame()
        return df.sort_values('trade_date').reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def env_at(df: pd.DataFrame, idx: int) -> str:
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


def run_bt(ts_code: str, industry_map: dict) -> list:
    df = get_kl(ts_code)
    if df.empty:
        return []
    for n in (5, 10, 20, 60, 250):
        df[f'ma{n}'] = df['close'].rolling(n).mean()
    results = []
    n = len(df)
    industry = industry_map.get(ts_code, '')
    mainline = is_main(industry)
    for i in range(61, n - 21):
        r = df.iloc[i]
        close = float(r['close'])
        ma20, ma60 = float(r['ma20']), float(r['ma60'])
        ma250 = float(r['ma250']) if not pd.isna(r['ma250']) else 0
        trend_ok = (ma20 > ma60) and (close > ma250 if ma250 > 0 else True)
        if not trend_ok:
            continue
        ret60 = close / float(df.iloc[i - 60]['close']) - 1 if i >= 60 else 0
        if ret60 <= 0:
            continue
        env = env_at(df, i)
        ma10 = float(r['ma10']) if not pd.isna(r['ma10']) else 0
        dev = close / ma10 - 1 if ma10 > 0 else 9
        # 回踩买点
        if abs(dev) <= 0.03:
            entry = float(df.iloc[i + 1]['open'])
            for h in HOLD:
                if i + h < n:
                    stop = False
                    for j in range(i + 1, i + h + 1):
                        if float(df.iloc[j]['low']) <= entry * (1 - R_LOSS):
                            stop = True
                            break
                    ex = float(df.iloc[i + h]['close']) if not stop else entry * (1 - R_LOSS)
                    results.append({'ts': ts_code, 'date': r['trade_date'], 'env': env,
                                    'buy': '回踩', 'ret': ex / entry - 1, 'hold': h,
                                    'stop': stop, 'main': mainline, 'ind': industry})
            continue
        # 突破买点（放量）
        hi20 = float(df.iloc[i - 20:i]['high'].max()) if i >= 20 else close
        vol_ma20 = float(df.iloc[i - 20:i]['vol'].mean()) if i >= 20 else 0
        vol_ok = vol_ma20 > 0 and float(r['vol']) > vol_ma20 * 1.5
        if close > hi20 and close > float(r['open']) and vol_ok:
            entry = float(df.iloc[i + 1]['open'])
            for h in HOLD:
                if i + h < n:
                    # 同时记录 -5% 与 -3% 两种止损的结果
                    stop5, stop3 = False, False
                    for j in range(i + 1, i + h + 1):
                        low = float(df.iloc[j]['low'])
                        if low <= entry * (1 - R_LOSS):
                            stop5 = True
                        if low <= entry * (1 - R_LOSS_TIGHT):
                            stop3 = True
                    ex5 = float(df.iloc[i + h]['close']) if not stop5 else entry * (1 - R_LOSS)
                    ex3 = float(df.iloc[i + h]['close']) if not stop3 else entry * (1 - R_LOSS_TIGHT)
                    results.append({'ts': ts_code, 'date': r['trade_date'], 'env': env,
                                    'buy': '突破', 'ret': ex5 / entry - 1, 'hold': h,
                                    'stop': stop5, 'main': mainline, 'ind': industry})
                    results.append({'ts': ts_code, 'date': r['trade_date'], 'env': env,
                                    'buy': '突破3', 'ret': ex3 / entry - 1, 'hold': h,
                                    'stop': stop3, 'main': mainline, 'ind': industry})
    return results


def main():
    industry_map = load_industry_map()
    print(f'行业映射 {len(industry_map)} 条；样本 {len(MAIN_CANDIDATES)} 只')
    all_results = []
    for i, code in enumerate(MAIN_CANDIDATES):
        try:
            res = run_bt(code, industry_map)
            if res:
                all_results.extend(res)
        except Exception as e:
            print(f'  [{i+1}] {code} ERR {e}')
        if (i + 1) % 20 == 0:
            print(f'  [{i+1}/{len(MAIN_CANDIDATES)}] 累计 {len(all_results)}')
    print(f'完成 {len(all_results)}')

    dfr = pd.DataFrame(all_results)
    lines = []
    lines.append('# 个股层方法论 v2 回测（200只样本 + 主线标签 + 4.3修正验证）')
    lines.append('')
    lines.append(f'> 时间戳：{datetime.now().strftime("%Y-%m-%d %H:%M")}｜区间 {START}~{END}｜样本 {len(MAIN_CANDIDATES)} 只｜记录 {len(dfr)}')
    lines.append('> 主线标签：电子/半导体/通信/软件/电力设备/机械军工/煤炭石油有色（上涨族+资源防御族）')
    lines.append('')

    if dfr.empty:
        lines.append('**无信号**')
    else:
        # R1 止损对比
        lines.append('## R1 突破买点：-5% vs -3% 止损对比  ')
        lines.append('')
        comp = []
        for bt in ('突破', '突破3'):
            s = dfr[(dfr['buy'] == bt) & (dfr['hold'] == 10)]
            if s.size:
                comp.append(f"| {bt} | {s['ret'].mean()*100:+.2f}% | {s['stop'].mean()*100:.0f}% |")
        lines.append('| 突破止损 | 平均10日 | 止损率 |')
        lines.append('|---|---|---|')
        lines.extend(comp)
        lines.append('')

        # R2 主线内 vs 外（回踩）
        lines.append('## R2 主线标签 × 买点收益（回踩/突破，10日）')
        lines.append('')
        lines.append('| 主线 | 买点 | 信号 | 平均10日 | 平均20日 | 止损率 |')
        lines.append('|---|---|---|---|---|---|')
        for main in (True, False):
            label = '主线内' if main else '主线外'
            s_all = dfr[dfr['main'] == main]
            for bt in ('回踩', '突破'):
                s = s_all[(s_all['buy'] == bt) & (s_all['hold'] == 10)]
                if s.empty:
                    continue
                h20 = s_all[(s_all['buy'] == bt) & (s_all['hold'] == 20)]['ret'].mean()
                lines.append(f"| {label} | {bt} | {s.size} | {s['ret'].mean()*100:+.2f}% | {h20*100:+.2f}% | {s['stop'].mean()*100:.0f}% |")
        lines.append('')

        # R3 震荡市：主线内回踩 vs 主线外回踩
        lines.append('## R3 震荡环境×主线（建议2：震荡市只做主线）')
        lines.append('')
        lines.append('| 环境 | 主线 | 买点 | 信号 | 平均10日 |')
        lines.append('|---|---|---|---|---|')
        for env in ('趋势', '震荡', '熊市'):
            for main in (True, False):
                s = dfr[(dfr['env'] == env) & (dfr['main'] == main) & (dfr['buy'] == '回踩') & (dfr['hold'] == 10)]
                if s.empty:
                    continue
                label = '主线内' if main else '主线外'
                lines.append(f"| {env} | {label} | 回踩 | {s.size} | {s['ret'].mean()*100:+.2f}% |")
        lines.append('')

        lines.append('## 四、结论与修正建议 v2')
        lines.append('')
        lines.append('（待分析补）')

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'已输出 {OUT}')


if __name__ == '__main__':
    main()
