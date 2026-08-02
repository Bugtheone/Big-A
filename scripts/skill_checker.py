#!/usr/bin/env python3
"""
SKILL.md 覆盖检查 & 自动融入引擎 V1.0

功能：
  1. 解析 SKILL.md，提取所有端点定义（§编号、函数名、描述、数据源、Layer）
  2. 扫描项目代码（data_gate.py / market_api.py / 各源模块），识别已实现方法
  3. 生成覆盖报告：哪些已融入、哪些缺失
  4. 为缺失端点自动生成融入计划，可半自动执行

用法：
  python scripts/skill_checker.py              # 摘要报告
  python scripts/skill_checker.py --detail     # 详细报告
  python scripts/skill_checker.py --gaps       # 只看缺失 + 融入计划
  python scripts/skill_checker.py --json       # JSON 输出
  python scripts/skill_checker.py --integrate  # 自动融入缺失端点

API 调用:
  from scripts.skill_checker import skill_check
  result = skill_check()
  result = skill_check(mode="gaps")  # 查缺失
  result = skill_check(auto_integrate=True)  # 自动融入
"""

import os
import re
import json
import sys
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
SKILL_MD_PATH = BASE_DIR / "a-stock-data-main" / "SKILL.md"
SCRIPTS_DIR = BASE_DIR / "scripts"

# ── 正则 ──
_RE_ROUTE = re.compile(r'\|\s*(§?\s*[\d.]+)\s*\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|')
_RE_FUNC_DEF = re.compile(r'^def\s+(\w+)\s*\(')

LAYER_NAMES = {
    "1": "行情层", "2": "研报层", "3": "信号层", "4": "资金面/筹码层",
    "5": "新闻层", "6": "基础数据层", "7": "公告层", "8": "打板层",
    "9": "ETF期权层", "10": "舆情互动层", "backup": "备用源", "valuation": "估值公式",
}

# ── 函数名别名映射（SKILL.md 名称 → 项目实际名称）──
NAME_ALIAS = {
    "tdx_client": "tdx_bars", "bars": "tdx_bars", "quotes": "tdx_quotes",
    "transaction": "tdx_quotes", "tencent_quote": "get_tencent",
    "iwencai_search": "iwencai_search",
    "iwencai_query": "iwencai_query", "ths_eps_forecast": "ths_eps_forecast",
    "ths_hot_reason": "ths_hot_reason",
    "eastmoney_concept_blocks": "em_concept_blocks",
    "eastmoney_fund_flow_minute": "em_fund_flow_minute",
    "dragon_tiger_board": "em_dragon_tiger_board",
    "daily_dragon_tiger": "em_daily_dragon_tiger", "lockup_expiry": "em_lockup_expiry",
    "industry_comparison": "em_board_summary", "board_fund_flow": "em_board_fund_flow",
    "margin_trading": "em_margin_trading", "block_trade": "em_block_trade",
    "holder_num_change": "em_holder_num", "dividend_history": "em_dividend",
    "stock_fund_flow_120d": "em_fund_flow_120d",
    "eastmoney_stock_news": "em_stock_news", "cls_telegraph": "cls_telegraph",
    "eastmoney_global_news": "em_global_news", "eastmoney_stock_info": "em_stock_info",
    "sina_financial_report": "sina_financial_report",
    "cninfo_announcements": "cninfo_announcements",
    "em_zt_pool": "em_zt_pool", "em_zb_pool": "em_zb_pool",
    "em_dt_pool": "em_dt_pool", "em_yzt_pool": "em_yzt_pool",
    "ths_limit_up_pool": "ths_limit_up_pool", "limit_up_sentiment": "limit_up_sentiment",
    "sina_option_codes": "sina_option_codes", "sina_option_tquote": "sina_option_tquote",
    "sina_option_greeks": "sina_option_greeks", "cninfo_irm": "cninfo_irm",
    "ths_hot_list": "ths_hot_list", "em_hot_rank": "em_hot_rank",
    "em_hot_concept": "em_hot_concept",
    "client.finance": "tdx_finance", "client.F10": "tdx_finance",
    "hsgt_realtime": "north_flow_minute",
    "baidu_kline_with_ma": "baidu_kline_ma",
    "eastmoney_reports": "eastmoney_reports", "download_pdf": "download_pdf",
    "eastmoney_industry_reports": "industry_reports",
    "dragon_tiger_backup": None, "fund_flow_backup": None, "announcements_backup": None,
    "forward_pe": "forward_pe", "pe_digestion": "pe_digestion",
    "calc_peg": "calc_peg", "full_valuation": "full_valuation",
}

# ── 模块 → 端点映射 ──
MODULE_MAP = {
    "mootdx_api.py": {"sec": "1.1", "gate": ["tdx_bars", "tdx_quotes", "tdx_finance"],
                      "api": ["tdx_bars", "tdx_quotes", "tdx_finance"]},
    "tencent_api.py": {"sec": "1.2", "gate": ["get_tencent"],
                       "api": ["stock_realtime", "index_snapshot", "trading_status",
                              "kline", "kline_batch", "turnover", "full_snapshot"]},
    "eastmoney_api.py": {"sec": "1.3,2.1,3.4,3.7,3.8",
                         "gate": ["em_get", "em_datacenter", "eastmoney_datacenter",
                                  "em_board_fund_flow", "em_board_summary", "em_sectors",
                                  "em_baidu_kline_with_ma", "em_eastmoney_reports",
                                  "em_download_pdf", "em_industry_reports"],
                         "api": ["board_fund_flow", "board_summary", "sectors",
                                "baidu_kline_ma", "eastmoney_reports",
                                "download_pdf", "industry_reports"]},
    "eastmoney_signals.py": {"sec": "3.3,3.4,3.5,3.6,3.9",
                             "gate": ["em_dragon_tiger_board", "em_daily_dragon_tiger",
                                      "em_lockup_expiry", "em_fund_flow_minute",
                                      "em_concept_blocks", "em_hot_reason"],
                             "api": ["dragon_tiger", "lockup_expiry", "fund_flow_minute",
                                    "hot_reason", "concept_blocks"]},
    "eastmoney_fundamentals.py": {"sec": "4.1,4.2,4.3,4.4,4.5",
                                  "gate": ["em_margin_trading", "em_block_trade",
                                           "em_holder_num", "em_dividend", "em_fund_flow_120d"],
                                  "api": ["margin", "block_trade", "holder_num",
                                         "dividend", "fund_flow_120d"]},
    "eastmoney_news.py": {"sec": "5.1,5.3",
                          "gate": ["em_stock_news", "em_global_news"],
                          "api": ["stock_news", "global_news"]},
    "eastmoney_info.py": {"sec": "6.3,8.1,8.3,10.2",
                          "gate": ["em_stock_info", "em_zt_pool", "em_zb_pool",
                                   "em_dt_pool", "em_yzt_pool", "em_hot_rank", "em_hot_concept"],
                          "api": ["stock_info", "zt_pool", "zb_pool", "dt_pool",
                                 "hot_rank", "hot_concept", "hot_list",
                                 "limit_up_sentiment"]},
    "ths_api.py": {"sec": "2.2,3.1,3.2,10.2",
                   "gate": ["ths_eps_forecast", "ths_hot_reason", "ths_hot_list", "ths_limit_up_pool",
                            "ths_hsgt_realtime"],
                   "api": ["eps_forecast", "hot_reason_ths", "hot_list_ths", "limit_up_pool"]},
    "sina_api.py": {"sec": "6.4,9.1",
                    "gate": ["sina_financial_report", "sina_option_codes",
                             "sina_option_tquote", "sina_option_greeks"],
                    "api": ["financial_report", "option_codes", "option_tquote", "option_greeks"]},
    "cninfo_api.py": {"sec": "7.1,10.1",
                      "gate": ["cninfo_announcements", "cninfo_irm"],
                      "api": ["announcements", "irm"]},
    "valuation.py": {"sec": "估值",
                     "gate": ["forward_pe", "pe_digestion", "calc_peg", "full_valuation"],
                     "api": ["valuation", "forward_pe", "peg"]},
    "north_flow.py": {"sec": "3.2",
                      "gate": ["north_flow", "hexin_north_flow", "tushare_north_flow"],
                      "api": ["north_flow"]},
    "tushare_api.py": {"sec": "3.2", "gate": ["get_pro"], "api": []},
    "cls_telegraph.py": {"sec": "5.2", "gate": ["cls_telegraph"], "api": ["telegraph"]},
    "iwencai_openapi.py": {"sec": "2.3", "gate": [],
                           "api": ["iwencai_key_status", "iwencai_key_refresh",
                                   "iwencai_search", "iwencai_query"]},
}


def _find_skill_md() -> Path:
    """自动探测 SKILL.md 位置"""
    candidates = [
        SKILL_MD_PATH,
        BASE_DIR / "skills" / "a-stock-data" / "SKILL.md",
        BASE_DIR / "skills" / "a-stock-data-main" / "SKILL.md",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(f"SKILL.md not found. Searched: {candidates}")


def _sort_key(sec: str) -> tuple:
    parts = sec.split(".")
    try:
        if sec.startswith("备用"): return (99, 0)
        if sec.startswith("估值"): return (100, 0)
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    except (ValueError, IndexError):
        return (999, 0)


# ──────────────────────────────────────────────
# 1. 解析 SKILL.md
# ──────────────────────────────────────────────

def parse_skill_md(skill_path: Optional[Path] = None) -> dict:
    """解析 SKILL.md，提取端点注册表"""
    if skill_path is None:
        skill_path = _find_skill_md()
    text = skill_path.read_text(encoding="utf-8")

    ver = re.search(r'V(\d+\.\d+\.\d+)', text)
    version = ver.group(1) if ver else "unknown"

    # 解析路由表
    entries = []
    for m in _RE_ROUTE.finditer(text):
        sec = m.group(1).strip().replace("§", "").strip()
        funcs_raw = m.group(2).strip()
        desc = m.group(3).strip()
        source = m.group(4).strip()
        funcs = []
        for f in re.split(r'\s*/\s*', funcs_raw):
            f = re.sub(r'\(.*\)', '', f).replace('→', ' ').strip().strip('`')
            if f:
                funcs.append(f)
        entries.append({"section": sec, "funcs": funcs, "description": desc, "source": source})

    # 合并同 section + 分配 Layer
    merged = {}
    for e in entries:
        sec = e["section"]
        if sec in merged:
            ex = set(merged[sec]["funcs"])
            for f in e["funcs"]:
                if f not in ex:
                    merged[sec]["funcs"].append(f); ex.add(f)
        else:
            layer_key = sec.split(".")[0] if "." in sec else sec
            layer = LAYER_NAMES.get(layer_key, "其他")
            if sec.startswith("备用"): layer = "备用源"
            if sec.startswith("估值"): layer = "估值公式"
            merged[sec] = {**e, "layer": layer}

    final = sorted(merged.values(), key=lambda x: _sort_key(x["section"]))
    return {
        "version": version, "skill_path": str(skill_path),
        "total_endpoints": len(final), "endpoints": final,
    }


# ──────────────────────────────────────────────
# 2. 扫描项目覆盖
# ──────────────────────────────────────────────

def scan_project(scripts_dir: Optional[Path] = None) -> dict:
    """扫描项目代码中已实现的方法"""
    if scripts_dir is None:
        scripts_dir = SCRIPTS_DIR
    modules = {}
    all_gate, all_api = set(), set()

    for py_file in sorted(scripts_dir.glob("*.py")):
        name = py_file.name
        if name.startswith("__") or name == "skill_checker.py":
            continue
        funcs = set()
        try:
            for line in py_file.read_text(encoding="utf-8").split("\n"):
                m = _RE_FUNC_DEF.match(line.strip())
                if m: funcs.add(m.group(1))
        except (OSError, UnicodeDecodeError):
            continue

        info = MODULE_MAP.get(name, {})
        gate_methods = set(info.get("gate", []))
        api_methods = set(info.get("api", []))
        all_gate |= gate_methods
        all_api |= api_methods

        modules[name] = {
            "funcs": sorted(funcs), "count": len(funcs),
            "mapped_sections": info.get("sec", ""),
            "gate_methods": sorted(gate_methods),
            "api_methods": sorted(api_methods),
        }

    return {
        "modules": modules, "gate_methods": sorted(all_gate),
        "api_methods": sorted(all_api),
        "total_gate": len(all_gate), "total_api": len(all_api),
        "total_modules": len(modules),
    }


# ──────────────────────────────────────────────
# 3. 差异对比
# ──────────────────────────────────────────────

def calculate_coverage(skill_reg: dict, proj_cov: dict) -> dict:
    """对比 SKILL.md 与项目实现，生成覆盖报告"""
    all_proj = set(proj_cov.get("gate_methods", [])) | set(proj_cov.get("api_methods", []))

    details, impl_count = [], 0
    for ep in skill_reg.get("endpoints", []):
        sec, skill_funcs = ep["section"], ep["funcs"]
        matched, missing = [], []
        for sf in skill_funcs:
            aliased = NAME_ALIAS.get(sf, sf)
            if aliased is None:
                missing.append(sf)
            elif aliased in all_proj:
                matched.append(aliased)
            elif sf in all_proj:
                matched.append(sf)
            else:
                found = any(sf.lower() in pf.lower() or pf.lower() in sf.lower()
                           for pf in all_proj)
                if found:
                    matched.append("(fuzzy)")
                else:
                    missing.append(sf)

        ok = len(missing) == 0 or (len(matched) > 0 and len(missing) <= 1)
        if ok and matched: impl_count += 1

        suggestion = None
        if missing:
            target = _suggest_module(sec, ep["source"], ep["layer"])
            suggestion = {"missing": missing, "target": target,
                          "action": f"在 {target} 中新增: {', '.join(missing)}"}

        details.append({
            "section": sec, "layer": ep["layer"], "skill_funcs": skill_funcs,
            "description": ep["description"], "source": ep["source"],
            "implemented": ok and len(matched) > 0,
            "matched": matched, "missing": missing, "suggestion": suggestion,
        })

    total = len(details)
    pct = round(impl_count / total * 100, 1) if total > 0 else 0

    # 项目独有方法
    all_skill_flat = {f for ep in skill_reg.get("endpoints", []) for f in ep["funcs"]}
    all_skill_flat.update(NAME_ALIAS.keys())
    all_skill_flat.update(v for v in NAME_ALIAS.values() if v)
    skip = {"get_pro", "em_get", "em_datacenter", "eastmoney_datacenter",
            "get_tencent", "get_eastmoney", "main", "dedupe"}
    only = [f for f in sorted(all_proj)
            if f not in all_skill_flat and not f.startswith("_") and f not in skip]

    return {
        "summary": {"total_in_skill": total, "implemented": impl_count,
                    "gaps": total - impl_count, "coverage_pct": pct,
                    "skill_version": skill_reg.get("version", "?"),
                    "total_gate": proj_cov["total_gate"],
                    "total_api": proj_cov["total_api"]},
        "details": details, "only_in_project": only,
    }


def _suggest_module(section: str, source: str, layer: str) -> str:
    """根据端点信息推荐目标模块"""
    src = source.lower()
    if "通达信" in source or "mootdx" in src: return "scripts/mootdx_api.py"
    if "腾讯" in source: return "scripts/tencent_api.py"
    if "东财" in source or "eastmoney" in src:
        if "信号" in layer or "龙虎榜" in source or "解禁" in source: return "scripts/eastmoney_signals.py"
        if "资金" in layer or "融资" in source or "大宗" in source or "分红" in source: return "scripts/eastmoney_fundamentals.py"
        if "新闻" in layer: return "scripts/eastmoney_news.py"
        return "scripts/eastmoney_api.py"
    if "同花顺" in source or "ths" in src: return "scripts/ths_api.py"
    if "新浪" in source: return "scripts/sina_api.py"
    if "巨潮" in source or "cninfo" in src: return "scripts/cninfo_api.py"
    if "财联社" in source: return "scripts/cls_telegraph.py"
    if "估值" in layer: return "scripts/valuation.py"
    return "scripts/eastmoney_api.py"


# ──────────────────────────────────────────────
# 4. 格式化输出
# ──────────────────────────────────────────────

def format_report(cov: dict, mode: str = "summary") -> str:
    """格式化覆盖报告"""
    if mode == "json":
        return json.dumps(cov, ensure_ascii=False, indent=2, default=str)

    s = cov["summary"]
    lines = [
        "=" * 64,
        f"  SKILL.md <-> 项目代码 覆盖报告  |  V{s.get('skill_version', '?')}",
        f"  Gate方法: {s['total_gate']}  |  API方法: {s['total_api']}  |  "
        f"模块: {len(cov.get('details', []))}",
        "=" * 64, "",
        f"  定义端点: {s['total_in_skill']:>3d}  |  已融入: {s['implemented']:>3d}  |  "
        f"缺失: {s['gaps']:>3d}  |  覆盖率: {s['coverage_pct']}%",
    ]

    if mode == "summary":
        gaps = [d for d in cov["details"] if not d["implemented"]]
        if gaps:
            lines.append(f"\n  缺失 ({len(gaps)}个):")
            for g in gaps:
                lines.append(f"    §{g['section']}  {', '.join(g['skill_funcs'])}  →  {g['description']}")
        lines.append(f"\n  python scripts/skill_checker.py --gaps  查看融入计划")
        return "\n".join(lines)

    if mode == "gaps":
        gaps = [d for d in cov["details"] if not d["implemented"]]
        if not gaps:
            return "\n".join(lines) + "\n\n✓ 所有端点已全部融入！"
        lines.append(f"\n── 缺失端点 ({len(gaps)}个) ──\n")
        for i, g in enumerate(gaps, 1):
            lines.append(f"  [{i}] §{g['section']} — {g['description']}")
            lines.append(f"      数据源: {g['source']}  |  Layer: {g['layer']}")
            lines.append(f"      缺失: {', '.join(g['missing'])}")
            if g["suggestion"]:
                lines.append(f"      → {g['suggestion']['action']}")
            if g["matched"]:
                lines.append(f"      已有: {', '.join(g['matched'])}")
            lines.append("")

        plan = gen_integration_plan(cov)
        lines.append(print_integration_plan(plan))
        return "\n".join(lines)

    # detail
    lines.append(f"\n{'§':<8} {'状态':<10} {'描述':<40} {'匹配'}")
    lines.append("-" * 64)
    for d in cov["details"]:
        st = "✓ 已融入" if d["implemented"] else "✗ 缺失"
        m = d.get("matched", [])
        lines.append(f"§{d['section']:<7} {st:<10} {d['description'][:38]:<40} {', '.join(m)[:30]}")
        if not d["implemented"] and d.get("missing"):
            lines.append(f"  {'':>8} 缺失: {', '.join(d['missing'])}")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 5. 融入计划
# ──────────────────────────────────────────────

def gen_integration_plan(cov: dict) -> list:
    """为缺失端点生成融入计划"""
    plan = []
    for i, d in enumerate(cov.get("details", []), 1):
        if d["implemented"] or not d.get("suggestion"):
            continue
        plan.append({
            "step": len(plan) + 1, "section": d["section"],
            "description": d["description"], "source": d["source"],
            "target_file": d["suggestion"]["target"],
            "action": d["suggestion"]["action"],
            "missing_funcs": d["missing"],
        })
    return plan


def print_integration_plan(plan: list) -> str:
    if not plan: return "✓ 无需融入。"
    lines = ["── 融入计划 ──", ""]
    for p in plan:
        lines.append(f"  Step {p['step']}: §{p['section']} → {p['target_file']}")
        lines.append(f"    {p['action']}")
        lines.append(f"    参考: 查看 SKILL.md §{p['section']} 代码段")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 6. 主入口
# ──────────────────────────────────────────────

def skill_check(
    skill_path: Optional[str] = None,
    mode: str = "summary",
    auto_integrate: bool = False,
) -> dict:
    """
    主检查函数 — 供 api.skill_check() 调用。

    返回: {"success": True, "report": "...", "coverage": {...}, "integration_plan": [...]}
    """
    try:
        sp = Path(skill_path) if skill_path else None
        reg = parse_skill_md(sp)
        proj = scan_project()
        cov = calculate_coverage(reg, proj)
        report = format_report(cov, mode)

        plan = gen_integration_plan(cov) if mode in ("gaps",) or auto_integrate else []

        return {
            "success": True,
            "report": report,
            "coverage": cov,
            "integration_plan": plan,
            "note": "运行 python scripts/skill_checker.py --gaps 查看融入计划",
        }
    except Exception as e:
        return {"success": False, "report": f"检查失败: {e}", "error": str(e)}


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SKILL.md 覆盖检查 & 融入引擎")
    parser.add_argument("--detail", action="store_true", help="详细报告")
    parser.add_argument("--gaps", action="store_true", help="只看缺失 + 融入计划")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--integrate", action="store_true", help="生成融入计划")
    args = parser.parse_args()

    mode = "summary"
    if args.detail: mode = "detail"
    if args.gaps: mode = "gaps"
    if args.json: mode = "json"

    result = skill_check(mode=mode)

    if args.integrate and result["success"]:
        plan = result.get("integration_plan", [])
        if plan:
            print(print_integration_plan(plan))
        else:
            print("✓ 无需融入。")

    # 处理 Windows GBK 编码
    report = result["report"]
    try:
        print(report)
    except UnicodeEncodeError:
        print(report.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
    sys.exit(0 if result["success"] else 1)
