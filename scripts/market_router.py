# -*- coding: utf-8 -*-
"""
行情策略路由引擎 — 主入口
一键运行：python scripts/market_router.py

设计原则：盘后15分钟自动执行，输出当日决策。盘中不分析、不决策。
模式选择：所有策略模式由 config/router_config.json 人工设定，代码只做 if-else。
"""

import sys, os, json, time, io

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR) if os.path.basename(BASE_DIR) == "scripts" else BASE_DIR
CONFIG_FILE = os.path.join(PROJECT_DIR, "config", "router_config.json")
sys.path.insert(0, BASE_DIR)

from market_gate import run_all_gates, get_sensitivity
from market_type_router import classify_market
from strategy_router import route_strategy
from sector_router import route_sector
from router_report import generate_report


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def show_current_mode():
    """显示当前模式设置"""
    cfg = load_config()
    print(f"  灵敏度: {cfg.get('sensitivity',{}).get('mode','standard')}")
    print(f"  切换时机: {cfg.get('switch_timing',{}).get('mode','pre_market')}")
    print(f"  个股池: {cfg.get('stock_pool',{}).get('mode','mvp_9')}")
    print(f"  输出: {cfg.get('output',{}).get('mode','both')}")
    print()


def interactive_select_mode():
    """交互式选择4个决策模式，返回 mode_dict"""
    print(f"\n{'─'*50}")
    print(f"  ⚙ 模式选择 — 请根据今日行情判断，选择以下4个选项")
    print(f"{'─'*50}")

    # --- 选项1: 灵敏度 ---
    print(f"\n  [1/4] 行情判定灵敏度")
    print(f"    a) 保守 — 牛短熊长防误判，容忍漏报、不容忍误报")
    print(f"    b) 标准 — 平衡漏报和误报，适合大多数行情 (默认)")
    print(f"    c) 激进 — 快速响应行情变化，容忍误报、不容忍漏报")
    while True:
        choice = input("  输入 (a/b/c，回车=b): ").strip().lower()
        if choice == "a":
            sensitivity = "conservative"
            break
        elif choice == "c":
            sensitivity = "aggressive"
            break
        else:
            sensitivity = "standard"
            if choice and choice != "b":
                continue
            break

    # --- 选项2: 切换时机 ---
    print(f"\n  [2/4] 策略切换时机")
    print(f"    a) 盘前切换 — 盘后运行，次日生效，纪律优先 (默认)")
    print(f"    b) 盘中切换 — 盘中预警，需人工二次确认，快速响应")
    while True:
        choice = input("  输入 (a/b，回车=a): ").strip().lower()
        if choice == "b":
            switch_timing = "intraday"
            break
        else:
            switch_timing = "pre_market"
            if choice and choice != "a":
                continue
            break

    # --- 选项3: 个股池 ---
    print(f"\n  [3/4] 个股池范围")
    print(f"    a) MVP_9板块 — 周期资源9板块：煤炭/石油/有色/钢铁/化工/建材/电力设备/机械/军工 (默认)")
    print(f"    b) 全市场 — 申万53个一级行业，市值>100亿+日均成交>1亿")
    while True:
        choice = input("  输入 (a/b，回车=a): ").strip().lower()
        if choice == "b":
            stock_pool = "full_market"
            break
        else:
            stock_pool = "mvp_9"
            if choice and choice != "a":
                continue
            break

    # --- 选项4: 输出 ---
    print(f"\n  [4/4] 输出形式")
    print(f"    a) 终端 — 彩色详细日志，开发调试用")
    print(f"    b) 飞书 — 推送到飞书群")
    print(f"    c) 双输出 — 终端详细 + 飞书精简 (默认)")
    while True:
        choice = input("  输入 (a/b/c，回车=c): ").strip().lower()
        if choice == "a":
            output = "terminal"
            break
        elif choice == "b":
            output = "feishu"
            break
        else:
            output = "both"
            if choice and choice != "c":
                continue
            break

    # 汇总确认
    mode_map = {
        "conservative": "保守", "standard": "标准", "aggressive": "激进",
        "pre_market": "盘前切换(次日生效)", "intraday": "盘中切换(即时生效)",
        "mvp_9": "MVP_9板块", "full_market": "全市场",
        "terminal": "终端", "feishu": "飞书", "both": "双输出",
    }
    print(f"\n{'─'*50}")
    print(f"  ✓ 模式选择确认：")
    print(f"    灵敏度: {mode_map[sensitivity]}")
    print(f"    切换时机: {mode_map[switch_timing]}")
    print(f"    个股池: {mode_map[stock_pool]}")
    print(f"    输出: {mode_map[output]}")
    print(f"{'─'*50}")

    # 允许人工二次确认
    confirm = input("\n  确认开始？(回车=确认，n=重新选择): ").strip().lower()
    if confirm == "n":
        return interactive_select_mode()

    return {
        "sensitivity": sensitivity,
        "switch_timing": switch_timing,
        "stock_pool": stock_pool,
        "output": output,
    }


def fetch_real_data():
    """拉取真实行情数据（腾讯+同花顺+Tushare）"""
    indices = []
    sectors = []
    limit_data = {}
    style_data = {}

    try:
        from tencent_api import tencent
        if tencent:
            print("[数据] 拉取腾讯九指数行情...")
            raw_indices = tencent.fetch_indices()
            indices = raw_indices if raw_indices else []

            print("[数据] 拉取腾讯板块行情...")
            raw_sectors = tencent.fetch_sectors()
            sectors = raw_sectors if raw_sectors else []
    except ImportError:
        print("[警告] tencent_api 不可用")
    except Exception as e:
        print(f"[警告] 腾讯数据拉取异常: {e}")

    try:
        from data_gate import gate as _gate
        if _gate is not None:
            print("[数据] 拉取涨停/跌停数据...")
            up_list = _gate.em_zt_pool()
            down_list = _gate.em_dt_pool()
            limit_data["limit_up_count"] = len(up_list) if up_list is not None and hasattr(up_list, "__len__") else 0
            limit_data["limit_down_count"] = len(down_list) if down_list is not None and hasattr(down_list, "__len__") else 0
    except ImportError:
        print("[警告] eastmoney_signals 不可用")
    except Exception as e:
        print(f"[警告] 情绪数据异常: {e}")

    try:
        from ths_api import ths
        if ths and indices:
            print("[数据] 拉取同花顺风格数据...")
            raw_style = ths.fetch_style()
            if raw_style:
                style_data = raw_style
    except ImportError:
        pass  # 非关键
    except Exception:
        pass

    return indices, sectors, limit_data, style_data


def main(modes=None):
    """主流程：数据拉取 → 门控 → 类型判定 → 策略路由 → 板块路由 → 报告输出

    modes: 可选 dict，包含 sensitivity/switch_timing/stock_pool/output 四个键。
           如果为 None，则交互式选择。
           如果为 "config"，则从 router_config.json 读取。
    """
    # 设置 stdout 编码（仅主入口执行时生效）
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except Exception:
        pass

    print(f"\n{'='*60}")
    print(f"  A股行情策略路由引擎 v1.0")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # --- 模式选择 ---
    if modes is None:
        # 交互式选择
        chosen = interactive_select_mode()
    elif modes == "config":
        # 从配置文件读取
        cfg = load_config()
        chosen = {
            "sensitivity": cfg.get("sensitivity", {}).get("mode", "standard"),
            "switch_timing": cfg.get("switch_timing", {}).get("mode", "pre_market"),
            "stock_pool": cfg.get("stock_pool", {}).get("mode", "mvp_9"),
            "output": cfg.get("output", {}).get("mode", "both"),
        }
    else:
        chosen = modes

    sens = chosen["sensitivity"]
    timing = chosen["switch_timing"]
    pool = chosen["stock_pool"]
    output = chosen["output"]
    print(f"\n[当前模式] 灵敏度={sens} | 切换={timing} | 池={pool} | 输出={output}")

    # Step 1: 拉取真实数据
    print("\n[Step 1/6] 拉取行情数据...")
    indices, sectors, limit_data, style_data = fetch_real_data()

    if not indices:
        print("[警告] 九指数数据不可用，使用默认降级判定")
        indices = [
            {"name": "上证指数", "change_pct": 0.0},
            {"name": "深证成指", "change_pct": 0.0},
            {"name": "创业板指", "change_pct": 0.0},
            {"name": "科创50", "change_pct": 0.0},
            {"name": "上证50", "change_pct": 0.0},
            {"name": "沪深300", "change_pct": 0.0},
            {"name": "中证500", "change_pct": 0.0},
            {"name": "中小100", "change_pct": 0.0},
            {"name": "国证2000", "change_pct": 0.0},
        ]

    # Step 2: Gate 门控（传入灵敏度）
    print(f"\n[Step 2/6] Gate 门控综合判断 (灵敏度: {sens})...")
    gate_result = run_all_gates(sensitivity_mode=sens)

    # Step 3: 行情类型判定（传入灵敏度）
    print(f"[Step 3/6] 行情类型判定 (灵敏度: {sens})...")
    market_type_result = classify_market(gate_result, indices, sectors, limit_data, style_data, sensitivity_mode=sens)

    # Step 4: 策略路由（传入切换时机）
    print(f"[Step 4/6] 策略路由 (切换时机: {timing})...")
    strategy_result = route_strategy(market_type_result, gate_result, switch_mode=timing)

    # Step 5: 板块路由（传入个股池范围）
    print(f"[Step 5/6] 板块路由 (池范围: {pool})...")
    sector_result = route_sector(market_type_result, strategy_result, sectors, pool_mode=pool)

    # Step 6: 报告输出（传入输出方式 + 全部模式信息）
    print(f"[Step 6/6] 生成决策报告 (输出: {output})...")
    report = generate_report(gate_result, market_type_result, strategy_result, sector_result,
                             output_mode=output, sensitivity_mode=sens,
                             switch_mode=timing, pool_mode=pool)

    # 保存决策快照
    snapshot = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "modes": chosen,
        "gate": gate_result,
        "market_type": market_type_result,
        "strategy": strategy_result,
        "sector": sector_result,
        "report_mode": report.get("mode", output),
    }

    history_file = os.path.join(PROJECT_DIR, "data", "router_history.json")
    try:
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        if os.path.exists(history_file):
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
            if not isinstance(history, list):
                history = []
        else:
            history = []
        history.append(snapshot)
        # 保留最近60天
        history = history[-60:]
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2, default=str)
        print(f"[存档] 决策已保存至 {history_file} (共{len(history)}条)")
    except Exception as e:
        print(f"[警告] 存档失败: {e}")

    return snapshot


def quick_route(modes="config"):
    """快捷入口，用于 market_api.py 调用。
    modes: "config" 从配置文件读取，或传 dict 手动指定。
    """
    if modes == "config":
        cfg = load_config()
        modes = {
            "sensitivity": cfg.get("sensitivity", {}).get("mode", "standard"),
            "switch_timing": cfg.get("switch_timing", {}).get("mode", "pre_market"),
            "stock_pool": cfg.get("stock_pool", {}).get("mode", "mvp_9"),
            "output": cfg.get("output", {}).get("mode", "both"),
        }

    indices, sectors, limit_data, style_data = fetch_real_data()
    gate = run_all_gates(sensitivity_mode=modes.get("sensitivity", "standard"))
    mtype = classify_market(gate, indices, sectors, limit_data, style_data,
                            sensitivity_mode=modes.get("sensitivity", "standard"))
    strat = route_strategy(mtype, gate, switch_mode=modes.get("switch_timing", "pre_market"))
    sect = route_sector(mtype, strat, sectors, pool_mode=modes.get("stock_pool", "mvp_9"))
    return {
        "gate": gate,
        "market_type": mtype,
        "strategy": strat,
        "sector": sect,
        "summary": f"{gate['gate_name']}({gate.get('position_pct','?')}%) | {mtype['primary']} | {strat.get('strategy','空仓')}",
    }


if __name__ == "__main__":
    main()
