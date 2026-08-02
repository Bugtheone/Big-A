# -*- coding: utf-8 -*-
"""a-stock-data V3.6.0 三大数据源连通性验证
验证 AI agent 实际调用链路是否真实可用：
  1) Tushare.pro  — gate.ts_index_daily / api.ts_daily_kline
  2) Westock      — _westock_helper.kline_last / sector_industry_ranking
  3) 问财 SkillHub — api.iwencai_query 自然语言选股
用法: python scripts/verify_v360_sources.py
"""
import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.market_api import api
from scripts.data_gate import gate

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_skill_version() -> str:
    """从 a-stock-data SKILL.md 读取版本号"""
    p = os.path.join(BASE, "a-stock-data-main", "SKILL.md")
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("version:"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "?"


def main():
    print("=" * 60)
    print(f"a-stock-data 版本: V{read_skill_version()}")
    print("=" * 60)

    # ---------- 1) Tushare.pro ----------
    print("\n[1] Tushare.pro")
    try:
        rows = gate.ts_index_daily(ts_code="000001.SH", start="20260730", end="20260731")
        if rows:
            last = rows[0]
            print(f"  PASS gate.ts_index_daily: 上证 {last.get('trade_date')} 收 {last.get('close')} "
                  f"涨跌幅 {last.get('pct_chg')}%")
        else:
            print("  FAIL gate.ts_index_daily: 空返回")
    except Exception as e:
        print(f"  FAIL gate.ts_index_daily: {e}")

    try:
        dk = api.ts_daily_kline(ts_code="000001.SZ", start="20260725", end="20260731")
        data = dk.get("data") or []
        if data:
            d0 = data[0]
            print(f"  PASS api.ts_daily_kline: 平安银行 {d0.get('trade_date')} 收 {d0.get('close')} "
                  f"共{len(data)}根日K (source={dk.get('source')})")
        else:
            print(f"  FAIL api.ts_daily_kline: 空 (msg={dk.get('message')})")
    except Exception as e:
        print(f"  FAIL api.ts_daily_kline: {e}")

    # ---------- 2) Westock ----------
    print("\n[2] Westock (腾讯自选股 CLI)")
    try:
        from scripts.utils._westock_helper import kline_last, sector_industry_ranking
        last = kline_last("sh000001")
        print(f"  PASS westock.kline_last: 上证指数(sh000001) 收盘 {last}")
        sectors = sector_industry_ranking()
        if sectors:
            top = sectors[0]
            print(f"  PASS westock.sector_industry_ranking: {len(sectors)}条, TOP1={top.get('name')} "
                  f"{top.get('changePct')}%")
        else:
            print("  FAIL westock.sector_industry_ranking: 空返回")
    except Exception as e:
        print(f"  FAIL westock: {e}")

    # ---------- 3) 问财 SkillHub ----------
    print("\n[3] 问财 SkillHub (iwencai OpenAPI)")
    try:
        r = api.iwencai_query("股息率大于6%的银行股", limit=5)
        if r.get("success"):
            items = r.get("data") or []
            print(f"  PASS api.iwencai_query: {len(items)}条命中 (msg={r.get('message')})")
            for it in items[:3]:
                print(f"    - {it.get('name', '?')} {it.get('code', '?')} 股息率 {it.get('dy_ratio', '?')}")
        else:
            print(f"  FAIL api.iwencai_query: success=False msg={r.get('message')}")
    except Exception as e:
        print(f"  FAIL api.iwencai_query: {e}")

    # ---------- 4) 附加: 腾讯行情主链路 (全链路兜底) ----------
    print("\n[4] 腾讯行情主链路 (附加)")
    try:
        snap = api.index_snapshot()
        sh = next((it for it in snap if it.get("code") == "sh000001"), {})
        print(f"  PASS api.index_snapshot: 上证 {sh.get('name')} {sh.get('price')} ({sh.get('change_pct')}%)")
    except Exception as e:
        print(f"  FAIL api.index_snapshot: {e}")

    print("\n" + "=" * 60)
    print("验证完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
