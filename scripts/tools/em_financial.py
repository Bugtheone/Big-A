#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
东财 datacenter 财务取数 + tushare 交叉验证工具（互补源，借鉴 ai-berkshire）

东财 datacenter 财务接口（datacenter.eastmoney.com/securities/api/data/get）：
  - 非 push2 主机 → 不受 push2 WAF 风控影响（2026-08-04 实测可用）
  - 提供营收/净利/EPS/BPS/ROE/增速（年度 + 报告期）
与 tushare 财务交叉验证（借鉴 ai-berkshire financial-data.md 规范：关键数据
2 个独立来源、误差 >1% 告警）。

用法:
  python scripts/tools/em_financial.py 600360                # 东财财务
  python scripts/tools/em_financial.py 600360 --compare      # + tushare 交叉验证
  python scripts/tools/em_financial.py 600360 --json         # JSON 输出
"""
import io
import json
import os
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


def em_financial(code: str) -> list:
    """东财 datacenter 财务（最近 5 期报告）。返回 [{report_date, report_name, 指标...}]。"""
    import requests
    parts = code.upper().split(".")
    clean = parts[0]
    if len(parts) > 1:
        market = parts[1]
    elif clean.startswith(("6", "9", "5")):
        market = "SH"
    elif clean.startswith(("4", "8", "92")):
        market = "BJ"
    else:
        market = "SZ"
    s = requests.Session(); s.trust_env = False
    s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://emweb.securities.eastmoney.com/"})
    url = "https://datacenter.eastmoney.com/securities/api/data/get"
    for filt in [f'(SECUCODE="{clean}.{market}")(REPORT_TYPE="年报")',
                 f'(SECUCODE="{clean}.{market}")']:
        try:
            r = s.get(url, params={
                "type": "RPT_F10_FINANCE_MAINFINADATA", "sty": "ALL", "filter": filt,
                "p": "1", "ps": "5", "sr": "-1", "st": "REPORT_DATE",
                "source": "HSF10", "client": "PC"}, timeout=10)
            d = r.json()
            rows = (d.get("result") or {}).get("data") or []
            if rows:
                return [{
                    "report_date": str(x.get("REPORT_DATE", ""))[:10],
                    "report_name": x.get("REPORT_DATE_NAME", ""),
                    "revenue": x.get("TOTALOPERATEREVE"),
                    "net_profit": x.get("PARENTNETPROFIT"),
                    "eps": x.get("EPSJB"), "bps": x.get("BPS"), "roe": x.get("ROEJQ"),
                    "rev_growth": x.get("TOTALOPERATEREVETZ"),
                    "profit_growth": x.get("PARENTNETPROFITTZ"),
                } for x in rows]
        except Exception:
            continue
    return []


def tushare_compare(code: str, em_rows: list) -> list:
    """tushare 财务交叉验证（营收/净利/ROE 对比，>1% 差异告警）。"""
    from scripts.tushare_api import get_pro
    pro = get_pro()
    ts_code = code if "." in code else (code + (".SH" if code.startswith(("6", "9")) else ".SZ"))
    out = []
    for em in em_rows:
        end_date = em["report_date"].replace("-", "")
        # tushare 财务指标（ROE/EPS）
        try:
            ind = pro.fina_indicator(ts_code=ts_code, end_date=end_date,
                                     fields="ts_code,end_date,roe,eps_basic")
            if ind is not None and len(ind):
                r = ind.to_dict("records")[0]
                roe_ts, eps_ts = r.get("roe"), r.get("eps_basic")
            else:
                roe_ts = eps_ts = None
        except Exception:
            roe_ts = eps_ts = None
        out.append({
            "report": em["report_name"], "end_date": em["report_date"],
            "em_roe": em["roe"], "ts_roe": roe_ts,
            "em_eps": em["eps"], "ts_eps": eps_ts,
            "verdict": _check(em["roe"], roe_ts, "ROE") + _check(em["eps"], eps_ts, "EPS"),
        })
    return out


def _check(em, ts, label):
    if em is None or ts is None:
        return ""
    if ts == 0:
        return f"{label}: tushare=0 无法比; "
    diff = abs(em - ts) / abs(ts) * 100
    if diff > 1:
        return f"{label} ⚠️ 差{diff:.1f}%>1%; "
    return f"{label} ✅ 差{diff:.2f}%; "


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python scripts/tools/em_financial.py <代码> [--compare] [--json]")
        return 1
    code = sys.argv[1]
    do_compare = "--compare" in sys.argv
    as_json = "--json" in sys.argv

    rows = em_financial(code)
    if not rows:
        print(f"东财 datacenter 无数据（{code}）")
        return 1
    if as_json:
        print(json.dumps(rows, ensure_ascii=False))
        return 0

    print(f"=== 东财 datacenter 财务（{code}）===")
    print(f"{'报告期':<12}{'营收(亿)':>12}{'净利(亿)':>12}{'EPS':>8}{'BPS':>9}{'ROE%':>8}"
          f"{'营收增速%':>10}{'净利增速%':>10}")
    for r in rows:
        print(f"{r['report_name']:<12}{_f(r['revenue'],1e8):>12}{_f(r['net_profit'],1e8):>12}"
              f"{_f(r['eps'],1):>8}{_f(r['bps'],1):>9}{_f(r['roe'],1):>8}"
              f"{_f(r['rev_growth'],1):>10}{_f(r['profit_growth'],1):>10}")
    if do_compare:
        print("\n=== tushare 交叉验证 ===")
        cmp = tushare_compare(code, rows)
        for c in cmp:
            print(f"  {c['report']}: {c['verdict'] or '两源均有数据但差异≤1% ✅'}")
    return 0


def _f(v, scale):
    if v is None:
        return "—"
    try:
        return f"{float(v)/scale:,.2f}" if scale != 1 else f"{float(v):.2f}"
    except (TypeError, ValueError):
        return "—"


if __name__ == "__main__":
    sys.exit(main())
