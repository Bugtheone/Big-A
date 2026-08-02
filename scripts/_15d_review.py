#!/usr/bin/env python3
"""近N个交易日大盘全景回顾 - 输出到文件 v4"""
import requests, time, sys, os

DAYS = 30  # 可调：15 / 20 / 30 / 60
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

s = requests.Session()

if __name__ == '__main__':
    s.trust_env = False
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    
    # 完整代码(含前缀)
    IDX = {
        "上证指数": "sh000001",
        "深证成指": "sz399001",
        "上证50": "sh000016",
        "沪深300": "sh000300",
        "中证全指": "sh000985",
        "中证500": "sh000905",
        "中证1000": "sh000852",
        "创业板指": "sz399006",
        "科创50": "sh000688",
    }
    
    def fetch_index(full_code, n=50):
        url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={full_code},day,,,{n},qfq"
        r = s.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return None
        inner = data.get("data", {})
        if not isinstance(inner, dict):
            return None
        stock_data = inner.get(full_code, {})
        if not isinstance(stock_data, dict):
            return None
        klines = stock_data.get("day") or stock_data.get("qfqday")
        if not klines:
            return None
        result = []
        for k in klines:
            if len(k) < 6:
                continue
            result.append([k[0], float(k[2])])
        return result
    
    lines = []
    def p(s=""):
        lines.append(s)
        sys.stdout.write(s + "\n")
        sys.stdout.flush()
    
    p("=" * 70)
    p(f"  近{DAYS}个交易日大盘全景回顾 (2026-07-23收盘)")
    p("=" * 70)
    
    all_data = {}
    for name, code in IDX.items():
        k = fetch_index(code)
        if k:
            all_data[name] = k
        else:
            sys.stderr.write(f"WARN: {name} ({code}) no data\n")
        time.sleep(0.3)
    
    if not all_data:
        p("ERROR: no data fetched!")
        sys.exit(1)
    
    # 取最近N个交易日
    dates_all = sorted(set(d for d, _ in all_data.get("上证指数", [])))
    dates_N = dates_all[-DAYS:] if len(dates_all) >= DAYS else dates_all
    start_date = dates_N[0]
    end_date = dates_all[-1]
    
    p(f"\n区间: {start_date} -> {end_date} ({len(dates_N)}个交易日)")
    p()
    p(f"{'指数':<10} {'起点':>8} {'终点':>8} {'涨跌幅':>8} {'最高':>8} {'最低':>8} {'振幅':>8} {'趋势'}")
    p("-" * 72)
    
    rankings = []
    for name, klines in all_data.items():
        d_map = {d: c for d, c in klines}
        vals = [d_map.get(d) for d in dates_N if d in d_map and d_map.get(d)]
        vals = [v for v in vals if v]
        if len(vals) < 2:
            continue
        start_v, end_v = vals[0], vals[-1]
        chg = (end_v - start_v) / start_v * 100
        hi, lo = max(vals), min(vals)
        amp = (hi - lo) / start_v * 100
    
        if chg > 5:
            trend = "暴涨"
        elif chg > 2:
            trend = "强涨"
        elif chg > 0:
            trend = "微涨"
        elif chg > -3:
            trend = "微跌"
        elif chg > -8:
            trend = "强跌"
        else:
            trend = "暴跌"
    
        rankings.append((name, chg, amp, start_v, end_v, hi, lo))
        p(f"{name:<10} {start_v:>8.2f} {end_v:>8.2f} {chg:>+7.2f}% {hi:>8.2f} {lo:>8.2f} {amp:>7.2f}% {trend}")
    
    # 逐日涨跌
    p()
    p("=" * 70)
    p("  逐日涨跌表")
    p("=" * 70)
    
    idx_list = ["上证指数", "深证成指", "上证50", "沪深300", "中证全指", "科创50", "中证1000"]
    
    for i, d in enumerate(dates_N):
        row = f"{d:<12}"
        for name in idx_list:
            cur = all_data.get(name, [])
            cur_map = {dt: c for dt, c in cur}
            if i == 0:
                row += f"{'--':>9}"
            else:
                prev_d = dates_N[i-1]
                pv, cv = cur_map.get(prev_d), cur_map.get(d)
                if pv and cv:
                    dc = (cv - pv) / pv * 100
                    row += f"{dc:>+8.2f}% "
                else:
                    row += f"{'--':>9}"
        p(row)
    
    # 三段式拆解
    p()
    p("=" * 70)
    p("  三段式拆解 (5日/5日/5日)")
    p("=" * 70)
    
    n = len(dates_N)
    third = max(n // 3, 1)
    segments = [
        ("前1/3", dates_N[0], dates_N[min(third-1, n-1)]),
        ("中1/3", dates_N[min(third, n-1)], dates_N[min(2*third-1, n-1)]),
        ("后1/3", dates_N[min(2*third, n-1)], dates_N[-1]),
    ]
    
    for seg_name, sd, ed in segments:
        p(f"\n{seg_name} ({sd} -> {ed}):")
        for name in ["上证指数", "深证成指", "上证50", "中证全指", "科创50", "中证1000"]:
            cur = all_data.get(name, [])
            cur_map = {dt: c for dt, c in cur}
            sv, ev = cur_map.get(sd), cur_map.get(ed)
            if sv and ev:
                chg = (ev - sv) / sv * 100
                p(f"  {name:<8} {sv:>8.2f} -> {ev:>8.2f}  {chg:+.2f}%")
    
    # 大小盘剪刀差
    p()
    p("=" * 70)
    p("  大小盘剪刀差")
    p("=" * 70)
    
    sz50_data = all_data.get("上证50", [])
    kc50_data = all_data.get("科创50", [])
    sz50_map = {d: c for d, c in sz50_data}
    kc50_map = {d: c for d, c in kc50_data}
    
    sz50_sv = sz50_map.get(start_date)
    sz50_ev = sz50_map.get(end_date)
    kc50_sv = kc50_map.get(start_date)
    kc50_ev = kc50_map.get(end_date)
    
    if all([sz50_sv, sz50_ev, kc50_sv, kc50_ev]):
        sz50_Nd = (sz50_ev - sz50_sv) / sz50_sv * 100
        kc50_Nd = (kc50_ev - kc50_sv) / kc50_sv * 100
        gap = abs(sz50_Nd - kc50_Nd)
        p(f"  上证50 {DAYS}日: {sz50_Nd:+.2f}%")
        p(f"  科创50 {DAYS}日: {kc50_Nd:+.2f}%")
        p(f"  剪刀差: {gap:.2f}%")
        p(f"  格局: {'权重逆势护盘' if sz50_Nd > kc50_Nd else '大小齐跌' if sz50_Nd < 0 else '普涨'}")
    
    # 总结
    p()
    p("=" * 70)
    p(f"  {DAYS}日总结")
    p("=" * 70)
    
    up = [n for n, c, a, sv, ev, h, l in rankings if c >= 0]
    dn = [n for n, c, a, sv, ev, h, l in rankings if c < 0]
    best = max(rankings, key=lambda x: x[1])
    worst = min(rankings, key=lambda x: x[1])
    
    p(f"  九指数: {len(up)}涨 {len(dn)}跌")
    p(f"  涨幅最大: {best[0]} {best[1]:+.2f}% (振幅{best[2]:.2f}%)")
    p(f"  跌幅最大: {worst[0]} {worst[1]:+.2f}% (振幅{worst[2]:.2f}%)")
    
    # 单日极端
    p()
    p("=" * 70)
    p("  单日极端")
    p("=" * 70)
    
    sh_data = all_data.get("上证指数", [])
    sh_map = {d: c for d, c in sh_data}
    daily_chgs = []
    for i in range(1, len(dates_N)):
        d = dates_N[i]
        pd = dates_N[i-1]
        pv, cv = sh_map.get(pd), sh_map.get(d)
        if pv and cv:
            daily_chgs.append((d, (cv-pv)/pv*100))
    
    daily_chgs.sort(key=lambda x: x[1])
    if daily_chgs:
        bd = daily_chgs[-1]
        wd = daily_chgs[0]
        p(f"  上证最大涨幅日: {bd[0]} {bd[1]:+.2f}%")
        p(f"  上证最大跌幅日: {wd[0]} {wd[1]:+.2f}%")
    
        up_days = sum(1 for d, c in daily_chgs if c > 0)
        dn_days = sum(1 for d, c in daily_chgs if c < 0)
        flat_days = len(daily_chgs) - up_days - dn_days
        p(f"  阳线{up_days}天 / 阴线{dn_days}天 / 平{flat_days}天")
    
    # 写入文件
    out_path = os.path.join(BASE_DIR, "log", f"20260723_{DAYS}日大盘全景回顾.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    p(f"\n报告已保存: {out_path}")

