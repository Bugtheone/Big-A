# -*- coding: utf-8 -*-
"""
行情策略路由引擎 — 模块④：板块路由器
行情类型 × 策略 → 板块方向推荐 + 禁止方向
支持 MVP_9板块 / 全市场 双模式
"""

import sys, os, json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR) if os.path.basename(BASE_DIR) == "scripts" else BASE_DIR
CONFIG_FILE = os.path.join(PROJECT_DIR, "config", "router_config.json")

# MVP 9个周期资源板块
MVP9_SECTORS = ["煤炭", "石油石化", "有色金属", "钢铁", "基础化工", "建筑材料", "电力设备", "机械设备", "国防军工"]

# 板块方向映射（行情类型 → 推荐板块逻辑 + 禁止方向）
SECTOR_DIRECTION = {
    "全面性普涨":     {"direction": "all",         "forbidden": ["无特别禁忌"], "logic": "动量排名前5均可"},
    "结构性行情":     {"direction": "mainline_1~2", "forbidden": ["非主线板块全部丢弃"], "logic": "只在主线板块内选"},
    "存量博弈震荡":   {"direction": "strongest_only", "forbidden": ["追突破的板块", "弱势板块抄底"], "logic": "只做最强方向的回踩低吸"},
    "风格行情":       {"direction": "style_only",   "forbidden": ["逆风格板块"], "logic": "只在占优风格内（大盘/小盘/价值/成长）"},
    "权重行情":       {"direction": "weight_only",   "forbidden": ["中小盘题材"], "logic": "银行/保险/运营商本身的段"},
    "板块轮动":       {"direction": "rotation_low",  "forbidden": ["连续大涨两天以上的板块"], "logic": "分歧日低吸承接+低位启动"},
    "超跌反弹":       {"direction": "oversold_leader","forbidden": ["还在地板上的弱势板块"], "logic": "最先抗跌转强的板块"},
    "抱团行情":       {"direction": "抱团核心板块",  "forbidden": ["非抱团板块"], "logic": "龙头首次缩量回踩MA10"},
    "防御性行情":     {"direction": "defensive_only", "forbidden": ["高弹性题材板块"], "logic": "红利/银行/公用事业，用配置框架"},
    "题材/事件行情":  {"direction": "none",          "forbidden": ["所有"], "logic": "波段不参与"},
    "全面性普跌":     {"direction": "observe_only",   "forbidden": ["所有"], "logic": "只观察谁先抗跌"},
    "反转/修复":      {"direction": "率先企稳",       "forbidden": ["仍在创新低的板块"], "logic": "止跌+放量+回踩守住的板块"},
}


def load_stock_pool_mode(mode_override=None):
    """获取个股池模式。mode_override 可选覆盖 config 中的设定。"""
    if mode_override is not None:
        return mode_override
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    return cfg.get("stock_pool", {}).get("mode", "mvp_9")


def route_sector(market_type_result, strategy_result, sector_data=None, pool_mode=None):
    """
    板块路由器
    pool_mode: None=从config读取, 或 "mvp_9"/"full_market"

    返回: {
        "direction": 推荐板块方向,
        "logic": 选择逻辑,
        "forbidden": 绝对不碰的方向,
        "pool": 具体板块列表,
        "pool_mode": "mvp_9" or "full_market",
        "top_sectors": 当前涨幅/动量前5板块
    }
    """
    pool_mode = load_stock_pool_mode(mode_override=pool_mode)
    primary_type = market_type_result.get("primary", "未分类")
    direction_cfg = SECTOR_DIRECTION.get(primary_type, SECTOR_DIRECTION.get("全面性普跌", {}))

    # 按模式生成板块池
    if pool_mode == "mvp_9":
        pool = MVP9_SECTORS[:]
    else:
        pool = ["全市场53个申万一级行业（需过滤：市值>100亿 + 日均成交>1亿 + 非ST + 上市>60日）"]

    # 当前行情下适用的板块筛选
    applicable = []
    if sector_data and direction_cfg["direction"] != "observe_only" and direction_cfg["direction"] != "none":
        top_sectors = sorted(sector_data, key=lambda x: x.get("change_pct", 0) or 0, reverse=True)[:10]
        # 防御日只保留防御板块
        from market_type_router import DEFENSIVE_SECTORS, OFFENSIVE_SECTORS

        is_defensive_day = all(
            any(ds in s.get("name", "") for ds in DEFENSIVE_SECTORS)
            for s in top_sectors[:5]
        ) if len(top_sectors) >= 5 else False

        if is_defensive_day:
            applicable = [s for s in top_sectors if any(ds in s.get("name", "") for ds in DEFENSIVE_SECTORS)]
        else:
            applicable = top_sectors[:5]

    return {
        "direction": direction_cfg.get("direction", "observe_only"),
        "logic": direction_cfg.get("logic", ""),
        "forbidden": direction_cfg.get("forbidden", []),
        "pool": pool,
        "pool_mode": pool_mode,
        "applicable_sectors": [
            {"name": s.get("name", ""), "change_pct": s.get("change_pct", 0)}
            for s in applicable
        ] if applicable else [],
        "note": "空仓/收缩模式 → 仅观察池维护" if direction_cfg["direction"] in ("observe_only", "none") else ""
    }


if __name__ == "__main__":
    mock_type = {"primary": "结构性行情"}
    mock_strategy = {"strategy": "顺势波段"}
    mock_sectors = [
        {"name": "半导体", "change_pct": 3.5}, {"name": "国防军工", "change_pct": 2.8},
        {"name": "食品饮料", "change_pct": 2.1}, {"name": "医药生物", "change_pct": 1.5},
        {"name": "银行", "change_pct": 0.3},
    ]
    result = route_sector(mock_type, mock_strategy, mock_sectors)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
