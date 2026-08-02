"""Tushare.pro 数据源初始化模块
用法:
    from scripts.tushare_api import get_pro
    pro = get_pro()
    df = pro.daily(ts_code='000001.SZ', start_date='20260701', end_date='20260723')
"""

import json
import os
import tushare as ts

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'tushare_config.json')
_pro = None


def get_config():
    """读取 Tushare 配置"""
    if not os.path.exists(_CONFIG_PATH):
        raise FileNotFoundError(f'Tushare 配置文件不存在: {_CONFIG_PATH}。请在 config/tushare_config.json 中配置 token。')
    with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_pro():
    """获取 Tushare.pro 连接实例（单例）"""
    global _pro
    if _pro is None:
        cfg = get_config()
        ts.set_token(cfg['token'])
        _pro = ts.pro_api(timeout=cfg.get('timeout', 30))
    return _pro


def test_connection():
    """测试 Tushare 连接"""
    pro = get_pro()
    try:
        df = pro.trade_cal(exchange='SSE', start_date='20260701', end_date='20260723')
        return not df.empty, f'连接成功，获取到 {len(df)} 条交易日历数据'
    except Exception as e:
        return False, f'连接失败: {e}'


def fetch_moneyflow_hsgt(start_date: str = None, end_date: str = None) -> list:
    """
    Tushare 沪深港通资金流向（北向 + 南向）。
    备用方案：当东财 kamt.kline 不可用时降级使用。
    注意：免费用户调用有限制。

    start_date / end_date: YYYYMMDD 格式，默认最近 1 个交易日

    返回: [{trade_date, ggt_ss(沪股通), ggt_sz(深股通), north_flow(北向合计),
            south_flow(港股通南向合计), balance(资金余额)}, ...]
    单位：亿元
    """
    from datetime import datetime, timedelta

    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    if start_date is None:
        # 往前推 5 天（覆盖周末/节假日）
        start_dt = datetime.strptime(end_date, "%Y%m%d") - timedelta(days=5)
        start_date = start_dt.strftime("%Y%m%d")

    try:
        pro = get_pro()
        df = pro.moneyflow_hsgt(
            start_date=start_date,
            end_date=end_date,
        )
        if df is None or df.empty:
            return []

        results = []
        for _, row in df.iterrows():
            sh_north = float(row.get("ggt_ss", 0) or 0) / 10000   # 沪股通净买 万元→亿
            sz_north = float(row.get("ggt_sz", 0) or 0) / 10000   # 深股通净买 万元→亿
            sh_south = float(row.get("sgt", 0) or 0) / 10000       # 沪港股通净买 万元→亿
            sz_south = float(row.get("ggt", 0) or 0) / 10000      # 深港股通净买 万元→亿
            results.append({
                "date": str(row.get("trade_date", "")),
                "north_flow_yi": round(sh_north + sz_north, 2),
                "south_flow_yi": round(sh_south + sz_south, 2),
                "sh_north_yi": round(sh_north, 2),
                "sz_north_yi": round(sz_north, 2),
            })
        return results
    except Exception as e:
        print(f"[TushareAPI] moneyflow_hsgt 请求失败: {e}")
        return []


if __name__ == '__main__':
    ok, msg = test_connection()
    print(f'Tushare.pro: {msg}')
