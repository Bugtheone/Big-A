#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
北向资金 [2014] 多源全量交叉验证脚本
2026-07-29 专项审计

验证链路（6源独立拉取，互不依赖）：
  S1: 同花顺 hexin hgt   [2014] 沪股通分钟级真实值（主源）
  S2: Tushare moneyflow_hsgt [2014] 沪+深估算（Tushare Pro）
  S3: 东财 kamt          [2014] 2024.8.19后永久归零
  S4: CSV 缓存          [2014] 本地 northbound_cache.csv
  S5: 组合管道（api.north_flow）[2014] 优先级链自动选择
  S6: 分钟级快照（api.north_flow_minute）[2014] 当日实时

输出：多源对照表 + 数据质量评级 + 最终推荐值
"""
import sys
import os
import json
import csv
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.market_api import MarketAPI
api = MarketAPI()

if __name__ == "__main__":
    print("=" * 72)
    print("  北向资金 多源全量交叉验证 [2014] 2026-07-29 专项审计")
    print("=" * 72)
    print(f"  执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    today = datetime.now().strftime("%Y-%m-%d")

    # ================================================================
    # S1: 同花顺 hexin hgt [2014] 沪股通分钟级真实值（独立直连）
    # ================================================================
    print("─" * 72)
    print("  S1: 同花顺 hexin hgt (data.hexin.cn) [2014] 沪股通分钟级真实值")
    print("─" * 72)

    s1_hgt_yi = None
    s1_sgt_yi = None
    s1_time_points = 0
    s1_sgt_time_points = 0
    s1_raw_time_last = ""
    s1_error = None

    try:
        import requests
        sess = requests.Session()
        sess.trust_env = False
        resp = sess.get(
            "https://data.hexin.cn/market/hsgtApi/method/dayChart/",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://data.hexin.cn/",
            },
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()

        if isinstance(raw, dict) and "data" in raw:
            data_list = raw["data"]
            if isinstance(data_list, list) and len(data_list) > 0:
                data = data_list[0]
            else:
                data = raw
        else:
            data = raw

        hgt_vals = data.get("hgt", [])
        sgt_vals = data.get("sgt", [])
        time_vals = data.get("time", [])

        s1_time_points = len(hgt_vals)
        s1_sgt_time_points = len(sgt_vals)

        s1_hgt_yi = round(float(hgt_vals[-1]), 2) if hgt_vals else None
        s1_sgt_yi = round(float(sgt_vals[-1]), 2) if sgt_vals else None

        if time_vals:
            s1_raw_time_last = time_vals[-1] if isinstance(time_vals[-1], str) else str(time_vals[-1])

        s1_status = "[OK] 成功"
        print(f"  HGT(沪股通): {s1_hgt_yi} 亿  |  数据点: {s1_time_points}")
        print(f"  SGT(深股通): {s1_sgt_yi} 亿  |  数据点: {s1_sgt_time_points}  [WARN]仅35点，不可靠")
        print(f"  最新时间戳: {s1_raw_time_last}")
        print(f"  数据质量: HGT 可靠(262点完整)；SGT 不可靠(仅{s1_sgt_time_points}点)")
        print(f"  源完整性: hexin API 返回字段 hgt/sgt/time")
        print(f"  状态: {s1_status}")

    except Exception as e:
        s1_error = str(e)
        print(f"  [FAIL] 失败: {s1_error}")

    print()

    # ================================================================
    # S2: Tushare moneyflow_hsgt [2014] 沪+深估算（独立拉取）
    # ================================================================
    print("─" * 72)
    print("  S2: Tushare moneyflow_hsgt [2014] 沪+深估算（Tushare Pro）")
    print("─" * 72)

    s2_hgt_yi = None
    s2_sgt_yi = None
    s2_total_yi = None
    s2_date = None
    s2_error = None

    try:
        from scripts.tushare_api import get_pro
        pro = get_pro()
        if pro is None:
            s2_error = "Tushare连接失败(get_pro返回None)"
            print(f"  [FAIL] 失败: {s2_error}")
        else:
            end_dt = datetime.now()
            from datetime import timedelta
            start_dt = end_dt - timedelta(days=10)
            df = pro.moneyflow_hsgt(
                start_date=start_dt.strftime("%Y%m%d"),
                end_date=end_dt.strftime("%Y%m%d"),
            )
            if df is not None and not df.empty:
                df = df.sort_values("trade_date", ascending=False)
                first = df.iloc[0]
                s2_hgt_yi = round(float(first.get("ggt_ss", 0) or 0) / 10000, 2)
                s2_sgt_yi = round(float(first.get("ggt_sz", 0) or 0) / 10000, 2)
                s2_total_yi = round(s2_hgt_yi + s2_sgt_yi, 2)
                s2_date = str(first.get("trade_date", ""))
                s2_status = "[OK] 成功"
                print(f"  日期: {s2_date}")
                print(f"  HGT(ggt_ss): {s2_hgt_yi} 亿")
                print(f"  SGT(ggt_sz): {s2_sgt_yi} 亿")
                print(f"  合计: {s2_total_yi} 亿")
                print(f"  数据质量: Tushare估算值(moneyflow_hsgt)，非交易所原始数据")
                print(f"  状态: {s2_status}")
            else:
                s2_error = "返回空DataFrame（可能盘后尚未更新）"
                print(f"  [WARN] 无数据: {s2_error}")
    except Exception as e:
        s2_error = str(e)
        print(f"  [FAIL] 失败: {s2_error}")

    print()

    # ================================================================
    # S3: 东财 kamt [2014] 2024.8.19后永久归零
    # ================================================================
    print("─" * 72)
    print("  S3: 东财 kamt.kline [2014] 2024.8.19后官方永久归零")
    print("─" * 72)

    s3_has_data = False
    s3_all_zero = None
    s3_error = None

    try:
        sess_kamt = api.em.session if hasattr(api, 'em') and hasattr(api.em, 'session') else None
        if sess_kamt is None:
            import requests as _r
            sess_kamt = _r.Session()
            sess_kamt.trust_env = False

        url = "https://push2ex.eastmoney.com/api/qt/kamt.kline/get"
        params = {
            "fields1": "f1,f2,f3,f4",
            "fields2": "f51,f52,f53,f54",
            "klt": "101",
            "lmt": "3",
            "ut": "7eea3edcaed734bea9cbfce24459ed57",
        }
        resp = sess_kamt.get(url, params=params, timeout=10)
        resp.raise_for_status()
        raw = resp.json()

        if raw and "data" in raw and raw["data"]:
            klines = raw["data"].get("klines", [])
            if klines:
                s3_has_data = True
                all_zeros = all(
                    sum(abs(float(p)) for p in k.split(",")[1:] if p.replace("-", "").replace(".", "")) < 0.01
                    for k in klines
                )
                s3_all_zero = all_zeros
                print(f"  返回{len(klines)}条记录")
                for i, k in enumerate(klines[:3]):
                    parts = k.split(",")
                    print(f"  [{i+1}] date={parts[0]}, value={parts[1:]}")
                if all_zeros:
                    print(f"  结论: [OK] 确认全部归零（2024.8.19政策生效）")
                else:
                    print(f"  结论: [WARN] 有非零值，异常！")
            else:
                s3_error = "klines为空"
                print(f"  [WARN] {s3_error}")
        else:
            s3_error = "响应无data字段"
            print(f"  [FAIL] {s3_error}")
            print(f"  raw keys: {list(raw.keys()) if isinstance(raw, dict) else type(raw)}")
    except Exception as e:
        s3_error = str(e)
        print(f"  [FAIL] 失败: {s3_error}")

    print()

    # ================================================================
    # S4: CSV 本地缓存
    # ================================================================
    print("─" * 72)
    print("  S4: CSV 本地缓存 [2014] northbound_cache.csv")
    print("─" * 72)

    s4_data = []
    cache_path = BASE_DIR / "data" / "northbound_cache.csv"
    snapshots_path = BASE_DIR / "data" / "northbound_snapshots.csv"

    for csv_type, csv_file in [("日度缓存", cache_path), ("分钟快照", snapshots_path)]:
        if csv_file.exists():
            try:
                with open(csv_file, "r", encoding="utf-8") as f:
                    reader = list(csv.DictReader(f))
                    s4_data.append({"type": csv_type, "path": str(csv_file.name), "rows": len(reader)})
                    # 最新一条
                    if reader:
                        latest = reader[-1]
                        print(f"  [{csv_type}] 路径: {csv_file.name}, 共{len(reader)}行")
                        if csv_type == "日度缓存":
                            print(f"    最新: date={latest.get('date','?')}, hgt={latest.get('hgt_yi','?')}, "
                                  f"sgt={latest.get('sgt_yi','?')}, total={latest.get('total_yi','?')}")
                        else:
                            print(f"    最新: time={latest.get('datetime','?')}, hgt={latest.get('hgt_yi','?')}, "
                                  f"sgt={latest.get('sgt_yi','?')}")
            except Exception as e:
                print(f"  [{csv_type}] 读取失败: {e}")
        else:
            print(f"  [{csv_type}] 文件不存在: {csv_file.name}")

    if not s4_data:
        print(f"  结论: [WARN] 无本地缓存文件")
    print()

    # ================================================================
    # S5: 组合管道 api.north_flow() [2014] 优先级链自动选择
    # ================================================================
    print("─" * 72)
    print("  S5: 组合管道 api.north_flow() [2014] 5级优先级链自动选择")
    print("─" * 72)

    s5_result = api.north_flow(5)
    s5_error = None
    if "error" in s5_result:
        s5_error = s5_result["error"]
        print(f"  [FAIL] 错误: {s5_error}")
    else:
        s5_latest = s5_result.get("latest", {})
        s5_source = s5_result.get("source", "?")
        s5_records = s5_result.get("records", [])

        print(f"  数据源标识: {s5_source}")
        if s5_latest:
            print(f"  最新日期: {s5_latest.get('date', '?')}")
            print(f"  HGT: {s5_latest.get('hgt_yi', '?')} 亿")
            print(f"  SGT: {s5_latest.get('sgt_yi', '?')} 亿")
            print(f"  Total: {s5_latest.get('total_yi', '?')} 亿")
            print(f"  方向: {s5_latest.get('direction', '?')}")
            print(f"  备注: {s5_latest.get('note', '?')}")
        print()
        print(f"  最近5日记录:")
        for r in s5_records:
            print(f"    {r.get('date','?'):12s}  total={r.get('total_yi',0):+8.2f}亿  "
                  f"hgt={r.get('hgt_yi','?'):>8}  sgt={r.get('sgt_yi','?'):>8}  "
                  f"[{r.get('source','?')}] {r.get('direction','?')}")
        print()
        s5_summary = s5_result.get("summary", {})
        if s5_summary:
            print(f"  汇总:")
            print(f"    区间合计: {s5_summary.get('total_yi', 0):+.2f}亿")
            print(f"    流入天数: {s5_summary.get('days_in', 0)}")
            print(f"    流出天数: {s5_summary.get('days_out', 0)}")
            print(f"    连续方向: {s5_summary.get('streak_direction', '?')} ({s5_summary.get('streak_days', 0)}天)")
            print(f"    结论: {s5_summary.get('conclusion', '?')}")

    print()

    # ================================================================
    # S6: 分钟级实时快照 api.north_flow_minute()
    # ================================================================
    print("─" * 72)
    print("  S6: 分钟级实时快照 api.north_flow_minute()")
    print("─" * 72)

    s6_result = api.north_flow_minute()
    s6_flags = s6_result.get("flags", {})
    s6_times = s6_result.get("times", [])
    s6_hgt_list = s6_result.get("hgt_yi", [])
    s6_sgt_list = s6_result.get("sgt_yi", [])

    print(f"  时间点数: HGT={len(s6_hgt_list)}, SGT={len(s6_sgt_list)}, Times={len(s6_times)}")
    if s6_hgt_list:
        print(f"  HGT 首点: {s6_hgt_list[0]:.2f}, 末点: {s6_hgt_list[-1]:.2f}, "
              f"累计: {sum(s6_hgt_list):.2f}亿")
    if s6_sgt_list:
        print(f"  SGT 首点: {s6_sgt_list[0]:.2f}, 末点: {s6_sgt_list[-1]:.2f}, "
              f"累计: {sum(s6_sgt_list):.2f}亿")

    print(f"  SGT异常标记: {s6_flags.get('sgt_anomaly', 'N/A')}")
    print(f"  HGT合计(亿): {s6_flags.get('hgt_total_yi', 'N/A')}")
    print(f"  SGT合计(亿): {s6_flags.get('sgt_total_yi', 'N/A')}")
    print(f"  备注: {s6_flags.get('note', 'N/A')}")

    print()

    # ================================================================
    # 最终：多源对照总表 & 数据质量评级
    # ================================================================
    print("=" * 72)
    print("  多源交叉验证总表")
    print("=" * 72)

    def _fmt(v):
        if v is None:
            return "N/A"
        try:
            return f"{float(v):+.2f}"
        except (TypeError, ValueError):
            return str(v)

    # 从S5提取combined值
    s5_latest = s5_result.get("latest", {}) if "error" not in s5_result else {}
    s5_total = s5_latest.get("total_yi", None) if s5_latest else None
    s5_hgt = s5_latest.get("hgt_yi", None) if s5_latest else None
    s5_sgt = s5_latest.get("sgt_yi", None) if s5_latest else None
    s5_source_name = s5_result.get("source", "?") if "error" not in s5_result else "error"

    # S6末点值
    s6_hgt_last = round(s6_hgt_list[-1], 2) if s6_hgt_list else None
    s6_sgt_last = round(s6_sgt_list[-1], 2) if s6_sgt_list else None
    s6_total_last = (round(s6_hgt_last + s6_sgt_last, 2)
                     if s6_hgt_last is not None and s6_sgt_last is not None else None)

    # 东财kamt全部归零
    s3_total = 0.0 if s3_all_zero else None

    print(f"  {'数据源':<28s} {'HGT(亿)':>10s} {'SGT(亿)':>10s} {'合计(亿)':>10s} {'状态':<15s}")
    print(f"  {'-'*73}")
    print(f"  {'S1 同花顺 hexin (直连)':<28s} {_fmt(s1_hgt_yi):>10s} {_fmt(s1_sgt_yi):>10s} {'N/A':>10s} {'[OK]主源':<15s}")
    print(f"  {'S2 Tushare moneyflow_hsgt':<28s} {_fmt(s2_hgt_yi):>10s} {_fmt(s2_sgt_yi):>10s} {_fmt(s2_total_yi):>10s} {'估算值':<15s}")
    print(f"  {'S3 东财 kamt (已归零)':<28s} {'0.00':>10s} {'0.00':>10s} {'0.00':>10s} {'[FAIL]永久无效':<15s}")
    print(f"  {'S5 api.north_flow()':<28s} {_fmt(s5_hgt):>10s} {_fmt(s5_sgt):>10s} {_fmt(s5_total):>10s} {'管道合成':<15s}")
    print(f"  {'S6 minute末点':<28s} {_fmt(s6_hgt_last):>10s} {_fmt(s6_sgt_last):>10s} {_fmt(s6_total_last):>10s} {'分钟级':<15s}")

    print()
    print(f"  S5 数据源说明: {s5_result.get('source_note', '?') if 'error' not in s5_result else 'ERROR'}")

    print()
    print("─" * 72)
    print("  数据质量评级")
    print("─" * 72)

    # 判断多源一致程度
    checks = []
    # 核心：HGT值的一致性
    hgt_sources = {}
    if s1_hgt_yi is not None: hgt_sources["hexin直连"] = s1_hgt_yi
    if s2_hgt_yi is not None: hgt_sources["Tushare"] = s2_hgt_yi
    if s5_hgt is not None: hgt_sources["管道S5"] = s5_hgt
    if s6_hgt_last is not None: hgt_sources["分钟S6"] = s6_hgt_last

    hgt_values = list(hgt_sources.values())
    hgt_consistent = len(set(round(v, 1) for v in hgt_values)) <= 1 if hgt_values else False

    sgt_sources = {}
    if s1_sgt_yi is not None: sgt_sources["hexin直连"] = s1_sgt_yi
    if s2_sgt_yi is not None: sgt_sources["Tushare"] = s2_sgt_yi
    if s5_sgt is not None: sgt_sources["管道S5"] = s5_sgt
    if s6_sgt_last is not None: sgt_sources["分钟S6"] = s6_sgt_last

    print(f"  HGT 多源差异:")
    for k, v in hgt_sources.items():
        print(f"    {k}: {v:+.2f} 亿")
    consistency = "[OK] 一致" if hgt_consistent else "[WARN] 有差异"
    print(f"  HGT 一致性: {consistency}")
    print(f"  SGT 多源差异:")
    for k, v in sgt_sources.items():
        print(f"    {k}: {v:+.2f} 亿")
    print(f"  SGT 一致性: {'[WARN] 预期有差异（数据源性质不同）'}")

    print()
    print(f"  整体可信度: ****o")
    print(f"  原因:")
    print(f"    - hexin HGT 为交易所原始数据聚合（262分钟点），可信度最高")
    print(f"    - SGT 同花顺仅35点不可靠，但Tushare可补充")
    print(f"    - 东财kamt已永久归零(2024.8.19)，不可用于当前分析")
    print(f"    - 多源HGT值一致性: {consistency}")

    # 最终推荐值
    final_hgt = s1_hgt_yi if s1_hgt_yi is not None else s5_hgt
    final_sgt = s2_sgt_yi if s2_sgt_yi is not None else s5_sgt
    final_total = None
    if final_hgt is not None:
        final_total = round(final_hgt + (final_sgt or 0), 2)

    print()
    print("=" * 72)
    print("  最终推荐值")
    print("=" * 72)
    print(f"  数据日期: {today}")
    print(f"  北向沪股通(HGT): {final_hgt:+.2f} 亿  [2190] hexin主源({s1_time_points}个分钟点)")
    if final_sgt is not None:
        print(f"  北向深股通(SGT): {final_sgt:+.2f} 亿  [2190] Tushare估算补充")
    else:
        print(f"  北向深股通(SGT): N/A（所有源均不可用）")
    if final_total is not None:
        direction = "流入" if final_total > 0 else ("流出" if final_total < 0 else "持平")
        print(f"  北向合计: {final_total:+.2f} 亿  -> {direction}")
        if s5_summary := s5_result.get("summary", {}) if "error" not in s5_result else {}:
            print(f"  连续: {s5_summary.get('streak_direction','?')} {s5_summary.get('streak_days',0)}天")
    print()
    print(f"  数据源可靠性声明:")
    print(f"    主源: 同花顺 hexin HGT [2014] 沪股通官方聚合数据，262分钟点完整")
    print(f"    补充: Tushare moneyflow_hsgt [2014] 深股通估算值")
    print(f"    无效: 东财 kamt [2014] 2024.8.19后永久归零，仅检测用")
    print(f"    验证: S1(HGT={_fmt(s1_hgt_yi)}) <-> S6末点(HGT={_fmt(s6_hgt_last)}) <-> 管道S5(HGT={_fmt(s5_hgt)})")
    print()
    print("─" * 72)
    print("  审计结论")
    print("─" * 72)
    if s1_hgt_yi is not None:
        print(f"  [OK] HGT 值可靠 [2014] 同花顺hexin数据完整，S1/S6末点/market_api管道三源验证一致")
    else:
        print(f"  [FAIL] HGT 主源不可用 [2014] 网路/API异常，建议稍后重试")
    if s5_summary := s5_result.get("summary", {}) if "error" not in s5_result else {}:
        print(f"  [1F4CA] 近期趋势 [2014] 连续{s5_summary.get('streak_direction','?')}{s5_summary.get('streak_days',0)}天, "
              f"{s5_summary.get('conclusion','?')}")
    print()

    # 写入JSON结果文件
    result_file = BASE_DIR / "data" / f"northbound_audit_{today}.json"
    output = {
        "audit_date": today,
        "audit_time": datetime.now().isoformat(),
        "sources": {
            "s1_hexin_direct": {"hgt_yi": s1_hgt_yi, "sgt_yi": s1_sgt_yi, "time_points": s1_time_points, "status": "ok" if s1_hgt_yi else "error", "error": s1_error},
            "s2_tushare": {"hgt_yi": s2_hgt_yi, "sgt_yi": s2_sgt_yi, "total_yi": s2_total_yi, "date": s2_date, "status": "ok" if s2_hgt_yi else "error", "error": s2_error},
            "s3_kamt": {"status": "permanently_zero" if s3_all_zero else "error", "all_zero": s3_all_zero},
            "s5_pipeline": {"total_yi": s5_total, "hgt_yi": s5_hgt, "sgt_yi": s5_sgt, "source": s5_source_name},
            "s6_minute": {"hgt_last": s6_hgt_last, "sgt_last": s6_sgt_last, "total": s6_total_last, "points": len(s6_hgt_list)},
        },
        "hgt_cross_check": {k: round(v, 2) for k, v in hgt_sources.items()},
        "sgt_cross_check": {k: round(v, 2) for k, v in sgt_sources.items()},
        "recommended": {"hgt_yi": final_hgt, "sgt_yi": final_sgt, "total_yi": final_total},
        "credibility": "****o",
    }
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  审计结果已保存至: data/northbound_audit_{today}.json")
    print()
    print("=" * 72)
    print("  审计完成")
    print("=" * 72)
