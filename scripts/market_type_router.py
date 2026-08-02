# -*- coding: utf-8 -*-
"""
行情策略路由引擎 — 模块②：行情类型判定（12种）
决策树：优先排除极端 → 判最常见 → 叠加型 → 特殊型
"""

import sys, os, json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR) if os.path.basename(BASE_DIR) == "scripts" else BASE_DIR
CONFIG_FILE = os.path.join(PROJECT_DIR, "config", "router_config.json")

DEFENSIVE_SECTORS = {"银行", "保险", "石油", "煤炭", "公用事业", "运营商", "电力", "石油石化"}
OFFENSIVE_SECTORS = {"电子", "计算机", "传媒", "通信", "半导体", "军工", "汽车", "新能源", "食品饮料", "家电", "医药生物"}


def load_sensitivity(mode_override=None):
    """获取灵敏度参数。mode_override 可选覆盖 config 中的设定。"""
    if mode_override is not None:
        cfg = {}
    else:
        cfg = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
    mode = mode_override or cfg.get("sensitivity", {}).get("mode", "standard")
    mapping = {"conservative": "保守", "standard": "标准", "aggressive": "激进"}
    key = mapping.get(mode, "标准")
    params = cfg.get("sensitivity", {}).get(key, {}) if cfg else {}
    # 从内置默认值取参（如果 config 中没写具体参数）
    sen_params_from_gate = {
        "conservative": {"涨跌家数差阈值_普涨": "2000", "涨跌家数差阈值_普跌": "2000",
                         "连续日数阈值_普涨": "3", "情绪跌停下限": "8"},
        "standard": {"涨跌家数差阈值_普涨": "1000", "涨跌家数差阈值_普跌": "1000",
                     "连续日数阈值_普涨": "3", "情绪跌停下限": "10"},
        "aggressive": {"涨跌家数差阈值_普涨": "500", "涨跌家数差阈值_普跌": "500",
                       "连续日数阈值_普涨": "2", "情绪跌停下限": "15"},
    }
    if not params:
        params = sen_params_from_gate.get(mode, sen_params_from_gate["standard"])
    return mode, params


def classify_market(gate_result, indices_data=None, sector_data=None,
                    limit_data=None, style_data=None, sensitivity_mode=None):
    """
    决策树：逐层排查12种行情类型，可叠加标签。
    sensitivity_mode: None=从config读取, 或 "conservative"/"standard"/"aggressive"

    返回: {"primary": str, "tags": [str], "evidence": dict, "action_level": str, "strategy_recommendation": str}
    """
    _, sen = load_sensitivity(mode_override=sensitivity_mode)
    tags = []
    evidence = {}

    # ── 度量 ──
    up_n = sum(1 for ix in (indices_data or []) if ix.get("change_pct", 0) > 0)
    down_n = len(indices_data or []) - up_n
    top5_names = [s.get("name", "") for s in sorted(
        (sector_data or []), key=lambda x: x.get("change_pct", 0) or 0, reverse=True)[:5]]
    
    is_defensive = all(any(ds in s for ds in DEFENSIVE_SECTORS) for s in top5_names) if top5_names else False
    is_offensive = any(any(os_ in s for os_ in OFFENSIVE_SECTORS) for s in top5_names[:2]) if len(top5_names) >= 2 else False
    real_limit_down = (limit_data or {}).get("limit_down_count", 0)
    limit_up_count = (limit_data or {}).get("limit_up_count", 0)
    size_div = (style_data or {}).get("大小盘剪刀差", 0)

    evidence["九指数涨跌"] = f"{up_n}涨{down_n}跌"
    evidence["涨幅前五板块"] = ", ".join(top5_names) if top5_names else "无"
    evidence["涨停数"] = limit_up_count
    evidence["跌停数"] = real_limit_down

    primary = "未分类"
    action_level = gate_result.get("gate_name", "空仓")
    strategy_rec = "空仓观察"

    diff_threshold = int(sen.get("涨跌家数差阈值_普涨", 1000))
    down_threshold = int(sen.get("涨跌家数差阈值_普跌", 1000))
    consecutive_days = int(sen.get("连续日数阈值_普涨", 3))

    # === Layer 1: 极端行情（最高优先级）===
    # 全面性普涨：极多数涨 + 多指数同步 + 涨停较多
    if up_n >= 7 and down_n <= 2 and limit_up_count >= 50:
        primary = "全面性普涨"
        action_level = "进攻"
        strategy_rec = "趋势跟踪（拿住，MA20止盈）"
        evidence["普涨判定"] = f"九指数{up_n}涨{down_n}跌，涨停{limit_up_count}只 → 全面性普涨"

    # 全面性普跌：极多数跌 + 真实跌停多
    elif down_n >= 7 and up_n <= 2 and real_limit_down >= int(sen.get("情绪跌停下限", 10)):
        primary = "全面性普跌"
        action_level = "空仓"
        strategy_rec = "空仓观察"
        evidence["普跌判定"] = f"九指数{up_n}涨{down_n}跌，跌停{real_limit_down}只 → 全面性普跌"

    # 防御性行情：涨幅前五全是防御板块
    elif is_defensive and down_n >= 5:
        primary = "防御性行情"
        action_level = "收缩"
        strategy_rec = "配置框架/红利策略（不用波段）"
        evidence["防御判定"] = f"涨幅前五全是防御板块: {', '.join(top5_names)}"

    # === Layer 2: 结构性/震荡/风格（中等优先级）===
    # 风格行情：大小盘剪刀差 > 3%
    elif size_div >= 3.0:
        primary = "风格行情"
        action_level = "试错"
        strategy_rec = "波段（只在占优风格内）"
        evidence["风格判定"] = f"大小盘剪刀差{size_div:.1f}% → 风格行情"
        tags.append("风格行情")

    # 权重行情：指数红但下跌家数多（鳄鱼口）
    elif up_n <= 3 and down_n >= 6 and any(ix.get("change_pct", 0) > 0 for ix in (indices_data or [])[:3]):
        primary = "权重行情"
        action_level = "试错"
        strategy_rec = "权重股本身的段（振幅10%，降低预期）"
        evidence["权重判定"] = f"指数红但{down_n}跌 → 权重行情（鳄鱼口）"
        tags.append("权重行情")

    # 结构性行情：部分指数涨、部分跌、涨停>30
    elif 3 <= up_n <= 6 and limit_up_count >= 30:
        primary = "结构性行情"
        action_level = "试错"
        strategy_rec = "顺势波段（主线内回踩买、冲高卖）"
        evidence["结构判定"] = f"九指数{up_n}涨{down_n}跌，涨停{limit_up_count}只 → 结构性行情"

    # 存在博弈震荡：涨跌各半 + 涨停<50
    elif 3 <= up_n <= 5 and limit_up_count < 50:
        primary = "存量博弈震荡"
        action_level = "试错"
        strategy_rec = "区间波段/均值回归（高抛低吸）"
        evidence["震荡判定"] = f"九指数{up_n}涨{down_n}跌，涨停{limit_up_count}只 → 存量博弈震荡"

    # === Layer 3: 特殊行情 ===
    # 超跌反弹：全面普跌后反弹
    elif real_limit_down >= int(sen.get("情绪跌停下限", 10)) and up_n >= 4:
        primary = "超跌反弹"
        action_level = "收缩"
        strategy_rec = "修复段轻仓（≤2成，碰压力就走）"
        evidence["超跌判定"] = f"跌停{real_limit_down}只 + 反弹{down_n}涨 → 超跌反弹"

    # 题材/事件：普跌但有涨停集中在单一概念
    elif down_n >= 6 and limit_up_count >= 20:
        primary = "题材/事件行情"
        action_level = "空仓"
        strategy_rec = "✗ 波段不参与"
        evidence["题材判定"] = f"普跌但涨停{limit_up_count}只 → 题材/事件"

    # 其他：兜底归类
    else:
        if up_n >= 5:
            primary = "结构性行情"
            action_level = "试错"
            strategy_rec = "顺势波段"
        elif down_n >= 6:
            primary = "全面性普跌"
            action_level = "空仓"
            strategy_rec = "空仓观察"
        else:
            primary = "存量博弈震荡"
            action_level = "试错"
            strategy_rec = "区间波段"
        evidence["兜底判定"] = f"九指数{up_n}涨{down_n}跌 → 自动归类为 {primary}"

    # 板块轮动叠加标签检测
    if len(top5_names) >= 3 and is_offensive:
        tags.append("板块轮动")
        evidence["轮动检测"] = "进攻板块轮动特征"

    # 抱团行情检测（需要补充数据，先标为潜在）
    if limit_up_count >= 80 and up_n <= 4:
        tags.append("潜在抱团")
        evidence["抱团检测"] = f"涨停{limit_up_count}但仅{up_n}指数涨"

    return {
        "primary": primary,
        "tags": tags,
        "evidence": evidence,
        "action_level": action_level,
        "strategy_recommendation": strategy_rec,
    }


if __name__ == "__main__":
    # 自测试
    mock_gate = {"gate": 1, "gate_name": "收缩", "position_pct": 20}
    mock_indices = [
        {"name": "上证", "change_pct": -1.5}, {"name": "深成", "change_pct": -2.0},
        {"name": "创业板", "change_pct": -3.0}, {"name": "科创50", "change_pct": -2.5},
        {"name": "上证50", "change_pct": -0.5}, {"name": "沪深300", "change_pct": -1.0},
        {"name": "中证500", "change_pct": -1.8}, {"name": "中小100", "change_pct": -2.2},
        {"name": "国证2000", "change_pct": -2.8},
    ]
    mock_sectors = [
        {"name": "食品饮料", "change_pct": 2.1}, {"name": "银行", "change_pct": 1.5},
        {"name": "家电", "change_pct": 1.2}, {"name": "公用事业", "change_pct": 0.8},
        {"name": "石油", "change_pct": 0.5},
    ]
    mock_limit = {"limit_up_count": 32, "limit_down_count": 67}
    result = classify_market(mock_gate, mock_indices, mock_sectors, mock_limit)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
