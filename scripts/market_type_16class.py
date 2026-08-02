# -*- coding: utf-8 -*-
"""
大盘行情类型 — 按用户提供的16类体系对近30个交易日分段定性
原则: 单日不定性，连续3~5日才定性，可叠加标签
"""
import sys, os, json, requests
from collections import OrderedDict, Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_session = requests.Session()
_session.trust_env = False
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# 上海交易所代码前缀判断（含 000001 上证指数！）
SH_PREFIX = frozenset({"000001","000300","000905","000016","000688","000852","000010","000002","000003","000004","000005","000006","000007","000008","000009"})

INDICES = OrderedDict([
    ("000001", "上证指数"), ("000300", "沪深300"), ("000016", "上证50"),
    ("000905", "中证500"), ("000852", "中证1000"), ("000688", "科创50"),
    ("399006", "创业板指"), ("399001", "深证成指"), ("399005", "中小100"),
])

def _prefix(c):
    c = c.lower()
    if c.startswith(("sh","sz","bj")): return c
    if c.startswith("92"): return f"bj{c}"       # V3.5.1: 920 北交所新股
    if c in SH_PREFIX or c[0] in "569": return f"sh{c}"
    if c[0] in "48": return f"bj{c}"
    return f"sz{c}"

def fetch_kline(code, n_days=50):
    """拉取腾讯前复权日K线"""
    pre = _prefix(code)
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pre},day,,,{n_days},qfq"
    try:
        r = _session.get(url, headers={"User-Agent": UA, "Host": "web.ifzq.gtimg.cn"}, timeout=15)
        d = r.json()
        raw = d.get("data",{}).get(pre,{}).get("qfqday",[]) or \
              d.get("data",{}).get(pre,{}).get("day",[])
        result = []
        for k in raw[-n_days:]:
            if len(k) >= 6:
                o, c = float(k[1]), float(k[2])
                pct = (c-o)/o*100 if o>0 else 0
                result.append({"date":k[0],"open":o,"close":c,"high":float(k[3]),
                               "low":float(k[4]),"volume":float(k[5]),"change_pct":round(pct,2)})
        return result
    except Exception as e:
        print(f"  [WARN] {code} fail: {e}")
        return []

def fetch_sectors_top(top_n=10):
    """拉取东财行业板块涨幅排名"""
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": str(top_n), "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fid": "f3", "fs": "m:90+t2",  # 行业板块
        "fields": "f2,f3,f4,f12,f14",
        "ut": "b2884a393a59ad640b1e6f0e8c8c4e3a",
    }
    try:
        r = _session.get(url, params=params, timeout=10)
        data = r.json().get("data", {})
        items = data.get("diff", [])
        return [(it["f14"], it.get("f3",0)) for it in items]
    except Exception:
        return []

def compute_style(day_data):
    """计算大盘vs小盘 / 价值vs成长背离"""
    sh50 = day_data.get("000016",{}).get("change_pct",0)
    zz1000 = day_data.get("000852",{}).get("change_pct",0)
    cyb = day_data.get("399006",{}).get("change_pct",0)
    size_gap = sh50 - zz1000
    growth_gap = cyb - sh50
    return {
        "size_gap": round(size_gap,2),
        "growth_gap": round(growth_gap,2),
        "size": "大盘强" if size_gap>0.5 else ("小盘强" if size_gap<-0.5 else "均衡"),
        "growth": "成长强" if growth_gap>0.5 else ("价值强" if growth_gap<-0.5 else "均衡"),
    }

# ============ 行情类型判定 ============
def classify(days, top_sectors=None):
    """
    对一段连续交易日判定行情类型，返回标签列表
    days: [{date, up_9, down_9, avg_chg, close_000001, size_gap, ...}, ...]
    """
    n = len(days)
    if n < 1: return ["无数据"]
    if n < 3: return ["数据不足(<3天)"]

    up = [d["up_9"] for d in days]
    chg = [d["avg_chg"] for d in days]
    total_up = sum(up)/n
    total_chg = sum(chg)/n

    # 上证区间涨跌
    sh0 = days[0].get("close_sh",0)
    sh1 = days[-1].get("close_sh",0)
    period_pct = (sh1-sh0)/sh0*100 if sh0>0 else 0

    labels = []

    # === 1. 全面性普涨 ===
    if total_up>=7 and all(c>0 for c in chg) and n>=3:
        labels.append("全面性普涨")

    # === 2. 全面性普跌 ===
    if total_up<=2 and all(c<0 for c in chg) and n>=3:
        labels.append("全面性普跌")

    # === 3. 权重行情：大盘指数涨(上证50>0)但小盘跌(中证1000<0) ===
    big_up_days = sum(1 for d in days if d.get("sh50_chg",0)>0)
    small_down_days = sum(1 for d in days if d.get("zz1000_chg",0)<0)
    if big_up_days>=n*0.6 and small_down_days>=n*0.5 and "全面性普涨" not in labels and "全面性普跌" not in labels:
        labels.append("权重行情")

    # === 4. 指数分化：大小盘持续背离 ===
    diverged = sum(1 for d in days if abs(d.get("size_gap",0))>1.0)
    if diverged>=n*0.5 and "全面性普涨" not in labels and "全面性普跌" not in labels:
        labels.append("指数分化")

    # === 5. 结构性行情：指数平淡+板块分化 ===
    if abs(total_chg)<0.5 and 3<=total_up<=6 and n>=3:
        labels.append("结构性行情")

    # === 6. 风格行情：持续的风格偏向 ===
    style_days = sum(1 for d in days if abs(d.get("style_gap",0))>0.8)
    if style_days>=n*0.6:
        labels.append("风格行情")

    # === 7. 抱团行情：九指涨幅极差>2.5%（头部vs尾部差距大） ===
    spread = sum(1 for d in days if d.get("chg_spread",0)>2.5)
    if spread>=n*0.5:
        labels.append("抱团行情")

    # === 8. 防御性行情：大盘强+指数跌+防御板块 ===
    def_days = sum(1 for d in days if d.get("size_gap",0)>0.5 and d.get("avg_chg",0)<0)
    if def_days>=n*0.6 and "全面性普涨" not in labels:
        labels.append("防御性行情")

    # === 9. 题材轮动：日间方向高频反转 ===
    flips = sum(1 for i in range(1,n) if (chg[i]>0)!=(chg[i-1]>0))
    if flips>=n*0.5 and n>=3:
        labels.append("题材轮动（高频反转）")

    # === 11. 存量博弈震荡 ===
    if abs(total_chg)<0.8 and flips>=n*0.4 and n>=4:
        labels.append("存量博弈震荡")

    # === 12. 超跌反弹：前段有大跌+本段涨 ===
    big_neg = [c for c in chg if c<-1.5]
    big_pos = [c for c in chg if c>1.5]
    if len(big_neg)>0 and len(big_pos)>0 and total_chg>0:
        labels.append("超跌反弹")

    # === 13. 缩量阴跌 ===
    if total_chg<-0.3 and all(c<0 for c in chg) and n>=3 and "全面性普跌" not in labels:
        labels.append("缩量阴跌")

    # === 14. 磨底/修复 ===
    if -0.3<=total_chg<=0.3 and all(abs(c)<1.0 for c in chg) and n>=3:
        labels.append("磨底/修复行情")

    # === 15. 一日游 ===
    if n<=2 and max(abs(c) for c in chg)>1.5:
        labels.append("一日游/消息脉冲")

    # === 16. 情绪极端（叠加标签） ===
    extreme = sum(1 for c in chg if abs(c)>2.5)
    if extreme>=1:
        labels.append("情绪极端(叠加)")

    if not labels:
        labels.append("震荡/无明确特征")

    # 过滤矛盾标签
    if "全面性普涨" in labels:
        labels = [l for l in labels if l not in ("存量博弈震荡","缩量阴跌","磨底/修复行情","防御性行情","权重行情")]
    if "全面性普跌" in labels:
        labels = [l for l in labels if l not in ("存量博弈震荡","磨底/修复行情","结构性行情","权重行情","题材轮动（高频反转）")]

    return labels

# ============ 主程序 ============
def main():
    print("="*90)
    print("  大盘整体行情类型 — 近30个交易日分段定性 (16类体系)")
    print("  原则: 单日不定性 | 连续3~5日才定性 | 行情可叠加标签")
    print("="*90)

    # 1. 拉取K线
    print("\n[1/3] 拉取九指数日K线...")
    all_data = {}
    vols = {}
    for code, name in INDICES.items():
        kd = fetch_kline(code, 55)
        for k in kd:
            d = k["date"]
            all_data.setdefault(d, {})[code] = k
            if code=="000001": vols[d] = k["volume"]
        print(f"  {name}: {len(kd)}条")

    # 2. 筛选有效日期 & 构建统计
    print("\n[2/3] 构建逐日统计...")
    dates = sorted(d for d in all_data if len(all_data[d])>=7)
    dates = dates[-30:]  # 最近30交易日

    stats = []
    for date in dates:
        day = all_data[date]
        chgs = [v["change_pct"] for v in day.values()]
        up_n = sum(1 for c in chgs if c>0)
        down_n = sum(1 for c in chgs if c<0)
        avg = sum(chgs)/max(len(chgs),1)
        st = compute_style(day)
        chgs_sort = sorted(chgs)
        spread = chgs_sort[-1]-chgs_sort[0] if len(chgs_sort)>1 else 0

        stats.append({
            "date": date,
            "up_9": up_n, "down_9": down_n,
            "avg_chg": round(avg,2),
            "close_sh": day.get("000001",{}).get("close",0),
            "volume_sh": vols.get(date,0),
            "size_gap": st["size_gap"],
            "style_gap": max(abs(st["size_gap"]), abs(st["growth_gap"])),
            "size_bias": st["size"],
            "growth_bias": st["growth"],
            "sh50_chg": day.get("000016",{}).get("change_pct",0),
            "zz1000_chg": day.get("000852",{}).get("change_pct",0),
            "cyb_chg": day.get("399006",{}).get("change_pct",0),
            "chg_spread": round(spread,2),
            "all_chgs": chgs_sort,
        })

    # 3. 拉取行业板块（取最近1日和1周前的快照）
    print("\n[3/3] 拉取行业板块表现...")
    sectors_today = fetch_sectors_top(10)
    print(f"  今日领涨板块: {', '.join(f'{n}({p:+.1f}%)' for n,p in sectors_today[:5])}")
    # 倒推一周前
    wk_ago_date = dates[-6] if len(dates)>6 else dates[0]
    print(f"  一周前({wk_ago_date})领涨板块: (K线日期, 非实时)")

    # ============ 自动分段 ============
    # 按方向反转 + 风格切换分段
    segments = []
    seg = [stats[0]]
    for i in range(1, len(stats)):
        cur, pre = stats[i], stats[i-1]
        # 方向反转
        dir_flip = (cur["avg_chg"]>0.5 and pre["avg_chg"]<-0.3) or \
                   (cur["avg_chg"]<-0.5 and pre["avg_chg"]>0.3)
        # 风格切换
        style_flip = abs(cur["size_gap"]-pre["size_gap"])>1.5

        if dir_flip or style_flip:
            segments.append(seg)
            seg = [cur]
        else:
            seg.append(cur)
    if seg: segments.append(seg)

    # 合并短段（<2天并入相邻）
    merged = []
    for s in segments:
        if len(s)<=1 and merged:
            merged[-1].extend(s)
        else:
            merged.append(s)

    # ============ 输出 ============
    print(f"\n{'='*90}")
    print(f"  {'日期区间':<24} {'天':>2} {'均值':>7} {'上证区间':>8} {'风格':<10} {'行情类型'}")
    print(f"  {'-'*86}")
    all_labels = Counter()
    for seg in merged:
        if len(seg)<1: continue
        sd, ed = seg[0]["date"], seg[-1]["date"]
        nd = len(seg)
        avg = sum(d["avg_chg"] for d in seg)/nd
        pct = (seg[-1]["close_sh"]-seg[0]["close_sh"])/seg[0]["close_sh"]*100
        bias = Counter(d["size_bias"] for d in seg).most_common(1)[0][0]
        tags = classify(seg)
        for t in tags: all_labels[t] += 1
        dr = f"{sd}~{ed}" if sd!=ed else sd
        print(f"  {dr:<24} {nd:>2} {avg:>+6.2f}% {pct:>+7.2f}% {bias:<10} {', '.join(tags)}")

    # ============ 汇总 ============
    print(f"\n{'='*90}")
    print(f"  近30交易日整体判定")
    print(f"{'='*90}")
    sh0 = stats[0]["close_sh"]
    sh1 = stats[-1]["close_sh"]
    tot_pct = (sh1-sh0)/sh0*100
    tot_avg = sum(d["avg_chg"] for d in stats)/len(stats)
    print(f"  上证指数: {sh0:.0f} → {sh1:.0f} ({tot_pct:+.2f}%)")
    print(f"  日均九指均值: {tot_avg:+.2f}% | 覆盖: {len(stats)}个交易日")
    
    print(f"\n  行情标签出现次数:")
    for label, cnt in all_labels.most_common():
        bar = "█"*cnt
        print(f"    {label:<24} {cnt}次  {bar}")

    # 综合性一句话
    dominant = [l for l,_ in all_labels.most_common(3)]
    recent = merged[-1]
    recent_tags = classify(recent)

    print(f"\n  综合判定:")
    verdict = []
    if "全面性普跌" in dominant or "缩量阴跌" in dominant:
        verdict.append("空头格局")
    elif "全面性普涨" in dominant:
        verdict.append("多头格局")
    else:
        verdict.append("震荡分化")

    if any(t in dominant for t in ["题材轮动（高频反转）","存量博弈震荡"]):
        verdict.append("高波动率")

    if abs(tot_pct)<3: verdict.append("窄幅区间")
    elif tot_pct<-5: verdict.append("趋势走弱")
    elif tot_pct>5: verdict.append("趋势走强")

    # 最近行情
    last_bias = recent[-1]["size_bias"]
    last_growth = recent[-1]["growth_bias"]
    print(f"  整体行情类型: {' + '.join(verdict)}")
    print(f"  最近一段({recent[0]['date']}~{recent[-1]['date']}, {len(recent)}天): {', '.join(recent_tags)}")
    print(f"  当前风格偏向: 大小盘={last_bias}, 成长/价值={last_growth}")

    # 今日板块佐证
    if sectors_today:
        top5_names = [n for n,_ in sectors_today[:5]]
        if any(kw in "".join(top5_names) for kw in ["银行","石油","煤炭","公用","电力","红利"]):
            print(f"  今日领涨板块佐证: 防御类占优 → 防御性行情确认")
        elif any(kw in "".join(top5_names) for kw in ["科技","芯片","AI","信创","算力","游戏","传媒"]):
            print(f"  今日领涨板块佐证: 科技成长类占优 → 进攻倾向")

    print(f"\n{'='*90}")
    print(f"  判定说明: 数据来源腾讯行情 → 九指数日K线 | 日内涨跌幅=open→close")
    print(f"  行业板块: 东财行业分类 | 局限性: 无全市场涨跌家数, 无精确成交量变化率")
    print(f"  建议: 叠加同花顺/东财的全市场广度+成交额趋势验证")

if __name__=="__main__":
    main()
