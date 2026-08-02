#!/usr/bin/env python3
"""
财联社电报 — 7x24 实时财经快讯（v1 API + 本地签名，零 key）。

接口: https://www.cls.cn/v1/roll/get_roll_list
返回: [{title, content, time}] 按时间倒序

用法:
  from scripts.cls_telegraph import get_cls, cls_telegraph
  cls = get_cls()
  items = cls.fetch_telegraph(limit=20)

集成到 DataGate:
  from scripts.data_gate import gate
  items = gate.em_cls_telegraph(limit=10)

上游: a-stock-data §5.2，2026-07 已复活，与东财 7x24 互为独立备份。
"""

import hashlib
from typing import Optional

import requests

from datetime import datetime


class CLSTelegraph:
    """财联社电报数据源（单例模式，纯本地签名，无需 Token）。"""

    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.cls.cn/",
        })

    @staticmethod
    def _sign(qs: str) -> str:
        """本地签名: MD5(SHA1(query_string))。"""
        sha1 = hashlib.sha1(qs.encode()).hexdigest()
        return hashlib.md5(sha1.encode()).hexdigest()

    def fetch_telegraph(self, limit: int = 20) -> list:
        """获取财联社实时电报（全频道，按时间倒序）。

        Args:
            limit: 返回条数上限

        Returns:
            [{title, content, time}]  time 格式 'YYYY-MM-DD HH:MM:SS'
        """
        params = {
            "appName": "CailianpressWeb",
            "os": "web",
            "sv": "7.7.5",
            "last_time": "",
            "refresh_type": "1",
            "rn": str(limit),
        }
        # 签名：按 key 字典序拼接 → MD5(SHA1(qs))
        qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
        sign = self._sign(qs)
        url = f"https://www.cls.cn/v1/roll/get_roll_list?{qs}&sign={sign}"

        r = self.session.get(url, timeout=15)
        data = r.json()

        items = []
        for row in data.get("data", {}).get("roll_data", []) or []:
            ts = row.get("ctime")
            t_str = ""
            if ts:
                try:
                    t_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError, OSError):
                    t_str = str(ts)
            items.append({
                "title": row.get("title", "") or row.get("brief", ""),
                "content": row.get("content", "") or row.get("brief", ""),
                "time": t_str,
            })
        return items[:limit]


# ==================== 单例 ====================

_CLS: Optional[CLSTelegraph] = None


def get_cls() -> CLSTelegraph:
    global _CLS
    if _CLS is None:
        _CLS = CLSTelegraph()
    return _CLS


# ==================== 便捷函数 ====================

def cls_telegraph(limit: int = 20) -> list:
    """直接调用获取电报"""
    return get_cls().fetch_telegraph(limit)


# ==================== 自测 ====================

if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    cls = get_cls()
    print("财联社电报连通性测试:\n")
    try:
        items = cls.fetch_telegraph(limit=5)
        print(f"  获取 {len(items)} 条")
        for it in items:
            print(f"  {it['time']} | {it['title'][:60]}")
    except Exception as e:
        print(f"  失败: {e}")
