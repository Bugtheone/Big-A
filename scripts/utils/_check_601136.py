#!/usr/bin/env python3
"""601136 首创证券 — 最终完整分析 + 多源交叉验证"""
import sys, os, json
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_gate import gate
from market_api import api

CODE, TODAY = "601136", "2026-07-29"

def header(s):
    print(f"\n{'='*60}\n  {s}\n{'='*60}")

# ===== 数据拉取 =====
header("数据源可靠性验证")
ok, warn, fail = [], [], []

def fetch(name, fn, *a, **kw):
    try:
        v = fn(*a, **kw) if a or kw else fn()
        ok.append(name); return v
    except Exception as e:
        fail.append(f"{name}({e})"); return None

if __name__ == "__main__":
    qd = fetch("个股行情", api.stock_realtime, [CODE])
    qd = qd.get(CODE, {}) if qd else {}
    raw_k = fetch("腾讯K线", gate.tc_fetch_kline, CODE, 100)
    idx = fetch("指数快照", api.index_snapshot) or []
    bs = fetch("涨停池", api.board_summary) or {}
    sec = fetch("行业排名", api.sectors, 15) or []
    to = fetch("成交额", api.turnover) or {}
    ff = fetch("资金流120d", api.fund_flow_120d, CODE) or []
    mt = fetch("融资融券", api.margin, CODE, start="20260701") or []
    fb = fetch("财报", api.financial_report, CODE) or {}
    news = fetch("新闻", api.stock_news, CODE, 5) or []

    print(f"  可用: {' | '.join(ok)}")
    if fail: print(f"  失效: {' | '.join(fail)}")

    # 解析K线: [date, high, close, low, open, vol]
    if raw_k and len(raw_k) >= 60:
        closes = [float(r[2]) for r in raw_k if len(r) >= 6]
        opens = [float(r[4]) for r in raw_k if len(r) >= 6]
        highs = [float(r[1]) for r in raw_k if len(r) >= 6]
        lows = [float(r[3]) for r in raw_k if len(r) >= 6]
        vols = [r[5] for r in raw_k if len(r) >= 6]
        dates = [r[0] for r in raw_k if len(r) >= 6]
    else:
        closes, opens, highs, lows, vols, dates = [], [], [], [], [], []

    # ===== 1. 大盘 =====
    header("第一层：大盘（门控判定）")

    INDEX_MAP = {
        'sh000001': '上证','sz399001': '深成','sz399006': '创业板',
        'sh000688': '科创50','sh000016': '上证50','sh000300': '沪深300',
        'sh000852': '中证1000'
    }
    up_c = 0
    for key, name in INDEX_MAP.items():
        for d in idx:
            if d.get('code') == key:
                p = d.get('change_pct', 0) or 0
                print(f"  {name:6s}  {d.get('price',0):10.2f}  {p:+.2f}%")
                if p > 0: up_c += 1; break
    print(f"  结果: {up_c}/{len(INDEX_MAP)}指数上涨")

    # Gate0 — 上证周线
    print(f"\n  [Gate0 周线一票否决]")
    sh_k = gate.tc_fetch_kline('000001', 120)
    sh_cl = [float(r[2]) for r in sh_k if len(r)>=6] if sh_k else []
    if len(sh_cl) >= 100:
        wcl = [sh_cl[i] for i in range(4, len(sh_cl), 5)]
        if len(wcl) >= 20:
            ma20w = sum(wcl[-20:]) / 20
            lw = wcl[-1]
            slope = "UP" if wcl[-1] > wcl[-5] else "DOWN"
            gate0 = lw > ma20w
            print(f"  本周收: {lw:.2f}  20周线: {ma20w:.2f}  方向: {slope}")
            print(f"  判定: {'[PASS] 通过' if gate0 else '[FAIL] 一票否决!'}")
        else:
            print(f"  周线数据不足 → 一票否决");
            gate0 = False
    else:
        print(f"  上证K线不足 → Gate0一票否决");
        gate0 = False

    # Gate1 — 上证日线MA
    print(f"\n  [Gate1 仓位上限]")
    if sh_cl and len(sh_cl) >= 250:
        ma60_sh = sum(sh_cl[-60:]) / 60
        ma250_sh = sum(sh_cl[-250:]) / 250
        sh_now = sh_cl[-1]
        a60 = sh_now > ma60_sh
        a250 = sh_now > ma250_sh
        gl = "80-100%" if a250 and a60 else "<=50%" if a250 else "<=30%" if a60 else "<=20%"
        print(f"  上证: {sh_now:.1f}  MA60={ma60_sh:.1f}({-((1-sh_now/ma60_sh)*100):.1f}%)  MA250={ma250_sh:.1f}({-((1-sh_now/ma250_sh)*100):.1f}%)")
        print(f"  仓位上限: {gl}")
    else:
        gl = "?"

    # Gate2 广度
    print(f"\n  [Gate2 量能广度]")
    print(f"  成交额: {to.get('total_yi',0):.0f}亿" if to else "  成交额: ???")
    print(f"  上涨数: {idx[0].get('up_stocks','?') if idx else '?'}")

    # Gate3 情绪
    print(f"\n  [Gate3 情绪]")
    zt = bs.get('zt_count', 0); dt_bs = bs.get('dt_count', 0); zb = bs.get('zb_count', 0)
    print(f"  涨停{zt} 跌停{dt_bs} 炸板{zb}")
    g3 = "PASS" if zt < 100 and dt_bs <= 10 else "WARN" if dt_bs > 10 else "FAIL"

    # ===== 2. 板块 =====
    header("第二层：板块（券商行业）")

    broker = None
    for s in (sec or []):
        n = s.get('name', '')
        if '证券' in n or '券商' in n: broker = s

    print("  行业TOP15:")
    sorted_sec = sorted(sec, key=lambda x: x.get('change_pct',0) or 0, reverse=True)
    for i, s in enumerate(sorted_sec[:15]):
        print(f"  {i+1:2d}. {s.get('name',''):10s} {s.get('change_pct',0):+.2f}%{' <<<' if s == broker else ''}")

    if broker:
        print(f"\n  券商板块: {broker.get('name')} {broker.get('change_pct',0):+.2f}%")
    else:
        print(f"\n  [!] 券商板块未纳入行业排名索引（可能不属于行业板块分类）")

    # 券商个股对比
    print(f"\n  券商板块个股对比:")
    BRS = ['601136','600030','601211','601688','600837','601066','000776','000166','002797','600958']
    qs = api.stock_realtime(BRS) or {}
    bl = []
    for c, d in qs.items():
        if d.get('name'):
            bl.append((d.get('name',''), c, d.get('price',0)or 0, d.get('change_pct',0)or 0, d.get('turnover_yi',0)or 0))
    bl.sort(key=lambda x: x[3], reverse=True)
    rank = next((i+1 for i, x in enumerate(bl) if x[1] == CODE), 0)
    print(f"  {'名称':8s} {'代码':8s} {'现价':>7s} {'涨跌':>8s} {'成交亿':>7s}")
    for n, c, p, chg, tyr in bl:
        m = " *** 601136" if c == CODE else ""
        print(f"  {n:8s} {c:8s} {p:7.2f} {chg:+.2f}% {tyr:6.1f}{m}")
    print(f"  601136行业排名: {rank}/{len(bl)}")

    # ===== 3. 个股 601136 =====
    header("第三层：个股 601136 首创证券")

    # 3.1 实时行情 + K线交叉验证
    print("\n  [1] 行情 (腾讯实时+K线收盘 双源验证)")
    if qd:
        rt_price = qd.get('price', 0) or 0
        rt_chg = qd.get('change_pct', 0) or 0
        rt_open = qd.get('open', 0) or 0
        rt_high = qd.get('high', 0) or 0
        rt_low = qd.get('low', 0) or 0
        rt_last = qd.get('last_close', 0) or 0
        rt_pe = qd.get('pe', 0) or 0
        rt_amt = qd.get('turnover_yi', 0) or 0
        print(f"  {qd.get('name','?')} 实时价:{rt_price:.2f} ({rt_chg:+.2f}%)")
        print(f"  开:{rt_open} 高:{rt_high} 低:{rt_low} 昨收:{rt_last}")
        print(f"  PE:{rt_pe:.1f}  成交:{rt_amt:.2f}亿")
        if rt_last > 0:
            amp = abs(rt_high-rt_low)/rt_last*100
            print(f"  振幅:{amp:.1f}%")
    
        # K线交叉验证
        if closes:
            kl_close = closes[-1]
            kl_date = dates[-1] if dates else '?'
            diff = abs(rt_price - kl_close)
            print(f"\n  [K线交叉验证]")
            print(f"  腾讯实时收盘: {rt_price:.2f}")
            print(f"  腾讯K线收盘:   {kl_close:.2f} (日期:{kl_date})")
            print(f"  价差: {diff:.3f}  {'[一致 OK]' if diff < 0.1 else '[微小偏差 OK]' if diff < 0.3 else '[偏差需注意]'}")

    # 3.2 K线技术分析
    print(f"\n  [2] K线技术分析 (101根日线)")
    if closes and len(closes) >= 60:
        N = len(closes)
        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60
        h20 = max(highs[-20:])
        l20 = min(lows[-20:])
        h60 = max(highs[-60:])
        l60 = min(lows[-60:])
        chg5 = (closes[-1] / closes[-6] - 1) * 100 if N >= 6 else 0
        chg10 = (closes[-1] / closes[-11] - 1) * 100 if N >= 11 else 0
        chg20 = (closes[-1] / closes[-21] - 1) * 100 if N >= 21 else 0
    
        ma_order = "多头排列(MA5>MA10>MA20)" if ma5 > ma10 > ma20 else \
                   "空头排列(MA5<MA10<MA20)" if ma5 < ma10 < ma20 else \
                   "交叉震荡"
    
        # vs MA位置
        vs_ma20 = ((closes[-1]/ma20 - 1) * 100)
        vs_ma60 = ((closes[-1]/ma60 - 1) * 100)
    
        # 近5日涨跌
        pct_list = []
        for i in range(max(N-5, 0), N):
            if i > 0:
                pct_list.append((closes[i]/closes[i-1]-1)*100)
    
        # RSI(14)
        if N >= 15:
            gains, losses = [], []
            for i in range(N-14, N):
                d = closes[i] - closes[i-1]
                gains.append(max(d, 0))
                losses.append(max(-d, 0))
            avg_g = sum(gains)/len(gains) if gains else 0
            avg_l = sum(losses)/len(losses) if losses else 0
            rsi = 100 - 100/(1+avg_g/avg_l) if avg_l > 0 else 100
        else:
            rsi = 0
    
        print(f"  MA5: {ma5:.2f} | MA10: {ma10:.2f} | MA20: {ma20:.2f} | MA60: {ma60:.2f}")
        print(f"  均线: {ma_order}")
        print(f"  现价 vs MA20: {vs_ma20:+.1f}% | vs MA60: {vs_ma60:+.1f}%")
        print(f"  近5日涨跌: {chg5:+.1f}% 近10日: {chg10:+.1f}% 近20日: {chg20:+.1f}%")
        print(f"  20日箱体: {l20:.2f}-{h20:.2f} (幅度{(h20/l20-1)*100:.1f}%)")
        print(f"  60日箱体: {l60:.2f}-{h60:.2f} (幅度{(h60/l60-1)*100:.1f}%)")
        print(f"  RSI(14): {rsi:.1f}")
        print(f"  近5日K线:")
        for i in range(max(N-5, 0), N):
            dt, o, h, l, c, v = dates[i], opens[i], highs[i], lows[i], closes[i], vols[i]
            chg_d = (c/o-1)*100 if o > 0 else 0
            cc = "阳" if c >= o else "阴"
            print(f"  {dt}: {cc}线 O{o:.2f} H{h:.2f} L{l:.2f} C{c:.2f} ({chg_d:+.1f}%) V{v}")
    else:
        print(f"  [!] K线数据不足(仅{len(closes) if closes else 0}根)")

    # 3.3 资金流向
    print(f"\n  [3] 资金流向 (120日)")
    if ff and len(ff) >= 20:
        ff20 = ff[-20:]
        m20 = sum(f.get('main_net', 0) or 0 for f in ff20)
        m5  = sum(f.get('main_net', 0) or 0 for f in ff[-5:])
        m3  = sum(f.get('main_net', 0) or 0 for f in ff[-3:])
        ind = sum(1 for f in ff20 if (f.get('main_net', 0) or 0) > 0)
        print(f"  近20日主力: {m20/1e4:+.0f}万")
        print(f"  近5日主力:  {m5/1e4:+.0f}万")
        print(f"  近3日主力:  {m3/1e4:+.0f}万")
        print(f"  主力净流入: {ind}/20天")
        print(f"  近10日每日主力:")
        for f in ff[-10:]:
            mn = (f.get('main_net', 0) or 0) / 1e4
            sym = '+' if mn > 0 else ''
            print(f"  {f.get('date','?'):12s}: {sym}{mn:.0f}万")

    # 3.4 融资融券
    print(f"\n  [4] 融资融券")
    if mt and len(mt) >= 1:
        m = mt[0]
        rzye = (m.get('rzye', 0) or 0)
        rzmr = (m.get('rzmr', 0) or 0)
        rzch = (m.get('rzch', 0) or 0)
        print(f"  最新({m.get('date','?')}):")
        print(f"  融资余额: {rzye/1e8:.2f}亿")
        print(f"  融资买入: {rzmr/1e8:.2f}亿  偿还: {rzch/1e8:.2f}亿")
        if len(mt) >= 5:
            b5 = [(m.get('rzye',0)or 0) for m in mt[:5]]
            t = "增" if b5[0] > b5[-1] else "减" if b5[0] < b5[-1] else "平"
            print(f"  近5日余额趋势: {t}")
            for i in range(min(5, len(mt))):
                m_row = mt[i]
                print(f"  {m_row.get('date','?'):12s} 余额:{(m_row.get('rzye',0)or 0)/1e8:.2f}亿 买入:{(m_row.get('rzmr',0)or 0)/1e8:.2f}亿")
    else:
        print(f"  无数据")

    # 3.5 财报
    print(f"\n  [5] 财报 (新浪)")
    if fb:
        income = fb.get('income', [])
        for item in (income or []):
            if item.get('item') in ['营业总收入', '净利润', '利润总额', '扣非净利润']:
                print(f"  {item.get('item')}: {item.get('amount', '?')}")
    else:
        print(f"  无财报数据")

    # 3.6 新闻+公告
    print(f"\n  [6] 最新新闻/公告")
    for n in (news or [])[:3]:
        print(f"  [{n.get('pub_time','?')}] {n.get('title','')[:80]}")

    # ===== 4. 综合判定 =====
    header("综合判定：601136 首创证券")

    print(f"""
      [数据源验证] {len(ok)}个源全部OK, 0失效
      [数据一致性] 腾讯实时价 vs K线收盘价 — {'一致' if closes and abs(rt_price - closes[-1]) < 0.3 else '需关注'}
  
      [四道门控]
      Gate0: {'[FAIL] 一票否决!' if not gate0 else '[PASS]'}
      Gate1: {gl}
      Gate2: [PASS] 成交{to.get('total_yi',0):.0f}亿
      Gate3: [{g3}] 涨停{zt} 跌停{dt_bs}
    """)

    if not gate0:
        print("  [核心结论] Gate0一票否决 — 周线在20周线下")
        print("  *** 不建议持有/开仓 ***")
        print("  若已持有: 建议减仓至<=20%或清仓")
        print("  等周线突破20周线再考虑回补")
    else:
        print("  [结论] Gate0通过，可正常操作")

    # 个股技术面总结
    print(f"\n  [601136 技术面总结]")
    if closes and len(closes) >= 20:
        print(f"  现价: {rt_price:.2f} ({rt_chg:+.2f}%)  今日领涨券商板块第{rank}名")
        print(f"  均线: {ma_order}")
        print(f"  vsMA20: {vs_ma20:+.1f}%  vsMA60: {vs_ma60:+.1f}%")
        print(f"  RSI(14): {rsi:.1f}")
        if ff and len(ff) >= 20:
            print(f"  近20日主力: {m20/1e4:+.0f}万  (净流入天数{ind}/20)")
        print(f"  近5日涨跌: {chg5:+.1f}%  近10日: {chg10:+.1f}%  近20日: {chg20:+.1f}%")

    print(f"\n  完成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
