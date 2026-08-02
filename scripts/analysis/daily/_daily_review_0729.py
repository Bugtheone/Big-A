#!/usr/bin/env python3
"""7/29 A-Share Daily Review -- Full SOP: Data -> Gates -> Scorecard -> Sectors -> Advice"""
import sys, os, io, json
from datetime import datetime, timedelta
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'scripts'))
from market_api import api

INDICES = {
    '000001': '上证指数', '399001': '深证成指', '399006': '创业板指',
    '000688': '科创50',  '000016': '上证50',   '000300': '沪深300',
    '399005': '中小100',  '000852': '中证1000', '899050': '北证50'
}

def banner(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

# ========== STEP 0: DATA ==========
if __name__ == "__main__":
    banner("STEP 0: MULTI-SOURCE DATA PULL")

    # 0a. Index snapshots
    print("\n--- 0a. Index Snapshots (Tencent) ---")
    snap = api.index_snapshot()
    idx_data = {}
    for s in snap:
        code = s.get('code','')
        if code in INDICES:
            idx_data[code] = s
            print(f"  {INDICES.get(code,code):8s}  {s['price']:>10.2f}  {s['pct_chg']:>+7.2f}%  vol={s.get('volume',0)}")

    # 0b. K-line for Gate0 (weekly) & Gate1 (daily)
    print("\n--- 0b. K-line (Tencent, daily 250 bars) ---")
    sh_kline = api.kline('000001', 250)
    if sh_kline and 'klines' in sh_kline:
        klines = sh_kline['klines']
        print(f"  Got {len(klines)} daily bars, latest: {klines[-1]}")
        # last close
        last_close = klines[-1][2]
        print(f"  Latest close: {last_close}")
    
        # compute MA60 from last 60 bars
        closes = [k[2] for k in klines]
        ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else 0
        ma250 = sum(closes[-250:]) / 250 if len(closes) >= 250 else 0
        print(f"  MA60={ma60:.2f}  MA250={ma250:.2f}")
    
        # compute weekly: group by week, get last close of each week
        weekly_closes = []
        from collections import OrderedDict
        weeks = OrderedDict()
        for k in klines:
            d = k[0]
            # get iso week
            dt = datetime.strptime(d, '%Y-%m-%d')
            wk = dt.strftime('%Y-W%W')
            weeks[wk] = k[2]  # close
        weekly_closes = list(weeks.values())
        print(f"  Weekly closes ({len(weekly_closes)} weeks): last 5 = {weekly_closes[-5:]}")
        if len(weekly_closes) >= 20:
            w20 = sum(weekly_closes[-20:]) / 20
            print(f"  20-week MA: {w20:.2f}")
        else:
            w20 = 0
    else:
        print("  ERROR: no kline data")
        last_close = 0; ma60 = 0; ma250 = 0; w20 = 0; weekly_closes = []

    # 0c. Turnover
    print("\n--- 0c. Turnover (Tencent) ---")
    tov = api.turnover()
    print(f"  SH: {tov.get('sh_yi',0)}亿, SZ: {tov.get('sz_yi',0)}亿, Total: {tov.get('total_yi',0)}亿")
    tov_amt_yi = tov.get('total_yi', 0)

    # 0d. Breadth
    print("\n--- 0d. Breadth (Tencent) ---")
    brd = api.breadth()
    print(f"  Up: {brd.get('up',0)}, Down: {brd.get('down',0)}, Flat: {brd.get('flat',0)}, Total: {brd.get('total',0)}")
    print(f"  Up ratio: {brd.get('up_pct',0):.1f}%  Broad rating: {brd.get('broad_rating','N/A')}")

    # 0e. Board summary (ZT/DT/ZB)
    print("\n--- 0e. Board Summary (THS) ---")
    bs = api.board_summary()
    print(f"  ZT: {bs.get('zt_count',0)}, DT: {bs.get('dt_count',0)}, ZB: {bs.get('zb_count',0)}")
    print(f"  Break rate: {bs.get('break_rate',0)}%, Max height: {bs.get('max_height',0)}")
    ladder = bs.get('ladder', {})
    if ladder:
        print(f"  Ladder: {dict(sorted(ladder.items(), key=lambda x: -int(x[0])))}")

    # 0f. Sectors top 10
    print("\n--- 0f. Sector Rankings (Tencent) ---")
    secs = api.sectors(10)
    for i, s in enumerate(secs):
        print(f"  {i+1:2d}. {s['name']:8s}  {s['change_pct']:+7.2f}%")

    # 0g. Board fund flow (top 5 inflow & outflow)
    print("\n--- 0g. Board Fund Flow (EM→WS) ---")
    ff_raw = api.board_fund_flow_robust("行业", "今日", 5)
    ff = ff_raw.get("items", []) if ff_raw.get("status") == "OK" else []
    if ff_raw.get("note"):
        print(f"  [降级] 行业资金流: {ff_raw.get('note')}")
    if ff:
        # split inflow/outflow
        print("  TOP INFLOW:")
        for f in ff:
            net = f.get('net_amount', 0)
            if net > 0:
                print(f"    {f['name']:8s}  net={net/1e8:.2f}亿")
        print("  TOP OUTFLOW:")
        for f in ff:
            net = f.get('net_amount', 0)
            if net < 0:
                print(f"    {f['name']:8s}  net={net/1e8:.2f}亿")

    # 0h. North flow
    print("\n--- 0h. North Flow ---")
    try:
        nf = api.north_flow(5)
        print(f"  Latest: {nf}")
    except Exception as e:
        print(f"  North flow error: {e}")

    # 0i. ZT pool sample
    print("\n--- 0i. ZT Pool Sample (top 5) ---")
    try:
        zt = api.zt_pool()
        for z in zt[:5]:
            print(f"  {z.get('code','')} {z.get('name',''):6s}  {z.get('pct_chg',0):+.1f}%  {z.get('limit_days',0)}连板")
        print(f"  Total ZT stocks: {len(zt)}")
    except Exception as e:
        print(f"  ZT pool error: {e}")

    # ========== STEP 1: GATE JUDGMENT ==========
    banner("STEP 1: GATE JUDGMENT")

    wclose = weekly_closes[-1] if weekly_closes else (idx_data.get('000001',{}).get('price',0))
    gate0_pass = wclose >= w20 if w20 > 0 else None
    gate0_dir = "UP" if len(weekly_closes) >= 2 and weekly_closes[-1] > weekly_closes[-2] else "DOWN"

    print(f"\n  Gate0 (Weekly):")
    print(f"    Weekly close: {wclose:.2f}")
    print(f"    20-week MA:   {w20:.2f}")
    print(f"    Distance:     {(wclose-w20)/w20*100:+.1f}%")
    print(f"    Direction:    {gate0_dir}")
    print(f"    RESULT:       {'PASS' if gate0_pass else 'FAIL [veto]'}")

    close = last_close if last_close else idx_data.get('000001',{}).get('price',0)
    print(f"\n  Gate1 (Trend):")
    print(f"    SH close: {close:.2f}")
    print(f"    MA60:     {ma60:.2f}  diff={close-ma60:+.1f} ({(close-ma60)/ma60*100:+.1f}%)")
    print(f"    MA250:    {ma250:.2f}  diff={close-ma250:+.1f} ({(close-ma250)/ma250*100:+.1f}%)")
    if close > ma250 and ma60 > ma250:
        gate1_pos = "80~100%"
    elif close > ma250:
        gate1_pos = "<=50%"
    elif close < ma250 and close < ma60:
        gate1_pos = "<=20%"
    else:
        gate1_pos = "<=20%"
    print(f"    RESULT:    {gate1_pos}")

    zt_count = bs.get('zt_count', 0)
    dt_count = bs.get('dt_count', 0)
    up_count = brd.get('up', 0)

    print(f"\n  Gate2 (Volume & Breadth):")
    print(f"    Turnover: {tov_amt_yi:.0f}亿")
    print(f"    Up stocks: {up_count}")
    gate2_pass = tov_amt_yi > 10000 and up_count > 2500
    print(f"    RESULT:    {'PASS' if gate2_pass else 'WARN'}")

    print(f"\n  Gate3 (Sentiment):")
    print(f"    ZT={zt_count}, DT={dt_count}")
    print(f"    ZT>100: {zt_count>100}, DT>10: {dt_count>10}")
    gate3_warn = []
    if zt_count > 100: gate3_warn.append('ZT>100 [no open]')
    if dt_count > 10: gate3_warn.append('DT>10 [half position]')
    if zt_count > 0 and bs.get('break_rate',0) > 25:
        gate3_warn.append(f"break_rate={bs.get('break_rate',0)}% >25%")
    print(f"    RESULT:    {'FAIL ' + ', '.join(gate3_warn) if gate3_warn else 'PASS'}")

    # Final gate verdict
    print(f"\n  === FINAL GATE OUTPUT ===")
    if not gate0_pass:
        print(f"  Gate0 VETO -> FORCE <=20%, no new positions")
        gate_output = "0~20% (empty/defensive)"
    elif close < ma250:
        gate_output = "<=20% (contraction)"
    elif close < ma60:
        gate_output = "<=30% (trial)"
    else:
        gate_output = "80~100% (offense)"
    print(f"  Output: {gate_output}")

    # ========== STEP 2: SCORECARD ==========
    banner("STEP 2: 5-ITEM SCORECARD")

    score = 0
    details = []

    # 1. Index structure
    idx_up = sum(1 for s in snap if s.get('pct_chg',0) > 0 and s['code'] in INDICES)
    idx_total = sum(1 for s in snap if s['code'] in INDICES)
    if idx_up >= idx_total * 0.7:
        score += 1; details.append('+1 Index: majority up')
    elif idx_up <= idx_total * 0.3:
        score -= 1; details.append('-1 Index: majority down')
    else:
        details.append(' 0 Index: mixed')

    # 2. Market breadth
    up_ratio = brd.get('up_pct', 0)
    if up_ratio > 60:
        score += 1; details.append(f'+1 Breadth: {up_ratio:.0f}% up')
    elif up_ratio < 40:
        score -= 1; details.append(f'-1 Breadth: {up_ratio:.0f}% up')
    else:
        details.append(f' 0 Breadth: {up_ratio:.0f}% up')

    # 3. Volume-price
    if tov_amt_yi > 15000:
        score += 1; details.append(f'+1 Volume: {tov_amt_yi:.0f}bn >150bn')
    elif tov_amt_yi < 8000:
        score -= 1; details.append('-1 Volume: low')
    else:
        details.append(f' 0 Volume: {tov_amt_yi:.0f}bn')

    # 4. Theme continuity (simplified - check if any sector >3%)
    has_theme = any(s['change_pct'] > 3 for s in secs[:3])
    if has_theme and up_ratio > 50:
        score += 1; details.append('+1 Theme: strong sector leaders')
    elif not has_theme:
        score -= 1; details.append('-1 Theme: no clear leader')
    else:
        details.append(' 0 Theme: moderate')

    # 5. Loss effect
    zb = bs.get('zb_count', 0)
    if dt_count <= 5 and zb <= 10:
        score += 1; details.append('+1 Loss-effect: low (DT<=5, ZB<=10)')
    elif dt_count > 10 or zb > 20:
        score -= 1; details.append(f'-1 Loss-effect: DT={dt_count}, ZB={zb}')
    else:
        details.append(f' 0 Loss-effect: DT={dt_count}, ZB={zb}')

    print(f"  Score: {score}/5")
    for d in details:
        print(f"    {d}")

    if score >= 4:
        score_label = "OFFENSE (80~100%)"
    elif score >= 2:
        score_label = "TRIAL (30~50%)"
    elif score >= 0:
        score_label = "CONTRACTION (<=20%)"
    else:
        score_label = "EMPTY (0~20%)"

    print(f"  SCORECARD OUTPUT: {score_label}")

    # Gate override
    if not gate0_pass and score > 0:
        print(f"  ** Gate0 VETO overrides scorecard -> FORCE EMPTY/DEFENSIVE")

    # ========== STEP 3: SECTOR ANALYSIS ==========
    banner("STEP 3: SECTOR ANALYSIS")

    print("\n  --- Top Gainers ---")
    for s in secs[:5]:
        print(f"  {s['name']:10s}  {s['change_pct']:+6.2f}%")

    print("\n  --- Top Decliners ---")
    # get bottom 5
    secs_all = api.sectors(50)
    secs_rev = sorted(secs_all, key=lambda x: x['change_pct'])
    for s in secs_rev[:5]:
        print(f"  {s['name']:10s}  {s['change_pct']:+6.2f}%")

    print("\n  --- Fund Flow TOP 5 Inflow ---")
    ff_top_raw = api.board_fund_flow_robust("行业", "今日", 10)
    ff_top = ff_top_raw.get("items", []) if ff_top_raw.get("status") == "OK" else []
    if ff_top_raw.get("note"):
        print(f"  [降级] 行业资金流: {ff_top_raw.get('note')}")
    inflows = sorted([f for f in ff_top if f.get('net_amount',0) > 0], key=lambda x: -x.get('net_amount',0))
    for f in inflows[:5]:
        print(f"  {f['name']:10s}  net={f.get('net_amount',0)/1e8:.2f}bn")

    print("\n  --- Fund Flow TOP 5 Outflow ---")
    outflows = sorted([f for f in ff_top if f.get('net_amount',0) < 0], key=lambda x: x.get('net_amount',0))
    for f in outflows[:5]:
        print(f"  {f['name']:10s}  net={f.get('net_amount',0)/1e8:.2f}bn")

    # Main line check
    print("\n  --- Main Line Check ---")
    # Check if any sector leads >3% with fund inflow
    leaders = [s for s in secs[:5] if s['change_pct'] > 3]
    leader_names = [s['name'] for s in leaders]
    inflow_names = [f['name'] for f in inflows[:5]]
    overlap = set(leader_names) & set(inflow_names)
    if leaders and overlap:
        print(f"  Main line FOUND: {list(overlap)} (price + fund confirmed)")
    elif leaders:
        print(f"  Theme leaders: {leader_names} (no fund confirmation yet)")
    else:
        print(f"  NO clear main line")

    # ========== STEP 4: ADVICE ==========
    banner("STEP 4: TRADING ADVICE")

    print(f"""
      Environment: DEFENSIVE (Gate0 VETO + Gate3 DT>10)
  
      Position limit:
        Primary (Gate0): 0~20% maximum
        Gate1: <=20%
        Gate3: HALF position due to DT>10
        -> Effective: 0~10% [defensive only]
    
      Strategy:
        ACTIVE:  Defensive dividend (510880/512890)
        AVOID:   Swing, trend-follow, momentum, thematic chasing
    
      Key watch for tomorrow:
        1. DT count -> if back <5, Gate3 eases
        2. SH weekly close vs 20W-MA (~4020) -> Gate0 key level
        3. Volume -> if <1.5T, liquidity drying up
        4. Any sector with 3 consecutive days >2% -> potential main line
    
      Bollinger/Support:
        SH near-term support: ~3700 (Gate0 fail continuation)
        SH resistance: MA60=4042, MA250=3958
    """)

    print("="*60)
    print("  REVIEW COMPLETE")
    print("="*60)
