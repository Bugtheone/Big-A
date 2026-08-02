# -*- coding: utf-8 -*-
"""止跌确认综合判断 - 五层信号塔框架
K线格式: [date, high, close, low, open, volume]"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from scripts.tencent_api import get_tencent
from scripts.eastmoney_api import get_eastmoney
from scripts.data_gate import gate


if __name__ == '__main__':
    tc = get_tencent()
    em = get_eastmoney()
    gate.reset()
    
    # K线字段索引: [date, high, close, low, open, volume]
    I_HIGH, I_CLOSE, I_LOW, I_OPEN, I_VOL = 1, 2, 3, 4, 5
    
    INDEXES = [
        ('上证指数', '000001', 'sh'),
        ('深证成指', '399001', 'sz'),
        ('创业板指', '399006', 'sz'),
        ('科创50',   '000688', 'sh'),
        ('上证50',   '000016', 'sh'),
        ('沪深300',  '000300', 'sh'),
        ('中证500',  '000905', 'sh'),
        ('中证1000', '000852', 'sh'),
    ]
    
    KEY_INDICES = ['上证指数', '上证50', '沪深300', '中证1000', '科创50']
    TODAY = date.today().strftime("%Y-%m-%d")
    
    def ma(values, n):
        if len(values) < n:
            return None
        return sum(values[-n:]) / n
    
    print("=" * 70)
    print("  止跌确认五层信号塔综合分析 - %s" % TODAY)
    print("=" * 70)
    
    # ═══════════════════════════ 数据采集 ═══════════════════════════
    print("\n>>> 数据采集中...")
    
    kline_data = {}
    for name, code, mkt in INDEXES:
        try:
            k = tc.fetch_kline(code, 15, mkt)
            if k and len(k) >= 5:
                kline_data[name] = k
        except Exception as e:
            print("  WARN: %s -> %s" % (name, e))
    
    print("  K线: %d/%d 指数" % (len(kline_data), len(INDEXES)))
    
    turnover = tc.fetch_turnover_simple()
    print("  成交额: %.0f亿" % turnover if turnover else "  成交额: N/A")
    
    try:
        ch = em.fetch_board_summary()
    except Exception:
        ch = {}
    zt = ch.get('zt_count', 0) if ch else 0
    br = ch.get('zr_rate', 0) if ch else 0
    print("  涨停: %d家 炸板率: %.1f%%" % (zt, br))
    
    try:
        north = em.fetch_north_flow(3)
    except Exception:
        north = []
    print("  北向: %d条" % len(north))
    
    # ═══════════════════════════ 第一层 ═══════════════════════════
    print("\n" + "-" * 50)
    print("第一层：价格结构 (需3-5天)")
    print("-" * 50)
    
    L1 = 0
    for name in KEY_INDICES:
        if name not in kline_data:
            continue
        kl = kline_data[name]
        close = [r[I_CLOSE] for r in kl]
        high  = [r[I_HIGH] for r in kl]
        low   = [r[I_LOW] for r in kl]
    
        nll = min(low[-3:])
        pll = min(low[-8:-3]) if len(low) >= 8 else nll
        no_new_low = nll >= pll * 0.995
    
        m5 = ma(close, 5)
        above_ma5 = close[-1] > m5 if m5 else False
    
        hh_hl = high[-1] > high[-2] and low[-1] > low[-2] if len(kl) >= 2 else False
    
        sigs = []
        if no_new_low: sigs.append("未创新低")
        if above_ma5: sigs.append(">MA5(%.1f)" % m5)
        if hh_hl: sigs.append("高低点上移")
        sc = sum([no_new_low, above_ma5, hh_hl])
    
        tag = "[PASS]" if sc >= 2 else ("[WARN]" if sc >= 1 else "[FAIL]")
        print("  %-6s %-8s: %7.2f | %s" % (tag, name, close[-1], " ".join(sigs) if sigs else "---"))
        if sc >= 2:
            L1 += 1
    
    print("  L1: %d/%d" % (L1, len([n for n in KEY_INDICES if n in kline_data])))
    
    # ═══════════════════════════ 第二层 ═══════════════════════════
    print("\n" + "-" * 50)
    print("第二层：量价配合 (需3天)")
    print("-" * 50)
    
    L2 = 0
    if '上证指数' in kline_data:
        sz = kline_data['上证指数']
        close = [r[I_CLOSE] for r in sz]
        vol   = [r[I_VOL] for r in sz]
    
        av5 = sum(vol[-6:-1]) / 5 if len(vol) >= 6 else sum(vol[:-1]) / max(len(vol)-1, 1)
        vr = vol[-1] / av5 if av5 > 0 else 0
    
        if vr > 1.2:
            print("  上证量: %.0f亿 | 放量(%.1fx)" % (vol[-1]/1e8, vr))
        elif vr < 0.6:
            print("  上证量: %.0f亿 | 缩量(%.1fx) 抛压衰竭" % (vol[-1]/1e8, vr))
            L2 += 1
        else:
            print("  上证量: %.0f亿 | 量平(%.1fx)" % (vol[-1]/1e8, vr))
    
        sync = 0
        for i in range(max(1, len(close)-3), len(close)):
            chg = close[i] - close[i-1]
            if chg > 0 and vol[i] > vol[i-1]:
                sync += 1
            elif chg < 0 and vol[i] < vol[i-1]:
                sync += 1
        print("  量价同步: %d/3天" % sync)
        if sync >= 2:
            L2 += 1
    
    if turnover:
        if turnover > 20000:
            print("  两市%.0f亿 充沛" % turnover)
            L2 += 1
        elif turnover > 15000:
            print("  两市%.0f亿 中等" % turnover)
        else:
            print("  两市%.0f亿 不足" % turnover)
    
    print("  L2: %d/3" % L2)
    
    # ═══════════════════════════ 第三层 ═══════════════════════════
    print("\n" + "-" * 50)
    print("第三层：广度确认")
    print("-" * 50)
    
    L3 = 0
    if ch:
        dt = ch.get('dt_count', 0)
        ml = ch.get('zt_high_lb', 0)
        print("  涨停:%d 跌停:%d 炸板率:%.1f%% 最高连板:%d" % (zt, dt, br, ml))
    
        if zt >= 80:
            print("  [PASS] 涨停活跃")
            L3 += 1
        elif zt >= 50:
            print("  [WARN] 涨停%d一般" % zt)
        else:
            print("  [FAIL] 涨停%d冷清" % zt)
    
        if br <= 25:
            print("  [PASS] 封板稳健")
            L3 += 1
        else:
            print("  [WARN] 封板偏弱" if br <= 35 else "  [FAIL] 封板差")
    
    if '上证50' in kline_data and '中证1000' in kline_data:
        s50 = kline_data['上证50']
        z1k = kline_data['中证1000']
        if len(s50) >= 5 and len(z1k) >= 5:
            s5 = (s50[-1][I_CLOSE] - s50[-5][I_CLOSE]) / s50[-5][I_CLOSE] * 100
            z5 = (z1k[-1][I_CLOSE] - z1k[-5][I_CLOSE]) / z1k[-5][I_CLOSE] * 100
            diff = s5 - z5
            print("  5日: 上证50 %+.2f%% vs 中证1000 %+.2f%% (差%+.1f%%)" % (s5, z5, diff))
            if abs(diff) < 2:
                print("  [PASS] 大小票同步")
                L3 += 1
            elif diff > 5:
                print("  [FAIL] 剪刀差极大 抱团防御")
            else:
                print("  [WARN] 略有分化")
    
    print("  L3: %d/3" % L3)
    
    # ═══════════════════════════ 第四层 ═══════════════════════════
    print("\n" + "-" * 50)
    print("第四层：资金面")
    print("-" * 50)
    
    L4 = 0
    if north and len(north) >= 2:
        flows = [(d.get('date',''), d.get('net_flow', 0)) for d in north[:3]]
        pos = sum(1 for _, f in flows if f > 0)
        tot = sum(f for _, f in flows)
        for dt, f in flows:
            print("  %s %+.1f亿" % (dt[-5:] if dt else "?", f))
        if pos >= 3:
            print("  [PASS] 连续3日净流入")
            L4 = 2
        elif pos >= 2:
            print("  [PASS] %d/3日净流入" % pos)
            L4 = 1
        elif tot > 0:
            print("  [WARN] %d日流入但不稳" % pos)
        else:
            print("  [FAIL] 北向持续流出")
    else:
        print("  [WARN] 数据不足")
    
    print("  L4: %d/2" % L4)
    
    # ═══════════════════════════ 第五层 ═══════════════════════════
    print("\n" + "-" * 50)
    print("第五层：均线系统 (周级别)")
    print("-" * 50)
    
    L5 = 0
    for name in ('上证50', '沪深300', '中证1000'):
        if name not in kline_data:
            continue
        kl = kline_data[name]
        c = [r[I_CLOSE] for r in kl]
        if len(c) < 10:
            continue
        m5 = ma(c, 5)
        m10 = ma(c, 10)
        m20 = ma(c, 20) if len(c) >= 20 else None
    
        pts = []
        pts.append(">MA5" if c[-1] > m5 else "<MA5")
        if m5 > m10:
            pts.append("MA5>MA10")
            if name == '上证50':
                L5 += 1
        else:
            pts.append("MA5<MA10")
    
        print("  %s: %7.2f | MA5:%.1f MA10:%.1f %s | %s" % (
            name, c[-1], m5, m10,
            ("MA20:%.1f" % m20) if m20 else "",
            " ".join(pts)))
    
    # 极端波动
    if '上证指数' in kline_data:
        sz = kline_data['上证指数']
        amps = []
        for r in sz[-5:]:
            a = (r[I_HIGH] - r[I_LOW]) / r[I_CLOSE] * 100
            amps.append(a)
        avg = sum(amps) / len(amps)
        ext = sum(1 for a in amps if a > 2)
        if ext > 0:
            print("  [FAIL] 近5日%d次极端波动(>2%%)" % ext)
            print("  振幅: %s" % " ".join("%.1f%%" % a for a in amps))
        elif avg < 1.0:
            print("  [PASS] 低波(%.1f%%)" % avg)
            L5 += 1
        else:
            print("  [WARN] 振幅%.1f%%" % avg)
    
    print("  L5: %d/2" % L5)
    
    # ═══════════════════════════ 综合判定 ═══════════════════════════
    print("\n" + "=" * 70)
    print("  综合判定")
    print("=" * 70)
    
    max_n = len([n for n in KEY_INDICES if n in kline_data])
    MAX = max_n + 3 + 3 + 2 + 2
    TOTAL = L1 + L2 + L3 + L4 + L5
    
    print("  第一层(价格): %d/%d" % (L1, max_n))
    print("  第二层(量价): %d/3" % L2)
    print("  第三层(广度): %d/3" % L3)
    print("  第四层(资金): %d/2" % L4)
    print("  第五层(均线): %d/2" % L5)
    print("  -------------------")
    print("  总计: %d/%d (%.0f%%)" % (TOTAL, MAX, TOTAL/MAX*100))
    
    print("")
    if TOTAL >= MAX * 0.8:
        v = "[初步止跌确认] 多维度信号共振，可以认为止跌有效"
    elif TOTAL >= MAX * 0.6:
        v = "[部分止跌信号] 多个信号出现但未充分共振，需再观察2-3天确认"
    elif TOTAL >= MAX * 0.4:
        v = "[止跌信号偏弱] 大概率仍在调整中，不建议抄底"
    else:
        v = "[未止跌] 下行趋势延续，信号偏空"
    
    print("  判定: %s" % v)
    print("")
    print("=" * 70)
    print("数据验证:")
    gate.print_audit()

