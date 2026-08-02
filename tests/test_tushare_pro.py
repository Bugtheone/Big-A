#!/usr/bin/env python3
"""
Tushare Pro 全量接口可用性测试（已清理无效接口）。
"""

from __future__ import annotations
import io, os, sys, time
from datetime import datetime

PASS, FAIL, SKIP = 0, 0, 0
results = []
TEST_CODE = "600519.SH"
TEST_DATE = datetime.now().strftime("%Y%m%d")
SLEEP = 0.35


def run_case(name, fn, **kw):
    global PASS, FAIL, SKIP
    pad = name.ljust(30)
    try:
        data = fn(**kw)
        if isinstance(data, dict):
            cnt = data.get("count", len(data.get("data", [])))
        elif isinstance(data, list):
            cnt = len(data)
        else:
            cnt = "?"
        if cnt is not None and (isinstance(cnt, int) and cnt > 0):
            print(f"  [PASS] {pad} → {cnt} 条")
            PASS += 1
            results.append(f"+ {name}: {cnt}条")
        elif isinstance(cnt, int) and cnt == 0:
            print(f"  [SKIP] {pad} → 0 条（可能非交易日）")
            SKIP += 1
            results.append(f"? {name}: 0条")
        else:
            print(f"  [SKIP] {pad} → {cnt}")
            SKIP += 1
        time.sleep(SLEEP)
    except Exception as e:
        msg = str(e)[:60]
        print(f"  [FAIL] {pad} → {msg}")
        FAIL += 1
        results.append(f"- {name}: {msg}")
        time.sleep(SLEEP)


if __name__ == "__main__":
    # 仓库根目录加入 sys.path，使脚本可直接运行（python tests/test_tushare_pro.py）
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts.tushare_pro_data import *

    # 仅在作为脚本运行时替换 stdout（避免模块级副作用破坏 import 方/pytest 捕获）
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print(f"Tushare Pro 有效接口测试 — {TEST_DATE}\n{'='*60}")

    # === I. 行情 ===
    print("\n【I. 行情】")
    run_case("daily", ts_daily, trade_date=TEST_DATE)
    run_case("weekly", ts_weekly, ts_code=TEST_CODE)
    run_case("monthly", ts_monthly, ts_code=TEST_CODE)
    run_case("adj_factor", ts_adj_factor, trade_date=TEST_DATE)
    run_case("suspend", ts_suspend, suspend_date=TEST_DATE)

    # === II. 基本面 ===
    print("\n【II. 基本面】")
    run_case("daily_basic", ts_daily_basic, ts_code=TEST_CODE)
    run_case("income", ts_income, ts_code=TEST_CODE)
    run_case("balancesheet", ts_balancesheet, ts_code=TEST_CODE)
    run_case("cashflow", ts_cashflow, ts_code=TEST_CODE)
    run_case("forecast", ts_forecast, ts_code=TEST_CODE)
    run_case("dividend", ts_dividend, ts_code=TEST_CODE)
    run_case("stk_holdernumber", ts_stk_holdernumber, ts_code=TEST_CODE)
    run_case("disclosure_date", ts_disclosure_date, ts_code=TEST_CODE)

    # === III. 融资融券 ===
    print("\n【III. 融资融券】")
    run_case("margin(全市场)", ts_margin)
    run_case("margin_detail", ts_margin_detail, ts_code=TEST_CODE)

    # === IV. 股东 ===
    print("\n【IV. 股东】")
    run_case("top10_holders", ts_top10_holders, ts_code=TEST_CODE)
    run_case("top10_floatholders", ts_top10_floatholders, ts_code=TEST_CODE)

    # === V. 交易信号 ===
    print("\n【V. 交易信号】")
    run_case("moneyflow", ts_moneyflow, ts_code=TEST_CODE)
    run_case("daily_info", ts_daily_info, trade_date=TEST_DATE)

    # === VI. 公司信息 ===
    print("\n【VI. 公司信息】")
    run_case("stock_company", ts_stock_company, ts_code=TEST_CODE)
    run_case("namechange", ts_namechange, ts_code=TEST_CODE)

    # === VII. 指数 ===
    print("\n【VII. 指数】")
    run_case("index_weekly", ts_index_weekly, ts_code="000001.SH")
    run_case("index_monthly", ts_index_monthly, ts_code="000001.SH")
    run_case("index_dailybasic", ts_index_dailybasic, ts_code="000001.SH")

    # === VIII. 因子 ===
    print("\n【VIII. 因子】")
    run_case("stk_factor", ts_stk_factor, ts_code=TEST_CODE)
    run_case("stk_factor_pro", ts_stk_factor_pro, ts_code=TEST_CODE)

    # === IX. 基金 ===
    print("\n【IX. 基金】")
    run_case("fund_daily", ts_fund_daily, ts_code="510050.SH")

    # === X. 概念板块 ===
    print("\n【X. 概念板块】")
    run_case("ths_index", ts_ths_index)
    run_case("ths_daily", ts_ths_daily, ts_code="883001.TI")

    # === XI. 新闻 ===
    print("\n【XI. 新闻公告】")
    run_case("major_news", ts_major_news, ts_code=TEST_CODE)

    # === XII. 港股通 ===
    print("\n【XII. 港股通】")
    run_case("ggt_daily", ts_ggt_daily)

    # === 汇总 ===
    total = PASS + FAIL + SKIP
    print(f"\n{'='*60}")
    print(f"汇总: {total} 接口 | PASS={PASS} | SKIP={SKIP} | FAIL={FAIL}")
    if FAIL:
        print(f"\n失败接口:")
        for r in results:
            if r.startswith("-"):
                print(f"  {r}")
    print(f"\n详细:")
    for r in results:
        print(f"  {r}")
