# -*- coding: utf-8 -*-
"""
大盘整体行情类型 — 三级体系完整判定（趋势市/震荡市/熊市 + 细分形态 + 叠加标签）
判定依据: MA20/MA60/MA250 + 周线 + 量能 + 广度 + 高低点
覆盖近30交易日，数据取自腾讯/东财
"""
import sys, os, json, requests
from collections import OrderedDict, Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

s = requests.Session()
s.trust_env = False
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

SH = frozenset("000001 000300 000905 000016 000688 000852 000010 000002 000003".split())

# ===== 指数清单（按用户分类） =====
INDEX_GROUPS = {
    "主锚指数":       {"000300": "沪深300", "000001": "上证指数"},
    "验证指数":       {"399001": "深证成指", "399006": "创业板指", "000688": "科创50"},
    "广度与规模":     {"000016": "上证50", "000905": "中证500", "000852": "中证1000"},
    # 中证A500/中证2000/北证50/全A/等权 → 无直接腾讯代码，用近似替代
}

ALL_INDICES = OrderedDict()
for g in INDEX_GROUPS.values():
    ALL_INDICES.update(g)

def _pfx(c):
    c = c.lower()
    if c.startswith(("sh","sz","bj")): return c
    if c in SH or c[0] in "569": return f"sh{c}"
    if c[0] in "48": return f"bj{c}"
    return f"sz{c}"

def fetch_kline(code, n_days=300):
    pre = _pfx(code)
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pre},day,,,{n_days},qfq"
    try:
        r = s.get(url, headers={"User-Agent":UA,"Host":"web.ifzq.gtimg.cn"}, timeout=20)
        d = r.json()
        raw = d.get("data",{}).get(pre,{}).get("qfqday",[]) or \
              d.get("data",{}).get(pre,{}).get("day",[])
        result = []
        for k in raw[-n_days:]:
            if len(k) >= 6:
                o,c = float(k[1]), float(k[2])
                pct = (c-o)/o*100 if o>0 else 0
                result.append({"d":k[0],"o":o,"c":c,"h":float(k[3]),"l":float(k[4]),
                               "v":float(k[5]),"pct":round(pct,2)})
        return result
    except Exception as e:
        print(f"  [WARN] {code} fail: {e}")
        return []

def fetch_weekly(code, n=60):
    """拉取周线"""
    pre = _pfx(code)
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pre},week,,,{n},qfq"
    try:
        r = s.get(url, headers={"User-Agent":UA,"Host":"web.ifzq.gtimg.cn"}, timeout=20)
        d = r.json()
        raw = d.get("data",{}).get(pre,{}).get("qfqweek",[]) or \
              d.get("data",{}).get(pre,{}).get("week",[])
        result = []
        for k in raw[-n:]:
            if len(k) >= 6:
                result.append({"d":k[0],"o":float(k[1]),"c":float(k[2]),
                               "h":float(k[3]),"l":float(k[4]),"v":float(k[5])})
        return result
    except Exception as e:
        print(f"  [WARN] weekly {code}: {e}")
        return []

def ma(arr, n):
    """简单移动均线"""
    if len(arr) < n: return None
    return sum(arr[-n:]) / n

def ema(arr, n):
    """指数移动均线"""
    if len(arr) < 2: return arr[-1] if arr else None
    k = 2/(n+1)
    val = arr[0]
    for x in arr[1:]:
        val = x*k + val*(1-k)
    return val

# ============ 逐日判定引擎 ============
def judge_period(seg_data, all_close_data, all_vol_data):
    """
    对一段连续交易日(≥3天)进行三级判定
    seg_data: [{date, avg_chg, up_9, down_9, close_hs300, close_sh, ...}, ...]
    all_close_data: {code: [closes]} 全历史数据
    all_vol_data: {code: [volumes]} 全历史成交量
    返回: {tier, sub_types, overlay_tags, position, strategies}
    """
    n = len(seg_data)
    dates = [d["date"] for d in seg_data]
    avg_chg = sum(d["avg_chg"] for d in seg_data)/n

    # ---- MA判定（用沪深300为主锚）----
    hs300_closes = all_close_data.get("000300", [])
    sh_closes = all_close_data.get("000001", [])
    cyb_closes = all_close_data.get("399006", [])
    kc_closes = all_close_data.get("000688", [])

    # 取最近一段末尾的MA值
    last_i = len(hs300_closes)
    ma20_hs = ma(hs300_closes, 20)
    ma60_hs = ma(hs300_closes, 60)
    ma250_hs = ma(hs300_closes, 250) if len(hs300_closes) >= 250 else None

    last_close_hs = hs300_closes[-1] if hs300_closes else 0

    ma20_up = ma60_up = ma250_pos = None
    if ma20_hs and ma60_hs:
        # MA60方向：对比20天前的MA60
        if len(hs300_closes) >= 80:
            old_ma60 = ma(hs300_closes[:-20], 60)
            ma60_up = ma60_hs > old_ma60 if old_ma60 else None
        ma20_up = last_close_hs > ma20_hs

    if ma250_hs:
        ma250_pos = last_close_hs > ma250_hs

    # ---- 量能：最近3日 vs 5日均量（用上证成交额）----
    vol_5d_avg = ma(all_vol_data.get("000001",[]), 5)
    vols_recent = all_vol_data.get("000001",[])[-3:]
    vol_avg_recent = sum(vols_recent)/3 if vols_recent else 0
    vol_expanding = vol_avg_recent > vol_5d_avg*1.05 if vol_5d_avg else None

    # ---- 广度：连续3~5日涨跌情况 ----
    up_9 = [d["up_9"] for d in seg_data]
    breadth_bull = all(u>=5 for u in up_9[-3:])  # 连续3天≥5涨
    breadth_bear = all(u<=3 for u in up_9[-3:])   # 连续3天≤3涨

    # ---- 高低点（用上证指数）----
    sh_highs = [d.get("sh_high",0) for d in seg_data]
    sh_lows = [d.get("sh_low",0) for d in seg_data]
    highs_rising = all(sh_highs[i]>=sh_highs[i-1] for i in range(1,len(sh_highs))) if len(sh_highs)>1 else None
    lows_rising = all(sh_lows[i]>=sh_lows[i-1] for i in range(1,len(sh_lows))) if len(sh_lows)>1 else None

    # ---- 周线：20周线位置 ----
    weekly_20 = all_close_data.get("W_ma20_hs300", None)
    above_w20 = last_close_hs > weekly_20 if weekly_20 else None

    # ---- 验证指数：至少2个同步 ----
    cyb_last = cyb_closes[-1] if cyb_closes else 0
    kc_last = kc_closes[-1] if kc_closes else 0
    verify_ma = 0
    for code_closes in [cyb_closes, kc_closes]:
        if code_closes and len(code_closes)>=20:
            if code_closes[-1] > ma(code_closes, 20):
                verify_ma += 1
    verify_ok = verify_ma >= 2

    # ======== 三级判定 ========
    # 趋势市条件
    trend_cond = (ma250_pos and ma60_up and highs_rising and breadth_bull and vol_expanding)
    # 熊市条件
    bear_cond = ((not ma250_pos) and (not ma60_up) and (not highs_rising) and breadth_bear)
    # 震荡市 = 不满足趋势也不满足熊市

    if trend_cond:
        tier = "趋势市"
    elif bear_cond:
        tier = "熊市"
    else:
        tier = "震荡市"

    # ======== 细分形态 ========
    subs = []
    overlays = []

    # --- 全面性普涨 ---
    if all(u>=6 for u in up_9[-3:]) and avg_chg>0.5:
        subs.append("全面性普涨")
    # --- 全面性普跌 ---
    if all(u<=2 for u in up_9[-3:]) and avg_chg<-0.5:
        subs.append("全面性普跌")
    # --- 结构性行情（指数平淡但部分强） ---
    if abs(avg_chg)<0.5 and 3<=sum(up_9)/n<=6:
        subs.append("结构性行情")
    # --- 权重行情（指数红但广度弱） ---
    sh_chg = sum(d.get("sh_chg",0) for d in seg_data)/n
    if sh_chg>0 and avg_chg<0:
        subs.append("权重行情")
    # --- 抱团行情（涨幅极差大） ---
    spreads = [d.get("chg_spread",0) for d in seg_data]
    if sum(spreads)/n > 2.0:
        subs.append("抱团行情")
    # --- 题材事件行情 ---
    # 无法自动判定，需人工
    # --- 存量博弈震荡 ---
    if abs(avg_chg)<0.8 and vol_expanding is False:
        subs.append("存量博弈震荡")
    # --- 缩量阴跌 ---
    if avg_chg<-0.3 and all(c<0 for _,c in [("",d["avg_chg"]) for d in seg_data]) and not vol_expanding:
        subs.append("缩量阴跌")
    # --- 防御性行情 ---
    def_days = sum(1 for d in seg_data if d.get("size_gap",0)>0.5 and d.get("avg_chg",0)<0)
    if def_days>=n*0.6:
        subs.append("防御性行情")
    # --- 超跌反弹 ---
    negs = [d["avg_chg"] for d in seg_data if d["avg_chg"]<-1.5]
    poss = [d["avg_chg"] for d in seg_data if d["avg_chg"]>1.5]
    if negs and poss and avg_chg>0:
        subs.append("超跌反弹")
    # --- 磨底 ---
    if -0.3<=avg_chg<=0.3 and all(abs(d["avg_chg"])<1.0 for d in seg_data):
        subs.append("磨底/修复行情")

    # --- 叠加标签 ---
    # 指数分化
    div_days = sum(1 for d in seg_data if abs(d.get("size_gap",0))>1.0)
    if div_days>=n*0.5: overlays.append("指数分化")
    # 题材轮动
    flips = sum(1 for i in range(1,n) if (seg_data[i]["avg_chg"]>0)!=(seg_data[i-1]["avg_chg"]>0))
    if flips>=n*0.5: overlays.append("题材轮动(高频反转)")
    # 一日游
    if n<=2 and max(abs(d["avg_chg"]) for d in seg_data)>1.5: overlays.append("一日游/消息脉冲")
    # 情绪极端
    if any(abs(d["avg_chg"])>2.5 for d in seg_data): overlays.append("情绪极端(叠加)")
    # 风格行情
    style_days = sum(1 for d in seg_data if abs(d.get("style_gap",0))>0.8)
    if style_days>=n*0.6: overlays.append("风格行情")

    if not subs: subs.append("无明确细分形态")

    # ======== 仓位 & 策略 ========
    if tier=="趋势市":
        pos = "50%~80%进攻"
        strat = "趋势跟踪 + 动量轮动 + 顺势波段"
    elif tier=="震荡市":
        pos = "≤50%高抛低吸 或 0%~20%只做最强"
        strat = "区间波段 + 均值回归/网格"
    else:
        pos = "0%~20%"
        strat = "空仓为主 + 超跌反弹轻仓试错"

    return {
        "tier": tier, "sub_types": subs, "overlay_tags": overlays,
        "position": pos, "strategy": strat,
        "ma_check": {"ma20_above": ma20_up, "ma60_rising": ma60_up, "ma250_above": ma250_pos,
                      "verify_count": verify_ma, "verify_ok": verify_ok,
                      "last_close_hs300": round(last_close_hs,0), "ma20": round(ma20_hs,0) if ma20_hs else None,
                      "ma60": round(ma60_hs,0) if ma60_hs else None, "ma250": round(ma250_hs,0) if ma250_hs else None},
        "volume_check": {"recent_3d_avg": round(vol_avg_recent,0), "ma5": round(vol_5d_avg,0) if vol_5d_avg else None,
                         "expanding": vol_expanding},
        "breadth_check": {"bull_3d": breadth_bull, "bear_3d": breadth_bear},
        "highlow": {"rising": highs_rising},
        "weekly": {"above_20w": above_w20},
    }


def main():
    print("=" * 100)
    print("  大盘整体行情类型 — 三级体系完整判定（趋势市/震荡市/熊市 + 细分形态 + 叠加标签）")
    print("  判定依据: MA20/60/250 + 周线20周 + 量能 + 广度 + 高低点")
    print("=" * 100)

    # ===== 1. 拉取日K线（~300天） =====
    print("\n[1/4] 拉取日K线(300日) + 周线(60周)...")
    all_kdata = {}
    vol_series = {}  # {code: [daily_volume]}
    close_series = {}

    for code, name in ALL_INDICES.items():
        kd = fetch_kline(code, 310)
        for k in kd:
            all_kdata.setdefault(k["d"], {})[code] = k
        close_series[code] = [k["c"] for k in kd]
        vol_series[code] = [k["v"] for k in kd]
        print(f"  {name}({code}): {len(kd)}条日线")

    # 周线（沪深300）
    wkl = fetch_weekly("000300", 60)
    if wkl:
        wk_closes = [w["c"] for w in wkl]
        wk_ma20 = ma(wk_closes, 20)
        close_series["W_ma20_hs300"] = wk_ma20
        print(f"  沪深300周线: {len(wkl)}周 | 20周均线: {wk_ma20:.0f}" if wk_ma20 else "  周线: MA20=无")

    # ===== 2. 统计所有可用日期 =====
    print("\n[2/4] 统计有效交易日...")
    sorted_dates = sorted(all_kdata.keys())
    # 只保留至少有全部8个指数的日期
    valid_dates = [d for d in sorted_dates if len(all_kdata[d]) >= 7]
    recent_30 = valid_dates[-30:]
    print(f"  总有效天数: {len(valid_dates)} | 最近30天: {recent_30[0]} ~ {recent_30[-1]}")

    # ===== 3. 构建逐日快照 =====
    print("\n[3/4] 构建逐日统计快照...")
    snapshots = []
    for date in recent_30:
        day = all_kdata[date]
        chgs = [v["pct"] for v in day.values()]
        up_n = sum(1 for c in chgs if c>0)
        dn_n = sum(1 for c in chgs if c<0)
        avg = sum(chgs)/max(len(chgs),1)
        chgs_sort = sorted(chgs)
        spread = chgs_sort[-1]-chgs_sort[0] if len(chgs_sort)>1 else 0

        # 风格
        sh50 = day.get("000016",{}).get("pct",0)
        zz1000 = day.get("000852",{}).get("pct",0)
        cyb = day.get("399006",{}).get("pct",0)
        size_gap = sh50 - zz1000
        growth_gap = cyb - sh50
        size = "大盘强" if size_gap>0.5 else ("小盘强" if size_gap<-0.5 else "均衡")

        snapshots.append({
            "date": date,
            "up_9": up_n, "down_9": dn_n,
            "avg_chg": round(avg,2),
            "sh_chg": day.get("000001",{}).get("pct",0),
            "sh_high": day.get("000001",{}).get("h",0),
            "sh_low": day.get("000001",{}).get("l",0),
            "close_hs300": day.get("000300",{}).get("c",0),
            "size_gap": round(size_gap,2),
            "style_gap": max(abs(round(size_gap,2)), abs(round(growth_gap,2))),
            "size_bias": size,
            "chg_spread": round(spread,2),
        })

    # ===== 4. 自动分段 + 判定 =====
    print("[4/4] 自动分段 & 三级判定...\n")

    # 方向反转分段
    raw_segs = []
    seg = [snapshots[0]]
    for i in range(1, len(snapshots)):
        cur, pre = snapshots[i], snapshots[i-1]
        dir_flip = (cur["avg_chg"]>0.5 and pre["avg_chg"]<-0.3) or \
                   (cur["avg_chg"]<-0.5 and pre["avg_chg"]>0.3)
        style_flip = abs(cur["size_gap"]-pre["size_gap"])>1.5
        if dir_flip or style_flip:
            raw_segs.append(seg)
            seg = [cur]
        else:
            seg.append(cur)
    if seg: raw_segs.append(seg)

    # 合并短段
    merged = []
    for s in raw_segs:
        if len(s)<=1 and merged:
            merged[-1].extend(s)
        else:
            merged.append(s)

    # ===== 输出 =====
    print(f"  {'日期区间':<24} {'天':>2} {'均值':>7} {'上证区间':>8} {'风格':<10} {'三级档位':<8} {'细分形态'}")
    print(f"  {'-'*96}")

    tier_count = Counter()
    all_subs = Counter()
    all_overlays = Counter()

    for seg in merged:
        if len(seg)<1: continue
        sd, ed = seg[0]["date"], seg[-1]["date"]
        nd = len(seg)
        avg = sum(d["avg_chg"] for d in seg)/nd
        pct = (seg[-1]["sh_high"]+seg[-1]["sh_low"])/2  # 用中间价简化
        # 上证区间涨跌用close价格
        # 我们直接取段首和段末的上证高低点中值近似
        sh_chg_seg = (seg[-1]["sh_low"]+seg[-1]["sh_high"] - seg[0]["sh_low"]-seg[0]["sh_high"])/(seg[0]["sh_low"]+seg[0]["sh_high"])*2*100
        bias = Counter(d["size_bias"] for d in seg).most_common(1)[0][0]
        result = judge_period(seg, close_series, vol_series)

        tier_count[result["tier"]] += 1
        for t in result["sub_types"]: all_subs[t] += 1
        for t in result["overlay_tags"]: all_overlays[t] += 1

        dr = f"{sd}~{ed}" if sd!=ed else sd
        print(f"  {dr:<24} {nd:>2} {avg:>+6.2f}% {sh_chg_seg:>+7.2f}% {bias:<10} "
              f"{result['tier']:<8} {', '.join(result['sub_types'])}")
        if result["overlay_tags"]:
            print(f"  {'':>26} {'':>1} {'':>7} {'':>8} {'':<10} {'':<8} [叠加] {', '.join(result['overlay_tags'])}")

    # ===== 汇总 =====
    print(f"\n{'='*100}")
    print(f"  近30交易日整体判定")
    print(f"{'='*100}")

    # 最后一个完整段的详细MA判定
    last_seg = merged[-1]
    last_result = judge_period(last_seg, close_series, vol_series)
    mc = last_result["ma_check"]
    vc = last_result["volume_check"]
    wc = last_result["weekly"]

    print(f"\n  === MA均线判定（沪深300为主锚）===")
    print(f"  收盘价: {mc['last_close_hs300']:.0f}")
    print(f"  MA20: {mc['ma20']:.0f} | {'收盘>MA20 ✓' if mc['ma20_above'] else '收盘<MA20 ✗'}")
    print(f"  MA60: {mc['ma60']:.0f} | {'MA60上升 ✓' if mc['ma60_rising'] else 'MA60下降/持平 ✗'}")
    print(f"  MA250: {mc['ma250']:.0f} | {'收盘>MA250 ✓' if mc['ma250_above'] else '收盘<MA250 ✗'}")
    print(f"  验证指数同步站上MA20: {mc['verify_count']}个 | {'至少2个确认 ✓' if mc['verify_ok'] else '不足2个 ✗'}")
    if wc["above_20w"] is not None:
        print(f"  周线: {'收盘>20周线 ✓' if wc['above_20w'] else '收盘<20周线 ✗'}")

    print(f"\n  === 量能判定 ===")
    if vc["recent_3d_avg"] and vc["ma5"]:
        print(f"  近3日均量: {vc['recent_3d_avg']:.0f} | 5日均量: {vc['ma5']:.0f} | {'放量 ✓' if vc['expanding'] else '缩量/持平 ✗'}")

    print(f"\n  === 三档分布 ===")
    for t, c in tier_count.most_common():
        bar = "█"*c
        print(f"  {t:<12} {c}段  {bar}")

    print(f"\n  === 细分形态分布 ===")
    for sub, c in all_subs.most_common():
        print(f"  {sub:<24} {c}次")
    print(f"\n  === 叠加标签分布 ===")
    for tag, c in all_overlays.most_common():
        print(f"  {tag:<24} {c}次")

    # ===== 综合结论 =====
    print(f"\n{'='*100}")
    print(f"  综合结论")
    print(f"{'='*100}")

    if tier_count.get("趋势市",0)>0:
        print(f"  大盘档位: 趋势市 → 50%~80%进攻, 趋势跟踪+动量轮动")
    elif tier_count.get("熊市",0)>0:
        print(f"  大盘档位: 熊市 → 0%~20%, 空仓为主+超跌反弹轻仓试错")
    else:
        print(f"  大盘档位: 震荡市 → ≤50%高抛低吸, 区间波段+均值回归")

    if last_result["sub_types"]:
        print(f"  当前细分: {', '.join(last_result['sub_types'])}")
    if last_result["overlay_tags"]:
        print(f"  叠加标签: {', '.join(last_result['overlay_tags'])}")

    # 终结信号检查
    print(f"\n  终结信号检查:")
    if mc["ma20_above"] is False:
        print(f"    [!] 跌破MA20 → 趋势可能终结")
    if mc["ma250_above"] is False:
        print(f"    [!] 收盘<MA250 → 整体降仓信号")
    if last_result["highlow"]["rising"] is False:
        print(f"    [!] 高低点未依次抬升")

    print(f"\n  建议仓位: {last_result['position']}")
    print(f"  建议策略: {last_result['strategy']}")

if __name__=="__main__":
    main()
