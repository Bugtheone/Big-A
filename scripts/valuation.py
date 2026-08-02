#!/usr/bin/env python3
"""估值公式层 — 前向PE + PE消化 + PEG + 完整估值 (SKILL.md 估值公式)"""
import math, json, requests
from datetime import datetime
from scripts.eastmoney_api import UA

def forward_pe(price: float, eps_forecast: float) -> float:
    """前向PE = 股价 / 未来一致预期EPS"""
    if eps_forecast <= 0: return float("inf")
    return price / eps_forecast

def pe_digestion(current_pe: float, cagr: float, target_pe: float = 30) -> float:
    """PE消化到目标PE需要的年数。target_pe 默认30x（A股成长股合理锚点）"""
    if current_pe <= target_pe: return 0.0
    if cagr <= 0: return float("inf")
    return math.log(current_pe / target_pe) / math.log(1 + cagr)

def calc_peg(pe: float, cagr: float) -> float:
    """PEG = 前向PE / (CAGR*100)。PEG<1=便宜, 1-1.5=合理, >1.5=贵"""
    if cagr <= 0: return float("inf")
    return pe / (cagr * 100)

def full_valuation(code: str) -> dict:
    """单票完整估值分析。返回 {price,mcap,pe_ttm,pb,pe_forward,peg,cagr,digestion_years,verdict}"""
    import urllib.request
    # 1. 腾讯行情
    prefix = "sh" if code.startswith(("6","9")) else ("bj" if code.startswith(("4","8","92")) else "sz")
    try:
        req = urllib.request.Request(f"https://qt.gtimg.cn/q={prefix}{code}")
        req.add_header("User-Agent","Mozilla/5.0")
        resp = urllib.request.urlopen(req, timeout=10)
        data = resp.read().decode("gbk")
        vals = data.split('"')[1].split("~")
        price = float(vals[3])
        mcap = float(vals[45])
        pe_ttm = float(vals[39]) if vals[39] else 0
        pb = float(vals[46]) if vals[46] else 0
    except Exception as e:
        return {"error": str(e), "code": code}

    # 2. 同花顺一致预期EPS
    from scripts.ths_api import ths_eps_forecast
    df = ths_eps_forecast(code)
    eps_cur = eps_next = None
    analyst_count = 0
    if df:
        # 按列名取「均值」=机构一致预期
        for row in df:
            if "均值" in str(row) or "平均值" in str(row):
                for k, v in row.items():
                    try:
                        eps_cur = float(v)
                        break
                    except (ValueError, TypeError): pass
            if eps_cur: break
        analyst_count = len(df)

    # 3. 计算
    if eps_cur and eps_cur > 0 and price:
        pe_forward = round(price / eps_cur, 2)
    else:
        pe_forward = None

    # 简化CAGR估算
    cagr = None
    if eps_next and eps_cur and eps_cur > 0:
        cagr = float(eps_next) / float(eps_cur) - 1

    peg = round(calc_peg(pe_forward or pe_ttm, cagr or 0.01), 2) if pe_forward else None
    digestion = round(pe_digestion(pe_forward or pe_ttm, cagr or 0.01), 1) if (pe_forward or pe_ttm) else None

    # 4. 判定
    if peg is None:
        verdict = "数据不足"
    elif peg < 1:
        verdict = "便宜(PEG<1)"
    elif peg < 1.5:
        verdict = "合理(PEG 1-1.5)"
    else:
        verdict = "偏贵(PEG>1.5)"

    return {"code": code, "price": price, "mcap_yi": round(mcap, 2),
            "pe_ttm": pe_ttm, "pb": pb, "pe_forward": pe_forward, "peg": peg,
            "cagr": round(cagr, 3) if cagr else None,
            "digestion_years": digestion, "analyst_count": analyst_count, "verdict": verdict}
