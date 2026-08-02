# -*- coding: utf-8 -*-
"""调试腾讯实时行情返回"""
import urllib.request

TARGETS = {
    "sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指",
    "sh000300": "沪深300", "sh000016": "上证50", "sh000905": "中证500",
    "sh000852": "中证1000", "sh000688": "科创50", "sz399967": "中证军工",
}
codes = "sh000001,sz399001,sz399006,sh000300,sh000016,sh000905,sh000852,sh000688,sz399967"
url = f"https://qt.gtimg.cn/q={codes}"
req = urllib.request.Request(url)
req.add_header("User-Agent", "Mozilla/5.0")
resp = urllib.request.urlopen(req, timeout=10)
data = resp.read().decode("gbk")
print("=== RAW RESPONSE (first 1500 chars) ===")
print(data[:1500])
print("\n=== PARSED ===")
for line in data.strip().split(";"):
    line = line.strip()
    if not line or "~" not in line:
        continue
    parts = line.split('"')
    if len(parts) < 2:
        continue
    meta = parts[0].replace("v_", "")
    vals = parts[1].split("~")
    if len(vals) < 40:
        print(f"SKIP {meta}: only {len(vals)} fields")
        continue
    print(f"\n{meta}: name={vals[1]}, price={vals[3]}, last_close={vals[4]}, change_pct={vals[32]}, amp={vals[43]}")
