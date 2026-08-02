"""Tushare.pro 数据拉取脚本 — 指数成份股、日K、基本面等

可用功能：
  1. 指数成份股          python scripts/tushare_fetch.py --index --code 000016.SH
  2. 日K线数据           python scripts/tushare_fetch.py --daily 000001.SZ 20260701 20260723
  3. 股票基本信息        python scripts/tushare_fetch.py --basic 000001.SZ
  4. 测试连接            python scripts/tushare_fetch.py --test
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.tushare_api import get_pro


def fetch_index_weights(index_code, trade_date=None):
    """拉取指数成份股权重"""
    pro = get_pro()
    kwargs = {'index_code': index_code}
    if trade_date:
        kwargs['trade_date'] = trade_date
    df = pro.index_weight(**kwargs)
    return df


def fetch_index_member(index_code):
    """拉取指数月调成份股调入调出记录"""
    pro = get_pro()
    df = pro.index_member_all(index_code=index_code)
    return df


def fetch_daily(ts_code, start_date, end_date):
    """拉取日K线（复权）"""
    pro = get_pro()
    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    return df


def fetch_index_daily(index_code, start_date, end_date):
    """拉取指数日行情"""
    pro = get_pro()
    df = pro.index_daily(ts_code=index_code, start_date=start_date, end_date=end_date)
    # Tushare 指数代码格式: 000001.SH / 399001.SZ 等
    # 如果传入的是数字，自动补前缀
    if not isinstance(index_code, str) or '.' not in index_code:
        index_code = f'{index_code}.SH'
    df = pro.index_daily(ts_code=index_code, start_date=start_date, end_date=end_date)
    return df


def fetch_stock_basic(ts_code=None):
    """拉取股票基本信息"""
    pro = get_pro()
    kwargs = {}
    if ts_code:
        kwargs['ts_code'] = ts_code
    df = pro.stock_basic(**kwargs, list_status='L')
    return df


def fetch_trade_cal(start_date, end_date):
    """查询交易日历"""
    pro = get_pro()
    df = pro.trade_cal(exchange='SSE', start_date=start_date, end_date=end_date)
    return df


# ── 主入口 ──

def main():
    parser = argparse.ArgumentParser(description='Tushare.pro 数据拉取')
    parser.add_argument('--test', action='store_true', help='测试连接')
    parser.add_argument('--index', action='store_true', help='拉取指数成份股')
    parser.add_argument('--daily', nargs=3, metavar=('TS_CODE', 'START', 'END'),
                        help='拉取日K线: 代码 起始日 结束日')
    parser.add_argument('--basic', nargs='?', const='', metavar='TS_CODE',
                        help='拉取股票基本信息（不指定代码则全量）')
    parser.add_argument('--code', type=str, default='000016.SH', help='指数代码（默认上证50）')
    parser.add_argument('--date', type=str, default='', help='成份股日期 YYYYMMDD')

    args = parser.parse_args()

    if args.test:
        from scripts.tushare_api import test_connection
        ok, msg = test_connection()
        print(f'[Tushare.pro] {msg}')
        return 0 if ok else 1

    if args.index:
        print(f'拉取 {args.code} 成份股...')
        df = fetch_index_weights(args.code, trade_date=args.date if args.date else None)
        if df is None or df.empty:
            print('  index_weight 无数据，尝试 index_member_all...')
            df = fetch_index_member(args.code)
        if df is not None and not df.empty:
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', 300)
            print(df.to_string())
        else:
            print(f'  (无数据返回)')
        return 0

    if args.daily:
        ts_code, start, end = args.daily
        # 自动补后缀
        if '.' not in ts_code:
            if ts_code.startswith('6'):
                ts_code += '.SH'
            elif ts_code.startswith('0') or ts_code.startswith('3'):
                ts_code += '.SZ'
        # 判断是指数还是个股
        # 指数代码如 000016.SH
        if ts_code == '000016.SH' or ts_code == '000300.SH' or ts_code == '000001.SH':
            df = fetch_index_daily(ts_code, start, end)
        else:
            df = fetch_daily(ts_code, start, end)
        if df is not None and not df.empty:
            print(df.to_string())
        else:
            print('(无数据)')
        return 0

    if args.basic is not None:
        ts_code = args.basic if args.basic else None
        df = fetch_stock_basic(ts_code)
        if df is not None and not df.empty:
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', 200)
            print(df.to_string())
        return 0

    # 默认: 测试连接
    from scripts.tushare_api import test_connection
    ok, msg = test_connection()
    print(f'[Tushare.pro] {msg}')
    return 0 if ok else 1


if __name__ == '__main__':
    import pandas as pd
    sys.exit(main())
