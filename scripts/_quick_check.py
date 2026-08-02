#!/usr/bin/env python3
"""快速检查两只票的介入点/确定点状态"""
import json, time
import requests

STOCKS = [("600131", "国网信通")]

def _ma(vals, n):
    if len(vals) < n: return None
    return round(sum(vals[-n:])/n, 2)

def check(code, name):
    m = "sz" if code.startswith(("0","3")) else "sh"
    s = requests.Session(); s.trust_env = False
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    
    # K线
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={m}{code},day,,,120,qfq"
    r = s.get(url, timeout=12); r.raise_for_status()
    klines = r.json()["data"][f"{m}{code}"].get("qfqday") or r.json()["data"][f"{m}{code}"].get("day")
    if not klines: return None
    
    dates, opens, closes, highs, lows, vols = [], [], [], [], [], []
    for k in klines:
        if len(k) < 6: continue
        dates.append(k[0]); opens.append(float(k[1])); closes.append(float(k[2]))
        highs.append(float(k[3])); lows.append(float(k[4])); vols.append(float(k[5]))
    
    # 均线
    ma5, ma10, ma20, ma60 = _ma(closes,5), _ma(closes,10), _ma(closes,20), _ma(closes,60)
    latest = closes[-1]
    dist_ma20 = round((latest-ma20)/ma20*100,2)
    
    # DKX金叉状态
    golden_now = ma5 > ma20 if ma5 and ma20 else False
    
    # 7/21金叉日确认
    cross_day_idx = None
    for i, d in enumerate(dates):
        if d >= "2026-07-21":
            cross_day_idx = i; break
    cross_price = closes[cross_day_idx] if cross_day_idx else None
    since_cross = round((latest-cross_price)/cross_price*100,2) if cross_price else 0
    
    # 金叉后最高/回撤
    if cross_day_idx:
        post_high = max(closes[cross_day_idx:])
        drawdown = round((latest-post_high)/post_high*100,2)
    else:
        post_high = drawdown = 0
    
    # ATR(14)
    trs = []
    for i in range(1, 15):
        tr = max(highs[-i]-lows[-i], abs(highs[-i]-closes[-i-1]), abs(lows[-i]-closes[-i-1]))
        trs.append(tr)
    atr = round(sum(trs)/len(trs)/latest*100,2)
    
    # 量比(5日均量)
    vol5 = sum(vols[-6:-1])/5 if len(vols)>=6 else vols[-1]
    vol_ratio = round(vols[-1]/vol5,2) if vol5>0 else 0
    
    # 实时行情
    rt_url = f"https://qt.gtimg.cn/q={m}{code}"
    rr = s.get(rt_url, timeout=8)
    today_chg = 0; today_high = 0; today_low = 0
    if rr.status_code == 200:
        raw = rr.text.split("~")
        if len(raw) > 50:
            try: today_chg = float(raw[32])
            except (IndexError, ValueError): pass
    
    # 近5日涨幅
    chg5 = round((closes[-1]-closes[-6])/closes[-6]*100,2) if len(closes)>=6 else 0
    chg10 = round((closes[-1]-closes[-11])/closes[-11]*100,2) if len(closes)>=11 else 0
    
    # 阶段判定
    if golden_now and abs(dist_ma20) <= 5:
        stage = "确定点"
    elif golden_now:
        stage = "介入点->等待回踩MA20"
    else:
        stage = "金叉已失效"
    
    return {
        "name": name, "code": code,
        "price": latest, "today_chg": today_chg,
        "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
        "dist_ma20": dist_ma20,
        "golden": golden_now,
        "since_cross": since_cross, "drawdown": drawdown,
        "atr": atr, "vol_ratio": vol_ratio,
        "chg5": chg5, "chg10": chg10,
        "stage": stage,
    }

if __name__ == '__main__':
    for code, name in STOCKS:
        r = check(code, name)
    if r:
        print(f"\n{'='*60}")
        print(f"  {r['name']} ({r['code']})  |  价格: {r['price']}  |  今日: {r['today_chg']}%")
        print(f"  MA5: {r['ma5']}  |  MA10: {r['ma10']}  |  MA20: {r['ma20']}  |  MA60: {r['ma60']}")
        print(f"  距MA20: {r['dist_ma20']}%  |  ATR: {r['atr']}%  |  量比: {r['vol_ratio']}")
        print(f"  金叉至今: {r['since_cross']}%  |  从高回撤: {r['drawdown']}%  |  5日: {r['chg5']}%  |  10日: {r['chg10']}%")
        print(f"  金叉状态: {'MA5>MA20 [OK]' if r['golden'] else 'MA5<MA20 [FAIL]'}")
        print(f"  阶段判定: {r['stage']}")
        print(f"{'='*60}")
    else:
        print(f"  [FAIL] {name} {code}")
    time.sleep(0.3)
