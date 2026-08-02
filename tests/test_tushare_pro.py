#!/usr/bin/env python3
"""
Tushare Pro 全量接口可用性测试（已清理无效接口）。
"""

from __future__ import annotations
import io, sys, time
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"c:\Users\PC-One\Desktop\整理后\股票相关\零散临时\1112345")

PASS, FAIL, SKIP = 0, 0, 0
results = []
TEST_CODE = "600519.SH"
TEST_DATE = datetime.now().strftime("%Y%m%d")
SLEEP = 0.35


def test(name, fn, **kw):
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
    from scripts.tushare_pro_data import *

    print(f"Tushare Pro 有效接口测试 — {TEST_DATE}\n{'='*60}")

    # === I. 行情 ===
    print("\n【I. 行情】")
    test("daily", ts_daily, trade_date=TEST_DATE)
    test("weekly", ts_weekly, ts_code=TEST_CODE)
    test("monthly", ts_monthly, ts_code=TEST_CODE)
    test("adj_factor", ts_adj_factor, trade_date=TEST_DATE)
    test("suspend", ts_suspend, suspend_date=TEST_DATE)

    # === II. 基本面 ===
    print("\n【II. 基本面】")
    test("daily_basic", ts_daily_basic, ts_code=TEST_CODE)
    test("income", ts_income, ts_code=TEST_CODE)
    test("balancesheet", ts_balancesheet, ts_code=TEST_CODE)
    test("cashflow", ts_cashflow, ts_code=TEST_CODE)
    test("forecast", ts_forecast, ts_code=TEST_CODE)
    test("dividend", ts_dividend, ts_code=TEST_CODE)
    test("stk_holdernumber", ts_stk_holdernumber, ts_code=TEST_CODE)
    test("disclosure_date", ts_disclosure_date, ts_code=TEST_CODE)

    # === III. 融资融券 ===
    print("\n【III. 融资融券】")
    test("margin(全市场)", ts_margin)
    test("margin_detail", ts_margin_detail, ts_code=TEST_CODE)

    # === IV. 股东 ===
    print("\n【IV. 股东】")
    test("top10_holders", ts_top10_holders, ts_code=TEST_CODE)
    test("top10_floatholders", ts_top10_floatholders, ts_code=TEST_CODE)

    # === V. 交易信号 ===
    print("\n【V. 交易信号】")
    test("moneyflow", ts_moneyflow, ts_code=TEST_CODE)
    test("daily_info", ts_daily_info, trade_date=TEST_DATE)

    # === VI. 公司信息 ===
    print("\n【VI. 公司信息】")
    test("stock_company", ts_stock_company, ts_code=TEST_CODE)
    test("namechange", ts_namechange, ts_code=TEST_CODE)

    # === VII. 指数 ===
    print("\n【VII. 指数】")
    test("index_weekly", ts_index_weekly, ts_code="000001.SH")
    test("index_monthly", ts_index_monthly, ts_code="000001.SH")
    test("index_dailybasic", ts_index_dailybasic, ts_code="000001.SH")

    # === VIII. 因子 ===
    print("\n【VIII. 因子】")
    test("stk_factor", ts_stk_factor, ts_code=TEST_CODE)
    test("stk_factor_pro", ts_stk_factor_pro, ts_code=TEST_CODE)

    # === IX. 基金 ===
    print("\n【IX. 基金】")
    test("fund_daily", ts_fund_daily, ts_code="510050.SH")

    # === X. 概念板块 ===
    print("\n【X. 概念板块】")
    test("ths_index", ts_ths_index)
    test("ths_daily", ts_ths_daily, ts_code="883001.TI")

    # === XI. 新闻 ===
    print("\n【XI. 新闻公告】")
    test("major_news", ts_major_news, ts_code=TEST_CODE)

    # === XII. 港股通 ===
    print("\n【XII. 港股通】")
    test("ggt_daily", ts_ggt_daily)

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
