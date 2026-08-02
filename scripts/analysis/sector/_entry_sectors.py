#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""入场板块分析：多源验证 + 四道门控 + 板块评分排名 | 盘后 2026-07-30"""
import sys, os, io, json, time, random
from datetime import datetime, timedelta
from collections import OrderedDict

# Windows GBK→UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import pandas as pd
import numpy as np

# ── 项目路径 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from market_api import api
from tushare_api import get_pro

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ── Tushare 配置 ──
PRO = get_pro()

TODAY = "20260730"
REPORT_FILE = os.path.join(BASE_DIR, "_entry_sectors_report.txt")
flow = None  # S0.4 资金流数据

# ── 防御/科技板块分类 ──
DEFENSE_SECTORS = {
    "食品饮料", "银行", "非银金融", "煤炭", "石油石化", "农林牧渔",
    "交通运输", "公用事业", "钢铁", "商贸零售", "美容护理"
}
TECH_SECTORS = {
    "电子", "通信", "计算机", "国防军工", "电力设备", "机械设备",
    "传媒", "汽车"
}

# ── 输出缓冲 ──
out_lines = []

def p(*args):
    line = " ".join(str(a) for a in args)
    out_lines.append(line)
    print(line)

# ═══════════════════════════════════════════
# S0: 数据获取 + 交叉验证
# ═══════════════════════════════════════════
if __name__ == "__main__":
    p("=" * 60)
    p("入场板块分析：多源验证 + 四道门控 + 板块评分")
    p(f"盘后 | {TODAY[:4]}-{TODAY[4:6]}-{TODAY[6:8]}")
    p("=" * 60)
    p()

    # ── S0.1 腾讯指数快照验证 ──
    p("-" * 50)
    p("S0.1 XV① 腾讯指数快照验证")
    p("-" * 50)
    try:
        snaps = api.index_snapshot()
        idx_map = {}
        for s in snaps:
            code = s.get("code", "")
            idx_map[code] = s
        for key in ["sh000001", "sz399001", "sz399006", "sh000688"]:
            if key in idx_map:
                s = idx_map[key]
                p(f"  {key}: price={s.get('price')} change_pct={s.get('change_pct')}%  name={s.get('name','')}")
        p(f"  → 成功获取 {len(snaps)} 个指数")
    except Exception as e:
        p(f"  [WARN] 腾讯指数获取失败: {e}")

    p()

    # ── S0.2 Tushare SW31 30日数据 ──
    p("-" * 50)
    p("S0.2 主源A: Tushare SW31 30日K线 (逐行业拉取)")
    p("-" * 50)

    START_DATE = "20260618"
    sector_data = {}

    name_map = {
        '801120.SI': '食品饮料', '801780.SI': '银行', '801790.SI': '非银金融',
        '801950.SI': '煤炭', '801960.SI': '石油石化', '801150.SI': '医药生物',
        '801010.SI': '农林牧渔', '801170.SI': '交通运输', '801980.SI': '美容护理',
        '801110.SI': '家用电器', '801200.SI': '商贸零售', '801160.SI': '公用事业',
        '801040.SI': '钢铁', '801760.SI': '传媒', '801130.SI': '纺织服饰',
        '801180.SI': '房地产', '801210.SI': '社会服务', '801880.SI': '汽车',
        '801720.SI': '建筑装饰', '801750.SI': '计算机', '801140.SI': '轻工制造',
        '801230.SI': '综合', '801050.SI': '有色金属', '801030.SI': '基础化工',
        '801740.SI': '国防军工', '801730.SI': '电力设备', '801710.SI': '建筑材料',
        '801890.SI': '机械设备', '801080.SI': '电子', '801770.SI': '通信',
        '801020.SI': '环保',
    }
    # 代码→名称反转
    code_to_name = {v: k for k, v in name_map.items()} if len(name_map) > 0 else {}

    try:
        # Step1: 获取SW31行业列表
        sw_class = PRO.index_classify(level='L1', src='SW2021',
                                       fields='index_code,industry_name')
        sw_codes = []
        for _, row in sw_class.iterrows():
            code = row['index_code']
            name = row['industry_name']
            sw_codes.append((code, name))
        p(f"  SW31分类: {len(sw_codes)} 行业")
    except Exception as e:
        p(f"  [FALLBACK] index_classify失败({e})，用硬编码SW31代码")
        sw_codes = [(k, v) for k, v in code_to_name.items()]

    success = 0
    for code, name in sw_codes:
        try:
            df = PRO.sw_daily(ts_code=code,
                              start_date=START_DATE, end_date=TODAY,
                              fields='ts_code,trade_date,close')
            if df is None or df.empty or len(df) < 25:
                continue
            # Tushare 返回降序 → reverse 为升序
            rows = [(x['trade_date'], float(x['close'])) for _, x in df.iterrows()]
            rows.reverse()
            closes = [c for _, c in rows]
            k30 = closes[-30:] if len(closes) >= 30 else closes
            if len(k30) < 28:
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
                trend = "↑" if seg3 > seg1 else "↑(减速)"
            else:
                trend = "↓" if seg3 < seg1 else "↓(收窄)"

            ma20 = np.mean(k30[-20:]) if len(k30) >= 20 else np.mean(k30)
            ma20_dev = (k30[-1] / ma20 - 1) * 100
            h30, l30 = max(k30), min(k30)
            pos = (k30[-1]-l30)/(h30-l30)*100 if h30!=l30 else 50

            sector_data[name] = {
                "code": code, "close": round(k30[-1], 2),
                "chg_30d": round(chg_30d, 2), "chg_15d": round(chg_15d, 2),
                "chg_5d": round(chg_5d, 2),
                "seg1": round(seg1, 2), "seg2": round(seg2, 2),
                "seg3": round(seg3, 2), "trend": trend,
                "daily_vol": round(daily_vol, 2),
                "max_up": round(max_up, 2), "max_dn": round(max_dn, 2),
                "streak_up": streak_up, "streak_dn": streak_dn,
                "ma20_dev": round(ma20_dev, 2),
                "position_30d": round(pos, 1), "ndays": len(k30),
            }
            success += 1
        except Exception as e:
            if success == 0:
                p(f"  [SKIP] {code} {name}: {e}")

    p(f"  成功获取: {success}/{len(sw_codes)} 行业")
    p(f"  日期范围: {START_DATE} ~ {TODAY}")

    if success == 0:
        p("  [FATAL] 无法获取SW31数据，尝试用腾讯行业替代...")
        try:
            tc_sectors = api.sectors(top_n=40)
            if tc_sectors:
                for s in tc_sectors:
                    name = s.get("name", "")
                    chg = s.get("change_pct", 0)
                    sector_data[name] = {
                        "code": name, "close": s.get("price", 0),
                        "chg_30d": chg, "chg_15d": chg, "chg_5d": chg,
                        "seg1": chg/3, "seg2": chg/3, "seg3": chg/3,
                        "trend": "↑" if chg>0 else "↓",
                        "daily_vol": 2.0, "max_up": 0, "max_dn": 0,
                        "streak_up": 0, "streak_dn": 0,
                        "ma20_dev": chg/3, "position_30d": 50, "ndays": 1,
                    }
                p(f"  腾讯行业替代: {len(sector_data)} 个")
        except Exception as e2:
            p(f"  [FATAL] 腾讯行业也失败: {e2}")
        import traceback
        traceback.print_exc()

    p()

    # ── S0.3 腾讯行业实时验证 ──
    p("-" * 50)
    p("S0.3 验证源B: 腾讯行业板块实时数据")
    p("-" * 50)

    tc_validation = {}
    try:
        tc_sectors = api.sectors(top_n=40)
        if tc_sectors:
            tc_map = {}
            for s in tc_sectors:
                tc_map[s.get("name", "")] = s

            # 方向验证映射
            verify_map = {
                "食品饮料": "食品饮料", "银行": "银行", "石油石化": "石油行业",
                "电子": "电子", "通信": "通信设备", "机械设备": "工程机械",
                "家用电器": "家用电器", "国防军工": "航天航空", "煤炭": "煤炭行业",
                "汽车": "汽车整车", "钢铁": "钢铁行业", "有色金属": "有色金属",
                "医药生物": "医药", "建筑材料": "水泥建材", "电力设备": "电源设备",
                "计算机": "计算机设备", "传媒": "文化传媒", "房地产": "房地产开发",
                "银行": "银行", "非银金融": "证券", "农林牧渔": "农牧饲渔",
            }

            directions = []
            for sw_name, tc_name in verify_map.items():
                if sw_name in sector_data and tc_name in tc_map:
                    sw_dir = 1 if sector_data[sw_name]["chg_30d"] > 0 else -1
                    tc_dir = 1 if tc_map[tc_name].get("change_pct", 0) > 0 else -1
                    directions.append(1 if sw_dir == tc_dir else 0)
                    tc_validation[sw_name] = {
                        "tc_chg": tc_map[tc_name].get("change_pct", 0),
                        "sw_chg": sector_data[sw_name]["chg_30d"],
                        "match": sw_dir == tc_dir,
                    }

            match_rate = sum(directions) / len(directions) * 100 if directions else 0
            p(f"  腾讯行业数: {len(tc_sectors)}")
            p(f"  方向一致性: {sum(directions)}/{len(directions)} ({match_rate:.0f}%)")

            stars = "★★★★★" if match_rate >= 90 else ("★★★★☆" if match_rate >= 70 else "★★★☆☆")
            p(f"  评级: {stars}")
    except Exception as e:
        p(f"  [WARN] 腾讯行业验证失败: {e}")

    p()

    # ── S0.4 东财 board_fund_flow 验证 ──
    p("-" * 50)
    p("S0.4 验证源C: 东财板块资金流(当日)")
    p("-" * 50)
    try:
        flow_raw = api.board_fund_flow_robust("行业", "今日", top_n=31)
        flow = flow_raw.get("items", []) if flow_raw.get("status") == "OK" else []
        if flow_raw.get("note"):
            p(f"  [降级] 行业资金流: {flow_raw.get('note')}")
        p(f"  获取: {len(flow) if flow else 0} 条资金流数据")
        if flow:
            for f in flow[:5]:
                direction = "流入" if f.get("main_net_yi", 0) > 0 else "流出"
                p(f"    {f.get('name','')}: {f.get('change_pct',0):+.2f}% 主力{direction}{abs(f.get('main_net_yi',0)):.2f}亿")
    except Exception as e:
        p(f"  [WARN] 东财资金流获取失败: {e}")

    p()

    # ═══════════════════════════════════════════
    # S1: 四道门控 大盘判定
    # ═══════════════════════════════════════════
    p("=" * 60)
    p("S1: 四道门控 大盘判定 (Gate Framework)")
    p("=" * 60)

    # Gate0: 周线判定 (日K MA100 ≈ 20周MA)
    gate0 = "UNKNOWN"
    curr_price = 0
    try:
        dk = api.kline("上证指数", 150)
        kls = dk.get("klines", [])
        if kls and len(kls) >= 100:
            # 腾讯K线格式: [date, open, close, high, low, volume]
            closes = [float(k[2]) for k in kls]
            curr_price = closes[-1]
            ma100 = sum(closes[-100:]) / 100  # ≈ 20周MA
            gate0 = "PASS" if curr_price > ma100 else "FAIL"
            p(f"  Gate0 周线: 上证{curr_price:.1f} vs MA100({ma100:.1f}) → {gate0}")
            if gate0 == "FAIL":
                p(f"    → 一票否决! 仓位上限≤20%, 仅防御性配置")
        else:
            p(f"  Gate0: 周K线数据不足({len(klines) if klines else 0}根)")
            gate0 = "UNKNOWN"
    except Exception as e:
        p(f"  Gate0: 获取失败({e})")
        gate0 = "UNKNOWN"

    # Gate1: MA60/MA250
    pos_ceiling = 20
    try:
        dk = api.kline("上证指数", 300)
        if dk and dk.get("klines") and len(dk["klines"]) >= 250:
            closes_d = [float(k[2]) for k in dk["klines"]]
            ma60 = sum(closes_d[-60:]) / 60
            ma250 = sum(closes_d[-250:]) / 250
            curr = closes_d[-1]
            if curr > ma250 and curr > ma60:
                pos_ceiling = 80
            elif curr > ma250 and curr < ma60:
                pos_ceiling = 50
            elif curr < ma250 and curr < ma60:
                pos_ceiling = 20
            else:
                pos_ceiling = 30
            p(f"  Gate1: close={curr:.1f} MA60={ma60:.1f} MA250={ma250:.1f} → 仓位上限{pos_ceiling}%")
        else:
            p(f"  Gate1: K线不足, 保守假定仓位上限{pos_ceiling}%")
    except Exception as e:
        p(f"  Gate1: 获取失败({e}), 保守假定仓位上限{pos_ceiling}%")

    # Gate2: 量能广度
    try:
        breadth = api.breadth()
        up_cnt = breadth.get("up", 0)
        down_cnt = breadth.get("down", 0)
        total_cnt = up_cnt + down_cnt
        up_ratio = up_cnt / total_cnt * 100 if total_cnt else 0
        turnover = api.turnover()
        total_amt = turnover.get("total_yi", 0)
        p(f"  Gate2: 上涨{up_cnt}/{down_cnt}({up_ratio:.0f}%) 成交额{total_amt:.2f}亿")
        gate2_adj = "降档" if up_ratio < 60 else "正常"
    except Exception:
        gate2_adj = "降档"
        p(f"  Gate2: 数据不足, 假定降档")

    # Gate3: 涨跌停情绪 (push2ex限流中，用 board_summary)
    zt_cnt = dt_cnt = 0
    gate3 = "UNKNOWN"
    try:
        bs = api.board_summary()
        if bs and isinstance(bs, dict) and bs.get("zt_count") is not None:
            zt_cnt = bs.get("zt_count", 0)
            dt_cnt = bs.get("dt_count", 0) if "dt_count" in bs else 0
            zr_rate = bs.get("zt_close_rate", 0) or bs.get("zr_rate", 0)
            p(f"  Gate3: 涨停{zt_cnt} 跌停{dt_cnt} 回封率{zr_rate}%")
            if zt_cnt > 100:
                gate3 = "WARN"
                p(f"    → 情绪过热，不开新仓")
            elif dt_cnt > 10:
                gate3 = "WARN"
                p(f"    → 恐慌蔓延，减半仓位")
            else:
                gate3 = "PASS"
                p(f"    → 情绪正常")
        else:
            p(f"  Gate3: board_summary返回空(push2ex限流)")
    except Exception as e:
        p(f"  Gate3: 获取失败({e})")

    p()

    # ═══════════════════════════════════════════
    # S2: 板块入场评分模型
    # ═══════════════════════════════════════════
    p("=" * 60)
    p("S2: 板块入场评分模型 (总分100)")
    p("=" * 60)
    p("  评分维度: 趋势30 + 动量25 + 风险20 + 门控合规15 + 数据可靠10")
    p()

    def score_sector(name, d):
        """板块入场评分（0-100）"""
        score = 0

        # ── 趋势评分 (0-30) ──
        chg30 = d["chg_30d"]
        trend_score = 0
        if chg30 > 5:
            trend_score = 30
        elif chg30 > 2:
            trend_score = 25
        elif chg30 > 0:
            trend_score = 20
        elif chg30 > -3:
            trend_score = 12
        elif chg30 > -10:
            trend_score = 5
        else:
            trend_score = 0

        # 趋势加速加分
        seg1, seg3 = d["seg1"], d["seg3"]
        if trend_score > 0 and seg3 > seg1 > 0:
            trend_score = min(30, trend_score + 5)  # 加速上涨
        elif trend_score < 10 and seg3 > seg1:
            trend_score = min(20, trend_score + 3)  # 跌幅收窄

        # MA20偏离
        if d["ma20_dev"] > 5:
            trend_score = max(0, trend_score - 3)  # 远离均线，追高风险
        elif d["ma20_dev"] < -5 and trend_score < 15:
            trend_score = min(15, trend_score + 3)  # 超跌反弹可能

        score += trend_score

        # ── 动量评分 (0-25) ──
        chg5 = d["chg_5d"]
        chg15 = d["chg_15d"]
        momentum_score = 0

        if chg5 > 3:
            momentum_score = 25
        elif chg5 > 1.5:
            momentum_score = 20
        elif chg5 > 0:
            momentum_score = 12
        elif chg5 > -2:
            momentum_score = 8
        elif chg5 > -5:
            momentum_score = 3
        else:
            momentum_score = 0

        # 近5日强于近15日 → 加速
        if chg5 > 0 and chg15 > 0 and chg5 > chg15 * 0.3:
            momentum_score = min(25, momentum_score + 3)

        # 近5日收窄跌幅
        if chg5 > chg15 and chg15 < 0:
            momentum_score = min(20, momentum_score + 5)

        score += momentum_score

        # ── 风险评分 (0-20) ──
        vol = d["daily_vol"]
        max_dn = abs(d["max_dn"])
        streak_dn = d["streak_dn"]
        risk_score = 20

        # 波动率惩罚
        if vol > 4:
            risk_score -= 8
        elif vol > 3:
            risk_score -= 5
        elif vol > 2.5:
            risk_score -= 3
        elif vol > 2:
            risk_score -= 1

        # 最大单日跌幅惩罚
        if max_dn > 7:
            risk_score -= 5
        elif max_dn > 5:
            risk_score -= 3
        elif max_dn > 4:
            risk_score -= 1

        # 连跌惩罚
        if streak_dn > 5:
            risk_score -= 5
        elif streak_dn > 4:
            risk_score -= 3
        elif streak_dn > 3:
            risk_score -= 1

        risk_score = max(0, risk_score)
        score += risk_score

        # ── 门控合规评分 (0-15) ──
        gate_score = 0
        if gate0 == "FAIL":
            # 下跌市场中，只有上涨的防御板块合规
            if chg30 > 3:
                gate_score = 15
            elif chg30 > 0:
                gate_score = 12
            elif chg30 > -5:
                gate_score = 5
            else:
                gate_score = 0
        else:
            gate_score = 12 if chg30 > 0 else 6

        score += gate_score

        # ── 数据可靠性 (0-10) ──
        reliability = 8  # SW31基准
        if name in tc_validation and tc_validation[name].get("match"):
            reliability += 2  # 腾讯验证通过
        score += min(10, reliability)

        # ── 额外调整 ──
        # 高波动+高涨幅 → 过热警告
        if vol > 3 and chg30 > 5:
            score = max(0, score - 5)

        # 价格在30日高位 + 动能减弱
        if d["position_30d"] > 85 and chg5 < 0:
            score = max(0, score - 5)

        return min(100, score), {
            "trend": trend_score,
            "momentum": momentum_score,
            "risk": risk_score,
            "gate": gate_score,
            "reliability": min(10, reliability),
        }

    # 对所有行业评分
    scored_sectors = []
    for name, d in sector_data.items():
        total, breakdown = score_sector(name, d)
        d["score"] = total
        d["breakdown"] = breakdown
        d["type"] = "防御" if name in DEFENSE_SECTORS else ("科技" if name in TECH_SECTORS else "周期/其他")
        scored_sectors.append((name, d))

    # 按评分降序
    scored_sectors.sort(key=lambda x: x[1]["score"], reverse=True)

    # 输出评分表
    p(f"{'排名':<4} {'行业':<10} {'评分':<5} {'趋势':<5} {'动量':<5} {'风险':<5} {'门控':<5} {'可靠':<5} {'30日':<8} {'近5日':<8} {'类型':<8}")
    p("-" * 85)
    for rank, (name, d) in enumerate(scored_sectors, 1):
        bd = d["breakdown"]
        p(f"{rank:<4} {name:<10} {d['score']:<5} "
          f"{bd['trend']:<5} {bd['momentum']:<5} {bd['risk']:<5} "
          f"{bd['gate']:<5} {bd['reliability']:<5} "
          f"{d['chg_30d']:+.2f}%{'':<3} {d['chg_5d']:+.2f}%{'':<3} {d['type']:<8}")

    p()

    # ═══════════════════════════════════════════
    # S3: 入场推荐分级
    # ═══════════════════════════════════════════
    p("=" * 60)
    p("S3: 入场推荐分级")
    p("=" * 60)

    # 评分阈值
    TIERS = [
        ("A级 优先关注", 75, "趋势明确+低波动+数据可靠，适合Gate0 FAIL下的防御配置"),
        ("B级 谨慎关注", 60, "有一定上行趋势但存在风险因素，小仓位试探"),
        ("C级 观望", 45, "趋势不明或风险较高，暂不参与"),
        ("D级 回避", 0, "趋势向下或高风险，坚决不参与"),
    ]

    tier_buckets = {"A": [], "B": [], "C": [], "D": []}

    for name, d in scored_sectors:
        s = d["score"]
        if s >= 75:
            tier_buckets["A"].append((name, d))
        elif s >= 60:
            tier_buckets["B"].append((name, d))
        elif s >= 45:
            tier_buckets["C"].append((name, d))
        else:
            tier_buckets["D"].append((name, d))

    for tier, threshold, desc in TIERS:
        bucket_key = tier[0]
        items = tier_buckets[bucket_key]
        p(f"\n  [{tier}] (评分≥{threshold})")
        p(f"  说明: {desc}")
        if items:
            p(f"  板块数: {len(items)}")
            for name, d in items:
                stars = "★" * min(5, d["score"] // 20 + 1)
                bd = d["breakdown"]
                risk_note = ""
                if d["daily_vol"] > 3:
                    risk_note = " [!高波动]"
                if d["streak_dn"] > 3:
                    risk_note += " [!连跌风险]"
                if d["position_30d"] > 85:
                    risk_note += " [!高位]"
                p(f"    {name}: {d['score']}分 {stars} | "
                  f"30日{d['chg_30d']:+.2f}% 近5日{d['chg_5d']:+.2f}% | "
                  f"波动率{d['daily_vol']:.2f}% | {d['trend']}{risk_note}")
        else:
            p(f"  (无板块入选)")

    p()

    # ═══════════════════════════════════════════
    # S4: 重点板块深度分析
    # ═══════════════════════════════════════════
    p("=" * 60)
    p("S4: 重点板块深度分析 (评分≥60)")
    p("=" * 60)

    focus = [item for item in scored_sectors if item[1]["score"] >= 60]

    for rank, (name, d) in enumerate(focus, 1):
        p(f"\n  [{rank}] {name} ({d['type']}) — {d['score']}分")
        p(f"    30日: {d['chg_30d']:+.2f}% | 近15日: {d['chg_15d']:+.2f}% | 近5日: {d['chg_5d']:+.2f}%")
        p(f"    三阶段: {d['seg1']:+.2f}% → {d['seg2']:+.2f}% → {d['seg3']:+.2f}%")
        p(f"    波动率: {d['daily_vol']:.2f}% | 最大日涨: {d['max_up']:+.2f}% | 最大日跌: {d['max_dn']:+.2f}%")
        p(f"    连涨: {d['streak_up']}日 | 连跌: {d['streak_dn']}日 | MA20偏离: {d['ma20_dev']:+.2f}%")
        p(f"    30日位置: {d['position_30d']:.1f}% (0=最低, 100=最高)")

        # 数据验证状态
        if name in tc_validation:
            tv = tc_validation[name]
            p(f"    腾讯验证: {'✓ 一致' if tv['match'] else '✗ 分歧'} "
              f"(SW30日{tv['sw_chg']:+.1f}% vs 腾讯{tv['tc_chg']:+.1f}%)")

        # 入场建议
        if d["score"] >= 75:
            if d["chg_5d"] > 0 and d["daily_vol"] < 2.0:
                p(f"    → 建议: 稳健上涨+低波动，可作为防御配置核心。Gate0 FAIL下建议仓位≤10%")
            elif d["chg_5d"] > 0:
                p(f"    → 建议: 上涨趋势确认，注意波动率偏高。分批建仓，仓位≤8%")
            else:
                p(f"    → 建议: 短期回调中，等待近5日翻正后介入")
        elif d["score"] >= 60:
            if d["chg_5d"] > 0 and d["seg3"] > d["seg1"]:
                p(f"    → 建议: 趋势改善中，可小仓位试仓(≤5%)，确认后再加仓")
            else:
                p(f"    → 建议: 暂时观望，等待技术面进一步改善")

    p()

    # ═══════════════════════════════════════════
    # S5: 数据验证总结
    # ═══════════════════════════════════════════
    p("=" * 60)
    p("S5: 数据源交叉验证总结")
    p("=" * 60)

    tc_match_cnt = sum(1 for v in tc_validation.values() if v.get("match"))
    tc_total = len(tc_validation)
    p(f"  主源A Tushare SW31: {len(sector_data)}/31个行业 ★★★★☆")
    p(f"  验证源B 腾讯行业: 方向一致性 {tc_match_cnt}/{tc_total} ★★★★☆" if tc_total else "  验证源B: 数据不可用")
    p(f"  验证源C 东财资金流: {'可用' if flow else '限流(空)'} ★★★☆☆")

    xv_stars = "★★★★☆" if tc_match_cnt >= tc_total * 0.7 else "★★★☆☆"
    p(f"  → 综合数据可靠性: {xv_stars}")

    p()
    p("=" * 60)
    p("报告结束 | 2026-07-30 盘后 | Gate0=FAIL(≤20%仓位)")
    p("=" * 60)

    # ═══════════════════════════════════════════
    # S6: 30日主线全景分析 (NEW)
    # ═══════════════════════════════════════════
    p()
    p("=" * 60)
    p("S6: 30日板块主线全景分析 — 三阶段分解")
    p("=" * 60)

    # 防御/科技/周期分类
    DEFENSE = {"食品饮料","银行","非银金融","煤炭","石油石化","农林牧渔","交通运输","公用事业","钢铁","商贸零售","美容护理"}
    TECH = {"电子","通信","计算机","国防军工","电力设备","机械设备","传媒","汽车"}

    # 持续性分类
    persist=[]; rot_out=[]; rot_in=[]; decline=[]
    for n,d in sector_data.items():
        s1=d['seg1']; s2=d['seg2']; s3=d['seg3']
        if s1>0 and s2>0 and s3>0: persist.append((n,d))
        elif s1>0 and s3<0: rot_out.append((n,d))
        elif s1<=0 and s3>0: rot_in.append((n,d))
        elif s1<0 and s2<0 and s3<0: decline.append((n,d))

    p()
    p("  ◆ 持续主线 (P1+ P2+ P3+, 三阶段全程向上):")
    if persist:
        persist.sort(key=lambda x:x[1]['chg_30d'],reverse=True)
        for n,d in persist:
            t='防御' if n in DEFENSE else ('科技' if n in TECH else '周期')
            p(f"    {n}[{t}]: P1{d['seg1']:+.1f}% -> P2{d['seg2']:+.1f}% -> P3{d['seg3']:+.1f}% | 30日{d['chg_30d']:+.1f}%")
    else:p("    (无)")

    p()
    p("  ◆ 衰退主线 (P1+ 但 P3-, 前期领涨>后退潮):")
    rot_out.sort(key=lambda x:x[1]['seg3'])
    for n,d in rot_out:
        t='防御' if n in DEFENSE else ('科技' if n in TECH else '周期')
        p(f"    {n}[{t}]: P1{d['seg1']:+.1f}% -> P2{d['seg2']:+.1f}% -> P3{d['seg3']:+.1f}% | 30日{d['chg_30d']:+.1f}%")

    p()
    p("  ◆ 新兴主线 (P1<=0 但 P3+, 后来居上):")
    rot_in.sort(key=lambda x:x[1]['seg3'],reverse=True)
    for n,d in rot_in:
        t='防御' if n in DEFENSE else ('科技' if n in TECH else '周期')
        p(f"    {n}[{t}]: P1{d['seg1']:+.1f}% -> P2{d['seg2']:+.1f}% -> P3{d['seg3']:+.1f}% | 30日{d['chg_30d']:+.1f}%")

    p()
    p("  ◆ 全线下跌 (P1- P2- P3-, 全程下跌):")
    decline.sort(key=lambda x:x[1]['chg_30d'])
    for n,d in decline[:8]:
        t='防御' if n in DEFENSE else ('科技' if n in TECH else '周期')
        p(f"    {n}[{t}]: P1{d['seg1']:+.1f}% -> P2{d['seg2']:+.1f}% -> P3{d['seg3']:+.1f}% | 30日{d['chg_30d']:+.1f}%")

    # 风格三阶段汇总
    p()
    p("  → 风格三阶段均值:")
    for st,names in [("防御",DEFENSE),("科技",TECH)]:
        items=[(n,d) for n,d in sector_data.items() if n in names]
        if not items:continue
        ap1=sum(d['seg1'] for _,d in items)/len(items)
        ap2=sum(d['seg2'] for _,d in items)/len(items)
        ap3=sum(d['seg3'] for _,d in items)/len(items)
        a30=sum(d['chg_30d'] for _,d in items)/len(items)
        av=sum(d['daily_vol'] for _,d in items)/len(items)
        p(f"    {st}({len(items)}个): P1{ap1:+.1f}% -> P2{ap2:+.1f}% -> P3{ap3:+.1f}% | 30日{a30:+.1f}% | 波{av:.2f}%")

    # 结论
    p()
    p("  ◆ 主线判断:")
    p(f"    持续: {[n for n,_ in persist]} (防御消费)")
    p(f"    回避: {[n for n,_ in decline]} (科技)")
    if rot_in:p(f"    新兴: {[n for n,_ in rot_in]}")
    if rot_out:p(f"    衰退: {[n for n,_ in rot_out]}")

    # ── 保存报告 ──
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines))
    print(f"\n报告已保存至: {REPORT_FILE}")
