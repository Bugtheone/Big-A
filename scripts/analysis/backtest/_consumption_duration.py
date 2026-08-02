#!/usr/bin/env python3
"""消费方向持续多久？—— 90交易日资金流回测 找到趋势起点"""
import subprocess, json, time, sys
from datetime import datetime

# ============================================================
# 核心消费板块 vs 科技板块 — 名称列表(代码自动搜索)
# ============================================================
CONSUMER_NAMES = [
    "白酒Ⅱ", "股份制银行Ⅱ", "国有大型银行Ⅱ", "乘用车",
    "食品加工", "饮料乳品", "商用车", "厨卫电器",
    "城商行Ⅱ", "农商行Ⅱ", "化学制药", "证券Ⅱ", "保险Ⅱ",
]

TECH_NAMES = [
    "半导体", "通信设备", "元件", "IT服务Ⅱ", "软件开发",
    "自动化设备", "军工电子Ⅱ", "光伏设备",
]

# 修复2026-07-31: --raw 不再支持, 委托给 _westock_helper Markdown表格解析
# ============================================================
def run_westock(cmd: str) -> dict:
    from scripts.utils._westock_helper import _run_westock_table
    clean_cmd = cmd.replace(" --raw", "").replace("--raw ", "")
    result = _run_westock_table(clean_cmd)
    if result:
        return result  # list[dict]
    return {}

def discover_codes(names):
    print(f"[发现代码] 搜索 {len(names)} 个板块...")
    code_map = {}
    for i, name in enumerate(names):
        print(f"  [{i+1}/{len(names)}] {name}...", end=" ", flush=True)
        result = run_westock(f'search {name} --type sector')
        if isinstance(result, list) and result:
            for item in result:
                if item.get("name") == name:
                    code_map[name] = item["code"]
                    print(f"-> {item['code']}")
                    break
            else:
                code_map[name] = result[0]["code"]
                print(f"-> {result[0]['code']} (模糊)")
        else:
            print("未找到")
        time.sleep(0.15)
    return code_map

def safe_float(v, default=0.0):
    try: return float(v) if v else default
    except Exception: return default

def get_fund_flow(code, start, end):
    result = run_westock(
        f'fund flow {code} --start {start} --end {end}')
    if isinstance(result, list):
        return result
    return []

def cumsum_analysis(daily_data, name, label):
    """分析累计资金流走向，检测趋势起点"""
    if not daily_data or len(daily_data) < 10:
        return None
    
    # 按日期排序
    dates = []
    flows = []
    for d in daily_data:
        try:
            date = str(d.get("date", d.get("EndDate", "")))
            mf = safe_float(d.get("MainNetFlow"))
            if date:
                dates.append(date)
                flows.append(mf)
        except Exception: continue
    
    if not dates or len(dates) < 10:
        return None
    
    # 计算累计
    cum = []
    total = 0
    for f in flows:
        total += f
        cum.append(total)
    
    # 找趋势起点：累计和从负转正，或累计连续N天为正
    pos_streak = 0
    best_streak_start = None
    best_streak_len = 0
    current_start = None
    current_len = 0
    
    for i, c in enumerate(cum):
        if c > 0:
            if current_start is None:
                current_start = dates[i]
            current_len += 1
        else:
            if current_len > best_streak_len:
                best_streak_len = current_len
                best_streak_start = current_start
            current_start = None
            current_len = 0
    
    if current_len > best_streak_len:
        best_streak_len = current_len
        best_streak_start = current_start
    
    # 反向扫描：从末尾往前找持续长度
    reverse_streak = 0
    start_idx = None
    for i in range(len(cum) - 1, -1, -1):
        # 检查是否在连续净流入区间(用3日窗口)
        window_flows = flows[max(0, i-2):i+1]
        window_cum = cum[max(0, i-2):i+1]
        
        # 宽松定义：近N日中有占优趋势
        if sum(1 for f in window_flows if f > 0) >= 2 and cum[i] > 0:
            reverse_streak += 1
            start_idx = i
        else:
            if reverse_streak > 0 and all(f < 0 for f in flows[i-2:i+1] if f <= 0):
                break
    
    # 找最近一个明确的谷底(拐点)
    valley_idx = None
    for i in range(len(cum) - 2, 1, -1):
        if cum[i] < cum[i-1] and cum[i] < cum[i+1]:
            # 局部最低点
            valley_idx = i
            break
    
    # 找转折点：累计和首次高于最近谷底的120%
    turning_idx = None
    recent_window = 15  # 近15天
    window_start = max(0, len(cum) - recent_window)
    
    # 在近recent_window天中找到最低点
    min_in_window = min(cum[window_start:])
    min_idx = cum[window_start:].index(min_in_window) + window_start
    
    return {
        "name": name,
        "label": label,
        "total_days": len(dates),
        "today_flow_yi": flows[-1] / 1e8,
        "cum_total_yi": cum[-1] / 1e8,
        "valley_date": dates[min_idx] if min_idx < len(dates) else "?",
        "valley_cum_yi": cum[min_idx] / 1e8,
        "since_valley_days": len(dates) - min_idx,
        "since_valley_cum_yi": (cum[-1] - cum[min_idx]) / 1e8,
        "dates": dates[-30:],
        "flows": flows[-30:],
        "cum": [c/1e8 for c in cum[-30:]],
    }

# ============================================================
# 主流程
# ============================================================
end_date = "2026-07-30"
start_date = "2026-03-15"  # ~90交易日
if __name__ == "__main__":
    print(f"消费持续时间分析: {start_date} → {end_date}")
    print("=" * 80)
    
    # 发现代码
    print("\n[Step 1] 发现消费板块代码...")
    consumer_codes = discover_codes(CONSUMER_NAMES)
    print(f"\n[Step 2] 发现科技板块代码...")
    tech_codes = discover_codes(TECH_NAMES)
    
    all_codes = {**consumer_codes, **tech_codes}
    print(f"\n共 {len(all_codes)} 个板块")
    
    # 批量获取
    print(f"\n[Step 3] 批量获取 90交易日 资金流数据...")
    results = {}
    total = len(all_codes)
    for i, (name, code) in enumerate(all_codes.items()):
        print(f"  [{i+1}/{total}] {name} ({code})...", end=" ", flush=True)
        daily = get_fund_flow(code, start_date, end_date)
        if daily and isinstance(daily, list) and len(daily) > 0:
            print(f"OK ({len(daily)}天)")
            analysis = cumsum_analysis(daily, name, "消费" if name in consumer_codes else "科技")
            if analysis:
                results[name] = {**analysis, "raw_days": len(daily)}
            else:
                results[name] = {"name": name, "error": "analysis failed", "raw_days": len(daily)}
        else:
            print("FAIL")
            results[name] = {"name": name, "error": "no data"}
        time.sleep(0.1)
    
    # ============================================================
    # 生成报告
    # ============================================================
    lines = []
    lines.append("=" * 90)
    lines.append(f"消费方向持续时间分析 — 90交易日资金流回测 ({start_date}~{end_date})")
    lines.append(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据源: Westock fund flow")
    lines.append("=" * 90)
    
    # --- 消费板块 ---
    lines.append("\n## 一、消费板块 资金流趋势分析\n")
    lines.append(f"{'板块':<14s} {'累计(亿)':>12s} {'今日(亿)':>10s} {'谷底日期':>12s} {'谷底至今(天)':>12s} {'谷底至今累计(亿)':>18s}")
    lines.append("-" * 90)
    consumer_ok = {k: v for k, v in results.items() if k in consumer_codes and "error" not in v}
    for name in CONSUMER_NAMES:
        if name in consumer_ok:
            d = consumer_ok[name]
            lines.append(f"{name:<14s} {d['cum_total_yi']:>+12.2f} {d['today_flow_yi']:>+10.2f} "
                         f"{d['valley_date']:>12s} {d['since_valley_days']:>12d} "
                         f"{d['since_valley_cum_yi']:>+18.2f}")
        elif name in results:
            lines.append(f"{name:<14s} {'N/A':>12s} {'N/A':>10s} {'N/A':>12s} {'N/A':>12s} {'N/A':>18s}")
    
    # --- 科技板块 ---
    lines.append("\n## 二、科技板块 资金流趋势分析 (对比)\n")
    lines.append(f"{'板块':<14s} {'累计(亿)':>12s} {'今日(亿)':>10s} {'谷底日期':>12s} {'谷底至今(天)':>12s} {'谷底至今累计(亿)':>18s}")
    lines.append("-" * 90)
    tech_ok = {k: v for k, v in results.items() if k in tech_codes and "error" not in v}
    for name in TECH_NAMES:
        if name in tech_ok:
            d = tech_ok[name]
            lines.append(f"{name:<14s} {d['cum_total_yi']:>+12.2f} {d['today_flow_yi']:>+10.2f} "
                         f"{d['valley_date']:>12s} {d['since_valley_days']:>12d} "
                         f"{d['since_valley_cum_yi']:>+18.2f}")
        elif name in results:
            lines.append(f"{name:<14s} {'N/A':>12s} {'N/A':>10s} {'N/A':>12s} {'N/A':>12s} {'N/A':>18s}")
    
    # --- 趋势总结 ---
    lines.append("\n## 三、趋势起点推断\n")
    lines.append("-" * 90)
    
    # 找消费板块的公共谷底区间
    consumer_valleys = []
    for name, d in consumer_ok.items():
        if d.get('valley_date') and d['valley_date'] != '?':
            consumer_valleys.append((name, d['valley_date'], d['since_valley_days'], d['since_valley_cum_yi']))
    
    if consumer_valleys:
        # 按谷底日期分组统计
        from collections import Counter
        valley_dates = [v[1] for v in consumer_valleys]
        valley_count = Counter(valley_dates)
        lines.append(f"\n### 消费板块谷底日期分布:")
        for date, cnt in valley_count.most_common():
            sectors = [v[0] for v in consumer_valleys if v[1] == date]
            lines.append(f"  {date}: {cnt}个板块 — {', '.join(sectors)}")
        
        # 整合判断
        earliest_valley = min(consumer_valleys, key=lambda x: x[1])
        latest_valley = max(consumer_valleys, key=lambda x: x[1])
        
        lines.append(f"\n### 关键时间节点:")
        lines.append(f"  最早谷底: {earliest_valley[0]} — {earliest_valley[1]}")
        lines.append(f"  最晚谷底: {latest_valley[0]} — {latest_valley[1]}")
        
        # 统计自谷底以来持续流入天数
        avg_days = sum(v[2] for v in consumer_valleys) / len(consumer_valleys)
        lines.append(f"  平均持续: {avg_days:.0f} 个交易日")
        
        # 根据数据判断持续周期
        # 如果有60天数据且谷底在中间，那么持续大约30-40天
        max_since = max(v[2] for v in consumer_valleys)
        lines.append(f"  最长持续: {max_since} 个交易日")
    
    # --- 消费vs科技分化 ---
    lines.append(f"\n### 消费vs科技 资金面分化程度\n")
    con_sum = sum(d['cum_total_yi'] for d in consumer_ok.values())
    tech_sum = sum(d['cum_total_yi'] for d in tech_ok.values())
    lines.append(f"  消费板块90日累计: {con_sum:+.2f}亿")
    lines.append(f"  科技板块90日累计: {tech_sum:+.2f}亿")
    lines.append(f"  分化差值: {con_sum - tech_sum:+.2f}亿")
    
    # --- 近30日逐日数据 ---
    lines.append(f"\n## 四、核心板块近30日逐日资金流\n")
    for name in ["白酒Ⅱ", "股份制银行Ⅱ", "乘用车", "国有大型银行Ⅱ", "半导体", "通信设备"]:
        if name in results and "dates" in results[name]:
            d = results[name]
            lines.append(f"\n### {name}")
            lines.append(f"{'日期':>12s}  {'日净流入(亿)':>14s}  {'累计(亿)':>12s}")
            lines.append("-" * 42)
            dates = d['dates']
            flows = d['flows']
            cum = d['cum']
            for i in range(len(dates)):
                lines.append(f"{dates[i]:>12s}  {flows[i]/1e8:>+14.2f}  {cum[i]:>+12.2f}")
    
    # 输出
    report_path = "_consumption_duration_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n#END\n")
    
    print(f"\n报告已保存: {report_path}")
    print(f"行数: {len(lines)}")
    
    # 摘要
    print("\n" + "=" * 80)
    print("快速摘要")
    print("=" * 80)
    if consumer_valleys:
        valley_dates_sorted = sorted(set(v[1] for v in consumer_valleys))
        print(f"消费板块谷底集中在: {', '.join(valley_dates_sorted[:3])}")
    if consumer_ok:
        con_days = max(v['since_valley_days'] for v in consumer_ok.values())
        con_cum = sum(v['since_valley_cum_yi'] for v in consumer_ok.values())
        print(f"消费自谷底以来最长持续: {con_days}交易日, 累计净流入: {con_cum:+.1f}亿")
    if tech_ok:
        tech_cum = sum(v['cum_total_yi'] for v in tech_ok.values())
        print(f"科技板块90日累计流出: {tech_cum:+.1f}亿")
    
    print(f"\n完整报告: {report_path}")
    sys.exit(0)
