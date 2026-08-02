"""北向资金实时流向分析"""
import requests, sys, pandas as pd
_session = requests.Session()
_session.trust_env = False

from datetime import date

sys.stdout.reconfigure(encoding="utf-8")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"
HSGT_HEADERS = {
    "User-Agent": UA,
    "Host": "data.hexin.cn",
    "Referer": "https://data.hexin.cn/",
}
today = date.today().strftime("%Y-%m-%d")

# === 实时分钟流向 ===
url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
try:
    r = _session.get(url, headers=HSGT_HEADERS, timeout=15)
    d = r.json()
    times = d.get("time", [])
    hgt = d.get("hgt", [])
    sgt = d.get("sgt", [])
except Exception as e:
    print(f"同花顺北向数据获取失败: {e}")
    sys.exit(1)

n = len(times)
df = pd.DataFrame({
    "time": times,
    "hgt_yi": hgt[:n] if len(hgt) >= n else hgt + [None] * (n - len(hgt)),
    "sgt_yi": sgt[:n] if len(sgt) >= n else sgt + [None] * (n - len(sgt)),
})

if df.empty:
    print("今日无北向数据（可能非交易日或数据未更新）")
    sys.exit(0)

# 过滤收盘有效数据
valid = df.dropna()
if valid.empty:
    print("当日所有数据为空，暂无北向流向记录")
    sys.exit(0)

hgt_close = valid["hgt_yi"].iloc[-1]
sgt_close = valid["sgt_yi"].iloc[-1]
total_close = hgt_close + sgt_close

print(f"=== 北向资金 · {today} ===")
print()
print(f"  沪股通累计净买入:  {hgt_close:+.2f} 亿")
print(f"  深股通累计净买入:  {sgt_close:+.2f} 亿")
print(f"  {'─'*30}")
print(f"  北向合计净买入:    {total_close:+.2f} 亿")
print()

direction = "流入" if total_close > 0 else "流出"
hgt_dir = "流入" if hgt_close > 0 else "流出"
sgt_dir = "流入" if sgt_close > 0 else "流出"
print(f"  全天净风向: 北向整体{direction}{abs(total_close):.2f}亿")
print(f"              沪股通{hgt_dir}{abs(hgt_close):.2f}亿 / 深股通{sgt_dir}{abs(sgt_close):.2f}亿")

# === 盘中轨迹 ===
print(f"\n=== 盘中资金轨迹 ===")
print(f"  总数据点: {len(df)} 个（含集合竞价 09:10–15:00）")
print(f"  有效点: {len(valid)} 个")

# 找开盘/午盘开始/收盘的值
if len(valid) >= 3:
    first = valid.iloc[0]
    mid_idx = len(valid) // 2
    mid = valid.iloc[mid_idx]
    last = valid.iloc[-1]
    print(f"\n  开盘初: 沪{first['hgt_yi']:+.2f}亿 深{first['sgt_yi']:+.2f}亿")
    print(f"  盘中:   沪{mid['hgt_yi']:+.2f}亿 深{mid['sgt_yi']:+.2f}亿")
    print(f"  收盘:   沪{last['hgt_yi']:+.2f}亿 深{last['sgt_yi']:+.2f}亿")

    # 判断走势（持续/逆转）
    hgt_trend = last["hgt_yi"] - first["hgt_yi"]
    sgt_trend = last["sgt_yi"] - first["sgt_yi"]
    hgt_t = "持续流入" if first["hgt_yi"] > 0 and hgt_trend > 0 else \
            ("持续流出" if first["hgt_yi"] < 0 and hgt_trend < 0 else "盘中反转")
    sgt_t = "持续流入" if first["sgt_yi"] > 0 and sgt_trend > 0 else \
            ("持续流出" if first["sgt_yi"] < 0 and sgt_trend < 0 else "盘中反转")
    print(f"\n  走势: 沪股通({hgt_t}) / 深股通({sgt_t})")

# === 极端值探测 ===
hgt_max = valid["hgt_yi"].max()
hgt_min = valid["hgt_yi"].min()
sgt_max = valid["sgt_yi"].max()
sgt_min = valid["sgt_yi"].min()

print(f"\n=== 极值探测 ===")
print(f"  沪股通 最高: {hgt_max:+.2f}亿  最低: {hgt_min:+.2f}亿")
print(f"  深股通 最高: {sgt_max:+.2f}亿  最低: {sgt_min:+.2f}亿")

# === 尾盘异动 ===
if len(valid) >= 20:
    early = valid.iloc[-20]
    h_tail = last["hgt_yi"] - early["hgt_yi"]
    s_tail = last["sgt_yi"] - early["sgt_yi"]
    if abs(h_tail) > 10 or abs(s_tail) > 10:
        print(f"\n  ⚠️ 尾盘异动! 最后20分钟变化: 沪{h_tail:+.1f}亿 深{s_tail:+.1f}亿")

# === 备注 ===
print(f"\n=== 数据说明 ===")
print(f"  数据源: 同花顺 hexin.cn hsgtApi")
print(f"  注意: 2024.8.19起北向每日净买卖不再披露总量，")
print(f"        本数据为交易所公布的当日可用额度变化推算")
