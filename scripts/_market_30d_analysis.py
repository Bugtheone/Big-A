#!/usr/bin/env python3
"""近30个交易日大盘整体分析 — 八大指数 + 阶段划分 + 大小盘剪刀差"""
import sys, io, os, math, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from scripts.tencent_api import get_tencent


if __name__ == '__main__':
    tc = get_tencent()
    
    # 纯数字代码 + 显式市场 (fetch_kline 返回: [date, high, close, low, open, vol])
    INDEXES = {
        "上证指数": ("000001", "sh"), "深证成指": ("399001", "sz"),
        "创业板指": ("399006", "sz"), "科创50": ("000688", "sh"),
        "上证50": ("000016", "sh"),   "沪深300": ("000300", "sh"),
        "中证500": ("000905", "sh"),   "中证1000": ("000852", "sh"),
    }
    
    results = []
    for name, (code, market) in INDEXES.items():
        raw = tc.fetch_kline(code, 30, market)
        if not raw:
            print(f"[SKIP] {name} 数据获取失败")
            continue
        # 转为 dict: {date, open, close, high, low, vol}
        kline = [{"date": r[0], "open": r[4], "close": r[2], "high": r[1], "low": r[3], "vol": r[5]} for r in raw]
        closes = [d["close"] for d in kline]
        highs = [d["high"] for d in kline]
        lows = [d["low"] for d in kline]
    
        first_close = closes[0]
        last_close = closes[-1]
        chg_pct = (last_close - first_close) / first_close * 100
    
        period_high = max(highs)
        period_low = min(lows)
        high_pct = (period_high - first_close) / first_close * 100
        low_pct = (period_low - first_close) / first_close * 100
    
        up_days = sum(1 for d in kline if d["close"] > d["open"])
        down_days = sum(1 for d in kline if d["close"] < d["open"])
    
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / max(len(returns) - 1, 1)
        annual_vol = math.sqrt(variance) * math.sqrt(250) * 100
    
        results.append({
            "name": name, "chg": round(chg_pct, 2), "high_pct": round(high_pct, 2),
            "low_pct": round(low_pct, 2), "up": up_days, "down": down_days,
            "vol": round(annual_vol, 1), "first": first_close, "last": last_close,
            "kline": kline,
        })
        time.sleep(0.15)
    
    # ============ 一、总览表 ============
    print("=" * 95)
    print("                    近30个交易日大盘全景分析 (2026-07-23)")
    print("=" * 95)
    
    print(f"\n{'指数':10s} │ {'30日前':>10s} │ {'今日':>10s} │ {'涨跌幅':>8s} │ {'最高%':>8s} │ {'最低%':>8s} │ {'阳线':>5s} │ {'阴线':>5s} │ 年化波")
    print("-" * 95)
    
    for r in results:
        print(f"{r['name']:10s} │ {r['first']:10.2f} │ {r['last']:10.2f} │ {r['chg']:+7.2f}% │ {r['high_pct']:+7.2f}% │ {r['low_pct']:+7.2f}% │ {r['up']:4d}天 │ {r['down']:4d}天 │ {r['vol']:5.1f}%")
    
    # ============ 二、阶段划分 ============
    print("\n" + "=" * 95)
    print("三阶段划分 (以沪深300为基准)")
    print("-" * 95)
    
    hs300 = next(r for r in results if r["name"] == "沪深300")
    kl = hs300["kline"]
    n = len(kl)
    segments = [
        ("前1/3  D-30~D-20", 0, n // 3),
        ("中1/3  D-20~D-10", n // 3, 2 * n // 3),
        ("后1/3  D-10~今日", 2 * n // 3, n),
    ]
    
    rep_indices = ["上证指数", "上证50", "沪深300", "中证1000", "科创50"]
    
    for seg_name, start, end in segments:
        seg_dates = f"{kl[start]['date']}~{kl[end-1]['date']}"
        print(f"\n  【{seg_name}】 {seg_dates}")
        for idx_name in rep_indices:
            r = next(x for x in results if x["name"] == idx_name)
            seg = r["kline"][start:end]
            seg_chg = (seg[-1]["close"] - seg[0]["close"]) / seg[0]["close"] * 100
            seg_high = (max(d["high"] for d in seg) - seg[0]["close"]) / seg[0]["close"] * 100
            seg_low = (min(d["low"] for d in seg) - seg[0]["close"]) / seg[0]["close"] * 100
            bar = "#" * max(1, int(abs(seg_chg) * 2))
            print(f"    {idx_name:6s}: {seg_chg:+7.2f}% {bar} (区间振幅 {seg_high:+.0f}%~{seg_low:+.0f}%)")
    
    # ============ 三、整体统计 ============
    print("\n" + "=" * 95)
    print("整体统计")
    print("-" * 95)
    
    up_count = sum(1 for r in results if r["chg"] > 0)
    down_count = sum(1 for r in results if r["chg"] < 0)
    avg_vol = sum(r["vol"] for r in results) / len(results)
    
    sz50 = next(r for r in results if r["name"] == "上证50")
    zz1000 = next(r for r in results if r["name"] == "中证1000")
    kc50 = next(r for r in results if r["name"] == "科创50")
    sz = next(r for r in results if r["name"] == "上证指数")
    
    best = max(results, key=lambda r: r["chg"])
    worst = min(results, key=lambda r: r["chg"])
    most_vol = max(results, key=lambda r: r["vol"])
    
    print(f"  30日涨跌比: {up_count}涨 / {down_count}跌")
    print(f"  平均年化波动率: {avg_vol:.1f}%")
    print(f"  涨幅冠军: {best['name']} ({best['chg']:+.2f}%)")
    print(f"  跌幅最大: {worst['name']} ({worst['chg']:+.2f}%)")
    print(f"  波动最大: {most_vol['name']} ({most_vol['vol']:.1f}%)")
    print(f"  大小盘剪刀差: 上证50 {sz50['chg']:+.2f}% vs 中证1000 {zz1000['chg']:+.2f}% (差值 {abs(sz50['chg']-zz1000['chg']):.1f}个百分点)")
    
    # ============ 四、上证阴阳线分布 ============
    print("\n" + "=" * 95)
    print("上证指数每日涨跌分布")
    print("-" * 95)
    sz_kline = sz["kline"]
    big_up = [d for d in sz_kline if (d["close"] - d["open"]) / d["open"] > 0.01]
    big_down = [d for d in sz_kline if (d["close"] - d["open"]) / d["open"] < -0.01]
    flat = [d for d in sz_kline if abs((d["close"] - d["open"]) / d["open"]) <= 0.01]
    
    print(f"  大阳线(+1%以上): {len(big_up)}天")
    print(f"  大阴线(-1%以下): {len(big_down)}天")
    print(f"  小星线(±1%内):  {len(flat)}天")
    print(f"  阳/阴/星比例: {len(big_up)}/{len(big_down)}/{len(flat)}")
    
    # ============ 五、单日暴跌/暴涨标记 ============
    print("\n" + "=" * 95)
    print("极端日标记 (沪深300当日涨跌>2% 或 <-2%)")
    print("-" * 95)
    for i in range(1, len(kl)):
        chg_i = (kl[i]["close"] - kl[i-1]["close"]) / kl[i-1]["close"]
        if abs(chg_i) > 0.02:
            tag = "暴跌" if chg_i < 0 else "暴涨"
            bar = "!" * min(5, int(abs(chg_i) * 50))
            print(f"  {kl[i]['date']} {tag} {chg_i*100:+.2f}% {bar} 收{kl[i]['close']:.0f}")
    
    # ============ 六、15日前半 vs 后半对比 ============
    print("\n" + "=" * 95)
    print("前15日 vs 后15日 对比")
    print("-" * 95)
    
    half = n // 2
    for idx_name in rep_indices:
        r = next(x for x in results if x["name"] == idx_name)
        kl_r = r["kline"]
        first_half = (kl_r[half-1]["close"] - kl_r[0]["close"]) / kl_r[0]["close"] * 100
        second_half = (kl_r[-1]["close"] - kl_r[half-1]["close"]) / kl_r[half-1]["close"] * 100
        arrow = "→" if first_half > 0 and second_half < 0 else "↗" if first_half < 0 and second_half > 0 else "→"
        print(f"  {idx_name:6s}: 前15日 {first_half:+7.2f}% {arrow} 后15日 {second_half:+7.2f}%")
    
    # ============ 七、综合判定 ============
    print("\n" + "=" * 95)
    print("综合判定")
    print("-" * 95)
    
    # 判定逻辑
    if avg_vol > 35:
        vol_level = "极高波动"
    elif avg_vol > 25:
        vol_level = "高波动"
    else:
        vol_level = "中等波动"
    
    scissors = sz50["chg"] - zz1000["chg"]
    if scissors > 10:
        style = "极致大盘偏好 (剪刀差>10pp)"
    elif scissors > 5:
        style = "明显大盘偏好"
    elif scissors > 0:
        style = "微弱大盘偏好"
    elif scissors > -5:
        style = "微弱小盘偏好"
    else:
        style = "极致小盘偏好"
    
    print(f"  波动级别: {vol_level} ({avg_vol:.1f}% 年化)")
    print(f"  风格偏向: {style}")
    print(f"  涨跌结构: {up_count}涨{down_count}跌")
    print(f"  科创50振幅: {kc50['high_pct']:+.0f}%~{kc50['low_pct']:+.0f}% (全市场最大)")
    print(f"  上证50振幅: {sz50['high_pct']:+.0f}%~{sz50['low_pct']:+.0f}% (最稳)")
    print()
    
    # 周期判定
    hs_chg = hs300["chg"]
    hs_first = (kl[half-1]["close"] - kl[0]["close"]) / kl[0]["close"] * 100
    hs_second = (kl[-1]["close"] - kl[half-1]["close"]) / kl[half-1]["close"] * 100
    
    if hs_first > 2 and hs_second < -5:
        print("  **周期判定: 牛转熊完成** — 前段牛市上涨,后段崩塌回吐全部涨幅")
    elif hs_first > 0 and hs_second < 0:
        print("  **周期判定: 牛转熊进行中** — 前涨后跌但尚未完全崩塌")
    elif hs_first < -5 and hs_second > 2:
        print("  **周期判定: 超跌反弹** — 前段暴跌后段修复")
    elif hs_first < 0 and hs_second > 0:
        print("  **周期判定: 触底企稳** — 前段下跌后段弱反弹")
    elif hs_first < 0 and hs_second < -5:
        print("  **周期判定: 持续阴跌** — 两段均下跌,无有效反弹")
    elif abs(hs_chg) < 3:
        print("  **周期判定: 窄幅横盘** — 30日整体变化不大")
    else:
        print(f"  **周期判定: 结构性震荡** — 前{hs_first:+.1f}%后{hs_second:+.1f}%")
    
    print()
    print("=" * 95)

