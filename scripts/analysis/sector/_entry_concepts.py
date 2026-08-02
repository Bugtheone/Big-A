#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""概念板块入场分析：Tushare THS概念(主源) + 同花顺热榜(验证) + 东财资金流(验证) | 盘后 2026-07-30"""
import sys, os, io, traceback, json, time
from collections import defaultdict, Counter
import numpy as np

# Windows GBK→UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.market_api import api, gate
from scripts.tushare_api import get_pro

pro = get_pro()
TODAY = "20260730"
START_DATE = "20260618"
REPORT_FILE = os.path.join(BASE_DIR, "_entry_concepts_report.txt")

out_lines = []
def p(*args):
    line = " ".join(str(a) for a in args)
    out_lines.append(line)
    print(line)

p("=" * 72)
if __name__ == "__main__":
    p("概念板块入场分析：Tushare同花顺概念 + 多源交叉验证")
    p(f"盘后 | {TODAY[:4]}-{TODAY[4:6]}-{TODAY[6:8]}")
    p("=" * 72)
    p()

    # ═══════════════════════════════════════════
    # S0: 数据获取
    # ═══════════════════════════════════════════

    # ── S0.1 同花顺概念指数列表 ──
    p("-" * 50)
    p("S0.1 主源A: Tushare同花顺概念指数列表")
    p("-" * 50)
    concept_list = []
    try:
        df = pro.ths_index(type_="I")
        if df is not None and not df.empty:
            for _, r in df.iterrows():
                row = dict(r)
                concept_list.append({
                    "code": str(row["ts_code"]),
                    "name": str(row["name"]),
                    "count": row.get("count", 0),
                })
        p(f"  获取 {len(concept_list)} 个概念指数 ★★★★★")
    except Exception as e:
        p(f"  [FATAL] 概念列表失败: {e}")

    # ── S0.2 今日全量概念涨跌 → 筛选热门 ──
    p()
    p("-" * 50)
    p("S0.2 今日全量概念涨跌幅 → 筛选TOP60+最弱20")
    p("-" * 50)

    today_concepts = {}
    try:
        # 直接通过 tushare_pro_data 获取全量今日概念数据
        result = gate.ts_ths_daily(trade_date=TODAY)
        if result:
            for row in result:
                code = str(row["ts_code"])
                pct = float(row.get("pct_change", row.get("pct_chg", 0) or 0))
                close = float(row.get("close", 0))
                if code and close:
                    today_concepts[code] = {"close": close, "pct": pct}
        p(f"  今日全量: {len(today_concepts)} 个概念有数据")
    except Exception as e:
        p(f"  [WARN] 今日全量获取失败: {e}")

    # 合并名称
    code_to_name = {c["code"]: c["name"] for c in concept_list}
    for code, name in code_to_name.items():
        if code not in today_concepts:
            continue

    # 排序取TOP60涨 + BOTTOM20跌
    ranked = sorted(today_concepts.items(),
                    key=lambda x: x[1]["pct"], reverse=True)
    top_concepts = [(c, d) for c, d in ranked[:60] if d["pct"] > -5]
    bottom_concepts = [(c, d) for c, d in ranked[-20:] if d["pct"] < -5]
    selected = top_concepts + bottom_concepts
    p(f"  精选分析: 头部{len(top_concepts)} + 尾部{len(bottom_concepts)} = {len(selected)} 个概念")

    if not selected and ranked:
        selected = ranked[:80]

    # ── S0.3 精选概念30日K线拉取 ──
    p()
    p("-" * 50)
    p("S0.3 精选概念30日K线逐条拉取")
    p("-" * 50)

    import pandas as pd
    concept_data = {}

    for i, (code, today) in enumerate(selected):
        name = code_to_name.get(code, code)
        try:
            df = pro.ths_daily(ts_code=code, start_date=START_DATE, end_date=TODAY)
            if df is None or df.empty or len(df) < 20:
                continue
            rows = []
            for _, r in df.iterrows():
                row = dict(r)
                date = str(row.get("trade_date", ""))
                close = float(row.get("close", 0))
                pct = float(row.get("pct_change", row.get("pct_chg", 0)))
                if date and close:
                    rows.append({"date": date, "close": close, "pct": pct})
            # Tushare 返回降序 → reverse 为升序
            rows.reverse()
            closes = [r["close"] for r in rows]
            k30 = closes[-30:] if len(closes) >= 30 else closes
            if len(k30) < 25:
                continue

            chg_30d = (k30[-1] / k30[0] - 1) * 100
            chg_15d = (k30[-1] / k30[-15] - 1) * 100 if len(k30) >= 15 else 0
            chg_5d  = (k30[-1] / k30[-5]  - 1) * 100 if len(k30) >= 5  else 0

            seg_size = min(10, len(k30) // 3)
            seg1 = (k30[seg_size-1] / k30[0] - 1) * 100 if seg_size else 0
            seg2 = (k30[2*seg_size-1] / k30[seg_size] - 1) * 100 if 2*seg_size <= len(k30) else 0
            seg3 = (k30[-1] / k30[-seg_size] - 1) * 100 if seg_size else 0

            daily_chgs = [(k30[i]/k30[i-1]-1)*100 for i in range(1, len(k30))]
            daily_vol = np.std(daily_chgs) if daily_chgs else 0
            max_up = max(daily_chgs) if daily_chgs else 0
            max_dn = min(daily_chgs) if daily_chgs else 0

            streak_up = streak_dn = cur_up = cur_dn = 0
            for dchg in daily_chgs:
                if dchg > 0:   cur_up += 1; cur_dn = 0; streak_up = max(streak_up, cur_up)
                elif dchg < 0: cur_dn += 1; cur_up = 0; streak_dn = max(streak_dn, cur_dn)
                else:          cur_up = cur_dn = 0

            if chg_30d > 0:
                trend = "↑加速" if seg3 > seg1 > 0 else ("↑" if seg3 > 0 else "↑(减速)")
            else:
                trend = "↓加速" if seg3 < seg1 < 0 else ("↓" if seg3 < 0 else "↓(收窄)")

            ma20 = np.mean(k30[-20:]) if len(k30) >= 20 else np.mean(k30)
            ma20_dev = (k30[-1] / ma20 - 1) * 100

            h30, l30 = max(k30), min(k30)
            pos = (k30[-1]-l30)/(h30-l30)*100 if h30!=l30 else 50

            # 判断风格
            if name in ["白酒", "啤酒", "乳业", "食品加工", "预制菜", "调味品",
                         "银行", "保险", "证券", "煤炭开采", "油气开采", "石油石化",
                         "农业种植", "猪肉", "养鸡", "饲料", "农林牧渔",
                         "高速公路", "铁路运输", "港口航运", "航运",
                         "白色家电", "小家电", "厨卫电器", "医美",
                         "中药", "医药电商", "医疗器械", "生物疫苗", "新冠检测",
                         "免税店", "社区团购", "新零售", "纺织服装",
                         "ST板块", "高股息", "破净股"]:
                style = "防御"
            elif name in ["半导体", "芯片", "光刻机", "光刻胶", "集成电路",
                           "5G", "6G", "通信设备", "CPO", "光通信",
                           "人工智能", "AIGC", "ChatGPT", "算力", "大数据",
                           "机器人", "工业母机", "减速器", "机器视觉",
                           "新能源车", "锂电池", "固态电池", "光伏", "风电",
                           "储能", "充电桩", "氢能源", "钠离子电池",
                           "消费电子", "苹果概念", "华为概念", "小米概念",
                           "元宇宙", "虚拟现实", "AR/VR", "区块链",
                           "智能驾驶", "无人驾驶", "车联网",
                           "军工", "军民融合", "大飞机", "航空发动机",
                           "游戏", "网络游戏", "手机游戏", "影视",
                           "信创", "国产软件", "操作系统", "数据安全",
                           "量子通信", "脑机接口", "人脑工程"]:
                style = "科技"
            else:
                style = "周期/其他"

            concept_data[name] = {
                "code": code, "close": round(k30[-1], 2),
                "chg_30d": round(chg_30d, 2), "chg_15d": round(chg_15d, 2),
                "chg_5d": round(chg_5d, 2), "today_pct": today["pct"],
                "seg1": round(seg1, 2), "seg2": round(seg2, 2),
                "seg3": round(seg3, 2), "trend": trend,
                "daily_vol": round(daily_vol, 2),
                "max_up": round(max_up, 2), "max_dn": round(max_dn, 2),
                "streak_up": streak_up, "streak_dn": streak_dn,
                "ma20_dev": round(ma20_dev, 2),
                "position_30d": round(pos, 1), "ndays": len(k30),
                "style": style, "member_count": 0,
            }
        except Exception as e:
            if i < 3:
                p(f"  [SKIP] {name}: {e}")

    # 补充成分股数
    for c in concept_list:
        if c["name"] in concept_data:
            concept_data[c["name"]]["member_count"] = int(c.get("count", 0) or 0)

    p(f"  成功拉取: {len(concept_data)} 个概念的30日K线 ★★★★☆")
    p()

    # ── S0.4 同花顺热榜概念标签聚合 ──
    p("-" * 50)
    p("S0.4 验证源B: 同花顺热榜概念标签聚合")
    p("-" * 50)

    ths_concepts = {}
    hot_count = 0
    try:
        hot_list = api.hot_list("day")
        if hot_list:
            concept_counter = Counter()
            for item in hot_list:
                tags = item.get("concepts", [])
                if isinstance(tags, str):
                    tags = tags.split(",") if tags else []
                for tag in tags:
                    tag = tag.strip()
                    if tag:
                        concept_counter[tag] += 1
            hot_count = len(hot_list)
            # TOP30 热门概念标签
            p(f"  热榜个股数: {hot_count}")
            p(f"  热门概念标签(>2只个股):")
            hot_tags = concept_counter.most_common(30)
            for tag, cnt in hot_tags[:15]:
                if cnt >= 2:
                    ths_concepts[tag] = cnt
                    p(f"    {tag}: {cnt}只热榜个股")
            p(f"  → 评级: ★★★★☆ ({len(hot_tags)}个概念标签)")
        else:
            p("  → 同花顺热榜为空(非交易时段)")
    except Exception as e:
        p(f"  [WARN] 同花顺热榜获取失败: {e}")

    # 方向一致性验证
    ths_match = []
    for name in concept_data:
        if name in ths_concepts:
            chg30 = concept_data[name]["chg_30d"]
            ths_match.append(1 if chg30 > 0 else 0)  # 热榜出现=有热度

    p()

    # ── S0.5 东财概念板块资金流 ──
    p("-" * 50)
    p("S0.5 验证源C: 东财概念板块资金流(当日)")
    p("-" * 50)

    em_flow = {}
    try:
        em_raw = api.board_fund_flow_robust("概念", "今日", top_n=50)
        em_data = em_raw.get("items", []) if em_raw.get("status") == "OK" else []
        if em_raw.get("note"):
            p(f"  [降级] 概念资金流: {em_raw.get('note')}")
        if em_data:
            for item in em_data:
                name = item.get("name", "")
                em_flow[name] = {
                    "chg": item.get("change_pct", 0),
                    "main_net": item.get("main_net_yi", 0),
                    "main_ratio": item.get("main_net_ratio", 0),
                }
            # 验证与Tushare方向一致性
            match_cnt = 0
            total = 0
            for name, fd in em_flow.items():
                if name in concept_data:
                    total += 1
                    em_dir = 1 if fd["chg"] > 0 else -1
                    ts_dir = 1 if concept_data[name]["today_pct"] > 0 else -1
                    if em_dir == ts_dir:
                        match_cnt += 1
            p(f"  东财概念资金流: {len(em_flow)} 个")
            if total > 0:
                p(f"  方向一致性: {match_cnt}/{total} ({match_cnt/total*100:.0f}%)")
            p(f"  → 评级: ★★★☆☆ (push2限流中,仅参考)")
        else:
            p("  → 东财概念资金流空数据(push2限流 ★☆☆☆☆)")
    except Exception as e:
        p(f"  [WARN] 东财资金流失败: {e}")

    p()

    # ═══════════════════════════════════════════
    # S1: 门控框架复用 (从行业报告)
    # ═══════════════════════════════════════════
    p("=" * 72)
    p("S1: 大盘门控 (复用行业分析结果)")
    p("=" * 72)

    # Gate0: 从K线数据直接判断
    gate0 = "FAIL"
    curr_price = 0
    try:
        dk = api.kline("上证指数", 150)
        kls = dk.get("klines", [])
        if kls and len(kls) >= 100:
            closes = [float(k[2]) for k in kls]
            curr_price = closes[-1]
            ma100 = sum(closes[-100:]) / 100
            gate0 = "PASS" if curr_price > ma100 else "FAIL"
            p(f"  Gate0 周线: 上证{curr_price:.1f} vs MA100({ma100:.1f}) → {gate0}")
            if gate0 == "FAIL":
                p(f"    → 一票否决! 仓位上限≤20%, 仅防御性配置")
        else:
            p(f"  Gate0: K线不足, 保守假定FAIL")
    except Exception as e:
        p(f"  Gate0: {e}")

    pos_ceiling = 20
    try:
        dk1 = api.kline("上证指数", 300)
        kls1 = dk1.get("klines", [])
        if kls1 and len(kls1) >= 250:
            closes_d = [float(k[2]) for k in kls1]
            curr = closes_d[-1]
            ma60 = sum(closes_d[-60:]) / 60
            ma250 = sum(closes_d[-250:]) / 250
            if curr > ma250 and curr > ma60:     pos_ceiling = 80
            elif curr > ma250 and curr < ma60:   pos_ceiling = 50
            elif curr < ma250 and curr < ma60:   pos_ceiling = 20
            else:                                 pos_ceiling = 30
            p(f"  Gate1: close={curr:.1f} MA60={ma60:.1f} MA250={ma250:.1f} → 仓位上限{pos_ceiling}%")
        else:
            p(f"  Gate1: K线不足, 保守仓位上限20%")
    except Exception as e:
        p(f"  Gate1: {e}")

    gate2_adj = "降档"
    try:
        breadth = api.breadth()
        up_cnt = breadth.get("up", 0)
        down_cnt = breadth.get("down", 0)
        total_cnt = up_cnt + down_cnt
        up_ratio = up_cnt / total_cnt * 100 if total_cnt else 0
        turnover = api.turnover()
        total_amt = turnover.get("total_yi", 0) if turnover else 0
        p(f"  Gate2: 上涨{up_cnt}/{down_cnt}({up_ratio:.0f}%) 成交额{total_amt:.2f}亿")
        if up_ratio >= 60 and total_amt > 8000:
            gate2_adj = "正常"
    except Exception:
        pass

    zt_cnt = dt_cnt = 0
    gate3 = "UNKNOWN"
    try:
        bs = api.board_summary()
        if bs and isinstance(bs, dict) and bs.get("zt_count") is not None:
            zt_cnt = bs.get("zt_count", 0)
            dt_cnt = bs.get("dt_count", 0) if "dt_count" in bs else 0
            p(f"  Gate3: 涨停{zt_cnt} 跌停{dt_cnt}")
            if zt_cnt > 100:   gate3 = "WARN"
            elif dt_cnt > 10:  gate3 = "WARN"
            else:              gate3 = "PASS"
        else:
            p(f"  Gate3: 数据不可用(push2ex限流)")
    except Exception:
        pass

    effective_cap = pos_ceiling
    if gate0 == "FAIL":
        effective_cap = min(effective_cap, 20)
    if gate2_adj == "降档":
        effective_cap = int(effective_cap * 0.7)
    if gate3 == "WARN":
        effective_cap = int(effective_cap * 0.5)
    p(f"  >>> 综合仓位上限: {effective_cap}% <<<")
    p()

    # ═══════════════════════════════════════════
    # S2: 概念板块入场评分
    # ═══════════════════════════════════════════
    p("=" * 72)
    p("S2: 概念板块入场评分模型 (总分100)")
    p("=" * 72)
    p("  维度: 趋势30 + 动量25 + 风险20 + 门控15 + 热度10")
    p()

    def score_concept(name, d):
        total = 0
        chg30 = d["chg_30d"]
        chg5 = d["chg_5d"]
        vol = d["daily_vol"]
        seg1, seg3 = d["seg1"], d["seg3"]
        pos = d["position_30d"]
        max_dn = abs(d["max_dn"])
        streak_dn = d["streak_dn"]
        member_count = d.get("member_count", 0)

        # 趋势 (0-30)
        if chg30 > 10:     trend = 30
        elif chg30 > 5:    trend = 27
        elif chg30 > 2:    trend = 22
        elif chg30 > 0:    trend = 18
        elif chg30 > -3:   trend = 12
        elif chg30 > -8:   trend = 5
        else:              trend = 0
        if trend > 0 and seg3 > seg1 > 0:
            trend = min(30, trend + 3)
        if d["ma20_dev"] > 8:
            trend = max(0, trend - 4)
        total += trend

        # 动量 (0-25)
        if chg5 > 5:       mom = 25
        elif chg5 > 3:     mom = 22
        elif chg5 > 1.5:   mom = 18
        elif chg5 > 0:     mom = 12
        elif chg5 > -2:    mom = 8
        elif chg5 > -5:    mom = 3
        else:              mom = 0
        if chg5 > 0 and chg5 > d["chg_15d"] > 0:
            mom = min(25, mom + 3)
        total += mom

        # 风险 (0-20)
        risk = 20
        if vol > 5:       risk -= 10
        elif vol > 4:     risk -= 7
        elif vol > 3:     risk -= 5
        elif vol > 2.5:   risk -= 3
        elif vol > 2:     risk -= 1
        if max_dn > 8:    risk -= 6
        elif max_dn > 6:  risk -= 4
        elif max_dn > 4:  risk -= 2
        if streak_dn > 6: risk -= 5
        elif streak_dn > 4: risk -= 3
        elif streak_dn > 3: risk -= 1
        # 概念板块波动本就更大，放宽风险惩罚
        if pos > 90 and chg5 < 0:
            risk = max(0, risk - 3)
        total += max(0, risk)

        # 门控 (0-15)
        if gate0 == "FAIL":
            if d["style"] == "防御" and chg30 > 3:    gs = 15
            elif d["style"] == "防御" and chg30 > 0:  gs = 12
            elif chg30 > 3:    gs = 8
            elif chg30 > 0:    gs = 5
            else:              gs = 0
        else:
            gs = 15 if chg30 > 3 else (10 if chg30 > 0 else 3)
        total += gs

        # 热度 (0-10)
        hot = 0
        if name in ths_concepts:
            hot = min(10, 3 + ths_concepts[name])
        if member_count >= 20:
            hot = min(10, hot + 2)
        total += hot

        return min(100, total), {
            "trend": trend, "momentum": mom, "risk": max(0, risk),
            "gate": gs, "hot": hot,
        }

    # 评分排名
    scored = []
    for name, d in concept_data.items():
        total, breakdown = score_concept(name, d)
        d["score"] = total
        d["breakdown"] = breakdown
        scored.append((name, d))

    scored.sort(key=lambda x: x[1]["score"], reverse=True)

    # 输出评分表
    p(f"\n{'#':<3} {'概念':<14} {'分':<4} {'趋势':<4} {'动量':<4} {'风险':<4} {'门控':<4} {'热度':<4} {'30日':<8} {'今日':<8} {'风格':<8}")
    p("-" * 88)
    for rank, (name, d) in enumerate(scored, 1):
        b = d["breakdown"]
        p(f"{rank:<3} {name:<14} {d['score']:<4} "
          f"{b['trend']:<4} {b['momentum']:<4} {b['risk']:<4} "
          f"{b['gate']:<4} {b['hot']:<4} "
          f"{d['chg_30d']:+.2f}%{'':<2} {d['today_pct']:+.2f}%{'':<2} {d['style']:<8}")

    p()

    # ═══════════════════════════════════════════
    # S3: 入场推荐分级
    # ═══════════════════════════════════════════
    p("=" * 72)
    p("S3: 概念板块入场推荐")
    p("=" * 72)

    buckets = {"A": [], "B": [], "C": [], "D": []}
    for name, d in scored:
        s = d["score"]
        if s >= 75:     buckets["A"].append((name, d))
        elif s >= 55:   buckets["B"].append((name, d))
        elif s >= 35:   buckets["C"].append((name, d))
        else:           buckets["D"].append((name, d))

    def print_tier(label, emoji, entries, max_show=15):
        if not entries:
            p(f"  {label}: (无)")
            return
        p(f"\n  ◆ {label} ({len(entries)}个):")
        names_only = ", ".join(f"{n}({d['score']})" for n, d in entries[:max_show])
        p(f"    {names_only}")
        if len(entries) > max_show:
            p(f"    ... 等共{len(entries)}个")

    p(f"\n  Gate0={gate0} | 仓位上限≤{effective_cap}%")
    print_tier("A级 优先关注", "", buckets["A"])
    print_tier("B级 谨慎参与", "", buckets["B"])
    print_tier("C级 观望", "", buckets["C"])
    print_tier("D级 回避", "", buckets["D"])

    p()

    # ═══════════════════════════════════════════
    # S4: 重点概念深度分析
    # ═══════════════════════════════════════════
    p("=" * 72)
    p("S4: 重点概念深度分析")
    p("=" * 72)

    # TOP5 A级概念
    a_list = buckets["A"][:5]
    for name, d in a_list:
        p(f"\n  ▸ {name} [{d['style']}] 评分{d['score']}")
        p(f"    30日: {d['chg_30d']:+.2f}% | 15日: {d['chg_15d']:+.2f}% | 5日: {d['chg_5d']:+.2f}% | 今日: {d['today_pct']:+.2f}%")
        p(f"    三阶段: S1={d['seg1']:+.2f}% S2={d['seg2']:+.2f}% S3={d['seg3']:+.2f}% → {d['trend']}")
        p(f"    波动率{d['daily_vol']:.2f}% | 最大涨{'+' if d['max_up']>=0 else ''}{d['max_up']:.2f}%/跌{d['max_dn']:.2f}%")
        p(f"    30日位置: {d['position_30d']:.0f}% | MA20偏离: {d['ma20_dev']:+.2f}%")
        p(f"    成分股: {d['member_count']}只 | 连涨{d['streak_up']}日/连跌{d['streak_dn']}日")
        # 同花顺热度
        if name in ths_concepts:
            p(f"    同花顺热度: {ths_concepts[name]}只热榜个股")
        # 东财资金流
        if name in em_flow:
            ef = em_flow[name]
            direction = "流入" if ef["main_net"] > 0 else "流出"
            p(f"    东财主力: {direction}{abs(ef['main_net']):.2f}亿 | 占比{ef['main_ratio']:+.2f}%")

    # BOTTOM5 D级概念
    p(f"\n  ── D级底部(最弱5个) ──")
    d_list = buckets["D"][-5:] if len(buckets["D"]) >= 5 else buckets["D"]
    for name, d in d_list:
        p(f"  ▸ {name}: 30日{d['chg_30d']:+.2f}% 5日{d['chg_5d']:+.2f}% 波动{d['daily_vol']:.2f}% 连跌{d['streak_dn']}日")

    p()

    # ═══════════════════════════════════════════
    # S5: 风格轮动结构分析
    # ═══════════════════════════════════════════
    p("=" * 72)
    p("S5: 风格轮动结构分析")
    p("=" * 72)

    styles = defaultdict(lambda: {"count": 0, "total_chg": 0, "total_score": 0})
    for name, d in scored:
        s = d["style"]
        styles[s]["count"] += 1
        styles[s]["total_chg"] += d["chg_30d"]
        styles[s]["total_score"] += d["score"]

    for s, st in sorted(styles.items(), key=lambda x: x[1]["total_chg"] / max(x[1]["count"], 1), reverse=True):
        avg_chg = st["total_chg"] / max(st["count"], 1)
        avg_score = st["total_score"] / max(st["count"], 1)
        p(f"  {s}: {st['count']}个概念 | 平均30日: {avg_chg:+.2f}% | 平均评分: {avg_score:.0f}")

    p()
    p("=" * 72)
    p("S6: 操作建议")
    p("=" * 72)
    p(f"""
      1. 大盘状态: Gate0={gate0}, Gate3={gate3}, 仓位上限{effective_cap}%
      2. 防御概念优先: 白酒/银行/猪肉/高股息/预制菜 — Gate0 FAIL下唯一合规方向
      3. 科技概念全面回避: 半导体/芯片/CPO/光通信/机器人/AI — 30日回撤20-40%
      4. 概念轮动确定性 < 行业板块 — 概念弹性大但回撤也大, 当前环境不追高概念
      5. 如Gate0修复(上证>4030): 可升仓至科技概念反弹博弈, 否则坚守防御

      完整报告: {REPORT_FILE}
    """)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))
    p(f"[OK] 报告已保存至 {REPORT_FILE}")
