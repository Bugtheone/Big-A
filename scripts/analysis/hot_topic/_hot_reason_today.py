"""同花顺当日强势股 + 题材归因"""
import requests, sys
from collections import Counter
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"
today = date.today().strftime("%Y-%m-%d")

url = f"http://zx.10jqka.com.cn/event/api/getharden/date/{today}/orderby/date/orderway/desc/charset/GBK/"
print(f"请求日期: {today}")
r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
d = r.json()

if d.get("errocode", 0) != 0:
    print(f"API错误: {d.get('errormsg', '')}")
    # 尝试前一天
    print("\n尝试前一天...")
    yesterday = "2026-07-25"  # 上周五
    url2 = f"http://zx.10jqka.com.cn/event/api/getharden/date/{yesterday}/orderby/date/orderway/desc/charset/GBK/"
    r2 = requests.get(url2, headers={"User-Agent": UA}, timeout=10)
    d = r2.json()
    if d.get("errocode", 0) != 0:
        print(f"前一天也失败: {d.get('errormsg', '')}")
        sys.exit(1)
    print(f"使用日期: {yesterday}")

rows = d.get("data") or []
print(f"\n当日强势股共 {len(rows)} 只\n")

# 按涨幅排序
rows.sort(key=lambda x: float(x.get("zhangfu", 0) or 0), reverse=True)

# === 涨幅TOP 20 ===
print("=" * 70)
print(" TOP 20 涨幅榜（按涨幅降序）")
print("=" * 70)
print(f" {'代码':<8}{'名称':<10}{'涨幅%':>6}{'题材归因'}")
print(" " + "-" * 68)
for r in rows[:20]:
    code = r.get("code", "")
    name = r.get("name", "")
    zf = float(r.get("zhangfu", 0) or 0)
    reason = r.get("reason", "")
    print(f" {code:<8}{name:<10}{zf:>5.1f}%  {reason[:55]}")

# === 题材词频统计 ===
print("\n" + "=" * 70)
print(" 题材热力图（词频统计）")
print("=" * 70)
all_tags = []
for r in rows:
    reason = r.get("reason", "")
    if reason:
        tags = [t.strip() for t in str(reason).split("+") if t.strip()]
        all_tags.extend(tags)

cnt = Counter(all_tags)
print(f" 共 {len(cnt)} 个独立题材标签\n")
print(f" {'排名':<6}{'题材':<30}{'出现次数':<10}{'示例股'}")
print(" " + "-" * 68)
top_tags = cnt.most_common(20)
for rank, (tag, n) in enumerate(top_tags, 1):
    # 找该题材的示例股
    examples = []
    for r in rows:
        tags_list = [t.strip() for t in str(r.get("reason", "")).split("+") if t.strip()]
        if tag in tags_list:
            examples.append(f"{r['name']}({r['zhangfu']}%)")
        if len(examples) >= 3:
            break
    ex_str = ", ".join(examples[:3])
    print(f" #{rank:<4} {tag:<30}{n:<10}{ex_str}")

# === 按题材聚类 ===
print("\n" + "=" * 70)
print(" 热门题材聚类")
print("=" * 70)
for tag, n in top_tags[:10]:
    stocks = []
    for r in rows:
        tags_list = [t.strip() for t in str(r.get("reason", "")).split("+") if t.strip()]
        if tag in tags_list:
            stocks.append(r)
    print(f"\n【{tag}】({n}只)")
    for s in sorted(stocks, key=lambda x: float(x.get("zhangfu", 0) or 0), reverse=True)[:8]:
        zf = float(s.get("zhangfu", 0) or 0)
        print(f"   {s['code']} {s['name']:<8} {zf:+.1f}%  {s.get('reason','')[:50]}")

# === 涨停统计 ===
zt_count = sum(1 for r in rows if float(r.get("zhangfu", 0) or 0) >= 9.8)
zt5_count = sum(1 for r in rows if float(r.get("zhangfu", 0) or 0) >= 5)
print(f"\n\n涨停(>=9.8%): {zt_count}只  |  涨超5%: {zt5_count}只")
