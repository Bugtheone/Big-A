# -*- coding: utf-8 -*-
"""
大盘整体行情类型 — 近30个交易日回顾
使用项目 L1 信号体系：九指数涨跌比/均值/风格 → 持续性判定 → 信号等级
"""
import sys
import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_session = requests.Session()
_session.trust_env = False
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
SH_CODES = frozenset({"000300", "000905", "000016", "000688", "000852", "000010"})

INDICES = OrderedDict([
    ("000001", "上证指数"),
    ("000300", "沪深300"),
    ("000016", "上证50"),
    ("000905", "中证500"),
    ("000852", "中证1000"),
    ("000688", "科创50"),
    ("399006", "创业板指"),
    ("399001", "深证成指"),
    ("399005", "中小100"),
])


def _prefix(code: str) -> str:
    """000001 -> sh000001"""
    low = code.lower()
    if low.startswith(("sh", "sz", "bj")):
        return low
    if code in SH_CODES or code.startswith(("5", "6", "9")):
        return f"sh{code}"
    if code.startswith(("4", "8", "92")):
        return f"bj{code}"
    return f"sz{code}"


def fetch_kline(code: str, n_days: int = 50) -> List[dict]:
    """拉取腾讯前复权日K线，返回 [{date, close, change_pct}, ...]"""
    pre = _prefix(code)
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pre},day,,,{n_days},qfq"
    headers = {"User-Agent": UA, "Host": "web.ifzq.gtimg.cn"}
    try:
        r = _session.get(url, headers=headers, timeout=15)
        d = r.json()
        kdata = d.get("data", {}).get(pre, {}).get("qfqday", []) or \
                d.get("data", {}).get(pre, {}).get("day", [])
        result = []
        for k in kdata[-n_days:]:
            if len(k) >= 6:
                # 用 open 和 close 计算涨跌幅
                close = float(k[2])
                open_p = float(k[1])
                if open_p > 0:
                    change_pct = (close - open_p) / open_p * 100
                else:
                    change_pct = 0.0
                result.append({
                    "date": k[0],
                    "open": float(k[1]),
                    "close": close,
                    "high": float(k[3]),
                    "low": float(k[4]),
                    "volume": float(k[5]),
                    "change_pct": round(change_pct, 2),
                })
        return result
    except Exception as e:
        print(f"  [WARN] {code} K线拉取失败: {e}")
        return []


def classify_day(indices_data: Dict[str, dict], yesterday: Optional[dict] = None) -> dict:
    """
    对单日九指数数据进行 L1 分类判定。
    indices_data: {code: {date, change_pct, ...}}
    yesterday: {up_count, down_count, avg_change_pct, date}
    """
    up = sum(1 for q in indices_data.values() if q["change_pct"] > 0)
    down = sum(1 for q in indices_data.values() if q["change_pct"] < 0)
    avg_chg = sum(q["change_pct"] for q in indices_data.values()) / max(len(indices_data), 1)

    sh = indices_data.get("000001", {})
    zz1000 = indices_data.get("000852", {})
    gap = sh.get("change_pct", 0) - zz1000.get("change_pct", 0)

    if gap > 0.5:
        style = "防御（大盘强）"
    elif gap < -0.5:
        style = "进攻（小盘强）"
    else:
        style = "均衡"

    # 持续性判定
    if yesterday and yesterday.get("up_count") is not None:
        y_up = yesterday["up_count"]
        y_avg = yesterday.get("avg_change_pct", 0)
        y_date = yesterday.get("date", "")

        # 趋势方向
        if avg_chg < 0 and y_avg < 0:
            trend_dir = "加速恶化" if avg_chg < y_avg else "恶化放缓"
        elif avg_chg < 0 and y_avg >= 0:
            trend_dir = "转弱"
        elif avg_chg >= 0 and y_avg < 0:
            trend_dir = "回暖"
        else:
            trend_dir = "加速回暖" if avg_chg > y_avg else "回暖放缓"

        # 信号判定
        if up >= 5 and y_up >= 5 and trend_dir not in ("加速恶化", "转弱"):
            signal = "进攻确认"
        elif up >= 5 and y_up < 4:
            signal = "进攻待确认"
        elif up <= 3 and y_up <= 3 and trend_dir in ("加速恶化", "转弱", "恶化放缓"):
            signal = "防御确认"
        elif up <= 3 and y_up <= 3:
            signal = "防御中"
        elif up <= 3 and y_up >= 5:
            signal = "陷阱日（进攻→防御反转）"
        elif up >= 5 and y_up <= 3:
            signal = "陷阱日（防御→进攻反转）"
        elif up >= 4 and y_up <= 3:
            signal = "回暖待确认"
        elif up <= 3 and y_up >= 4:
            signal = "转弱待确认"
        else:
            signal = "震荡"
    else:
        signal = "首日运行"
        trend_dir = "首日无对比"

    return {
        "up_count": up,
        "down_count": down,
        "avg_change_pct": round(avg_chg, 2),
        "style": style,
        "signal": signal,
        "trend_direction": trend_dir,
    }


def main():
    print("=" * 80)
    print("  大盘整体行情类型 — 近30个交易日回溯")
    print("  判定体系: 九指数涨跌比 + 持续性确认 + 陷阱日检测")
    print("=" * 80)

    # Step 1: 拉取九大指数近50天K线（含休假日，取最近30个有数据的交易日）
    print("\n[1/3] 拉取九大指数日K线...")
    all_kdata: Dict[str, Dict[str, dict]] = {}  # {date: {code: {date, change_pct}}}
    for code, name in INDICES.items():
        kdata = fetch_kline(code, n_days=50)
        for k in kdata:
            date = k["date"]
            if date not in all_kdata:
                all_kdata[date] = {}
            all_kdata[date][code] = k
        print(f"  {name} ({code}): {len(kdata)} 条K线")

    # Step 2: 筛选至少有7个指数有数据的日期（有效的交易日）
    print(f"\n[2/3] 筛选有效交易日（至少7/9指数有数据）...")
    sorted_dates = sorted(all_kdata.keys(), reverse=True)
    valid_days = []
    for date in sorted_dates:
        if len(all_kdata[date]) >= 7:
            valid_days.append(date)

    # 取最近30个交易日
    valid_days = valid_days[:30]
    if not valid_days:
        print("  [ERROR] 没有找到有效交易日！"); return
    print(f"  有效交易日: {len(valid_days)} 天（{valid_days[-1]} ~ {valid_days[0]}）")

    # Step 3: 逐日分类
    print(f"\n[3/3] 逐日 L1 信号判定...\n")
    results = []
    prev_day: Optional[dict] = None  # yesterday's stats

    # 按时间正序
    for date in reversed(valid_days):
        day_data = all_kdata[date]
        result = classify_day(day_data, prev_day)
        result["date"] = date
        results.append(result)

        # 更新 prev_day 供下一个交易日对比
        prev_day = {
            "date": date,
            "up_count": result["up_count"],
            "down_count": result["down_count"],
            "avg_change_pct": result["avg_change_pct"],
        }

    # =====================
    # 输出
    # =====================
    # 统计各类型天数
    type_count: Dict[str, int] = {}
    for r in results:
        sig = r["signal"]
        type_count[sig] = type_count.get(sig, 0) + 1

    print(f"{'日期':<12} {'涨':>2} {'跌':>2} {'均值':>7} {'风格':<14} {'信号':<22} {'趋势':<8}")
    print("-" * 80)
    for r in results:
        sig_icon = "[!]" if "陷阱" in r["signal"] else ("*" if "确认" in r["signal"] else " ")
        print(f"{r['date']:<12} {r['up_count']:>2} {r['down_count']:>2} {r['avg_change_pct']:>+6.2f}% "
              f"{r['style']:<14} {sig_icon}{r['signal']:<21} {r['trend_direction']:<8}")

    # 汇总统计
    print("\n" + "=" * 80)
    print("  各类型天数统计（近30交易日）")
    print("=" * 80)
    for sig, cnt in sorted(type_count.items(), key=lambda x: -x[1]):
        bar = "█" * cnt
        pct = cnt / len(results) * 100
        print(f"  {sig:<24} {cnt:>2} 天  ({pct:>5.1f}%)  {bar}")

    # 净值估算（等权九指数）
    print("\n" + "=" * 80)
    print("  九指数等权净值（30日，以首日=100基点）")
    print("=" * 80)
    nav = 100.0
    for r in results:
        nav *= (1 + r["avg_change_pct"] / 100)
    print(f"  首日基准: 100.00 → 30日后: {nav:.2f}  (累计 {nav-100:+.2f}%)")

    # 波段区间判定
    print("\n" + "=" * 80)
    print("  区间整体行情类型")
    print("=" * 80)
    attack_days = type_count.get("进攻确认", 0) + type_count.get("进攻待确认", 0)
    defend_days = type_count.get("防御确认", 0) + type_count.get("防御中", 0)
    trap_days = type_count.get("陷阱日（进攻→防御反转）", 0) + type_count.get("陷阱日（防御→进攻反转）", 0)
    oscillate_days = type_count.get("震荡", 0) + type_count.get("回暖待确认", 0) + type_count.get("转弱待确认", 0) + type_count.get("首日运行", 0)

    if nav < 95:
        zone = "深度调整区间"
    elif nav < 98:
        zone = "中期调整区间"
    elif nav < 100:
        zone = "轻度回调区间"
    elif nav < 103:
        zone = "震荡整理区间"
    elif nav < 108:
        zone = "稳步上行区间"
    else:
        zone = "强势上涨区间"

    print(f"  30日净值变动: {nav-100:+.2f}%")
    print(f"  区间判定: {zone}")
    print(f"  进攻信号: {attack_days}天 | 防御信号: {defend_days}天 | 陷阱日: {trap_days}天 | 震荡/过渡: {oscillate_days}天")
    print(f"  主导特征: ", end="")
    if defend_days > attack_days and defend_days > oscillate_days:
        print("防御主导（空头市场）")
    elif attack_days > defend_days and attack_days > oscillate_days:
        print("进攻主导（多头市场）")
    else:
        print("震荡过渡（方向不明）")

    if trap_days >= 2:
        print(f"  [!] 陷阱日 >=2天，市场方向急剧摇摆，注意风险控制")

    print("\n" + "=" * 80)
    print("  信号说明")
    print("=" * 80)
    print("  进攻确认    = 连续2天≥5指数上涨 + 趋势未恶化 → 尾盘可介入")
    print("  进攻待确认  = 今日≥5涨但昨日<4 → 等明天确认")
    print("  防御确认    = 连续2天≤3指数上涨 + 趋势恶化 → 空仓/轻仓")
    print("  防御中      = 连续2天≤3涨但趋势未恶化")
    print("  陷阱日      = 单日急速反转（≥5↔≤3）→ 不操作")
    print("  回暖待确认  = 4涨区间或3→4变化 → 等连续2天确认")
    print("  转弱待确认  = 4涨区间或4→3变化 → 减仓为主")
    print("  震荡        = 其他情况")


if __name__ == "__main__":
    main()
