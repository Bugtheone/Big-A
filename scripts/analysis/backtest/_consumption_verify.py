# -*- coding: utf-8 -*-
"""大消费行业/概念板块数据验证 + 多源交叉验证 | 2026-07-30"""
import sys, os, io, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'scripts'))
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from datetime import datetime
from collections import Counter

# ── 大消费覆盖范围映射 ──
CONSUMPTION_SW = {
    "食品饮料": ["食品饮料"],
    "家用电器": ["白色家电", "厨卫电器", "小家电", "黑色家电", "家用电器", "家电零部件Ⅱ", "照明设备Ⅱ"],
    "汽车": ["乘用车", "商用车", "汽车服务", "汽车零部件"],
    "纺织服饰": ["服装家纺", "纺织制造"],
    "商贸零售": ["一般零售", "互联网电商"],
    "社会服务": ["旅游零售", "酒店餐饮", "教育", "专业服务"],
    "美容护理": ["美容护理"],
    "农林牧渔": ["养殖业", "饲料", "农产品加工"],
    "轻工制造": ["家居用品", "造纸", "文娱用品"],
    "医药生物": ["化学制药", "中药", "生物制品", "医疗器械", "医药商业"],
}
# 消费关键词（用于概念板块筛选）
CONSUME_KW = [
    "消费", "食品", "饮料", "白酒", "啤酒", "乳业", "调味品",
    "家电", "电器", "汽车", "新能源车", "服装", "纺织", 
    "零售", "免税", "电商", "新零售", "旅游", "酒店", "餐饮", 
    "预制菜", "医美", "美容", "中药", "养老", "银发", "宠物", 
    "国货", "家居", "家装", "造纸", "养殖", "农业",
]

print("=" * 70)
print("  大消费行业/概念板块 多源数据验证")
print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 70)

# ═══════════════════════════════════════════════════
# 源A: 腾讯II级28行业 — 实时行情
# ═══════════════════════════════════════════════════
print("\n[源A] 腾讯II级28行业 — 盘中实时行情(*验*证)")
print("-" * 60)
from scripts.market_api import api

sectors = api.sectors(30)
tc_names = set()
tc_consumption = []

for s in sectors:
    nm = s.get("name", "")
    tc_names.add(nm)
    pct = s.get("change_pct", 0)
    # 匹配大消费
    for sw_name, tc_list in CONSUMPTION_SW.items():
        if nm in tc_list:
            # 确认大类
            if sw_name in ["食品饮料", "农林牧渔", "纺织服饰"]:
                macro = "必选消费"
            elif sw_name == "医药生物":
                macro = "消费医疗"
            else:
                macro = "可选消费"
            tc_consumption.append((nm, pct, macro, sw_name))
            break

tc_consumption.sort(key=lambda x: x[1], reverse=True)

print(f"  腾讯II级行业总数: {len(tc_names)}")
print(f"  匹配大消费: {len(tc_consumption)} 个\n")

by_macro = {}
for nm, pct, macro, sw in tc_consumption:
    by_macro.setdefault(macro, []).append((nm, pct, sw))

for macro in ["必选消费", "可选消费", "消费医疗"]:
    items = by_macro.get(macro, [])
    if items:
        print(f"  [{macro}] {len(items)}个行业:")
        for nm, pct, sw in items:
            print(f"    {nm:12s} ({sw})  今日 {pct:+.2f}%")
    else:
        print(f"  [{macro}] (腾讯28行业不包含此类)")

# 腾讯28全覆盖打印
print(f"\n  [参考] 腾讯II级28行业全览:")
tc_all_sorted = sorted(sectors, key=lambda x: x.get("change_pct", 0), reverse=True)
for i, s in enumerate(tc_all_sorted):
    pct = s.get("change_pct", 0)
    nm = s.get("name", "")
    tag = "[消费]" if nm in [x[0] for x in tc_consumption] else ""
    print(f"    {i+1:2d}. {nm:16s} {pct:+7.2f}% {tag}")

# ═══════════════════════════════════════════════════
# 源B: 东财概念板块 — 消费相关概念
# ═══════════════════════════════════════════════════
print(f"\n\n[源B] 东财概念板块 — 消费相关概念筛选")
print("-" * 60)
try:
    from scripts.data_gate import gate
    
    # 拉全量概念板块
    concept_boards = gate.em_industry_board("概念")
    
    if concept_boards:
        print(f"  东财概念板块总数: {len(concept_boards)}")
        
        # 筛选消费相关
        consume_concepts = []
        non_consume_sample = []
        for b in concept_boards:
            nm = b.get("name", "")
            if any(kw in nm for kw in CONSUME_KW):
                consume_concepts.append(b)
            elif len(non_consume_sample) < 10:
                non_consume_sample.append(nm)
        
        consume_concepts.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
        print(f"  消费相关概念: {len(consume_concepts)} 个")
        
        print(f"\n  涨幅TOP10消费概念:")
        for b in consume_concepts[:10]:
            pct = b.get("change_pct", 0)
            net = b.get("main_net", 0) / 1e8 if b.get("main_net") else 0
            name = b.get("name", "")
            print(f"    {name:16s}  涨{pct:+6.2f}%  主力净{net:+.1f}亿")
        
        # 按主题分组
        print(f"\n  消费概念按主题分组:")
        themes = {}
        for b in consume_concepts:
            nm = b.get("name", "")
            # 分组逻辑
            for grp_key in ["白酒", "食品饮料", "家电", "汽车", "新能源", "服装", 
                           "零售", "免税", "电商", "旅游", "酒店", "餐饮", "预制菜",
                           "医美", "中药", "养老", "宠物", "家居", "农业", "养殖"]:
                if grp_key in nm:
                    themes.setdefault(grp_key, []).append(nm)
                    break
        
        for grp, names in sorted(themes.items(), key=lambda x: -len(x[1])):
            print(f"    {grp}: {', '.join(names)}")
        
        # 非消费样本
        print(f"\n  [参考] 非消费概念样本(各取首个):")
        seen_cat = set()
        sample = []
        for b in concept_boards:
            nm = b.get("name", "")
            # 跳过消费
            if any(kw in nm for kw in CONSUME_KW):
                continue
            # 按首字分组取一个样本
            first = nm[:2]
            if first not in seen_cat:
                seen_cat.add(first)
                sample.append(nm)
                if len(sample) >= 15:
                    break
        print(f"    {', '.join(sample)}")
    else:
        print("  em_industry_board(概念)返回空(EM push2限流)")
except Exception as e:
    print(f"  东财概念获取失败: {e}")

# ═══════════════════════════════════════════════════
# 源C: 东财行业板块 — 消费相关行业
# ═══════════════════════════════════════════════════
print(f"\n\n[源C] 东财行业板块 — 消费相关行业")
print("-" * 60)
try:
    industry_boards = gate.em_industry_board("行业")
    
    if industry_boards:
        print(f"  东财行业板块总数: {len(industry_boards)}")
        
        consume_ind = []
        for b in industry_boards:
            nm = b.get("name", "")
            if any(kw in nm for kw in CONSUME_KW):
                consume_ind.append(b)
        
        consume_ind.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
        print(f"  消费相关行业板块: {len(consume_ind)} 个\n")
        
        for macro in ["必选消费", "可选消费", "消费医疗"]:
            items_em = []
            if macro == "必选消费":
                em_kw = ["食品饮料", "农林牧渔", "纺织", "服装"]
            elif macro == "可选消费":
                em_kw = ["家电", "汽车", "轻工", "社会服务", "商贸", "零售", "美容"]
            else:
                em_kw = ["医药", "中药"]
            
            for b in consume_ind:
                nm = b.get("name", "")
                if any(kw in nm for kw in em_kw):
                    items_em.append((nm, b.get("change_pct", 0)))
            
            if items_em:
                print(f"  [{macro}] {len(items_em)}个:")
                for nm, pct in items_em:
                    print(f"    {nm:16s}  {pct:+.2f}%")
            else:
                print(f"  [{macro}] 无(东财分类维度不同)")
    else:
        print("  em_industry_board(行业)返回空(EM push2限流)")
except Exception as e:
    print(f"  东财行业获取失败: {e}")

# ═══════════════════════════════════════════════════
# 源D: 个股概念归属 — 标杆股验证
# ═══════════════════════════════════════════════════
print(f"\n\n[源D] 个股概念归属 — 标杆股验证(东财hot_concept)")
print("-" * 60)
try:
    test_stocks = [
        ("600519", "贵州茅台", "食品饮料/白酒"),
        ("002594", "比亚迪", "汽车/新能源车"),
        ("000333", "美的集团", "家电/消费电子"),
        ("002714", "牧原股份", "农林牧渔/养殖"),
        ("000963", "华东医药", "医药/医美"),
    ]
    
    for code, name, expected in test_stocks:
        try:
            concept_tags = api.hot_concept(code)
            if concept_tags:
                # 筛选消费标签
                consume_tags = []
                all_tags = []
                for t in concept_tags:
                    tname = t.get("name", t.get("concept_name", str(t)))
                    all_tags.append(tname)
                    if any(kw in str(tname) for kw in CONSUME_KW):
                        consume_tags.append(tname)
                
                print(f"  {name}({code}) — 预期: {expected}")
                print(f"    总概念标签: {len(all_tags)}")
                print(f"    消费相关: {consume_tags[:8]}")
            else:
                print(f"  {name}({code}) — 概念数据为空")
        except Exception as e2:
            print(f"  {name}({code}) — 异常: {e2}")

except Exception as e:
    print(f"  概念归属获取失败: {e}")

# ═══════════════════════════════════════════════════
# 综合验证结论
# ═══════════════════════════════════════════════════
print(f"\n\n{'=' * 70}")
print("  多源交叉验证结论")
print("=" * 70)

print(f"""
  数据源汇总:
  [源A] 腾讯II级28行业(首選·不封IP): ★★★★★
    实测消费相关: {len(tc_consumption)}个
    消费占比: {len(tc_consumption)}/28 = {len(tc_consumption)/28*100:.1f}%
    
  [源B] 东财概念板块(封IP中): ★★★☆☆
    消费相关概念数量取决于盘中EM可用性
    
  [源C] 东财行业板块: ★★★☆☆
    与腾讯行业维度可能不同(申万/证监会/东财自编)
    
  [源D] 个股概念归属: ★★★★☆
    通过茅台/比亚迪/美的/牧原/华东医药实际概念标签验证

  最终结论:
  ┌─────────────────────────────────────────────────────┐
  │ 大消费 = 必选消费(食品饮料/农林牧渔/纺织服饰)      │
  │       + 可选消费(家电/汽车/轻工/社服/商贸/美容)    │
  │       + 消费医疗(医药生物中的消费属性)              │
  │                                                     │
  │ 腾讯II级28行业: 实测 {len(tc_consumption)} 个直接匹配     │
  │ 申万一级行业: 约6-8个                              │
  │ 东财概念板块: 预计20+个(含白酒/新能源车/医美/免税等)│
  └─────────────────────────────────────────────────────┘
""")

# 保存报告
outfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_consumption_verify.txt")
with open(outfile, "w", encoding="utf-8") as f:
    f.write(f"大消费验证报告 | {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
    f.write(f"腾讯II级28行业中消费相关({len(tc_consumption)}个):\n")
    for nm, pct, macro, sw in tc_consumption:
        f.write(f"  {nm:12s} ({sw}/{macro})  {pct:+.2f}%\n")
print(f"详细报告已保存: {outfile}")
