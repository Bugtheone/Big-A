# -*- coding: utf-8 -*-
"""真实北京时间唯一时间源（2026-08-05 用户纪律：禁止推算/猜测时间）。

所有报告/快照/信号的时间戳必须来自本工具，禁止推算：
  - 主源: 腾讯 CDN HTTP Date 头（权威 UTC → +8 北京时间）
  - 校验: 本机 date
用法:
  from scripts.tools.real_time import get_real_time
  t = get_real_time()   # → {local, cdn_beijing, used, source, delta_s}
"""
import sys, os
from datetime import datetime, timedelta, timezone

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

_CN_TZ = timezone(timedelta(hours=8))


def get_real_time():
    """返回真实北京时间（腾讯 CDN 权威 + 本机校验）。used 为采信值。"""
    import requests
    cdn = None
    source = "local"
    try:
        S = requests.Session()
        S.trust_env = False
        S.headers.update({"User-Agent": "Mozilla/5.0"})
        r = S.head("https://qt.gtimg.cn/q=sh000001", timeout=5)
        dt = r.headers.get("Date")
        if dt:
            # HTTP Date 是 GMT，转北京时间
            from email.utils import parsedate_to_datetime
            cdn = parsedate_to_datetime(dt).astimezone(_CN_TZ)
            source = "tencent_cdn"
    except Exception:
        cdn = None
    local = datetime.now(_CN_TZ)
    if cdn is not None:
        delta = abs((cdn - local).total_seconds())
        return {
            "local": local.strftime("%Y-%m-%d %H:%M:%S"),
            "cdn_beijing": cdn.strftime("%Y-%m-%d %H:%M:%S"),
            "used": cdn.strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
            "delta_s": round(delta, 1),
        }
    return {
        "local": local.strftime("%Y-%m-%d %H:%M:%S"),
        "cdn_beijing": None,
        "used": local.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "local_only",
        "delta_s": None,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_real_time(), ensure_ascii=False, indent=1))
