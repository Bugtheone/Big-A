# -*- coding: utf-8 -*-
"""
行情策略路由引擎 — 模块③：策略路由器
行情类型 → 策略族映射，支持盘前/盘中双模式
"""

import sys, os, json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR) if os.path.basename(BASE_DIR) == "scripts" else BASE_DIR
CONFIG_FILE = os.path.join(PROJECT_DIR, "config", "router_config.json")


# ============ 核心路由表 ============
ROUTE_TABLE = {
    "全面性普涨": {
        "primary": "趋势跟踪",
        "secondary": "顺势波段",
        "buy_rule": "突破买点正常执行 + 回踩MA20可加仓",
        "sell_rule": "跌破MA20减半 → MA60清仓；吊灯止损3×ATR",
        "stop_loss": "结构失效 或 -8%",
        "hold_period": "2周~数月",
        "position_multiplier": 1.0,
        "sector_filter": "all",
        "forbidden": ["频繁做段高抛", "提前止盈"],
        "说明": "普涨里用波段手法=用勤奋换更少收益。拿住比做段赚得多。"
    },
    "结构性行情": {
        "primary": "顺势波段",
        "secondary": None,
        "buy_rule": "主线内回踩MA10/MA20企稳买；分歧日低吸",
        "sell_rule": "+15%卖1/3 → +30%卖1/3；放量滞涨全走",
        "stop_loss": "结构失效 或 -5%~8%",
        "hold_period": "数天~数周",
        "position_multiplier": 0.5,
        "sector_filter": "mainline_only",
        "forbidden": ["非主线选股", "追突破"],
        "说明": "波段主场。主线内龙头/中军，回踩买冲高卖。"
    },
    "存量博弈震荡": {
        "primary": "区间波段",
        "secondary": "均值回归",
        "buy_rule": "箱体下沿/均线支撑缩量企稳买；不追突破",
        "sell_rule": "箱体上沿/中轨到了就卖，至少卖一半",
        "stop_loss": "放量跌破箱体下沿/前低",
        "hold_period": "数天~数周",
        "position_multiplier": 0.25,
        "sector_filter": "strongest_only",
        "forbidden": ["追突破", "弱势板块抄底", "均值回归做个股"],
        "说明": "趋势策略在震荡市：胜率与盈亏比同时塌陷。"
    },
    "风格行情": {
        "primary": "顺势波段",
        "secondary": "动量轮动",
        "buy_rule": "只在占优风格内做（大盘/小盘/价值/成长）",
        "sell_rule": "冲高滞涨主动止盈",
        "stop_loss": "结构失效 或 -5%~8%",
        "hold_period": "数天~数周",
        "position_multiplier": 0.4,
        "sector_filter": "style_only",
        "forbidden": ["逆风格选股"],
        "说明": "跑输先查风格错配。"
    },
    "权重行情": {
        "primary": "波段",
        "secondary": None,
        "buy_rule": "权重股本身的段（银行/保险/运营商）",
        "sell_rule": "振幅小(10%)，降低预期，加速止盈",
        "stop_loss": "结构失效 或 -5%",
        "hold_period": "数天~2周",
        "position_multiplier": 0.3,
        "sector_filter": "weight_only",
        "forbidden": ["中小盘题材"],
        "说明": "权重涨时中小盘可能在阴跌。"
    },
    "板块轮动": {
        "primary": "分歧低吸",
        "secondary": "低位启动",
        "buy_rule": "分歧日低吸承接/低位启动；连续大涨两天不追",
        "sell_rule": "次日有溢价就走；轮动市场持股不过3天",
        "stop_loss": "放量破位 或 -5%",
        "hold_period": "1~3天",
        "position_multiplier": 0.15,
        "sector_filter": "rotation_only",
        "forbidden": ["追高潮", "追连续大涨两天以上的板块"],
        "说明": "轮动市要么不做，要么只做分歧低吸。"
    },
    "超跌反弹": {
        "primary": "修复段轻仓",
        "secondary": None,
        "buy_rule": "止跌阳线/长下影后试仓（≤2成）",
        "sell_rule": "反弹至5日线减1/3 → 10日线减1/3 → 20日线清",
        "stop_loss": "跌破止跌阳线最低点",
        "hold_period": "数天",
        "position_multiplier": 0.1,
        "sector_filter": "oversold_leader",
        "forbidden": ["加仓", "格局", "追涨"],
        "说明": "超跌反弹是逃生窗，不是赚钱机会。"
    },
    "抱团行情": {
        "primary": "抱团龙头回踩",
        "secondary": None,
        "buy_rule": "龙头首次缩量回踩MA10（唯一买点）",
        "sell_rule": "放量滞涨就走；跌破MA10无条件走",
        "stop_loss": "无条件最快止损（-3%或跌破MA10）",
        "hold_period": "数天~1周",
        "position_multiplier": 0.15,
        "sector_filter": "抱团核心板块",
        "forbidden": ["非抱团板块", "逆势加仓"],
        "说明": "抱团崩溃时比谁跑得快。"
    },
    "防御性行情": {
        "primary": "配置框架",
        "secondary": "红利策略",
        "buy_rule": "按配置框架（股息率+估值分位），不是波段买点",
        "sell_rule": "按配置框架（再平衡/止盈）",
        "stop_loss": "按配置框架",
        "hold_period": "数月~年",
        "position_multiplier": 0.2,
        "sector_filter": "defensive_only",
        "forbidden": ["用波段框架做配置"],
        "说明": "红利振幅5%~8%，装不下波段止损。"
    },
    "题材/事件行情": {
        "primary": None,
        "secondary": None,
        "buy_rule": None,
        "sell_rule": None,
        "stop_loss": None,
        "hold_period": "不参与",
        "position_multiplier": 0.0,
        "sector_filter": "none",
        "forbidden": ["所有买入操作"],
        "说明": "波段不参与题材。进场即接最后一棒。"
    },
    "全面性普跌": {
        "primary": None,
        "secondary": None,
        "buy_rule": None,
        "sell_rule": None,
        "stop_loss": None,
        "hold_period": "不参与",
        "position_multiplier": 0.0,
        "sector_filter": "observe_only",
        "forbidden": ["所有买入操作"],
        "说明": "全面普跌是波段坟场。"
    },
    "反转/修复": {
        "primary": "试错仓",
        "secondary": "趋势跟踪",
        "buy_rule": "试错仓起步（≤20%），确认后升级",
        "sell_rule": "试错阶段快速止盈，确认后用趋势跟踪规则",
        "stop_loss": "结构再次失效",
        "hold_period": "数天→确认后数周",
        "position_multiplier": 0.15,
        "sector_filter": "率先企稳板块",
        "forbidden": ["重仓抢跑"],
        "说明": "止跌收敛+放量承接+回踩守住 同时出现才升级。"
    },
}


def load_switch_timing(mode_override=None):
    """获取切换时机模式。mode_override 可选覆盖 config 中的设定。"""
    if mode_override is not None:
        return mode_override
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    return cfg.get("switch_timing", {}).get("mode", "pre_market")


def route_strategy(market_type_result, gate_result, switch_mode=None):
    """
    策略路由：行情类型 → 策略族

    参数:
        market_type_result: classify_market() 返回值
        gate_result: run_all_gates() 返回值
        switch_mode: None=从config读取, 或 "pre_market"/"intraday"

    返回: {
        "strategy": 策略族名,
        "strategy_detail": ROUTE_TABLE 中的详细参数,
        "switch_mode": "pre_market" or "intraday",
        "effective_time": "盘前切换=明日生效 / 盘中切换=立即生效",
        "warnings": [警告列表]
    }
    """
    switch_mode = load_switch_timing(mode_override=switch_mode)
    primary_type = market_type_result.get("primary", "未分类")
    strategy = ROUTE_TABLE.get(primary_type, ROUTE_TABLE.get("全面性普跌", {}))

    warnings = []

    # 盘前模式：策略明日生效，今日只输出建议
    if switch_mode == "pre_market":
        effective = "明日9:30开盘生效"
        warnings.append("⚠ 策略锁定：盘中不切换，次日生效")
    else:
        effective = "立即生效"
        warnings.append("⚠ 盘中模式：策略即时生效，但盘中不自动下单")
        # 盘中极端反转预警
        if gate_result.get("details", {}).get("gate3_情绪温度", {}).get("恐慌"):
            warnings.append("🚨 盘中情绪恐慌，建议立即减仓")

    # 门控覆盖：空仓档强制策略为None
    if gate_result.get("gate") == 0 or gate_result.get("vetoed"):
        strategy = ROUTE_TABLE.get("全面性普跌", {})
        warnings.append("🚨 门控空仓档 → 策略强制关闭")

    return {
        "strategy": strategy.get("primary"),
        "strategy_detail": strategy,
        "market_type": primary_type,
        "switch_mode": switch_mode,
        "effective_time": effective,
        "warnings": warnings,
    }


if __name__ == "__main__":
    mock_type = {"primary": "结构性行情", "evidence": {}}
    mock_gate = {"gate": 2, "gate_name": "试错", "position_pct": 50, "vetoed": False}
    result = route_strategy(mock_type, mock_gate)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
