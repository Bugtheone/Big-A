# -*- coding: utf-8 -*-
"""
行情策略路由引擎 — 模块⑤：每日决策报告生成器
输出模式：终端彩色 / 飞书推送 / 双输出（由 config/router_config.json 决定）
"""

import sys, os, json, time, requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR) if os.path.basename(BASE_DIR) == "scripts" else BASE_DIR
CONFIG_FILE = os.path.join(PROJECT_DIR, "config", "router_config.json")
FEISHU_CONFIG = os.path.join(PROJECT_DIR, "config", "feishu_config.json")

# ANSI 颜色
C = {
    "R": "\033[91m", "G": "\033[92m", "Y": "\033[93m", "B": "\033[94m",
    "W": "\033[97m", "D": "\033[90m", "END": "\033[0m", "BOLD": "\033[1m",
}


def load_config():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    return cfg


def load_feishu_webhook():
    if os.path.exists(FEISHU_CONFIG):
        with open(FEISHU_CONFIG, "r", encoding="utf-8") as f:
            fc = json.load(f)
        return fc.get("webhook_url", "")
    return ""


# ============ 终端输出 ============
def terminal_report(gate, market_type, strategy, sector, sensitivity_mode, switch_mode, pool_mode):
    """彩色终端决策报告"""

    gate_level = gate.get("gate", 0)
    gate_name = gate.get("gate_name", "未知")
    position_pct = gate.get("position_pct", 0)
    total_score = gate.get("total_score", 0)

    # 门控颜色
    gate_colors = {3: C["G"], 2: C["Y"], 1: C["Y"], 0: C["R"]}
    gc = gate_colors.get(gate_level, C["W"])

    print(f"\n{C['BOLD']}{'='*60}{C['END']}")
    print(f"{C['BOLD']}  A股行情策略路由 — 每日决策报告{C['END']}")
    print(f"  {time.strftime('%Y-%m-%d %H:%M')}  |  灵敏度:{sensitivity_mode}  |  切换:{switch_mode}  |  池:{pool_mode}")
    print(f"{C['BOLD']}{'='*60}{C['END']}\n")

    # Gate 门控
    print(f"{C['BOLD']}【Gate 门控】{C['END']}")
    details = gate.get("details", {})
    g0 = details.get("gate0_周线否决", {})
    g1 = details.get("gate1_趋势三档", {})
    g2 = details.get("gate2_量能广度", {})
    g3 = details.get("gate3_情绪温度", {})

    vetoed = gate.get("vetoed", False)
    if vetoed:
        print(f"  {C['R']}Gate 0 周线否决: 沪深300<20周线 → 🚨 一票否决！{C['END']}")
        print(f"    收盘 {g0.get('沪深300_本周收盘','?')} | 20周线 {g0.get('20周线','?')} | 方向 {g0.get('20周线方向','?')}")
    else:
        if "skipped" not in str(g0):
            direction = g0.get("20周线方向", "?")
            below = g0.get("低于20周线", False)
            status = f"{C['G']}✓{C['END']}" if not g0.get("否决", True) else f"{C['R']}✗{C['END']}"
            print(f"  Gate 0 周线: 收盘{g0.get('沪深300_本周收盘','?')} / 20周线{g0.get('20周线','?')}({direction}) {status}")

        if "skipped" not in str(g1):
            print(f"  Gate 1 趋势: {g1.get('判定','?')} | MA60:{g1.get('MA60','?')} MA250:{g1.get('MA250','?')}")

        if "skipped" not in str(g2):
            print(f"  Gate 2 量能广度: 量能OK={g2.get('量能OK','?')} 广度OK={g2.get('广度OK','?')} | {g2.get('九指数_涨跌比','?')} | 成交{g2.get('两市成交额_亿','?')}亿")

        if "skipped" not in str(g3):
            print(f"  Gate 3 情绪: 涨停{g3.get('涨停数','?')}/跌停{g3.get('跌停数','?')} | {g3.get('情绪判定','?')}")

    print(f"\n  {gc}门控结论: {gate_name} | Gate{gate_level} | 总分{total_score} | 仓位上限{position_pct}%{C['END']}")

    # 行情类型
    print(f"\n{C['BOLD']}【行情类型】{C['END']}")
    primary = market_type.get("primary", "?")
    tags = market_type.get("tags", [])
    evidence = market_type.get("evidence", {})
    tags_str = f" + {', '.join(tags)}" if tags else ""
    print(f"  判定: {C['Y']}{primary}{C['END']}{tags_str}")
    for k, v in evidence.items():
        print(f"  证据: {k} = {v}")

    # 策略路由
    print(f"\n{C['BOLD']}【策略路由】{C['END']}")
    strat = strategy.get("strategy_detail", {})
    ws = strategy.get("warnings", [])
    if strat.get("primary"):
        print(f"  → 主策略: {C['G']}{strat['primary']}{C['END']}")
        if strat.get("secondary"):
            print(f"    辅策略: {strat['secondary']}")
        print(f"    买点: {strat.get('buy_rule','')}")
        print(f"    卖点: {strat.get('sell_rule','')}")
        print(f"    止损: {strat.get('stop_loss','')}")
        print(f"    持仓周期: {strat.get('hold_period','')}")
        print(f"    仓位系数: {strat.get('position_multiplier',0):.0%}")
        if strat.get("forbidden"):
            print(f"    禁止: {C['R']}{' | '.join(strat['forbidden'])}{C['END']}")
    else:
        print(f"  {C['R']}→ 策略族: ✗ 不执行任何策略{C['END']}")
        if strat.get("说明"):
            print(f"    原因: {strat['说明']}")

    for w in ws:
        print(f"  {C['Y']}{w}{C['END']}")

    # 板块方向
    print(f"\n{C['BOLD']}【板块方向】{C['END']}")
    print(f"  → 该做的: {sector.get('direction','')} | {sector.get('logic','')}")
    if sector.get("applicable_sectors"):
        print(f"    适用板块: {', '.join(s['name'] for s in sector['applicable_sectors'])}")
    if sector.get("forbidden"):
        print(f"    禁止: {C['R']}{' | '.join(sector['forbidden'])}{C['END']}")
    if sector.get("note"):
        print(f"    {C['Y']}{sector['note']}{C['END']}")

    # 个股
    print(f"\n{C['BOLD']}【个股建议】{C['END']}")
    if position_pct == 0:
        print(f"  {C['R']}→ 今日无买入建议（空仓档）{C['END']}")
    elif gate_level <= 1:
        print(f"  {C['Y']}→ 仅维护观察池，不追突破{C['END']}")
    else:
        print(f"  → 候选池上限: {min(10 if pool_mode == 'mvp_9' else 20, 999)}只")
    print(f"  → 策略生效时间: {strategy.get('effective_time','?')}")

    # 模式信息
    print(f"\n{C['D']}当前模式: 灵敏度={sensitivity_mode} | 切换时机={switch_mode} | 池={pool_mode}{C['END']}")
    print(f"{C['BOLD']}{'='*60}{C['END']}\n")


# ============ 飞书推送 ============
def feishu_report(gate, market_type, strategy, sector, sensitivity_mode, switch_mode, pool_mode):
    """飞书markdown卡片推送"""
    webhook = load_feishu_webhook()
    if not webhook:
        print("[飞书] webhook未配置")
        return False

    gate_name = gate.get("gate_name", "?")
    position_pct = gate.get("position_pct", 0)
    primary_type = market_type.get("primary", "?")
    tags = market_type.get("tags", [])
    strat = strategy.get("strategy_detail", {})
    ws = strategy.get("warnings", [])

    gate_emoji = {3: "🟢", 2: "🟡", 1: "🟠", 0: "🔴"}.get(gate.get("gate", 0), "⚪")

    # 构建markdown
    md_lines = [
        f"# {gate_emoji} A股策略路由日报",
        f"**{time.strftime('%Y-%m-%d')}** | 门控: **{gate_name}({position_pct}%)** | 行情: **{primary_type}**",
        "",
        "---",
        "",
        "### 📊 行情判定",
        f"- **类型**: {primary_type}" + (f" + {', '.join(tags)}" if tags else ""),
    ]

    evidence = market_type.get("evidence", {})
    for k, v in list(evidence.items())[:3]:
        md_lines.append(f"- **{k}**: {v}")

    md_lines += [
        "",
        "### 🎯 策略路由",
    ]

    if strat.get("primary"):
        md_lines.append(f"- **策略族**: {strat['primary']}")
        if strat.get("secondary"):
            md_lines.append(f"- **辅策略**: {strat['secondary']}")
        md_lines.append(f"- **买点**: {strat.get('buy_rule','')}")
        md_lines.append(f"- **止损**: {strat.get('stop_loss','')}")
        md_lines.append(f"- **仓位系数**: {strat.get('position_multiplier',0):.0%}")
        if strat.get("forbidden"):
            md_lines.append(f"- **禁止**: {' | '.join(strat['forbidden'])}")
    else:
        md_lines.append(f"- **策略**: ✗ 不执行（{strat.get('说明','')}）")

    if ws:
        md_lines.append("")
        for w in ws:
            md_lines.append(f"> {w}")

    md_lines += [
        "",
        "### 📌 板块方向",
        f"- **方向**: {sector.get('direction','')}",
        f"- **逻辑**: {sector.get('logic','')}",
    ]

    if sector.get("forbidden"):
        md_lines.append(f"- **禁止**: {' | '.join(sector['forbidden'])}")

    applicable = sector.get("applicable_sectors", [])
    if applicable:
        top_sectors_str = ", ".join(f"{s['name']}({s['change_pct']:+.1f}%)" for s in applicable[:5])
        md_lines.append(f"- **适用板块**: {top_sectors_str}")

    md_lines += [
        "",
        f"---",
        f"*灵敏度:{sensitivity_mode} | 切换:{switch_mode} | 池:{pool_mode} | 生成:{time.strftime('%H:%M')}*"
    ]

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"{gate_emoji} A股策略路由日报"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": "\n".join(md_lines),
                }
            ],
        },
    }

    try:
        s = requests.Session()
        s.trust_env = False
        r = s.post(webhook, json=payload, timeout=10)
        if r.status_code == 200:
            print("[飞书] 推送成功 ✓")
            return True
        else:
            print(f"[飞书] 推送失败: {r.status_code} {r.text[:200]}")
            return False
    except Exception as e:
        print(f"[飞书] 推送异常: {e}")
        return False


# ============ 主入口 ============
def generate_report(gate, market_type, strategy, sector,
                    output_mode=None, sensitivity_mode=None, switch_mode=None, pool_mode=None):
    """
    根据 output_mode 决定输出方式。其余 mode 参数用于报告中展示。
    参数为 None 时从 config/router_config.json 读取。

    返回: {"terminal_ok": bool, "feishu_ok": bool, "mode": str}
    """
    cfg = load_config() if (output_mode is None or sensitivity_mode is None or switch_mode is None or pool_mode is None) else {}
    output_mode = output_mode or cfg.get("output", {}).get("mode", "both")
    sensitivity_mode = sensitivity_mode or cfg.get("sensitivity", {}).get("mode", "standard")
    switch_mode = switch_mode or cfg.get("switch_timing", {}).get("mode", "pre_market")
    pool_mode = pool_mode or cfg.get("stock_pool", {}).get("mode", "mvp_9")

    terminal_ok = False
    feishu_ok = False

    if output_mode in ("terminal", "both"):
        terminal_report(gate, market_type, strategy, sector,
                        sensitivity_mode, switch_mode, pool_mode)
        terminal_ok = True

    if output_mode in ("feishu", "both"):
        feishu_ok = feishu_report(gate, market_type, strategy, sector,
                                  sensitivity_mode, switch_mode, pool_mode)

    return {
        "terminal_ok": terminal_ok,
        "feishu_ok": feishu_ok,
        "mode": output_mode,
    }


if __name__ == "__main__":
    mock_gate = {
        "gate": 1, "gate_name": "收缩", "position_pct": 20, "total_score": 1, "vetoed": False,
        "details": {
            "gate0_周线否决": {"沪深300_本周收盘": 3980.5, "20周线": 4100, "20周线方向": "向下", "否决": False},
            "gate1_趋势三档": {"判定": "熊市", "MA60": 4200, "MA250": 4300},
            "gate2_量能广度": {"量能OK": False, "广度OK": False, "九指数_涨跌比": "1:8"},
            "gate3_情绪温度": {"涨停数": 32, "跌停数": 67, "情绪判定": "恐慌 → 空仓/减半", "恐慌": True},
        }
    }
    mock_type = {"primary": "防御性行情", "tags": [], "evidence": {"九指数涨跌": "1涨8跌", "涨幅前五板块": "银行/食品饮料/家电/公用事业/石油"}}
    mock_strat = {
        "strategy": None, "switch_mode": "pre_market", "effective_time": "明日生效", "warnings": ["🚨 门控空仓档 → 策略强制关闭"],
        "strategy_detail": {"primary": None, "说明": "全面普跌是波段坟场。", "forbidden": ["所有买入操作"]}
    }
    mock_sector = {"direction": "observe_only", "logic": "只观察谁先抗跌", "forbidden": ["所有"], "applicable_sectors": [], "note": "空仓模式 → 仅观察池维护"}

    generate_report(mock_gate, mock_type, mock_strat, mock_sector)
