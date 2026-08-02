#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DKX金叉(7/22) 全量66只 K线验证 + 波段评分排名
"""

import json, time, os, sys
from datetime import datetime
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "log")
TODAY = "2026-07-23"
OUTPUT = os.path.join(LOG_DIR, f"{TODAY.replace('-','')}_DKX金叉_全量排名.md")

# ─── 66只DKX金叉股 ───
DKX_STOCKS = [
    ("600011", "华能国际"), ("600021", "上海电力"), ("600032", "浙江新能"),
    ("600126", "杭钢股份"), ("600131", "国网信通"), ("600251", "冠农股份"),
    ("600282", "南钢股份"), ("600309", "万华化学"), ("600383", "金地集团"),
    ("600452", "涪陵电力"), ("600486", "扬农化工"), ("600499", "科达制造"),
    ("600505", "西昌电力"), ("600547", "山东黄金"), ("600551", "时代出版"),
    ("600611", "大众交通"), ("600635", "大众公用"), ("600642", "申能股份"),
    ("600682", "南京新百"), ("600737", "中粮糖业"), ("600744", "华银电力"),
    ("600760", "中航沈飞"), ("600780", "通宝能源"), ("600797", "浙大网新"),
    ("600821", "金开新能"), ("600863", "华能蒙电"), ("600905", "三峡能源"),
    ("600956", "新天绿能"), ("601001", "晋控煤业"), ("601330", "绿色动力"),
    ("601888", "中国中免"), ("601969", "海南矿业"), ("603193", "润本股份"),
    ("603228", "景旺电子"), ("603333", "福华尚纬"), ("603881", "数据港"),
    ("603927", "中科软"),  ("603979", "金诚信"), ("603993", "洛阳钼业"),
    ("000011", "深物业A"),  ("000037", "深南电A"), ("000408", "藏格矿业"),
    ("000537", "绿发电力"), ("000560", "我爱我家"), ("000582", "北部湾港"),
    ("000617", "中油资本"), ("000680", "山推股份"), ("000690", "宝新能源"),
    ("000825", "太钢不锈"), ("000889", "中嘉博创"), ("000997", "新大陆"),
    ("001979", "招商蛇口"), ("002001", "新和成"),  ("002039", "黔源电力"),
    ("002040", "南京港"),   ("002053", "云南能投"), ("002067", "景兴纸业"),
    ("002197", "证通电子"), ("002226", "江南化工"), ("002302", "西部建设"),
    ("002373", "千方科技"), ("002493", "荣盛石化"), ("002556", "辉隆股份"),
    ("002608", "江苏国信"), ("002640", "跨境通"),  ("003039", "顺控发展"),
]

# 主线标签
MAIN_THEMES = {
    "电力/电网/绿电": {"华能国际","上海电力","浙江新能","涪陵电力","西昌电力","华银电力",
                    "通宝能源","金开新能","华能蒙电","三峡能源","新天绿能","绿色动力",
                    "绿发电力","宝新能源","黔源电力","云南能投","江苏国信","深南电A",
                    "申能股份","顺控发展","国网信通","福华尚纬"},
    "能源金属/矿业": {"山东黄金","海南矿业","金诚信","洛阳钼业","藏格矿业","晋控煤业"},
    "化工/周期":     {"万华化学","扬农化工","科达制造","新和成","江南化工","荣盛石化"},
    "中报预增/AI科技":{"证通电子","中科软","数据港","浙大网新","景旺电子","千方科技","新大陆"},
    "基建/地产/交通": {"招商蛇口","金地集团","西部建设","大众交通","大众公用","南京港","北部湾港"},
    "消费/免税/农业": {"中国中免","中粮糖业","冠农股份","辉隆股份","润本股份"},
    "钢铁/制造":      {"南钢股份","杭钢股份","太钢不锈","山推股份","科达制造"},
    "其他央企/金融":  {"中航沈飞","中油资本","时代出版","深物业A","我爱我家","跨境通",
                    "南京新百","中嘉博创","景兴纸业"},
}

session = requests.Session()
session.trust_env = False
session.headers.update({"User-Agent": "Mozilla/5.0"})
TENCENT_KLINE = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={market}{code},day,,,30,qfq"


def get_market(code):
    return "sz" if code.startswith(("0", "3")) else "sh"


def fetch_kline(code):
    m = get_market(code)
    try:
        r = session.get(TENCENT_KLINE.format(market=m, code=code), timeout=10)
        r.raise_for_status()
        data = json.loads(r.text)
        klines = data["data"][f"{m}{code}"].get("qfqday") or data["data"][f"{m}{code}"].get("day")
        if not klines:
            return None
        result = {"dates":[], "opens":[], "closes":[], "highs":[], "lows":[], "vols":[]}
        for row in klines[-30:]:
            if len(row) < 6:
                continue
            result["dates"].append(row[0])
            result["opens"].append(float(row[1]))
            result["closes"].append(float(row[2]))
            result["highs"].append(float(row[3]))
            result["lows"].append(float(row[4]))
            result["vols"].append(float(row[5]))
        return result if result["closes"] else None
    except Exception:
        return None


def calc_dkx(closes):
    if len(closes) < 20:
        return None
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20
    if len(closes) >= 21:
        prev_ma5 = sum(closes[-6:-1]) / 5
        prev_ma20 = sum(closes[-21:-1]) / 20
        today_golden = (ma5 > ma20) and (prev_ma5 <= prev_ma20)
    else:
        today_golden = False
    return {"ma5": round(ma5,2), "ma10": round(ma10,2), "ma20": round(ma20,2),
            "is_golden": ma5 > ma20, "today_golden": today_golden}


def analyze(code, name, kline):
    if not kline:
        return None
    closes = kline["closes"]
    opens = kline["opens"]
    highs = kline["highs"]
    lows = kline["lows"]
    vols = kline["vols"]
    latest = closes[-1]

    dkx = calc_dkx(closes)
    if dkx is None:
        return None

    # 距MA20
    dist_ma20 = round((latest - dkx["ma20"]) / dkx["ma20"] * 100, 2)

    # 量比 5日/20日
    vol5 = sum(vols[-5:]) / 5 if len(vols) >= 5 else 1
    vol20 = sum(vols[-20:]) / 20 if len(vols) >= 20 else 1
    vol_ratio = round(vol5 / vol20, 2) if vol20 > 0 else 1

    # 今日振幅
    amp_today = round((highs[-1] - lows[-1]) / opens[-1] * 100, 2)

    # 近5/10/20日涨跌幅
    chg5 = round((closes[-1] - closes[-5]) / closes[-5] * 100, 2) if len(closes) >= 5 else 0
    chg10 = round((closes[-1] - closes[-10]) / closes[-10] * 100, 2) if len(closes) >= 10 else 0
    chg20 = round((closes[-1] - closes[-20]) / closes[-20] * 100, 2) if len(closes) >= 20 else 0

    # ─── 综合评分 ───
    score = 0
    reasons = []

    # 1. 距MA20距离 (核心)
    if 0 <= dist_ma20 <= 5:
        score += 3.0
        reasons.append(f"紧贴MA20(+{dist_ma20:.1f}%)")
    elif -3 <= dist_ma20 < 0:
        score += 3.0
        reasons.append(f"回踩MA20({dist_ma20:.1f}%)")
    elif 5 < dist_ma20 <= 10:
        score += 2.0
        reasons.append(f"略高于MA20(+{dist_ma20:.1f}%)")
    elif 10 < dist_ma20 <= 15:
        score += 1.0
        reasons.append(f"偏高MA20(+{dist_ma20:.1f}%)")
    elif dist_ma20 > 15:
        score += 0.0
        reasons.append(f"远离MA20(+{dist_ma20:.1f}%)，追高风险")

    # 2. 量比
    if 1.3 <= vol_ratio <= 2.5:
        score += 2.0
        reasons.append(f"温和放量(量比{vol_ratio})")
    elif 1.0 <= vol_ratio < 1.3:
        score += 1.0
        reasons.append(f"正常量(量比{vol_ratio})")
    elif vol_ratio > 2.5:
        score += 1.5
        reasons.append(f"明显放量(量比{vol_ratio})")

    # 3. 振幅（波段空间）
    if 2 <= amp_today <= 7:
        score += 1.5
        reasons.append(f"振幅适中({amp_today:.1f}%)")
    elif 1 <= amp_today < 2:
        score += 0.5
        reasons.append(f"振幅偏小({amp_today:.1f}%)")

    # 4. 近期趋势
    if 2 <= chg5 <= 15:
        score += 1.5
        reasons.append(f"5日温和上涨({chg5:+.1f}%)")
    elif -5 <= chg5 < 0:
        score += 1.0
        reasons.append(f"5日微调({chg5:+.1f}%)，蓄力中")
    elif chg5 > 15:
        score += 0.0
        reasons.append(f"5日急涨({chg5:+.1f}%)，追高风险")

    # 5. 今日金叉加分
    if dkx["today_golden"]:
        score += 1.0
        reasons.append("今日发金叉")
    elif dkx["is_golden"]:
        score += 0.5

    # 6. MA5 > MA10 多头加分
    if dkx["ma5"] > dkx["ma10"]:
        score += 0.5

    return {
        "code": code, "name": name,
        "latest": round(latest, 2),
        "ma5": dkx["ma5"], "ma20": dkx["ma20"],
        "dist_ma20": dist_ma20,
        "vol_ratio": vol_ratio,
        "amp_today": amp_today,
        "chg5": chg5, "chg10": chg10, "chg20": chg20,
        "is_golden": dkx["is_golden"],
        "today_golden": dkx["today_golden"],
        "score": round(score, 2),
        "reasons": reasons,
    }


def find_theme(name):
    themes = []
    for t, s in MAIN_THEMES.items():
        if name in s:
            themes.append(t)
    return themes[0] if themes else "其他"


def main():
    print("=" * 60)
    print(f"DKX金叉 全量66只 K线验证")
    print("=" * 60)

    total = len(DKX_STOCKS)
    results = []
    fail = []

    for i, (code, name) in enumerate(DKX_STOCKS, 1):
        pct = i / total * 100
        bar = "#" * int(pct / 2)
        print(f"\r  [{i:2d}/{total}] {bar:<33s} {pct:.0f}% | {name}({code})", end="", flush=True)
        kline = fetch_kline(code)
        if not kline:
            fail.append((code, name))
            continue
        r = analyze(code, name, kline)
        if r:
            r["theme"] = find_theme(name)
            results.append(r)
        else:
            fail.append((code, name))
        time.sleep(0.25)

    print(f"\n\n  完成！成功: {len(results)}只 | 失败: {len(fail)}只")

    results.sort(key=lambda x: (-x["score"], x["dist_ma20"]))

    # ─── 生成报告 ───
    lines = []
    lines.append(f"# DKX金叉(7/22) 全量K线验证 + 波段评分排名")
    lines.append(f"\n> 报告时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 数据源：腾讯日K API（近30日）")
    lines.append(f"> 评分维度：距MA20(3分) + 量比(2分) + 振幅(1.5分) + 趋势(1.5分) + 金叉确认(1分)")
    lines.append(f"> 成功率：{len(results)}/{total}（{len(results)/total*100:.0f}%）")
    lines.append("")

    # 一、综合排名
    lines.append("---")
    lines.append("## 一、全量排名")
    lines.append("")
    lines.append("| 排名 | 代码 | 名称 | 板块 | 评分 | 现价 | 距MA20 | 量比 | 振幅 | 5日涨跌 | 核心信号 |")
    lines.append("|------|------|------|------|------|------|--------|------|------|---------|----------|")
    for i, r in enumerate(results, 1):
        stars = "★★★" if r["score"] >= 7 else ("★★" if r["score"] >= 5 else "★")
        sig = "今日金叉" if r["today_golden"] else ("金叉" if r["is_golden"] else "—")
        dist = f"{r['dist_ma20']:+.1f}%"
        lines.append(f"| {i} | {r['code']} | {r['name']} | {r['theme']} | **{r['score']:.1f}** {stars} | {r['latest']:.2f} | {dist} | {r['vol_ratio']} | {r['amp_today']:.1f}% | {r['chg5']:+.1f}% | {sig} |")

    lines.append("")

    # 二、按板块分组排名
    lines.append("---")
    lines.append("## 二、按板块分组排名")
    lines.append("")

    for theme_name in MAIN_THEMES:
        theme_results = [r for r in results if r["theme"] == theme_name]
        if not theme_results:
            continue
        lines.append(f"### {theme_name}（{len(theme_results)}只）")
        lines.append("")
        lines.append("| 排名 | 代码 | 名称 | 评分 | 现价 | 距MA20 | 量比 | 5日涨跌 |")
        lines.append("|------|------|------|------|------|--------|------|---------|")
        for i, r in enumerate(theme_results, 1):
            dist = f"{r['dist_ma20']:+.1f}%"
            lines.append(f"| {i} | {r['code']} | {r['name']} | **{r['score']:.1f}** | {r['latest']:.2f} | {dist} | {r['vol_ratio']} | {r['chg5']:+.1f}% |")
        lines.append("")

    # 三、TOP20详细分析
    lines.append("---")
    lines.append("## 三、TOP 15 详细分析")
    lines.append("")

    for i, r in enumerate(results[:15], 1):
        stars = "★★★" if r["score"] >= 7 else ("★★" if r["score"] >= 5 else "★")
        lines.append(f"### {i}. {r['name']}（{r['code']}） {stars} {r['score']:.1f}分")
        lines.append("")
        lines.append(f"- **板块**：{r['theme']}")
        lines.append(f"- **现价**：{r['latest']:.2f}")
        lines.append(f"- **MA5/MA20**：{r['ma5']} / {r['ma20']}")
        lines.append(f"- **距MA20**：{r['dist_ma20']:+.1f}%")
        lines.append(f"- **量比(5/20)**：{r['vol_ratio']}")
        lines.append(f"- **今日振幅**：{r['amp_today']:.1f}%")
        lines.append(f"- **5日/10日/20日涨跌**：{r['chg5']:+.1f}% / {r['chg10']:+.1f}% / {r['chg20']:+.1f}%")
        lines.append(f"- **DKX状态**：{'今日金叉' if r['today_golden'] else '金叉中'}")
        lines.append(f"- **评分理由**：{'；'.join(r['reasons'])}")
        lines.append("")

    # 四、策略总结
    lines.append("---")
    lines.append("## 四、策略总结")
    lines.append("")

    dist_ok = [r for r in results if abs(r["dist_ma20"]) <= 5]
    vol_ok = [r for r in results if 1.3 <= r["vol_ratio"] <= 2.5]
    golden_today = [r for r in results if r["today_golden"]]
    high_score = [r for r in results if r["score"] >= 6]

    lines.append(f"### 筛选统计")
    lines.append(f"- 距MA20 <=5%：**{len(dist_ok)}只**（安全边际充分）")
    lines.append(f"- 温和放量(量比1.3-2.5)：**{len(vol_ok)}只**（资金确认）")
    lines.append(f"- 今日发金叉：**{len(golden_today)}只**（信号最新）")
    lines.append(f"- 综合评分>=6分：**{len(high_score)}只**")
    lines.append("")

    # 三重过滤精华
    elite = [r for r in results if abs(r["dist_ma20"]) <= 7 and r["vol_ratio"] >= 1.2 and r["score"] >= 5]
    lines.append("### 三重过滤精华（距MA20<=7% + 量比>=1.2 + 评分>=5）")
    lines.append("")
    if elite:
        lines.append("| 代码 | 名称 | 板块 | 评分 | 距MA20 | 量比 | 5日涨跌 |")
        lines.append("|------|------|------|------|--------|------|---------|")
        for r in elite:
            lines.append(f"| {r['code']} | {r['name']} | {r['theme']} | {r['score']:.1f} | {r['dist_ma20']:+.1f}% | {r['vol_ratio']} | {r['chg5']:+.1f}% |")

    lines.append("")
    lines.append("### 情景B下的波段优先顺序")
    lines.append("")
    lines.append("```")
    lines.append("第一梯队（距MA20近+放量+高分）：")
    for r in elite[:8]:
        lines.append(f"  {r['name']}({r['code']}) - {r['score']:.1f}分 - {r['theme']}")
    lines.append("")
    lines.append("第二梯队（距MA20近但量能一般 or 放量但略偏高）：")
    second = [r for r in results if 5 <= r["score"] < 6 and abs(r["dist_ma20"]) <= 10]
    for r in second[:10]:
        lines.append(f"  {r['name']}({r['code']}) - {r['score']:.1f}分 - {r['theme']}")
    lines.append("")
    lines.append("需等回踩（偏离MA20>10%但有金叉信号）：")
    far = [r for r in results if r["dist_ma20"] > 10]
    for r in far[:8]:
        lines.append(f"  {r['name']}({r['code']}) - 偏离MA20 {r['dist_ma20']:+.1f}%")
    lines.append("```")
    lines.append("")

    if fail:
        lines.append("### 数据拉取失败")
        lines.append("")
        for code, name in fail:
            lines.append(f"- {name}({code})")
        lines.append("")

    lines.append("---")
    lines.append(f"\n*全量报告由 `_dkx_full_rank.py` 自动生成 | {TODAY}*")

    report = "\n".join(lines)
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[OK] 报告: {OUTPUT}")


if __name__ == "__main__":
    main()
