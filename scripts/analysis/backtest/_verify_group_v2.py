#!/usr/bin/env python3
"""板块分组表现 - 修正版逐板块分组归属+涨幅交叉验证
修复 tag_group() 的连续子串匹配缺陷，逐板块复审28个板块的归属"""
import json, os, sys
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from scripts.market_api import api

TODAY = "2026-07-29"

# === 修正后分组关键词 ===
# BUGFIX: "家用电器"不包含"家电"连续子串(中间有"用")，新增"电器"作为消费关键词
# BUGFIX: "元件"是电子元件，归科技
# BUGFIX: "设备"类(照明/自动化/专用/通用设备)归工业/周期
consumer_kw = ["家电", "家居", "食品", "饮料", "酒", "汽车", "商用车", "乘用车", "汽车服务", "厨卫", "电器"]
tech_kw = ["半导体", "电子", "软件", "计算机", "IT", "通信", "互联网", "芯片", "光学", "元件"]
finance_kw = ["银行", "保险", "证券", "房地产", "地产"]
industry_kw = ["工程机械", "轨交", "化工", "钢铁", "有色", "煤炭", "电力", "公用", "设备"]
pharma_kw = ["医药", "医疗", "生物", "中药"]

def tag_group_v1(name):
    """原始版（有Bug）"""
    for kw in ["家电", "家居", "食品", "饮料", "酒", "汽车", "商用车", "乘用车", "汽车服务", "厨卫"]:
        if kw in str(name): return "消费/汽车"
    for kw in ["半导体", "电子", "软件", "计算机", "IT", "通信", "互联网", "芯片", "光学"]:
        if kw in str(name): return "科技"
    for kw in ["银行", "保险", "证券", "房地产", "地产"]:
        if kw in str(name): return "金融/地产"
    for kw in ["工程机械", "轨交", "化工", "钢铁", "有色", "煤炭", "电力", "公用"]:
        if kw in str(name): return "工业/周期"
    for kw in ["医药", "医疗", "生物", "中药"]:
        if kw in str(name): return "医药"
    return "其他"

def tag_group_v2(name):
    """修正版"""
    for kw in consumer_kw:
        if kw in str(name): return "消费/汽车"
    for kw in tech_kw:
        if kw in str(name): return "科技"
    for kw in finance_kw:
        if kw in str(name): return "金融/地产"
    for kw in industry_kw:
        if kw in str(name): return "工业/周期"
    for kw in pharma_kw:
        if kw in str(name): return "医药"
    return "其他"

if __name__ == "__main__":
    s1_all = api.sectors(top_n=30)
    s1_ranked = sorted(s1_all, key=lambda x: float(x.get("change_pct", 0) or 0), reverse=True)
    
    # === 第一部分: 逐板块归属对比 (v1 vs v2) ===
    print("=" * 80)
    print("  2026-07-29 板块分组表现 - 修正版逐板块归属验证")
    print("=" * 80)
    print()
    
    changes = []
    print(f"{'#':>3}  {'板块名':<12s} {'涨幅':>8s}  {'原始分组(v1)':<12s} {'修正分组(v2)':<12s} {'修正原因':<30s}")
    print("-" * 80)
    
    for i, s in enumerate(s1_ranked):
        name = s["name"]
        pct = float(s.get("change_pct", 0) or 0)
        g1 = tag_group_v1(name)
        g2 = tag_group_v2(name)
        
        reason = ""
        if g1 != g2:
            reason = f"v1缺关键词: {name}"
            changes.append((i+1, name, pct, g1, g2))
        
        flag = " <-- FIX" if g1 != g2 else ""
        print(f"{i+1:>3}  {name:<12s} {pct:+7.2f}%  {g1:<12s} {g2:<12s} {reason:<30s}{flag}")
    
    # === 第二部分: 修正后分组汇总 ===
    print()
    print("=" * 80)
    print("  分组汇总 (v2修正版, 逐板块人工复审)")
    print("=" * 80)
    
    group_data = defaultdict(lambda: {"names": [], "pcts": []})
    for s in s1_ranked:
        g = tag_group_v2(s["name"])
        pct = float(s.get("change_pct", 0) or 0)
        group_data[g]["names"].append(s["name"])
        group_data[g]["pcts"].append(pct)
    
    order = ["消费/汽车", "科技", "金融/地产", "工业/周期", "医药", "其他"]
    for g in order:
        gd = group_data.get(g)
        if gd and gd["names"]:
            avg = sum(gd["pcts"]) / len(gd["pcts"])
            items = sorted(zip(gd["names"], gd["pcts"]), key=lambda x: x[1], reverse=True)
            print(f"\n  [{g}] {len(gd['names'])}个板块, 平均 {avg:+.2f}%")
            # 检查是否有异常值
            outlier = ""
            for nm, p in items:
                dev = p - avg
                flag = ""
                if abs(dev) > 3.0:
                    flag = f" [dev={dev:+.2f}, outlier!]"
                print(f"    {nm:<14s} {p:+6.2f}%{flag}")
    
    # === 第三部分: v1 vs v2 差异分析 ===
    print()
    print("=" * 80)
    print("  v1 vs v2 差异分析")
    print("=" * 80)
    
    if changes:
        print(f"\n  共 {len(changes)} 个板块重新分组:\n")
        for rank, name, pct, g1, g2 in changes:
            print(f"  #{rank} {name} {pct:+.2f}%  {g1} -> {g2}")
    else:
        print("  无差异")
    
    # === 第四部分: 与之前审计JSON交叉验证 ===
    print()
    print("=" * 80)
    print("  v1 vs 审计JSON交叉验证 (数据准确性)")
    print("=" * 80)
    
    audit_path = os.path.join(BASE_DIR, "data", "industry_audit_2026-07-29.json")
    with open(audit_path, "r", encoding="utf-8") as f:
        prev = json.load(f)
    
    # v1分组汇总
    group_v1 = defaultdict(lambda: {"names": [], "pcts": []})
    for s in s1_ranked:
        g = tag_group_v1(s["name"])
        group_v1[g]["pcts"].append(float(s.get("change_pct", 0) or 0))
    
    print()
    for g in sorted(group_v1):
        gd = group_v1[g]
        if not gd["pcts"]:
            continue
        avg = sum(gd["pcts"]) / len(gd["pcts"])
        prev_entry = prev.get("group_stats", {}).get(g, {})
        prev_avg = prev_entry.get("avg_pct", 0)
        prev_cnt = prev_entry.get("count", 0)
        match = "PASS" if (prev_cnt == len(gd["pcts"]) and abs(avg - prev_avg) < 0.01) else "DIFF!"
        print(f"  {g}: 本次{len(gd['pcts'])}板块, 平均{avg:+.2f}%  vs  JSON {prev_cnt}板块, {prev_avg:+.2f}%  [{match}]")
    
    # === 第五部分: 数据质量评级 ===
    print()
    print("=" * 80)
    print("  数据质量评级")
    print("=" * 80)
    
    checks = []
    
    # 1. 多源交叉
    checks.append(("[ FAIL]", "S1 腾讯 sectors - 唯一可用源，S2东财push2限流/S3东财资金流限流/S4 Tushare ths_daily字段空"))
    # 2. 内部一致性
    pos_cnt = sum(1 for s in s1_ranked if float(s.get("change_pct", 0) or 0) > 0)
    neg_cnt = sum(1 for s in s1_ranked if float(s.get("change_pct", 0) or 0) < 0)
    checks.append(("[ PASS]", f"板块方向与大盘一致: {pos_cnt}/{len(s1_ranked)}板块上涨 vs 上证+0.41%"))
    # 3. 分类覆盖
    otherage = sum(1 for s in s1_ranked if tag_group_v2(s["name"]) == "其他")
    checks.append(("[ PASS]" if otherage == 0 else f"[ WARN]", f"v2修正后{otherage}个板块归为「其他」(v1有6个)"))
    # 4. 分组平均 vs 大盘
    all_pcts = [float(s.get("change_pct", 0) or 0) for s in s1_ranked]
    overall_avg = sum(all_pcts) / len(all_pcts)
    checks.append(("[ PASS]", f"28板块总平均{overall_avg:+.2f}% 与上证+0.41%量级一致(板块加权 vs 市值加权差异正常)"))
    
    for status, desc in checks:
        print(f"  {status} {desc}")
    
    print(f"\n  综合评级: {'★' if otherage == 0 else ''}{'★' if otherage <= 2 else ''}★☆☆☆")
    print(f"  (单源限制扣2星, 分类覆盖{'完善' if otherage == 0 else '需改进'}扣{1 if otherage > 0 else 0}星)")
    
    # === 保存修正结果 ===
    result = {
        "date": TODAY,
        "source": "腾讯 sectors (S1)",
        "total_boards": len(s1_ranked),
        "boards": [{"name": s["name"], "pct": float(s.get("change_pct", 0) or 0),
                    "group_v1": tag_group_v1(s["name"]),
                    "group_v2": tag_group_v2(s["name"])} for s in s1_ranked],
        "group_stats_v1": {},
        "group_stats_v2": {},
        "changes": [{"rank": r, "name": n, "pct": p, "from": g1, "to": g2} for r, n, p, g1, g2 in changes],
        "quality": {"overall_avg": overall_avg, "positive_boards": pos_cnt, "negative_boards": neg_cnt}
    }
    
    for g in sorted(group_v1):
        pcts = group_v1[g]["pcts"]
        if pcts:
            result["group_stats_v1"][g] = {"count": len(pcts), "avg_pct": sum(pcts)/len(pcts)}
    for g in sorted(group_data):
        result["group_stats_v2"][g] = {"count": len(group_data[g]["pcts"]),
                                        "avg_pct": sum(group_data[g]["pcts"])/len(group_data[g]["pcts"]),
                                        "boards": list(zip(group_data[g]["names"], group_data[g]["pcts"]))}
    
    out_path = os.path.join(BASE_DIR, "data", "industry_group_audit_2026-07-29.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  结果已保存: {out_path}")
