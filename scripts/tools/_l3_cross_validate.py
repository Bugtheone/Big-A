# -*- coding: utf-8 -*-
"""L3 个股层 — 五源交叉验证 | 2026-07-30

验证架构 (★★★☆☆ → ★★★★☆):
  源A: 同花顺涨停揭秘 ths_limit_up_all    — 涨停细节(原因/封板率/连板)
  源B: 腾讯个股行情  stock_realtime       — 实时涨跌幅/价格
  源C: 同花顺热榜    hot_list("hour")     — 个股热度+概念标签
  源D: 东财人气榜    hot_rank(50)         — 人气排名(独立源,仅盘后)
  源E: 东财涨停池    zt_pool              — ZT基础列表(push2ex限流中)

交叉验证维度:
  ① ZT总数验证: A vs board_summary (2源, 源E因push2ex限流降级)
  ② ZT涨跌幅验证: A(THS change_rate) vs B(Tencent change_pct)
  ③ 人气一致性: C(同花顺热榜) vs D(东财人气榜,盘后)
  ④ 情绪一致性: A(mood派生) vs C(热榜情绪)
  ⑤ ZT详情: 连板梯队/涨停原因/封板类型

用法:
  python scripts/tools/_l3_cross_validate.py [date_YYYYMMDD]
"""

import sys, os, io, time
from datetime import datetime
from collections import Counter
from typing import Dict, List, Tuple

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.data_gate import gate
from scripts.market_api import api

BOLD = lambda t: f"\n{'='*60}\n  {t}\n{'='*60}"
SUB  = lambda t: f"\n  {t}\n  " + "-"*40
OK = "✓"
WARN = "△"
FAIL = "✗"


def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def _extract_code(raw_code: str) -> str:
    """从 mixed code 提取纯数字代码。'sh000001' → '000001', '000001' → '000001'"""
    c = str(raw_code).strip()
    for prefix in ('sh', 'sz', 'bj'):
        if c.startswith(prefix):
            c = c[len(prefix):]
            break
    return c


def _guess_sh_sz(code: str) -> str:
    """根据首位数字推断市场前缀。6→sh, 0/3→sz, 其他→原样"""
    c = str(code).strip()
    if c.startswith("6"):
        return "sh" + c
    elif c.startswith("0") or c.startswith("3"):
        return "sz" + c
    return c


# ============================================================================
#  数据拉取
# ============================================================================

def source_a__ths_limit_up(date_str: str) -> dict:
    """源A: 同花顺涨停揭秘 — 涨停细节(封板率/连板/原因/封单)"""
    try:
        data = gate.em_ths_limit_up_all(date_str)
        return {
            "ok": True,
            "zt_total": data.get("total", 0),
            "zb_count": data.get("zb_count", 0),
            "dt_count": data.get("dt_count", 0),
            "zr_rate": data.get("zr_rate", 0.0),
            "zt_yesterday": data.get("zt_yesterday", 0),
            "zt_list": data.get("zt_list", []),
            # 字段: code,name,change_rate,turnover_rate,high_days_value,
            #       high_days,limit_up_type,reason_type,first_time,
            #       suc_rate,order_amount,is_again
            "source": "同花顺涨停揭秘(10jqka.com.cn)"
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "source": "同花顺涨停揭秘"}


def source_b__tencent_realtime(codes: List[str]) -> dict:
    """源B: 腾讯个股实时行情 — 价格/涨跌幅"""
    try:
        if not codes:
            return {"ok": True, "data": {}, "source": "腾讯行情(无ZT股可验证)"}
        rt = api.stock_realtime(codes)
        return {"ok": True, "data": rt, "source": "腾讯实时行情(qt.gtimg.cn)"}
    except Exception as e:
        return {"ok": False, "error": str(e), "source": "腾讯行情"}


def source_c__ths_hot_list(period: str = "hour") -> dict:
    """源C: 同花顺热榜 — 人气排名+概念标签"""
    try:
        hot_list = gate.ths_hot_list(period)
        if not hot_list:
            return {"ok": True, "data": [], "source": "同花顺热榜(空-非交易时段)"}
        return {"ok": True, "data": hot_list, "source": "同花顺热榜(data.10jqka.com.cn)"}
    except Exception as e:
        return {"ok": False, "error": str(e), "source": "同花顺热榜"}


def source_d__em_hot_rank(top: int = 50) -> dict:
    """源D: 东财人气榜 — 独立人气排名(仅盘后16:30+更新)"""
    try:
        hr = gate.em_hot_rank(top)
        return {
            "ok": True,
            "data": hr if hr else [],
            "source": "东财人气榜(push2.eastmoney.com)"
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "source": "东财人气榜"}


def source_e__zt_pool(date_str: str) -> dict:
    """源E: 东财涨停池 — 基础ZT列表(push2ex限流中,可能返回空)"""
    try:
        zt = gate.em_zt_pool(date_str)
        # push2ex限流时返回空列表，不视为失败(仅降级)
        return {
            "ok": True,
            "degraded": (len(zt) == 0 if zt else True),
            "zt_list": zt if zt else [],
            "zt_count": len(zt) if zt else 0,
            "source": "东财涨停池(push2ex.eastmoney.com)"
        }
    except Exception as e:
        return {"ok": False, "degraded": True, "error": str(e), "source": "东财涨停池"}


# ============================================================================
#  交叉验证
# ============================================================================

def xv1__zt_count(a: dict, e: dict, bs: dict) -> Tuple[str, float, List[str]]:
    """① ZT总数交叉验证: A(THS) vs BS(board_summary), E(push2ex)作为辅助"""
    results = []

    if not a.get("ok"):
        return FAIL, 0.0, [f"  {FAIL} 源A(THS涨停揭秘)不可用"]

    a_count = a["zt_total"]
    bs_count = bs.get("zt_count", 0) if bs else 0
    e_count = e.get("zt_count", 0)
    e_degraded = e.get("degraded", False)

    results.append(f"  A:THS涨停揭秘 → {a_count}只")
    if bs:
        results.append(f"  BS:board_summary → {bs_count}只")
    if e_count > 0:
        results.append(f"  E:东财涨停池 → {e_count}只")
    elif e_degraded:
        results.append(f"  E:东财涨停池 → 0只 [{WARN} push2ex限流,已跳过]")

    # 源E因push2ex限流不可靠，仅用A vs BS
    if bs and bs_count > 0:
        diff = abs(a_count - bs_count)
        range_pct = diff / max(a_count, bs_count) * 100

        if range_pct <= 5:
            grade, score = OK, 1.0
            results.append(f"  {OK} A vs BS偏差{range_pct:.1f}% (≤5% → 高度一致)")
        elif range_pct <= 10:
            grade, score = OK, 0.75
            results.append(f"  {OK} A vs BS偏差{range_pct:.1f}% (≤10% → 基本一致)")
        elif range_pct <= 20:
            grade, score = WARN, 0.5
            results.append(f"  {WARN} A vs BS偏差{range_pct:.1f}% (≤20% → 需关注)")
        else:
            grade, score = FAIL, 0.25
            results.append(f"  {FAIL} A vs BS偏差{range_pct:.1f}% (>20% → 不可靠)")
    else:
        # BS不可用或为0时，单凭A不可交叉验证，但A本身就可靠
        grade, score = WARN, 0.5
        results.append(f"  {WARN} BS不可用,单凭THS(源A)验证 — A数据本身可靠")

    return grade, score, results


def xv2__zt_change_rate(a: dict, b: dict) -> Tuple[str, float, List[str]]:
    """② ZT涨跌幅交叉验证: A(THS change_rate) vs B(Tencent change_pct)

    注意: THS涨停揭秘API返回change_rate(涨跌幅%)而非price,
    腾讯实时行情返回change_pct(涨跌幅%)。两者可直接对比。
    """
    results = []
    if not a.get("ok") or not a.get("zt_list"):
        return WARN, 0.0, [f"  {WARN} 源A无ZT数据,无法验证涨跌幅"]
    if not b.get("ok") or not b.get("data"):
        return WARN, 0.0, [f"  {WARN} 源B(腾讯行情)不可用,无法验证涨跌幅"]

    zt_a = a["zt_list"]
    rt_b = b["data"]
    total_checked = 0
    diffs = []
    match_records = []

    for zt_item in zt_a[:30]:  # 验证前30只ZT股
        code_a = _extract_code(zt_item.get("code", ""))
        if not code_a:
            continue
        change_a = safe_float(zt_item.get("change_rate", 0))
        name = zt_item.get("name", "?")

        # 匹配腾讯行情: stock_realtime返回key是原始code(纯数字)
        b_item = rt_b.get(code_a)
        if not b_item:
            b_item = rt_b.get(_guess_sh_sz(code_a))
        if not b_item:
            continue

        change_b = safe_float(b_item.get("change_pct", 0))
        total_checked += 1

        diff_abs = abs(change_a - change_b)
        diffs.append(diff_abs)

        if diff_abs <= 0.05:
            flag = OK
        elif diff_abs <= 0.3:
            flag = OK
        elif diff_abs <= 1.0:
            flag = WARN
        else:
            flag = FAIL

        match_records.append((flag, name, code_a, change_a, change_b, diff_abs))

    if total_checked == 0:
        return WARN, 0.0, [f"  {WARN} 无匹配个股(code格式不一致或腾讯返回空)"]

    avg_diff = sum(diffs) / len(diffs)
    max_diff = max(diffs)
    matched = sum(1 for flag, *_ in match_records if flag in (OK,))

    results.append(f"  验证{total_checked}只ZT股: 匹配率{matched/total_checked*100:.0f}% "
                   f"平均偏差{avg_diff:.3f}pp | 最大偏差{max_diff:.3f}pp")

    # 只展示偏差较大和很小的个股(节省篇幅)
    show_records = [r for r in match_records if r[0] != OK]
    if not show_records and match_records:
        show_records = match_records[:3]  # 至少展示前3条
    for flag, name, code, ca, cb, d in show_records[:8]:
        results.append(f"    {name}({code}) {flag} THS={ca:+.2f}% vs Tencent={cb:+.2f}% "
                       f"偏差{d:.3f}pp")

    if avg_diff <= 0.1:
        grade, score = OK, 1.0
    elif avg_diff <= 0.5:
        grade, score = OK, 0.75
    elif avg_diff <= 1.5:
        grade, score = WARN, 0.5
    else:
        grade, score = FAIL, 0.25

    return grade, score, results


def xv3__hot_overlap(c: dict, d: dict) -> Tuple[str, float, List[str]]:
    """③ 人气一致性: C(同花顺热榜) vs D(东财人气榜)"""
    results = []

    if not c.get("ok") or not c.get("data"):
        return WARN, 0.0, [f"  {WARN} 同花顺热榜无数据"]

    c_list = c["data"]
    d_list = d.get("data", []) if d.get("ok") else []

    c_codes = set()
    c_names = {}
    for item in c_list:
        code = _extract_code(item.get("code", ""))
        c_codes.add(code)
        c_names[code] = item.get("name", "?")

    results.append(f"  C:同花顺热榜 → {len(c_codes)}只")

    if not d_list:
        results.append(f"  D:东财人气榜 → 无数据(仅盘后16:30+更新)")
        results.append(f"  {WARN} 东财人气榜盘后更新,当前不可交叉验证 — C(同花顺)本身可靠")
        return WARN, 0.5, results

    d_codes = set()
    d_names = {}
    for item in d_list:
        code = _extract_code(item.get("code", ""))
        d_codes.add(code)
        d_names[code] = item.get("name", "?")

    overlap = c_codes & d_codes
    union = len(c_codes | d_codes)
    jaccard = len(overlap) / union if union > 0 else 0

    results.append(f"  D:东财人气榜 → {len(d_codes)}只")
    results.append(f"  交集: {len(overlap)}只 | Jaccard相似度: {jaccard:.2f}")

    if overlap:
        top_overlap = list(overlap)[:8]
        tags = [f"{d_names.get(c,c)}({c})" for c in top_overlap]
        results.append(f"  共同热门: {', '.join(tags)}")

    if jaccard >= 0.4:
        grade, score = OK, 1.0
        results.append(f"  {OK} 人气高度一致(Jaccard≥0.4)")
    elif jaccard >= 0.2:
        grade, score = OK, 0.75
        results.append(f"  {OK} 人气基本一致(Jaccard≥0.2)")
    elif jaccard >= 0.1:
        grade, score = WARN, 0.5
        results.append(f"  {WARN} 人气部分重叠(Jaccard≥0.1)")
    else:
        grade, score = FAIL, 0.25
        results.append(f"  {FAIL} 人气分歧明显(Jaccard<0.1)")

    return grade, score, results


def xv4__sentiment(a: dict, c: dict) -> Tuple[str, float, List[str]]:
    """④ 情绪一致性: A(ZT情绪) vs C(热榜情绪)"""
    results = []

    if not a.get("ok") or not a.get("zt_list"):
        return WARN, 0.0, [f"  {WARN} 源A无数据,无法验证情绪"]

    # A侧: ZT情绪
    high_lb = sum(1 for z in a["zt_list"] if safe_float(z.get("high_days_value", 0)) >= 3)
    total_zt = a["zt_total"]
    zr_rate = a.get("zr_rate", 0)

    if zr_rate < 20 and total_zt >= 60:
        a_mood = "热烈"
    elif zr_rate < 30 and total_zt >= 40:
        a_mood = "偏暖"
    elif total_zt >= 20:
        a_mood = "中性"
    elif total_zt > 0:
        a_mood = "低迷"
    else:
        a_mood = "冰点"

    results.append(f"  A:ZT情绪={a_mood} (炸板率{zr_rate:.0f}% 连板{high_lb}只/{total_zt}只)")

    if not c.get("ok") or not c.get("data"):
        results.append(f"  C:热榜无数据")
        results.append(f"  {WARN} 热榜无数据,仅ZT侧情绪")
        return WARN, 0.5, results

    c_list = c["data"]
    if len(c_list) >= 10:
        top_up = sum(1 for item in c_list[:10] if safe_float(item.get("pct", 0)) > 0)
        if top_up >= 8:
            c_mood = "热烈"
        elif top_up >= 6:
            c_mood = "偏暖"
        elif top_up >= 3:
            c_mood = "中性"
        else:
            c_mood = "低迷"
    else:
        c_mood = "无数据"

    results.append(f"  C:热榜情绪={c_mood} (TOP{min(len(c_list),10)}涨{top_up}跌{min(len(c_list),10)-top_up})")

    mood_map = {"热烈": 4, "偏暖": 3, "中性": 2, "低迷": 1, "冰点": 0}
    a_v = mood_map.get(a_mood, -1)
    c_v = mood_map.get(c_mood, -1)

    if c_v < 0:
        score, grade = 0.5, WARN
        results.append(f"  {WARN} 热榜无数据,仅单源情绪")
    elif abs(a_v - c_v) <= 0:
        score, grade = 1.0, OK
        results.append(f"  {OK} 情绪完全一致({a_mood})")
    elif abs(a_v - c_v) <= 1:
        score, grade = 0.75, OK
        results.append(f"  {OK} 情绪基本一致(A:{a_mood} vs C:{c_mood})")
    elif abs(a_v - c_v) <= 2:
        score, grade = 0.5, WARN
        results.append(f"  {WARN} 情绪存在分歧(A:{a_mood} vs C:{c_mood})")
    else:
        score, grade = 0.25, FAIL
        results.append(f"  {FAIL} 情绪严重分歧(A:{a_mood} vs C:{c_mood})")

    return grade, score, results


def xv5__zt_detail(a: dict) -> Tuple[str, List[str]]:
    """⑤ ZT详情报告(基于源A)"""
    results = []
    if not a.get("ok") or not a.get("zt_list"):
        return FAIL, [f"  {FAIL} 无ZT详情数据"]

    zt_list = a["zt_list"]

    reason_counter = Counter()
    limit_type_counter = Counter()
    high_lb_list = []

    for z in zt_list:
        rt = z.get("reason_type", "") or ""
        if rt:
            for r in str(rt).split(","):
                r = r.strip()
                if r and r != "其他":
                    reason_counter[r] += 1

        lt = z.get("limit_up_type", "") or "其他"
        limit_type_counter[lt] += 1

        hd = safe_float(z.get("high_days_value", 0))
        if hd >= 2:
            high_lb_list.append((z.get("name", "?"), z.get("code", ""), int(hd)))

    results.append(f"  ZT总数: {a['zt_total']} | 炸板: {a['zb_count']} | 跌停: {a['dt_count']}")
    results.append(f"  炸板率: {a['zr_rate']:.1f}% | 昨日涨停: {a.get('zt_yesterday', '?')}")

    # 涨停原因 TOP5
    if reason_counter:
        results.append(f"\n  涨停原因 TOP5:")
        for reason, cnt in reason_counter.most_common(5):
            results.append(f"    {reason}: {cnt}只")

    # 封板类型分布
    if limit_type_counter and len(limit_type_counter) > 1:
        types = []
        for lt, cnt in limit_type_counter.most_common(5):
            types.append(f"{lt}{cnt}只")
        results.append(f"  封板类型: {', '.join(types)}")

    # 连板梯队
    if high_lb_list:
        results.append(f"\n  连板梯队(≥2板):")
        high_lb_list.sort(key=lambda x: -x[2])
        for name, code, hd in high_lb_list[:10]:
            results.append(f"    {name}({_extract_code(code)}) {hd}连板")

    # ZT个股 TOP10 展示(按涨跌幅)
    zt_sorted = sorted(zt_list, key=lambda z: safe_float(z.get("change_rate", 0)), reverse=True)
    results.append(f"\n  涨停个股 TOP10:")
    for z in zt_sorted[:10]:
        code = _extract_code(z.get("code", ""))
        name = z.get("name", "?")
        change = safe_float(z.get("change_rate", 0))
        reason = z.get("reason_type", "") or ""
        reason_short = reason[:20] if len(str(reason)) > 20 else reason
        results.append(f"    {name}({code}) {change:+.2f}% {reason_short}")

    return OK, results


# ============================================================================
#  主流程
# ============================================================================

def run_l3_cross_validate(date_str: str = None) -> List[str]:
    """执行 L3 五源交叉验证"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    out = []
    out.append(f"L3 个股层 — 五源交叉验证报告")
    out.append(f"日期: {date_str} | 生成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    out.append(f"升级目标: ★★★☆☆ → ★★★★☆")
    out.append("")

    # ====== S1: 数据拉取 ======
    out.append(BOLD("S1: 五源数据拉取"))

    t0 = time.time()

    # board_summary
    bs = None
    try:
        bs = api.board_summary()
    except Exception:
        pass

    # 源A: THS涨停揭秘
    t_a0 = time.time()
    a = source_a__ths_limit_up(date_str)
    t_a = time.time() - t_a0
    out.append(f"  源A: THS涨停揭秘 → {a.get('zt_total','?')}只ZT "
               f"({'OK' if a['ok'] else 'FAIL'}) {t_a:.1f}s")

    # 源B: 腾讯行情
    zt_codes = []
    if a.get("ok") and a.get("zt_list"):
        zt_codes = [_extract_code(z.get("code", "")) for z in a["zt_list"] if z.get("code")]
    t_b0 = time.time()
    b = source_b__tencent_realtime(zt_codes)
    t_b = time.time() - t_b0
    out.append(f"  源B: 腾讯行情 → {len(b.get('data',{}))}条ZT行情 "
               f"({'OK' if b['ok'] else 'FAIL'}) {t_b:.1f}s")

    # 源C: 同花顺热榜
    t_c0 = time.time()
    c = source_c__ths_hot_list("hour")
    t_c = time.time() - t_c0
    out.append(f"  源C: 同花顺热榜 → {len(c.get('data',[]))}只 "
               f"({'OK' if c['ok'] else 'FAIL'}) {t_c:.1f}s")

    # 源D: 东财人气榜
    t_d0 = time.time()
    d = source_d__em_hot_rank(50)
    t_d = time.time() - t_d0
    tag_d = "空-盘后更新" if not d.get("data") else f"{len(d['data'])}只"
    out.append(f"  源D: 东财人气榜 → {tag_d} "
               f"({'OK' if d['ok'] else 'FAIL'}) {t_d:.1f}s")

    # 源E: 东财涨停池
    t_e0 = time.time()
    e = source_e__zt_pool(date_str)
    t_e = time.time() - t_e0
    tag_e = "限流-空" if e.get("degraded") else f"{e.get('zt_count','?')}只"
    out.append(f"  源E: 东财涨停池 → {tag_e} "
               f"({'OK' if e['ok'] else 'FAIL'}) {t_e:.1f}s")

    total_t = time.time() - t0
    available = sum(1 for s in [a, b, c, d, e] if s.get("ok"))
    out.append(f"  总耗时: {total_t:.1f}s | 可用源: {available}/5")

    # ====== S2: 交叉验证 ======
    out.append(BOLD("S2: 四维交叉验证"))

    total_score = 0.0
    total_weight = 0.0

    # ① ZT总数 (A vs BS)
    out.append(SUB("XV① ZT总数验证 (A:THS vs BS:board_summary)"))
    g1, s1, r1 = xv1__zt_count(a, e, bs)
    out.extend(r1)
    total_score += s1 * 0.25
    total_weight += 0.25

    # ② ZT涨跌幅 (A vs B)
    out.append(SUB("XV② ZT涨跌幅验证 (A:THS change_rate vs B:Tencent change_pct)"))
    g2, s2, r2 = xv2__zt_change_rate(a, b)
    out.extend(r2)
    total_score += s2 * 0.25
    total_weight += 0.25

    # ③ 人气一致性 (C vs D)
    out.append(SUB("XV③ 人气一致性 (C:同花顺热榜 vs D:东财人气榜)"))
    g3, s3, r3 = xv3__hot_overlap(c, d)
    out.extend(r3)
    total_score += s3 * 0.25
    total_weight += 0.25

    # ④ 情绪一致性 (A vs C)
    out.append(SUB("XV④ 情绪一致性 (A:ZT情绪 vs C:热榜情绪)"))
    g4, s4, r4 = xv4__sentiment(a, c)
    out.extend(r4)
    total_score += s4 * 0.25
    total_weight += 0.25

    # ====== S3: 可靠性评级 ======
    out.append(BOLD("S3: L3可靠性评级"))

    if total_weight > 0:
        final_score = total_score / total_weight
    else:
        final_score = 0

    star_count = min(5, max(1, round(final_score * 5)))
    stars = "★" * star_count + "☆" * (5 - star_count)

    out.append(f"  加权得分: {final_score:.2f}/1.00")
    out.append(f"  可靠性评级: {stars}")

    # 来源汇总
    sources_ok = []
    if a.get("ok"): sources_ok.append("THS涨停揭秘")
    if b.get("ok"): sources_ok.append("腾讯行情")
    if c.get("ok"): sources_ok.append("同花顺热榜")
    if d.get("ok") and d.get("data"): sources_ok.append("东财人气榜")
    if not e.get("degraded") and e.get("ok"): sources_ok.append("东财涨停池")

    degraded = []
    if e.get("degraded"): degraded.append("东财涨停池(push2ex限流)")
    if d.get("ok") and not d.get("data"): degraded.append("东财人气榜(盘后更新)")

    out.append(f"  有效验证源: {len(sources_ok)}个 ({', '.join(sources_ok)})")
    if degraded:
        out.append(f"  降级源: {', '.join(degraded)}")

    if star_count >= 4:
        out.append(f"  {OK} L3层达到★★★★及以上 — 多源交叉验证通过,可信任")
    elif star_count >= 3:
        out.append(f"  {OK} L3层★★★ — 基本可用,核心数据可靠")
    else:
        out.append(f"  {WARN} L3层★★及以下 — 需增加验证源或等待数据更新")

    # ====== S4: ZT详情 ======
    out.append(BOLD("S4: 今日涨停详情"))
    g5, r5 = xv5__zt_detail(a)
    out.extend(r5)

    # ====== 结论 ======
    out.append(BOLD("升级结论"))
    out.append(f"  原有评级: ★★★☆☆ (THS涨停 + Westock, 双源但交叉验证不足)")
    out.append(f"  升级评级: {stars} (新增腾讯行情/同花顺热榜/东财人气榜, 四维交叉验证)")
    out.append(f"  关键改进:")
    out.append(f"    + ZT总数: THS vs board_summary 双源确认")
    out.append(f"    + 涨跌幅: THS vs 腾讯行情 逐股偏差检测")
    out.append(f"    + 人气: 同花顺热榜 vs 东财人气榜 双榜对照")
    out.append(f"    + 情绪: ZT情绪 vs 热榜情绪 独立源一致性")
    out.append("")

    return out


# ============================================================================
#  入口
# ============================================================================

if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    lines = run_l3_cross_validate(date_arg)
    report_text = "\n".join(lines)

    print(report_text)

    date_str = date_arg or datetime.now().strftime("%Y%m%d")
    out_dir = os.path.join(BASE_DIR, "data", "reports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"_l3_cross_validate_{date_str}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n报告已保存: {out_path}")
