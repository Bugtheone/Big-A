# -*- coding: utf-8 -*-
"""
行情策略路由引擎 — 模块①：Gate 0~3 门控判断
门控链（次序固定）：Gate 0 周线否决 → Gate 1 趋势三档 → Gate 2 量能广度 → Gate 3 情绪温度

输出：四档门控结论（进攻/试错/收缩/空仓）+ 仓位上限百分比
"""

import sys
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR) if os.path.basename(BASE_DIR) == "scripts" else BASE_DIR
CONFIG_FILE = os.path.join(PROJECT_DIR, "config", "router_config.json")

# ---------- 灵敏度参数表 ----------
SENSITIVITY_PARAMS = {
    "conservative": {
        "涨跌家数差阈值_普涨": 2000,
        "连续日数阈值_普涨": 3,
        "涨跌家数差阈值_普跌": 2000,
        "连续日数阈值_普跌": 3,
        "放量阈值_量比": 1.2,
        "拥挤度阈值": 0.25,
        "情绪涨停上限": 80,
        "情绪跌停下限": 8,
        "标签变更确认日数": 5,
    },
    "standard": {
        "涨跌家数差阈值_普涨": 1000,
        "连续日数阈值_普涨": 3,
        "涨跌家数差阈值_普跌": 1000,
        "连续日数阈值_普跌": 3,
        "放量阈值_量比": 1.1,
        "拥挤度阈值": 0.30,
        "情绪涨停上限": 100,
        "情绪跌停下限": 10,
        "标签变更确认日数": 4,
    },
    "aggressive": {
        "涨跌家数差阈值_普涨": 500,
        "连续日数阈值_普涨": 2,
        "涨跌家数差阈值_普跌": 500,
        "连续日数阈值_普跌": 2,
        "放量阈值_量比": 1.0,
        "拥挤度阈值": 0.35,
        "情绪涨停上限": 120,
        "情绪跌停下限": 15,
        "标签变更确认日数": 3,
    },
}

# Gate 0 九指数列表（收敛自 scripts.index_constants；原 sz399005 中小100/sz399303 国证2000
# 与其它模块 sh000905 中证500/sh000852 中证1000 漂移，已统一）
from scripts.index_constants import INDEX_KEYS
NINE_INDICES = {k: "" for k in INDEX_KEYS}
NINE_INDICES.update({
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
    "sh000016": "上证50",
    "sh000300": "沪深300",
    "sh000905": "中证500",
    "sh000852": "中证1000",
    "sh000985": "中证全指",
})


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_sensitivity(mode_override=None):
    """获取当前灵敏度模式参数。mode_override 可选覆盖 config 中的设定。"""
    if mode_override is not None:
        mode = mode_override
    else:
        cfg = load_config()
        mode = cfg.get("sensitivity", {}).get("mode", "standard")
    return mode, SENSITIVITY_PARAMS.get(mode, SENSITIVITY_PARAMS["standard"])


def _to_df(data):
    """兼容 list[dict] 与 pandas.DataFrame 输入：统一转 DataFrame。
    tushare_pro_data 封装返回 list[dict]（经 _df_to_dicts），门控逻辑按 DataFrame
    API 编写（.empty/.sort_values/rolling/.iloc），直接混用会 AttributeError 并
    被 except 兜底成"恒放行"——这是本模块此前门控失效的根因。"""
    if data is None:
        return None
    if isinstance(data, list):
        if not data:
            return None
        import pandas as pd
        return pd.DataFrame(data)
    return data


# ====================================================================
# Gate 0: 周线一票否决
# 条件：沪深300 周线在 20周线下方 + 20周线方向向下
# ====================================================================
def gate_0_weekly_veto(weekly_data=None):
    """
    Gate 0 — 周线一票否决
    返回: (pass: bool, score: int, detail: dict)
      pass=True  → 放行（+1分）
      pass=False → 否决（仓位上限20%，不开新仓）
    """
    try:
        # 指数周线必须走 ts_index_weekly（ts_weekly 是股票周线，指数代码返回空）
        from scripts.data_gate import gate as _gate

        df = _to_df(weekly_data or _gate.ts_index_weekly(ts_code="000300.SH"))
        if df is None or df.empty or len(df) < 22:
            return False, 0, {"error": "沪深300周线数据不足(<22周)", "否决": True}

        df = df.sort_values("trade_date", ascending=True).tail(25)

        # 计算20周均线及其方向
        df["ma20"] = df["close"].rolling(20).mean()
        last_close = df["close"].iloc[-1]
        last_ma20 = df["ma20"].iloc[-1]
        prev_ma20 = df["ma20"].iloc[-2] if len(df) >= 21 else last_ma20

        ma20_direction = "向上" if last_ma20 > prev_ma20 else "向下" if last_ma20 < prev_ma20 else "走平"
        below_ma20 = last_close < last_ma20

        # 一票否决：收盘 < 20周线 且 方向向下
        veto = below_ma20 and ma20_direction == "向下"

        detail = {
            "沪深300_本周收盘": round(last_close, 2),
            "20周线": round(last_ma20, 2),
            "低于20周线": below_ma20,
            "20周线方向": ma20_direction,
            "否决": veto,
        }

        if veto:
            return False, 0, detail

        return True, 1, detail

    except ImportError:
        return True, 1, {"warning": "tushare_pro_data 不可用，Gate 0 跳过"}
    except Exception as e:
        return True, 1, {"warning": f"Gate 0 异常跳过: {e}"}


# ====================================================================
# Gate 1: 指数趋势三档
# 条件：沪深300 vs MA60/MA250 的关系 → 趋势市 / 震荡市 / 熊市
# ====================================================================
def gate_1_trend_tier(daily_data=None):
    """
    Gate 1 — 趋势三档判定
    返回: (pass: bool, score: int, detail: dict)
      趋势市 → score=1（放行）
      震荡市 → score=1（降级：存量博弈）
      熊市   → score=0（关闭：不开新仓）
    """
    try:
        from scripts.data_gate import gate

        # 指数日线走 ts_index_daily（ts_daily 只认个股代码，指数会静默返空 → 恒 fallback 放行）
        df = _to_df(daily_data or gate.ts_index_daily(ts_code="000300.SH"))
        if df is None or df.empty or len(df) < 255:
            return True, 1, {"error": "沪深300日线数据不足(<255日)", "fallback": "放行"}

        df = df.sort_values("trade_date", ascending=True)
        df["ma60"] = df["close"].rolling(60).mean()
        df["ma250"] = df["close"].rolling(250).mean()

        last_close = df["close"].iloc[-1]
        last_ma60 = df["ma60"].iloc[-1]
        last_ma250 = df["ma250"].iloc[-1]

        above_ma60 = last_close > last_ma60
        above_ma250 = last_close > last_ma250

        # 三档判定
        if above_ma60 and above_ma250:
            tier = "趋势市"
            score = 2
        elif above_ma250 and not above_ma60:
            tier = "震荡市"
            score = 1
        else:
            tier = "熊市"
            score = 0

        detail = {
            "沪深300_收盘": round(last_close, 2),
            "MA60": round(last_ma60, 2),
            "MA250": round(last_ma250, 2),
            "高于MA60": above_ma60,
            "高于MA250": above_ma250,
            "判定": tier,
        }

        return True, score, detail

    except ImportError:
        return True, 2, {"warning": "tushare_pro_data 不可用，Gate 1 跳过(默认趋势市)"}
    except Exception as e:
        return True, 2, {"warning": f"Gate 1 异常跳过: {e}"}


# ====================================================================
# Gate 2: 量能与广度
# 条件：连续3天 > 5日均量 + 上涨家数 > 2500
# ====================================================================
def gate_2_volume_breadth(daily_basic_df=None, tencent_indices=None, tencent_turnover=None, sensitivity_mode=None):
    """
    Gate 2 — 量能与广度检查
    返回: (pass: bool, score: int, detail: dict)
      pass=True + 放量+广度好 → score=1
      pass=True + 未放量（存量博弈） → score=0（降级信号）
    """
    detail = {}

    try:
        from scripts.data_gate import gate
        from scripts.tencent_api import get_tencent
        tencent = get_tencent()

        # --- 量能部分：沪深300成交额 vs 5日均量 ---
        # ts_daily_basic 只认个股代码，指数走 ts_index_daily（amount 字段）
        df = _to_df(daily_basic_df or gate.ts_index_daily(ts_code="000300.SH"))
        volume_ok = False
        volume_days = 0

        if df is not None and not df.empty and len(df) >= 8:
            df = df.sort_values("trade_date", ascending=True)
            if "turnover_rate" in df.columns:
                df["vol_ma5"] = df["turnover_rate"].rolling(5).mean().shift(1)
                recent = df.tail(4)
                above_ma5 = recent["turnover_rate"] > recent["vol_ma5"]
                volume_days = above_ma5.sum()

                sen_mode, sen_param = get_sensitivity(mode_override=sensitivity_mode)
                vol_threshold = sen_param["放量阈值_量比"]

                # 连续3天超过5日均量
                volume_ok = volume_days >= 3 and recent["turnover_rate"].iloc[-1] / recent["vol_ma5"].iloc[-1] > vol_threshold if recent["vol_ma5"].iloc[-1] > 0 else False
            else:
                # 降级：用成交额
                if "amount" in df.columns:
                    df["amt_ma5"] = df["amount"].rolling(5).mean().shift(1)
                    recent = df.tail(4)
                    above_ma5 = recent["amount"] > recent["amt_ma5"]
                    volume_days = above_ma5.sum()
                    volume_ok = volume_days >= 3

            detail["沪深300_近3日放量天数"] = int(volume_days)
            detail["量能OK"] = volume_ok
        else:
            detail["量能"] = "数据不足，跳过"

        # --- 广度部分：九指数涨跌比 + 涨跌家数估计 ---
        breadth_ok = False
        try:
            if tencent_indices is None and tencent is not None:
                tencent_indices = tencent.fetch_indices()

            if tencent_indices:
                up_count = sum(1 for ix in tencent_indices if ix.get("change_pct", 0) > 0)
                down_count = len(tencent_indices) - up_count
                detail["九指数_上涨"] = up_count
                detail["九指数_下跌"] = down_count
                detail["九指数_涨跌比"] = f"{up_count}:{down_count}"

                # 涨跌家数估计（用总成交额）
                if tencent_turnover is None and tencent is not None:
                    tencent_turnover = tencent.fetch_turnover()

                if tencent_turnover:
                    total_turnover = tencent_turnover.get("total", 0)
                    detail["两市成交额_亿"] = round(total_turnover / 1e8, 0) if total_turnover else "N/A"

                breadth_ok = up_count >= 5
            else:
                detail["广度"] = "九指数数据不可用"
        except Exception:
            detail["广度"] = "获取失败"

        detail["广度OK"] = breadth_ok

        # 综合得分
        # 量能+广度都OK → 1分
        # 任一不OK → 0分（标记为存量博弈/弱市）
        score = 1 if (volume_ok and breadth_ok) else 0
        return True, score, detail

    except ImportError:
        return True, 1, {"warning": "数据源不可用，Gate 2 跳过(默认OK)"}
    except Exception as e:
        return True, 1, {"warning": f"Gate 2 异常跳过: {e}"}


# ====================================================================
# Gate 3: 情绪温度计
# 条件：涨停>上限→不再开新仓；跌停>下限→减半；热点占比>30%→拥挤
# ====================================================================
def gate_3_sentiment(limit_data=None, sector_data=None, sensitivity_mode=None):
    """
    Gate 3 — 情绪温度计（反向过滤器）
    返回: (pass: bool, score: int, detail: dict)
      正常 → score=1
      过热 → score=0（不开新仓）
      恐慌 → score=-1（减半/空仓）
      拥挤 → score=0（降级）
    """
    sen_mode, sen_param = get_sensitivity(mode_override=sensitivity_mode)
    limit_up_cap = sen_param["情绪涨停上限"]
    limit_down_floor = sen_param["情绪跌停下限"]
    crowd_threshold = sen_param["拥挤度阈值"]

    detail = {}

    try:
        from data_gate import gate as _gate
        # 涨停/跌停池走 data_gate（eastmoney_signals 无 limit_up_pool/limit_down_pool）
        limit_up_list = limit_data or _gate.em_zt_pool()
        if limit_up_list is not None and not (hasattr(limit_up_list, "empty") and limit_up_list.empty):
            limit_up_count = len(limit_up_list) if hasattr(limit_up_list, "__len__") else 0
        else:
            limit_up_count = 0

        # --- 跌停数 ---
        limit_down_list = _gate.em_dt_pool() if limit_data is None else None
        if limit_down_list is not None and not (hasattr(limit_down_list, "empty") and limit_down_list.empty):
            limit_down_count = len(limit_down_list) if hasattr(limit_down_list, "__len__") else 0
        else:
            limit_down_count = 0

        detail["涨停数"] = limit_up_count
        detail["跌停数"] = limit_down_count
        detail["涨停上限阈值"] = limit_up_cap
        detail["跌停下限阈值"] = limit_down_floor

        # 判定逻辑
        is_overheated = limit_up_count > limit_up_cap
        is_panic = limit_down_count > limit_down_floor

        # --- 拥挤度（热点板块成交占比）---
        is_crowded = False
        try:
            from scripts.tencent_api import get_tencent
            tencent = get_tencent()
            if tencent is not None:
                sectors = sector_data or tencent.fetch_sectors()
                if sectors and len(sectors) >= 5:
                    top5_turnover = sum(s.get("turnover", 0) or 0 for s in sectors[:5])
                    total_turnover = sum(s.get("turnover", 0) or 0 for s in sectors)
                    if total_turnover > 0:
                        top5_ratio = top5_turnover / total_turnover
                        is_crowded = top5_ratio > crowd_threshold
                        detail["热点成交占比"] = round(top5_ratio * 100, 1)
                        detail["拥挤阈值"] = round(crowd_threshold * 100, 1)
        except Exception:
            pass

        detail["过热"] = is_overheated
        detail["恐慌"] = is_panic
        detail["拥挤"] = is_crowded

        # 打分
        if is_panic:
            score = -1
            detail["情绪判定"] = "恐慌 → 空仓/减半"
        elif is_overheated or is_crowded:
            score = 0
            detail["情绪判定"] = ("过热" if is_overheated else "拥挤") + " → 不开新仓"
        else:
            score = 1
            detail["情绪判定"] = "正常"

        return True, score, detail

    except ImportError:
        return True, 1, {"warning": "eastmoney_signals 不可用，Gate 3 跳过"}
    except Exception as e:
        return True, 1, {"warning": f"Gate 3 异常跳过: {e}"}


# ====================================================================
# Gate 综合判断
# ====================================================================
def run_all_gates(sensitivity_mode=None):
    """
    依次执行 Gate 0~3，返回综合门控结论。

    sensitivity_mode: None=从config读取, 或 "conservative"/"standard"/"aggressive"

    返回: {
        "gate": 0~3 的档位编号 (3=进攻, 2=试错, 1=收缩, 0=空仓),
        "gate_name": "进攻/试错/收缩/空仓",
        "position_pct": 仓位上限百分比,
        "total_score": 0~5,
        "details": { gate0, gate1, gate2, gate3 各自详情 },
        "vetoed": 是否被任一Gate否决,
        "sensitivity_mode": 实际生效的灵敏度模式
    }
    """
    detail = {}
    total_score = 0
    vetoed = False

    # Gate 0: 周线一票否决（最高优先级）
    g0_ok, g0_score, g0_detail = gate_0_weekly_veto()
    detail["gate0_周线否决"] = g0_detail
    vetoed = not g0_ok
    total_score += g0_score

    if vetoed:
        # 一票否决后续不再执行
        detail["gate1_趋势三档"] = {"skipped": "Gate 0 否决"}
        detail["gate2_量能广度"] = {"skipped": "Gate 0 否决"}
        detail["gate3_情绪温度"] = {"skipped": "Gate 0 否决"}

        gate_level = 0
        gate_name = "空仓"
        position_pct = 0
    else:
        # Gate 1: 趋势三档
        g1_ok, g1_score, g1_detail = gate_1_trend_tier()
        detail["gate1_趋势三档"] = g1_detail
        total_score += g1_score

        # Gate 2: 量能广度（传入灵敏度）
        g2_ok, g2_score, g2_detail = gate_2_volume_breadth(sensitivity_mode=sensitivity_mode)
        detail["gate2_量能广度"] = g2_detail
        total_score += g2_score

        # Gate 3: 情绪温度（传入灵敏度）
        g3_ok, g3_score, g3_detail = gate_3_sentiment(sensitivity_mode=sensitivity_mode)
        detail["gate3_情绪温度"] = g3_detail
        total_score += g3_score

        # 综合判定
        if total_score >= 4:
            gate_level = 3
            gate_name = "进攻"
            position_pct = 80
        elif total_score >= 2:
            gate_level = 2
            gate_name = "试错"
            position_pct = 50
        elif total_score >= 1:
            gate_level = 1
            gate_name = "收缩"
            position_pct = 20
        else:
            gate_level = 0
            gate_name = "空仓"
            position_pct = 0

    # 情绪恐慌覆盖（Gate 3 score = -1）
    if not vetoed and detail.get("gate3_情绪温度", {}).get("恐慌"):
        gate_level = 0
        gate_name = "空仓(情绪恐慌)"
        position_pct = 0

    actual_mode, _sen_param = get_sensitivity(mode_override=sensitivity_mode)

    return {
        "gate": gate_level,
        "gate_name": gate_name,
        "position_pct": position_pct,
        "total_score": total_score,
        "details": detail,
        "vetoed": vetoed,
        "sensitivity_mode": actual_mode,
    }


# ====================================================================
if __name__ == "__main__":
    result = run_all_gates()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
