#!/usr/bin/env python3
"""主线标签工具 get_mainline_status() —— A股实战交易系统 v1.2 二级门控

数据：scripts/data/stock_industry_map.csv（tushare stock_basic 行业映射，5549 只）
主线族定义：验证基准（2022-2026 上涨主线族 + 资源防御主线族）——齐备后可按季度校准。
用法：
  from scripts.data.mainline import get_mainline_status, is_mainline_stock, MAINLINE_KWS

允许自由扩展（MAINLINE_KWS）：若某行业在查表时被误标/漏标，直接改 mainline.py 内列表即可。
"""
import os
import csv
import threading
from functools import lru_cache

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAP_PATH = os.path.join(_BASE_DIR, 'data', 'stock_industry_map.csv')

# 主线行业关键词族（东财行业名包含即算主线）——回测验证：主线族突破 +1.94% vs 主线外 -0.40%
# v1.2 定义（对齐回测样本）：科技成长族（半导体/通信/软件/电子/电气/军工机械）+ 资源防御族（煤/油/有色）
# 不含金融银行（v1 回测主线族定义不含金融；银行属红利防御另算，防止主线标签过宽稀释 alpha）
MAINLINE_KWS = [
    '半导体', '通信', '软件', 'IT设备', '电子', '元器件', '光学', '电气设备',
    '汽车整车', '汽车配件', '机械基件', '专用机械', '电脑设备', '互联网',
    '煤炭', '石油', '有色', '贵金属', '稀有金属', '铜', '铝', '锌', '镍',
    '航天', '船舶', '航空', '国防军工',
]

_lock = threading.Lock()
_map = None  # {ts_code: industry}
_open = None


def _load_map() -> dict:
    global _map
    if _map is None:
        with _lock:
            if _map is None:
                m = {}
                if os.path.exists(_MAP_PATH):
                    with open(_MAP_PATH, 'r', encoding='utf-8') as f:
                        for row in csv.DictReader(f):
                            m[row['ts_code']] = row.get('industry', '')
                _map = m
    return _map


def get_industry(code: str):
    """6位代码或带后缀 → 行业名（tushare 口径）"""
    m = _load_map()
    return m.get(code) or m.get(f'{code}.SH') or m.get(f'{code}.SZ')


def is_mainline_stock(code: str) -> bool:
    """个股是否属主线行业族（v1.2 二级门控）"""
    ind = get_industry(code)
    if not ind:
        return False
    return any(kw in ind for kw in MAINLINE_KWS)


def get_mainline_status(code: str) -> dict:
    """单票主线标签判定（流水线 Step ③/④ 用）
    返回 {code, industry, mainline(bool), kws(命中的关键词)} """
    ind = get_industry(code)
    if not ind:
        return {'code': code, 'industry': None, 'mainline': False,
                'kws': [], 'note': '无行业映射（非A股/未上市/代码错）'}
    hits = [kw for kw in MAINLINE_KWS if kw in ind]
    return {'code': code, 'industry': ind, 'mainline': bool(hits),
            'kws': hits, 'note': ''}


@lru_cache(maxsize=64)
def mainline_stats() -> dict:
    """全市场主线/非主线统计（辅助校验）"""
    m = _load_map()
    main = 0
    non = 0
    for ind in m.values():
        if any(kw in ind for kw in MAINLINE_KWS):
            main += 1
        else:
            non += 1
    return {'total': len(m), 'mainline': main, 'non_mainline': non}


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('用法: python3 scripts/data/mainline.py <code> [code...]')
        print('示例: python3 scripts/data/mainline.py 600519 688981 300750')
        sys.exit(0)
    for code in sys.argv[1:]:
        r = get_mainline_status(code)
        flag = '✅主线' if r['mainline'] else '❌非主线'
        print(f"{r['code']}: {flag} | 行业={r['industry']} | 命中={r['kws']}")
    print(f"\n全市场统计: {mainline_stats()}")
