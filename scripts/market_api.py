# -*- coding: utf-8 -*-
"""
MarketAPI — 统一行情数据接口层。

设计目标：让 AI Agent 或调用方只需一行调用，即可获取结构化、已验证的数据结果。
所有数据均经 DataGate 守门员自动验证，不烧脑、不写临时脚本。

用法:
    from scripts.market_api import api

    # 大盘快照
    data = api.index_snapshot()         # 九大指数实时行情
    data = api.turnover()               # 两市成交额

    # K线
    data = api.kline("上证指数", 30)      # 单指数K线
    data = api.kline_batch(["上证50","沪深300","中证1000"], 10)  # 批量K线

    # 资金面
    data = api.north_flow(5)            # 北向资金最近N天
    data = api.board_fund_flow("概念", "今日", 10)  # 板块资金流向

    # 打板
    data = api.board_summary()          # 涨停/炸板/跌停/连板

    # 板块排名
    data = api.sectors(10)              # 行业板块涨幅TOP N

    # 新闻
    data = api.telegraph(10)            # 财联社7x24电报

    # iwencai API Key 管理
    data = api.iwencai_key_status()     # 检查 Key 是否有效
    data = api.iwencai_key_refresh()    # 自动刷新（无头→浏览器降级）

    # 个股
    data = api.stock_realtime(["000001","600519"])  # 个股实时行情

    # 综合分析（一键）
    data = api.full_snapshot()          # 全维度快照（开盘/盘中用）
    data = api.stop_falling_check()     # 五层止跌判断（收盘后用）
    data = api.daily_review()           # 每日复盘报告（收盘后用）

    # 审计 & 技能检查
    data = api.audit_report()           # 数据质量报告
    api.reset_audit()                   # 重置审计轨迹
    data = api.skill_check()            # SKILL.md 覆盖检查 + 融入计划

    # 新增（2026-07-24 §1.3/§2.1/§3.2/§8.3）
    data = api.baidu_kline_ma(code)            # 百度K线·自带MA5/10/20
    data = api.eastmoney_reports(code)         # 个股研报列表
    data = api.download_pdf(record)            # 下载研报PDF
    data = api.industry_reports()              # 行业研报列表
    data = api.north_flow_minute()             # 北向分钟级快照
    data = api.limit_up_sentiment(date)        # 打板情绪·炸板率/连板
"""

from __future__ import annotations
import os, sys, json
from datetime import datetime, time
from enum import Enum
from typing import Any, Dict, List

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.data_gate import gate

# 东财板块资金流主源会话状态（Issue #4）：失败冷却 600s + 自动恢复探测。
# 东财 push2 clist 被 IP 风控（RemoteDisconnected）时避免每次调用都打失效端点。
_EM_FF_STATE = {"fail_count": 0, "last_attempt": 0.0}
_EM_FF_COOLDOWN = 600  # 秒


# ============================================================
#  K线字段索引  [date, high, close, low, open, volume]
# ============================================================
I_DATE = 0; I_HIGH = 1; I_CLOSE = 2; I_LOW = 3; I_OPEN = 4; I_VOL = 5

# ============================================================
#  指数代码常量
# ============================================================
INDEX_CODE_MAP = {
    "上证指数": ("000001", "sh"),   "深证成指": ("399001", "sz"),
    "创业板指": ("399006", "sz"),    "科创50":  ("000688", "sh"),
    "上证50":   ("000016", "sh"),   "沪深300": ("000300", "sh"),
    "中证500":  ("000905", "sh"),   "中证1000":("000852", "sh"),
    "中证全指": ("000985", "sh"),
}
# 保持与 scripts.index_constants 一致（收敛九指数定义）；如需调整请改公共常量

# ============================================================
#  交易时段枚举
# ============================================================

class Session(Enum):
    """交易时段状态"""
    PRE_MARKET   = "盘前"         # 0:00 ~ 9:15（集合竞价前）
    CALL_AUCTION = "集合竞价"      # 9:15 ~ 9:25
    MORNING      = "盘中(上午)"    # 9:30 ~ 11:30
    LUNCH        = "午休"         # 11:30 ~ 13:00
    AFTERNOON    = "盘中(下午)"    # 13:00 ~ 15:00
    POST_MARKET  = "收盘后"       # 15:00 ~ 24:00（交易日）
    WEEKEND      = "周末"         # 非交易日·周六日
    HOLIDAY      = "节假日"       # 非交易日·法定假日
    UNKNOWN      = "未知"

# 关键时间节点（北京时间）
_T_AUCTION_START = time(9, 15)
_T_MORNING_START = time(9, 30)
_T_MORNING_END   = time(11, 30)
_T_AFTERNOON_START = time(13, 0)
_T_AFTERNOON_END   = time(15, 0)

# ============================================================
#  MarketAPI
# ============================================================

class MarketAPI:
    """统一行情数据接口。单例: `from scripts.market_api import api`"""

    def __init__(self):
        pass

    # ---- 工具 ----

    @staticmethod
    def _safe_float(v, default=0.0):
        try:
            return float(v)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _calc_ma(values: list, n: int):
        """简单移动均线"""
        if len(values) < n:
            return None
        return sum(values[-n:]) / n

    @staticmethod
    def _is_weekend_date(dstr: str) -> bool:
        """判断 'YYYY-MM-DD' 是否为周六/周日（用于过滤非交易日估算数据）。"""
        try:
            return datetime.strptime(str(dstr), "%Y-%m-%d").weekday() >= 5
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _fetch_hkex_daily(trade_date: str) -> Dict[str, Any]:
        """HKEX 官方沪深股通日统计（备用源速查 · 权威北向，Issue #3）。

        trade_date: 'YYYYMMDD'。
        返回 {date, sh_turnover_yi, sz_turnover_yi, sh_top10, sz_top10}
        说明：2024-08-18 起官方停止披露北向净买入，权威口径为成交额
        （源文件单位为百万元，此处换算为亿元）。
        失败时返回空 dict（非交易日/网络异常，调用方自行兜底）。
        """
        y, m, d = trade_date[:4], trade_date[4:6], trade_date[6:8]
        url = (f"https://www.hkex.com.hk/chi/csm/DailyStat/"
               f"data_tab_daily_{y}{m}{d}c.js")
        try:
            import requests as _rq
            s = _rq.Session()
            s.trust_env = False
            r = s.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code != 200:
                return {}
            text = r.text.lstrip("\ufeff")
            start = text.find("[")
            if start < 0:
                return {}
            data = json.loads(text[start:].rstrip().rstrip(";"))
        except Exception:
            return {}

        out = {"date": f"{y}-{m}-{d}", "sh_turnover_yi": None,
               "sz_turnover_yi": None, "sh_top10": [], "sz_top10": []}
        # 仅取北向（Northbound）；Southbound 为港股通（港股十大活跃股），非北向需排除
        for entry in data:
            mk = entry.get("market", "")
            is_sh = mk == "SSE Northbound"
            is_sz = mk == "SZSE Northbound"
            if not (is_sh or is_sz):
                continue
            for tbl in entry.get("content", []):
                t = tbl.get("table", {})
                cls = t.get("classname", "")
                if cls == "tradingTable":
                    tr = t.get("tr", [])
                    if tr and tr[0].get("td"):
                        val = tr[0]["td"][0][0].replace(",", "")
                        try:
                            val = round(float(val) / 100, 2)  # 百万元 → 亿元
                        except (ValueError, TypeError):
                            val = None
                        if is_sh:
                            out["sh_turnover_yi"] = val
                        else:
                            out["sz_turnover_yi"] = val
                elif cls == "top10Table":
                    top = []
                    for row in t.get("tr", []):
                        td = row.get("td", [])
                        if td and len(td[0]) >= 4:
                            top.append({"rank": td[0][0], "code": td[0][1],
                                        "name": td[0][2].strip(),
                                        "turnover": td[0][3]})
                    if is_sh:
                        out["sh_top10"] = top
                    else:
                        out["sz_top10"] = top
        return out

    @staticmethod
    def _resolve_index(name_or_code: str) -> tuple:
        """解析指数名称→(code, market)。
         支持中文名(如'上证指数')和代码(如'000001')"""
        if name_or_code in INDEX_CODE_MAP:
            return INDEX_CODE_MAP[name_or_code]
        # 尝试纯代码
        for nm, (cd, mk) in INDEX_CODE_MAP.items():
            if cd == name_or_code:
                return (cd, mk)
        # 默认上证
        return (name_or_code, "sh")

    # ================================================================
    #  零、交易时段判断
    # ================================================================

    def trading_status(self) -> Dict[str, Any]:
        """判断当前时间处于哪个交易时段，以及是否为交易日。

        返回:
            {session: Session枚举,
             session_cn: 中文描述,
             is_trading_day: bool,
             is_trading_hour: bool (9:30-15:00),
             is_post_market: bool (15:00后),
             current_time: str,
             next_event: str,      # 下一个关键时点
             data_freshness: str,  # 数据时效性: "实时"/"收盘"/"历史"
             suggestion: str,      # 使用建议
             trade_cal_source: str} # 交易日历来源
        """
        now = datetime.now()
        t = now.time()
        weekday = now.weekday()  # 0=Mon ~ 6=Sun
        date_str = now.strftime("%Y%m%d")
        time_str = now.strftime("%H:%M:%S")

        # ---- 确定当前时段 ----
        if t < _T_AUCTION_START:
            session = Session.PRE_MARKET
            next_event = "集合竞价 9:15"
        elif t < _T_MORNING_START:
            session = Session.CALL_AUCTION
            next_event = "开盘 9:30"
        elif t < _T_MORNING_END:
            session = Session.MORNING
            next_event = "午休 11:30"
        elif t < _T_AFTERNOON_START:
            session = Session.LUNCH
            next_event = "下午开盘 13:00"
        elif t < _T_AFTERNOON_END:
            session = Session.AFTERNOON
            next_event = "收盘 15:00"
        else:
            session = Session.POST_MARKET
            next_event = "次日集合竞价 9:15"

        # ---- 判断是否为交易日 ----
        is_trading_day = False
        trade_cal_source = "weekday_check"

        if weekday >= 5:  # 周六日
            is_trading_day = False
            session = Session.WEEKEND
            next_event = "下周一集合竞价 9:15"
        else:
            # 周一到周五：默认可能为交易日，再通过 Tushare trade_cal 验证
            is_trading_day = True  # 先假定是交易日
            try:
                from scripts.tushare_api import get_pro
                pro = get_pro()
                cal = pro.trade_cal(exchange='SSE', start_date=date_str, end_date=date_str,
                                    fields='cal_date,is_open')
                if cal is not None and len(cal) > 0:
                    row = cal.iloc[0]
                    is_open = int(row['is_open']) if row.get('is_open') is not None else 1
                    is_trading_day = (is_open == 1)
                    trade_cal_source = "tushare trade_cal"
                    if not is_trading_day and session != Session.WEEKEND:
                        session = Session.HOLIDAY
                        next_event = "下一交易日集合竞价 9:15"
            except Exception:
                # Tushare 不可用时降级为 weekday 判断
                pass

            # 收盘后覆写
            if is_trading_day and session == Session.POST_MARKET:
                session = Session.POST_MARKET

        # ---- 数据时效性判断 ----
        if not is_trading_day:
            data_freshness = "历史(非交易日)"
            suggestion = "盘后分析模式，数据为最近交易日数据"
        elif session in (Session.MORNING, Session.AFTERNOON):
            data_freshness = "实时"
            suggestion = "盘中快照模式，数据实时更新"
        elif session == Session.POST_MARKET:
            data_freshness = "收盘"
            suggestion = "收盘复盘模式，数据为今日最终数据"
        elif session in (Session.PRE_MARKET, Session.CALL_AUCTION):
            data_freshness = "盘前(可能含隔夜数据)"
            suggestion = "盘前预览模式，数据可能不完整"
        elif session == Session.LUNCH:
            data_freshness = "实时(午间)"
            suggestion = "午间快照模式，上午数据为最新"
        else:
            data_freshness = "未知"
            suggestion = "请检查交易日历"

        # ---- 是否盘中 ----
        is_trading_hour = session in (Session.MORNING, Session.AFTERNOON)
        is_post_market = session == Session.POST_MARKET

        return {
            "session": session,
            "session_cn": session.value,
            "is_trading_day": is_trading_day,
            "is_trading_hour": is_trading_hour,
            "is_post_market": is_post_market,
            "current_time": time_str,
            "current_date": date_str,
            "weekday": weekday,
            "next_event": next_event,
            "data_freshness": data_freshness,
            "suggestion": suggestion,
            "trade_cal_source": trade_cal_source,
        }

    # ================================================================
    #  一、大盘行情
    # ================================================================

    def index_snapshot(self, names: list = None) -> List[Dict[str, Any]]:
        """九大指数实时快照（指定names可过滤）。

        返回: [{name, code, price, change_pct, high, low, volume, turnover_yi, pe}, ...]
        ⚠️ 成交额口径：腾讯对指数返回的 turnover 为"当日成交额"——
        沪指=沪市总成交、深证成指=深市总成交（故两市总额=二者之和，行业标准口径）；
        Tushare 指数 amount 为指数样本成交，两者在深市差异可达 1.6~1.9 倍，
        跨源比对时请用全市场 ts_daily amount 加总。
        """
        data = gate.tc_fetch_indices(names=names)
        for it in data:
            it["turnover_yi"] = round(self._safe_float(it.get("turnover", 0)) / 10000, 2)
        return data

    def turnover(self) -> Dict[str, Any]:
        """两市成交额。

        返回: {total_yi, sh_yi, sz_yi}
        """
        # 使用实时行情中的 turnover 字段
        idx = gate.tc_fetch_indices()
        result = {"total_yi": 0.0, "sh_yi": 0.0, "sz_yi": 0.0}
        for it in idx:
            code = it.get("code", "")
            t = self._safe_float(it.get("turnover", 0)) / 10000
            if code == "sh000001":
                result["sh_yi"] = round(t, 2)
            elif code == "sz399001":
                result["sz_yi"] = round(t, 2)
        # fallback: 用 tc.fetch_turnover_simple()
        try:
            total = gate.tc_fetch_turnover_simple()
            result["total_yi"] = round(total, 2)
        except Exception:
            result["total_yi"] = round(result["sh_yi"] + result["sz_yi"], 2)
        return result

    # ================================================================
    #  二、K线 & 技术指标
    # ================================================================

    def kline(self, name_or_code: str, n_days: int = 30) -> Dict[str, Any]:
        """单指数K线（含MA指标）。

        参数:
            name_or_code: 指数名称(如'上证指数')或代码(如'000001')
            n_days: 拉取天数，默认30

        返回:
            {name, code, market, date_range: [start, end], klines: [[date,high,close,low,open,vol],...],
             indicators: {ma5, ma10, ma20, ma60, latest_close, latest_vol_yi,
                          vol_ratio, amplitude_5d}}
        """
        code, mkt = self._resolve_index(name_or_code)
        name = name_or_code
        if name in INDEX_CODE_MAP:
            # 已经是中文名
            pass
        else:
            for nm, (cd, _) in INDEX_CODE_MAP.items():
                if cd == code:
                    name = nm
                    break

        raw = gate.tc_fetch_kline(code, n_days, mkt)

        if not raw:
            return {"name": name, "code": code, "market": mkt, "error": "无K线数据"}

        closes = [r[I_CLOSE] for r in raw]
        vols   = [r[I_VOL] for r in raw]
        latest_close = closes[-1] if closes else 0
        latest_vol   = vols[-1] if vols else 0
        latest_vol_yi = round(latest_vol / 1e8, 2)

        # 均线
        indicators = {
            "ma5":  round(self._calc_ma(closes, 5), 2) if len(closes) >= 5 else None,
            "ma10": round(self._calc_ma(closes, 10), 2) if len(closes) >= 10 else None,
            "ma20": round(self._calc_ma(closes, 20), 2) if len(closes) >= 20 else None,
            "ma60": round(self._calc_ma(closes, 60), 2) if len(closes) >= 60 else None,
            "latest_close": latest_close,
            "latest_vol_yi": latest_vol_yi,
        }

        # 量比（相对前5日均量）
        if len(vols) >= 6:
            avg5 = sum(vols[-6:-1]) / 5
            indicators["vol_ratio"] = round(vols[-1] / avg5, 2) if avg5 > 0 else 1.0
        else:
            indicators["vol_ratio"] = 1.0

        # 近5日平均振幅
        if len(raw) >= 5:
            amps = [(r[I_HIGH] - r[I_LOW]) / r[I_CLOSE] * 100 for r in raw[-5:]]
            indicators["amplitude_5d_avg"] = round(sum(amps) / 5, 2)
            indicators["amplitude_5d_max"] = round(max(amps), 2)

        # MA位置关系
        indicators["ma_position"] = self._ma_position(closes, indicators)

        return {
            "name": name, "code": code, "market": mkt,
            "date_range": [raw[0][I_DATE], raw[-1][I_DATE]],
            "n_days": len(raw),
            "klines": raw,
            "indicators": indicators,
        }

    def kline_batch(self, names: list, n_days: int = 10) -> Dict[str, Dict[str, Any]]:
        """批量K线。返回 {名称: kline结果, ...}"""
        results = {}
        for nm in names:
            try:
                results[nm] = self.kline(nm, n_days)
            except Exception as e:
                results[nm] = {"name": nm, "error": str(e)}
        return results

    @staticmethod
    def _ma_position(closes, ind):
        """判断当前收盘价与各均线的位置关系"""
        c = ind["latest_close"]
        lines = []
        if ind["ma5"] is not None:
            lines.append(f"{'站上' if c > ind['ma5'] else '跌破'}MA5({ind['ma5']})")
        if ind["ma10"] is not None:
            lines.append(f"{'站上' if c > ind['ma10'] else '跌破'}MA10({ind['ma10']})")
        if ind["ma20"] is not None:
            lines.append(f"{'站上' if c > ind['ma20'] else '跌破'}MA20({ind['ma20']})")

        # 金叉/死叉
        if ind["ma5"] is not None and ind["ma10"] is not None:
            if ind["ma5"] > ind["ma10"]:
                lines.append("MA5↑MA10(金叉)")
            else:
                lines.append("MA5↓MA10(死叉)")
        if ind["ma10"] is not None and ind["ma20"] is not None:
            if ind["ma10"] > ind["ma20"]:
                lines.append("MA10↑MA20(金叉)")
            else:
                lines.append("MA10↓MA20(死叉)")
        return " | ".join(lines) if lines else "数据不足"

    # ================================================================
    #  三、资金面
    # ================================================================

    def north_flow(self, n_days: int = 5) -> Dict[str, Any]:
        """北向资金最近N日（2026-07-24 数据栈重构）。

        新数据栈（优先级）：
          ① 同花顺 hexin hgt — 沪股通分钟级真实值（主源）
          ② Tushare ggt_sz — 深股通估算（补充）
          ③ Tushare 全量 — 估算（降级）
          ④ CSV 缓存 — 历史回查
          ⑤ 东财 kamt — 回退检测

        返回:
            {records: [{date, total_yi, hgt_yi, sgt_yi, direction, source, note}, ...],
             latest: {date, total_yi, hgt_yi, sgt_yi, direction, source, note},
             source: 数据源描述,
             summary: {total_yi, days_in, days_out, streak_direction, streak_days, conclusion}}
        """
        raw = gate.em_fetch_north_flow(lmt=n_days)
        if not raw:
            return {
                "error": "北向数据为空(可能盘后未发布)",
                "records": [], "latest": None, "source": "none",
                "summary": {},
            }

        records = []
        primary_source = "unknown"
        for it in raw:
            # 过滤周末：断供后估算缓存可能产生周六/周日的"当日"数据（2026-08-02 实测），
            # 非交易日北向无成交，直接剔除，避免污染统计。
            if self._is_weekend_date(it.get("date", "")):
                continue
            net_flow = round(self._safe_float(it.get("total_yi", 0)), 2)
            direction = "流入" if net_flow > 0 else ("流出" if net_flow < 0 else "持平")
            rec = {
                "date": it.get("date", "?"),
                "total_yi": net_flow,
                "hgt_yi": it.get("hgt_yi"),
                "sgt_yi": it.get("sgt_yi"),
                "direction": direction,
                "source": it.get("source", "unknown"),
                "note": it.get("note", ""),
            }
            records.append(rec)
            if it.get("source"):
                primary_source = it["source"]

        # 统计
        days_in  = sum(1 for r in records if r["total_yi"] > 0)
        days_out = sum(1 for r in records if r["total_yi"] < 0)
        total = sum(r["total_yi"] for r in records)

        # 连续天数
        streak_dir = ""
        streak_days = 0
        for r in records:
            if r["total_yi"] > 0:
                if streak_dir == "out" or streak_dir == "":
                    streak_dir = "in"
                    streak_days = 1
                elif streak_dir == "in":
                    streak_days += 1
            elif r["total_yi"] < 0:
                if streak_dir == "in" or streak_dir == "":
                    streak_dir = "out"
                    streak_days = 1
                elif streak_dir == "out":
                    streak_days += 1

        # 数据源说明（Issue #3：官方 2024-08-18 起停止披露北向净买入，估算值一律标注不可信）
        if primary_source == "hexin+tushare":
            src_note = "估算值（同花顺沪股通分钟级 + Tushare深股通估算）⚠️不可信，权威口径见 hkex_official"
        elif primary_source == "hexin_hgt":
            src_note = "估算值（同花顺沪股通分钟级，深股通暂缺）⚠️不可信，权威口径见 hkex_official"
        elif primary_source == "tushare":
            src_note = "Tushare估算值（沪+深）⚠️不可信，权威口径见 hkex_official"
        elif primary_source and primary_source.startswith("kamt"):
            src_note = "东财kamt（注: 2024.8.19后北向永久归零）⚠️不可信"
        elif primary_source == "cache":
            src_note = "本地离线缓存 ⚠️不可信，权威口径见 hkex_official"
        else:
            src_note = f"未知源({primary_source}) ⚠️不可信"

        # HKEX 官方成交额（权威备胎，Issue #3）——取记录中最新交易日
        hkex_official = {}
        try:
            latest_td = max((r["date"] for r in records), default="").replace("-", "")
            if latest_td:
                hkex_official = self._fetch_hkex_daily(latest_td)
        except Exception:
            hkex_official = {}

        return {
            "records": records,
            "latest": records[0] if records else None,
            "source": src_note,
            "hkex_official": hkex_official or None,
            "summary": {
                "total_yi": round(total, 2),
                "days_in": days_in,
                "days_out": days_out,
                "conclusion": (
                    f"近{n_days}日{'净流入' if total > 0 else '净流出'}"
                    f"{abs(total):.1f}亿，{days_in}入{days_out}出"
                ),
                "streak_direction": streak_dir,
                "streak_days": streak_days,
            },
        }

    def board_fund_flow(self, board_type: str = "行业",
                        period: str = "今日", top_n: int = 10) -> List[Dict[str, Any]]:
        """板块资金流向（行业/概念/地域 × 今日/5日/10日）。

        返回: [{name, code, change_pct, main_net_yi, main_net_ratio, lead_stock, ...}, ...]
        """
        return gate.em_board_fund_flow(board_type, period, top_n)

    def board_fund_flow_robust(self, board_type: str = "行业",
                               period: str = "今日", top_n: int = 10) -> Dict[str, Any]:
        """板块资金流鲁棒获取 — 东财限流时自动降级 Westock 板块资金。

        降级链:
          ① 东财 board_fund_flow (行业/概念, 含涨跌幅+主力净额)
          ② Westock sector ranking 资金段落 (独立源, 需npx)

        主源会话状态（Issue #4）：东财失败进入 600s 冷却，期间直接走 westock；
        冷却到期自动重试，恢复即切回主源（note 标记）。

        返回: {source, status, items: [...], note}
        """
        result = {"source": "eastmoney", "status": "FAIL", "items": [], "note": ""}
        now = datetime.now().timestamp()
        cooldown = (_EM_FF_STATE["fail_count"] > 0
                    and now - _EM_FF_STATE["last_attempt"] < _EM_FF_COOLDOWN)
        # ① 东财（冷却期内跳过，直接降级）
        if not cooldown:
            try:
                _EM_FF_STATE["last_attempt"] = now
                data = self.board_fund_flow(board_type, period, top_n)
                if data:
                    if _EM_FF_STATE["fail_count"] > 0:
                        print("[fund_flow] 东财 push2 已恢复，切回主源 ✅")
                    _EM_FF_STATE["fail_count"] = 0
                    result["source"] = "eastmoney"
                    result["status"] = "OK"
                    result["items"] = data
                    return result
                result["note"] = "东财返回空(疑似IP风控)"
            except Exception as e:
                result["note"] = f"东财限流: {e}"
            _EM_FF_STATE["fail_count"] += 1
        else:
            result["note"] = f"东财冷却中(近期风控, {_EM_FF_COOLDOWN}s 后自动重试)"
        # ② Westock 资金段落
        try:
            from scripts.utils._westock_helper import sector_ranking
            secs = sector_ranking()
            # 资金段落 key: "行业资金流入 Top5" 或类似
            fund_items = None
            for k in ("行业资金流入", "资金流入", "资金流", "行业资金"):
                for key, rows in secs.items():
                    if k in key and rows:
                        fund_items = rows
                        break
                if fund_items:
                    break
            if fund_items:
                # 字段归一化: Westock(changePct/mainNetInflow万元) → 东财风格(change_pct/main_net_yi亿)
                norm = []
                for it in fund_items:
                    pct = it.get("changePct", it.get("change_pct", 0))
                    net_wan = float(it.get("mainNetInflow", 0) or 0)
                    norm.append({
                        "name": it.get("name", "?"),
                        "code": it.get("code", ""),
                        "change_pct": float(pct) if pct else 0.0,
                        "main_net_yi": round(net_wan / 1e4, 2),  # 万元→亿
                        "main_net_ratio": it.get("mainNetRatio", 0),
                        "lead_stock": it.get("leadStock", ""),
                    })
                result["source"] = "westock"
                result["status"] = "OK"
                result["items"] = norm
                result["note"] = ("东财冷却中已直接降级Westock" if cooldown
                                  else "东财限流, 已降级Westock")
                return result
        except Exception as e:
            result["note"] = f"{result['note']}; Westock失败: {e}"
        return result

    def fund_flow_robust(self, code: str) -> Dict[str, Any]:
        """个股资金流鲁棒获取 — 东财120日不可用时降级 Tushare 当日资金流。

        降级链:
          ① 东财 fund_flow_120d (日级主力净额)
          ② Tushare ts_moneyflow_today (当日, 盘后可用)

        返回: {source, status, days, main_net_yi, data}
        """
        result = {"source": "eastmoney", "status": "FAIL", "days": 0,
                  "main_net_yi": 0.0, "data": []}
        # ① 东财120日
        try:
            data = self.fund_flow_120d(code)
            if data:
                # 统一为 {date, main_net_yi, ...}
                norm = []
                for it in data:
                    norm.append({
                        "date": it.get("date", ""),
                        "main_net": it.get("main_net", 0),
                        "main_net_yi": round((it.get("main_net", 0) or 0) / 1e8, 2),
                    })
                result["source"] = "eastmoney_120d"
                result["status"] = "OK"
                result["days"] = len(norm)
                result["main_net_yi"] = sum(n["main_net_yi"] for n in norm[-5:])
                result["data"] = norm
                return result
        except Exception as e:
            result["note"] = f"东财120日失败: {e}"
        # ② Tushare当日 (盘中count=0时回退最近交易日)
        try:
            from datetime import timedelta
            ts_code = code
            if "." not in ts_code:
                ts_code = code + (".SZ" if code.startswith(("0", "3")) else ".SH")
            mf = self.ts_moneyflow_today(ts_code)
            if mf and mf.get("count", 0) > 0:
                result["source"] = "tushare"
                result["status"] = "OK"
                result["days"] = 1
                result["main_net_yi"] = mf.get("total_net_mf_yi", 0)
                result["data"] = mf.get("data", [])
                result["note"] = "东财120日不可用, 降级Tushare当日"
                return result
            # 盘中无当日数据 → 回退最近5个自然日
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=6)).strftime("%Y%m%d")
            hist = gate.ts_moneyflow(ts_code=ts_code, start=start, end=end)
            if hist:
                # 按 trade_date 取最新一天 (net_mf_amount 单位=万元)
                latest_date = max(h.get("trade_date", "") for h in hist)
                latest = [h for h in hist if h.get("trade_date") == latest_date]
                total = sum((d.get("net_mf_amount") or 0) for d in latest)
                result["source"] = "tushare_prev"
                result["status"] = "OK"
                result["days"] = 1
                result["main_net_yi"] = round(total / 1e4, 2)  # 万元→亿
                result["data"] = latest
                result["note"] = f"东财120日不可用且盘中无当日数据, 降级Tushare最近交易日{latest_date}"
                return result
        except Exception as e:
            result["note"] = f"{result.get('note','')}; Tushare失败: {e}"
        return result

    # ================================================================
    #  四、打板数据
    # ================================================================

    def board_summary(self) -> Dict[str, Any]:
        """涨停打板统计。

        返回:
            {zt_count, zb_count, dt_count, zr_rate, zt_high_lb, zt_high_name,
             zt_top_reasons, zt_top_types, zt_names, status}
        """
        data = gate.em_fetch_board_summary()
        zt = data.get("zt_count", 0) if data else 0
        zb = data.get("zb_count", 0) if data else 0

        # 市场情绪评估
        if zt >= 100 and data.get("zr_rate", 50) < 20:
            mood = "热烈"
        elif zt >= 60 and data.get("zr_rate", 50) < 30:
            mood = "偏暖"
        elif zt >= 30:
            mood = "中性"
        elif zt > 0:
            mood = "低迷"
        else:
            mood = "冰点(或非交易日)"

        data["mood"] = mood
        data["zt_total"] = zt + (zb or 0)  # 摸涨停总数
        return data

    # ================================================================
    #  五、板块排名
    # ================================================================

    def sectors(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """行业板块涨幅排名TOP N。

        返回: [{name, code, change_pct}, ...]
        """
        return gate.tc_fetch_sectors(top_n=top_n)

    def breadth(self, verbose: bool = False) -> Dict[str, Any]:
        """全市场涨跌比（含北交所）。

        通过腾讯批量扫描沪深京全A股，按涨跌幅正负统计涨/跌/平。
        返回:
            {total, up, down, flat, up_pct, down_pct,
             markets: {sh:{up,down,flat,total}, sz:{...}, bj:{...}},
             elapsed_s, broad_rating}

        broad_rating: 赚钱效应评级
            ≥70% 赚钱 → 强势
            50~70%   → 正常
            30~50%   → 偏弱
            <30%     → 恐慌
        """
        from scripts.tencent_api import get_tencent
        tc = get_tencent()
        data = tc.fetch_breadth(verbose=verbose)
        up_pct = data.get("up_pct", 0)
        if up_pct >= 70:
            data["broad_rating"] = "强势"
        elif up_pct >= 50:
            data["broad_rating"] = "正常"
        elif up_pct >= 30:
            data["broad_rating"] = "偏弱"
        else:
            data["broad_rating"] = "恐慌"
        return data

    # ================================================================
    #  六、新闻电报
    # ================================================================

    def telegraph(self, limit: int = 10) -> List[Dict[str, str]]:
        """财联社7x24小时实时电报。

        返回: [{title, content, time}, ...]
        """
        return gate.em_cls_telegraph(limit)

    # ================================================================
    #  七、个股实时行情
    # ================================================================

    def stock_realtime(self, codes: list) -> Dict[str, Dict[str, Any]]:
        """个股实时行情（批量）。

        参数: codes 如 ["000001", "600519", "sh000001"] — 纯数字自动补充交易所前缀

        返回: {原始code: {name, price, change_pct, high, low, volume, turnover_yi, pe}, ...}
        """
        # 自动补充交易所前缀: 6xxxxx→sh, 0/3xxxxx→sz
        tc_codes = []
        code_map = {}  # tc_code -> original_code
        for c in codes:
            c2 = str(c).strip()
            if c2.startswith("sh") or c2.startswith("sz") or c2.startswith("bj"):
                tc = c2
            elif c2.startswith("6"):
                tc = "sh" + c2
            elif c2.startswith("0") or c2.startswith("3"):
                tc = "sz" + c2
            else:
                tc = c2
            tc_codes.append(tc)
            code_map[tc] = c2

        raw = gate.tc_fetch_realtime(tc_codes)

        # 映射回原始code
        data = {}
        for tc, item in raw.items():
            orig = code_map.get(tc, tc)
            item["turnover_yi"] = round(self._safe_float(item.get("turnover", 0)) / 10000, 2)
            item["direction"] = "涨" if self._safe_float(item.get("change_pct", 0)) > 0 else \
                              ("跌" if self._safe_float(item.get("change_pct", 0)) < 0 else "平")
            data[orig] = item
        return data

    # ================================================================
    #  八、综合快照（全维度一览，适合盘中快速判断）
    # ================================================================

    def full_snapshot(self) -> Dict[str, Any]:
        """全维度市场快照 — 一次调用获取所有关键数据。

        返回:
            {indices, turnover, sectors, board, north, telegraph,
             performance: {涨跌比, 最强指数, 最弱指数, 总市值变化}}
        """
        gate.reset()

        indices = self.index_snapshot()
        turnover = self.turnover()
        sectors = self.sectors(5)
        board = self.board_summary()
        north = self.north_flow(3)
        telegraph = self.telegraph(5)

        # 表现分析
        if indices:
            sorted_idx = sorted(indices, key=lambda x: self._safe_float(x.get("change_pct", 0)), reverse=True)
            strongest = sorted_idx[0] if sorted_idx else None
            weakest = sorted_idx[-1] if sorted_idx else None
            up_count = sum(1 for i in indices if self._safe_float(i.get("change_pct", 0)) > 0)
        else:
            strongest = weakest = None
            up_count = 0

        return {
            "indices": indices,
            "turnover": turnover,
            "sectors_top5": sectors,
            "board": board,
            "north": north,
            "telegraph_top5": telegraph,
            "performance": {
                "up_count": up_count,
                "down_count": len(indices) - up_count if indices else 0,
                "strongest_index": strongest,
                "weakest_index": weakest,
            },
            "trading_status": self.trading_status(),
            "audit": gate.audit_markdown(),
        }

    # ================================================================
    #  九、止跌确认（五层信号塔）
    # ================================================================

    def stop_falling_check(self) -> Dict[str, Any]:
        """五层止跌信号塔综合分析。
        返回完整的各层评分和综合判断。
        """
        gate.reset()

        KEY_INDEXES = ["上证指数", "上证50", "沪深300", "中证1000", "科创50"]
        ALL_INDEXES = list(INDEX_CODE_MAP.keys())[:-1]  # 前8个

        # ---- 数据采集 ----
        kline_data = {}
        for name in ALL_INDEXES:
            try:
                code, mkt = INDEX_CODE_MAP[name]
                k = gate.tc_fetch_kline(code, 15, mkt)
                if k and len(k) >= 5:
                    kline_data[name] = k
            except Exception as e:
                # 单指数失败不致命，但静默会缺数据——记录便于排查
                print(f"[WARN] market_api kline 获取失败 {name}: {e}")

        turnover_data = gate.tc_fetch_turnover_simple()
        board = gate.em_fetch_board_summary()
        zt_count = board.get("zt_count", 0) if board else 0
        zr_rate = board.get("zr_rate", 0) if board else 0
        dt_count = board.get("dt_count", 0) if board else 0
        zt_high_lb = board.get("zt_high_lb", 0) if board else 0

        north_data = gate.em_fetch_north_flow(lmt=3)

        # ---- 第一层：价格结构 ----
        L1 = {"score": 0, "max": 0, "details": {}, "pass": False}
        for name in KEY_INDEXES:
            if name not in kline_data:
                continue
            L1["max"] += 1
            kl = kline_data[name]
            closes = [r[I_CLOSE] for r in kl]
            highs  = [r[I_HIGH] for r in kl]
            lows   = [r[I_LOW] for r in kl]

            nll = min(lows[-3:]) if len(lows) >= 3 else lows[-1]
            pll = min(lows[-8:-3]) if len(lows) >= 8 else 999999

            signals = {
                "close": closes[-1],
                "no_new_low": nll >= pll * 0.995,
                "above_ma5": closes[-1] > self._calc_ma(closes, 5) if len(closes) >= 5 else False,
                "hh_hl": highs[-1] > highs[-2] and lows[-1] > lows[-2] if len(kl) >= 2 else False,
            }
            sc = sum([signals["no_new_low"], signals["above_ma5"], signals["hh_hl"]])
            signals["sub_score"] = sc
            L1["details"][name] = signals
            if sc >= 2:
                L1["score"] += 1
        L1["pass"] = L1["score"] >= L1["max"] * 0.5 if L1["max"] > 0 else False

        # ---- 第二层：量价配合 ----
        L2 = {"score": 0, "max": 3, "details": {}, "pass": False}
        if "上证指数" in kline_data:
            sz = kline_data["上证指数"]
            closes = [r[I_CLOSE] for r in sz]
            vols = [r[I_VOL] for r in sz]
            av5 = sum(vols[-6:-1]) / 5 if len(vols) >= 6 else sum(vols[:-1]) / max(len(vols)-1, 1)
            vr = vols[-1] / av5 if av5 > 0 else 1
            L2["details"]["vol_ratio"] = round(vr, 2)
            L2["details"]["latest_vol_yi"] = round(vols[-1] / 1e8, 2)
            if vr < 0.6:
                L2["score"] += 1  # 缩量止跌
                L2["details"]["vol_status"] = "缩量"
            elif vr > 1.2:
                L2["details"]["vol_status"] = "放量"

            sync = 0
            for i in range(max(1, len(closes)-3), len(closes)):
                if closes[i] > closes[i-1] and vols[i] > vols[i-1]:
                    sync += 1
                elif closes[i] < closes[i-1] and vols[i] < vols[i-1]:
                    sync += 1
            L2["details"]["vol_price_sync"] = f"{sync}/3"
            if sync >= 2:
                L2["score"] += 1

        if turnover_data and turnover_data > 20000:
            L2["score"] += 1
        L2["details"]["turnover_yi"] = turnover_data if turnover_data else 0
        L2["pass"] = L2["score"] >= 2

        # ---- 第三层：广度确认 ----
        L3 = {"score": 0, "max": 3, "details": {}, "pass": False}
        L3["details"]["zt_count"] = zt_count
        L3["details"]["zr_rate"] = zr_rate
        L3["details"]["dt_count"] = dt_count
        if zt_count >= 80:
            L3["score"] += 1
        if zr_rate <= 25:
            L3["score"] += 1

        if "上证50" in kline_data and "中证1000" in kline_data:
            s50 = kline_data["上证50"]
            z1k = kline_data["中证1000"]
            if len(s50) >= 5 and len(z1k) >= 5:
                s5 = (s50[-1][I_CLOSE] - s50[-5][I_CLOSE]) / s50[-5][I_CLOSE] * 100
                z5 = (z1k[-1][I_CLOSE] - z1k[-5][I_CLOSE]) / z1k[-5][I_CLOSE] * 100
                diff = s5 - z5
                L3["details"]["s50_5d"] = round(s5, 2)
                L3["details"]["z1000_5d"] = round(z5, 2)
                L3["details"]["scissors"] = round(diff, 2)
                if abs(diff) < 2:
                    L3["score"] += 1
        L3["pass"] = L3["score"] >= 2

        # ---- 第四层：资金面 ----
        L4 = {"score": 0, "max": 2, "details": {}, "pass": False}
        L4["details"]["north_days"] = len(north_data) if north_data else 0
        if north_data and len(north_data) >= 2:
            flows = []
            for d in north_data[:3]:
                nf = self._safe_float(d.get("total_yi", 0))
                flows.append(nf)
            pos_count = sum(1 for f in flows if f > 0)
            L4["details"]["recent_flows"] = flows
            L4["details"]["positive_days"] = pos_count
            if pos_count >= 3:
                L4["score"] = 2
            elif pos_count >= 2:
                L4["score"] = 1
        L4["pass"] = L4["score"] >= 1

        # ---- 第五层：均线系统 ----
        L5 = {"score": 0, "max": 2, "details": {}, "pass": False}
        for name in ("上证50", "沪深300", "中证1000"):
            if name not in kline_data:
                continue
            kl = kline_data[name]
            c = [r[I_CLOSE] for r in kl]
            if len(c) < 10:
                continue
            m5 = self._calc_ma(c, 5)
            m10 = self._calc_ma(c, 10)
            L5["details"][name] = {"ma5": round(m5, 2) if m5 else None,
                                    "ma10": round(m10, 2) if m10 else None,
                                    "close": c[-1]}
            if name == "上证50" and m5 and m10 and m5 > m10:
                L5["score"] += 1

        # 极端波动
        if "上证指数" in kline_data:
            sz = kline_data["上证指数"][-5:]
            amps = [(r[I_HIGH] - r[I_LOW]) / r[I_CLOSE] * 100 for r in sz]
            ext_count = sum(1 for a in amps if a > 2)
            L5["details"]["amplitude_5d"] = [round(a, 1) for a in amps]
            L5["details"]["extreme_waves"] = ext_count
            if ext_count == 0 and sum(amps)/len(amps) < 1.0:
                L5["score"] += 1
        L5["pass"] = L5["score"] >= 1

        # ---- 综合判定 ----
        total_score = L1["score"] + L2["score"] + L3["score"] + L4["score"] + L5["score"]
        max_score = L1["max"] + L2["max"] + L3["max"] + L4["max"] + L5["max"]
        ratio = total_score / max_score if max_score > 0 else 0

        if ratio >= 0.8:
            verdict = "初步止跌确认"
            verdict_detail = "多维度信号共振，可以认为止跌有效"
        elif ratio >= 0.6:
            verdict = "部分止跌信号"
            verdict_detail = "多个信号出现但未充分共振，需再观察2-3天确认"
        elif ratio >= 0.4:
            verdict = "止跌信号偏弱"
            verdict_detail = "大概率仍在调整中，不建议抄底"
        else:
            verdict = "未止跌"
            verdict_detail = "下行趋势延续，信号偏空"

        return {
            "L1_price": L1,
            "L2_volume": L2,
            "L3_breadth": L3,
            "L4_capital": L4,
            "L5_ma": L5,
            "total_score": total_score,
            "max_score": max_score,
            "ratio": round(ratio, 2),
            "verdict": verdict,
            "verdict_detail": verdict_detail,
            "trading_status": self.trading_status(),
            "audit": gate.audit_markdown(),
        }

    # ================================================================
    #  十、一键复盘
    # ================================================================

    def daily_review(self) -> Dict[str, Any]:
        """每日收盘复盘快照（不含DKX选股框架，那是硬编码的战略内容）。

        返回: indices, turnover, sectors, board, north, audit
        """
        gate.reset()
        ts = self.trading_status()
        return {
            "indices": self.index_snapshot(),
            "turnover": self.turnover(),
            "sectors": self.sectors(5),
            "board": self.board_summary(),
            "north": self.north_flow(3),
            "trading_status": ts,
            "audit": gate.audit_markdown(),
        }

    # ================================================================
    #  十一、审计
    # ================================================================

    # ========== 龙虎榜（§3.5）==========
    def dragon_tiger(self, date: str = None) -> List[Dict]:
        """龙虎榜日榜。返回 [{code,name,pct,close,reason,net_buy_yi,buy_seats,sell_seats}, ...]"""
        return gate.em_dragon_tiger_board(date)

    # ========== 限售解禁（§3.6）==========
    def lockup_expiry(self, days: int = 7) -> List[Dict]:
        """近期限售解禁。返回 [{code,name,unlock_date,unlock_ratio,float_mcap,days_left}, ...]"""
        return gate.em_lockup_expiry(days)

    # ========== 个股资金流（§3.4）==========
    def fund_flow_minute(self, code: str) -> List[Dict]:
        """个股分钟级主力资金流向。返回 [{time,main_in,big_in,mid_in,small_in}, ...]"""
        return gate.em_fund_flow_minute(code)

    # ========== 融资融券（§4.1）==========
    def margin(self, code: str = None, start: str = None, end: str = None) -> List[Dict]:
        """融资融券数据。code不传=全市场汇总。返回 [{date,rzye,rqye,rzmr,rzch}, ...]"""
        return gate.em_margin_trading(code, start, end)

    # ========== 大宗交易（§4.2）==========
    def block_trade(self, code: str, start: str = None, end: str = None) -> List[Dict]:
        """个股大宗交易记录。返回 [{date,price,volume,amount,buyer,seller,discount}, ...]"""
        return gate.em_block_trade(code, start, end)

    # ========== 股东户数（§4.3）==========
    def holder_num(self, code: str) -> List[Dict]:
        """股东户数变化（筹码集中度）。返回 [{end_date,holder_num,avg_hold,chg_pct}, ...]"""
        return gate.em_holder_num_change(code)

    # ========== 分红历史（§4.4）==========
    def dividend(self, code: str) -> List[Dict]:
        """分红送转历史。返回 [{year,ex_date,cash_div,bonus_share,rights_issue}, ...]"""
        return gate.em_dividend_history(code)

    # ========== 120日资金流（§4.5）==========
    def fund_flow_120d(self, code: str) -> List[Dict]:
        """个股120日主力资金流向。返回 [{date,main_net,big_net,mid_net,small_net,main_pct}, ...]"""
        return gate.em_stock_fund_flow_120d(code)

    # ========== 个股新闻（§5.1）==========
    def stock_news(self, code: str, page_size: int = 20) -> List[Dict]:
        """东财个股新闻。返回 [{title,url,source,pub_time,summary}, ...]"""
        return gate.em_stock_news(code, page_size=page_size)

    # ========== 全球新闻（§5.3）==========
    def global_news(self, page_size: int = 20) -> List[Dict]:
        """东财全球宏观新闻。返回 [{title,url,source,pub_time,summary}, ...]"""
        return gate.em_global_news(page_size=page_size)

    # ========== 个股信息（§6.3）==========
    def stock_info(self, code: str) -> Dict:
        """东财个股基础信息。返回 {code,name,industry,pe_ttm,pb,total_mcap_yi,float_mcap_yi,listing_date}"""
        return gate.em_stock_info(code)

    # ========== 涨停四池（§8.1）==========
    def zt_pool(self, date: str = None) -> List[Dict]:
        """涨停池。返回 [{code,name,pct,limit_days,first_time,reason}, ...]"""
        return gate.em_zt_pool(date)

    def zb_pool(self, date: str = None) -> List[Dict]:
        """炸板池。返回 [{code,name,pct,first_time,reason}, ...]"""
        return gate.em_zb_pool(date)

    def dt_pool(self, date: str = None) -> List[Dict]:
        """跌停池。返回 [{code,name,pct,reason}, ...]"""
        return gate.em_dt_pool(date)

    # ========== 人气榜（§10.2）==========
    def hot_rank(self, top: int = 50) -> List[Dict]:
        """东财人气榜TOP N。返回 [{rank,code,name,price,pct,rank_chg}, ...]"""
        return gate.em_hot_rank(top)

    def hot_concept(self, code: str) -> List[Dict]:
        """个股热门概念命中。返回 [{concept,bk,hit}, ...]"""
        return gate.em_hot_concept(code)

    # ========== 同花顺（§2.2/§3.1/§10.2）==========
    def eps_forecast(self, code: str) -> List[Dict]:
        """同花顺一致预期EPS。返回列表"""
        return gate.ths_eps_forecast(code)

    def hot_reason(self) -> List[Dict]:
        """同花顺当日强势股+涨停原因。返回 [{code,name,pct,reason,turnover}, ...]"""
        return gate.ths_hot_reason()

    def hot_list(self, period: str = "hour") -> List[Dict]:
        """同花顺热榜。返回 [{rank,code,name,heat,pct,rank_chg,concepts,tag}, ...]"""
        return gate.ths_hot_list(period)

    # ========== ETF期权（§9.1）==========
    def option_codes(self, underlying: str = "510050", call: bool = True) -> Dict:
        """ETF期权合约清单。返回 {YYMM: [合约代码,...]}"""
        return gate.sina_option_codes(underlying, call)

    def option_tquote(self, code: str) -> Dict:
        """期权T型报价。返回 {bid,bid_vol,ask,ask_vol,last,strike,open_interest,...}"""
        return gate.sina_option_tquote(code)

    def option_greeks(self, code: str) -> Dict:
        """期权希腊字母+IV。返回 {delta,gamma,theta,vega,iv,...}"""
        return gate.sina_option_greeks(code)

    # ========== 新浪财报（§6.4）==========
    def financial_report(self, code: str) -> Dict:
        """新浪财报三表。返回 {balance:[],income:[],cashflow:[]} 每表 [{item,amount}, ...]"""
        return gate.sina_financial_report(code)

    # ========== 巨潮公告+互动易（§7.1/§10.1）==========
    def announcements(self, code: str, page_size: int = 20, keyword: str = "") -> List[Dict]:
        """巨潮公告检索。返回 [{title,url,ann_date,sec_code,sec_name}, ...]"""
        return gate.cninfo_announcements(code, page_size=page_size, keyword=keyword)

    def irm(self, code: str, page_size: int = 30) -> List[Dict]:
        """互动易问答。返回 [{code,company,question,answer,answerer,ask_time}, ...]"""
        return gate.cninfo_irm(code, page_size=page_size)

    # ========== 通达信mootdx（§1.1/§6.1/§6.2）==========
    def tdx_bars(self, code: str, freq: int = 9, count: int = 100) -> List[Dict]:
        """通达信K线。freq: 0=5min 4=日线 5=周线 6=月线 9=年线"""
        return gate.tdx_bars(code, freq=freq, count=count)

    def tdx_quotes(self, codes: list) -> List[Dict]:
        """通达信批量盘口快照"""
        return gate.tdx_quotes(codes)

    def tdx_finance(self, code: str) -> Dict:
        """通达信财务快照（PE/PB/ROE/营收/净利润等）"""
        return gate.tdx_finance(code)

    # ========== 估值 ==========
    def valuation(self, code: str) -> Dict:
        """单票完整估值分析。返回 {price,mcap_yi,pe_ttm,pb,pe_forward,peg,cagr,digestion_years,verdict}"""
        return gate.val_full_valuation(code)

    def audit_report(self) -> str:
        """返回当前审计轨迹的 Markdown 报告。"""
        return gate.audit_markdown()

    def reset_audit(self):
        """重置审计轨迹（新任务开始时调用）。"""
        gate.reset()

    def audit_health(self) -> Dict[str, Any]:
        """数据健康度评分 (0-100)。"""
        return gate.health_check()

    # ================================================================
    #  十二、iwencai 问财自然语言选股 + API Key 管理
    # ================================================================

    def iwencai_query(self, query: str, limit: int = 10, page: int = 1) -> Dict[str, Any]:
        """问财自然语言选股/查询（AI Agent 核心入口）。

        自然语言触发词: "选股" / "筛选" / "问财" / "找出...的股票" / "哪些股票..."
        示例查询:
          - "ROE>20%且PE<30的消费股"
          - "今日涨幅超3%且市值大于500亿的银行股"
          - "连续3日主力净流入的半导体股票"
          - "股息率最高的前10只银行股"

        Args:
            query: 自然语言查询条件
            limit: 返回条数 (1-100)
            page: 页码

        返回: {
            success: bool,
            code_count: int,     # 命中总数
            data: list,          # 结果行 (code/name/最新价/涨跌幅等)
            message: str,
        }
        """
        result = {"success": False, "code_count": 0, "data": [], "message": ""}
        try:
            from scripts.iwencai_openapi import get_openapi
            api_iwencai = get_openapi()
        except ImportError as e:
            result["message"] = f"问财模块不可用: {e}"
            return result

        if not api_iwencai.api_key:
            result["message"] = "IWENCAI_API_KEY 未配置，请先调用 iwencai_key_status() 检查"
            return result

        resp = api_iwencai.query2data(query, page=str(page), limit=str(limit))
        result.update(resp)
        # 简化 data：只保留常用字段，避免把原始超大 payload 灌给 AI
        if resp.get("success") and resp.get("data"):
            simplified = []
            for row in resp["data"]:
                item = {}
                # 问财返回中文键，映射为统一字段名
                key_map = {
                    "股票代码": "code", "stock_code": "code", "code": "code",
                    "股票简称": "name", "stock_name": "name", "name": "name",
                    "最新价": "price", "price": "price",
                    "最新涨跌幅": "change_pct", "涨跌幅": "change_pct",
                    "涨跌幅(%)": "change_pct", "change_pct": "change_pct",
                    "换手率": "turnover",
                    "总市值": "market_cap", "流通市值": "float_cap",
                    "所属同花顺行业": "industry", "所属行业": "industry",
                    "所属概念": "concepts",
                    "最新价[复权]": "adj_price",
                }
                for k, v in row.items():
                    if v is None:
                        continue
                    mapped = key_map.get(k)
                    if mapped:
                        item[mapped] = v
                    # 顺带保留年度股息率等特殊字段
                    elif "股息率" in str(k):
                        item["dividend_yield"] = v
                simplified.append(item)
            result["data"] = simplified
            result["message"] = f"问财命中 {resp.get('code_count', 0)} 条，已返回 {len(simplified)} 条"
        return result

    def iwencai_key_status(self) -> Dict[str, Any]:
        """检查 iwencai OpenAPI Key 是否有效。

        自然语言触发词: "检查 API Key" / "Key 是否有效" / "iwencai 状态"
        无需参数，自动从 config/env 读取 Key 并做一次轻量搜索验证。

        返回: {
            valid: bool,        # Key 是否有效
            key_masked: str,    # 脱敏显示 (sk-proj-01-XXXX****XXXX)
            message: str,       # 人类可读的状态描述
            source: str,        # Key 来源: config/env/none
        }
        """
        result = {"valid": False, "key_masked": "", "message": "", "source": "none"}

        try:
            from scripts.iwencai_openapi import IwencaiOpenAPI
            api_iwencai = IwencaiOpenAPI()
        except ImportError:
            result["message"] = "iwencai OpenAPI 模块不可用"
            return result

        key = api_iwencai.api_key
        if not key:
            result["message"] = "API Key 未配置，请先设置环境变量 IWENCAI_API_KEY 或 config/iwencai_config.json"
            return result

        result["source"] = "env" if os.environ.get("IWENCAI_API_KEY") == key else "config"
        result["key_masked"] = (key[:14] + "****" + key[-4:]) if len(key) > 18 else "****"

        ok = api_iwencai.health_check(auto_refresh=False)
        result["valid"] = ok
        result["message"] = "API Key 有效" if ok else "API Key 已失效，请调用 iwencai_key_refresh() 自动刷新"
        return result

    def iwencai_key_refresh(self, auto_login: bool = True) -> Dict[str, Any]:
        """自动刷新 iwencai OpenAPI Key。

        自然语言触发词: "刷新 API Key" / "Key 过期了" / "自动刷新" / "重新获取 Key"
        - 有浏览器保存的登录会话时: 无头恢复 → 自动提取 → 全自动（零人工）
        - 会话也过期时: 弹出浏览器 → 你登录一次 → 再次全自动
        - auto_login=False: 仅尝试无头模式，不弹出浏览器

        返回: {
            success: bool,      # 是否成功
            method: str,        # 刷新方式: headless / browser / failed
            key_masked: str,    # 脱敏显示
            message: str,       # 人类可读描述
        }
        """
        result = {"success": False, "method": "failed", "key_masked": "", "message": ""}

        try:
            from scripts.iwencai_refresh_key import (
                auto_refresh_or_raise,
                refresh_key_from_saved_session,
            )
            from scripts.iwencai_openapi import get_openapi
        except ImportError as e:
            result["message"] = f"刷新模块不可用: {e}"
            return result

        # 执行刷新
        if auto_login:
            ok = auto_refresh_or_raise()
            result["method"] = "browser" if ok else "failed"
        else:
            ok = refresh_key_from_saved_session()
            result["method"] = "headless" if ok else "failed"

        if ok and not os.environ.get("IWENCAI_API_KEY"):
            # setx 不会影响当前进程，此处手动注入
            try:
                cfg_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "config", "iwencai_config.json",
                )
                if os.path.exists(cfg_path):
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    new_key = cfg.get("IWENCAI_API_KEY", "")
                    if new_key:
                        os.environ["IWENCAI_API_KEY"] = new_key
            except Exception:
                pass

        # 重新加载单例
        api_iwencai = get_openapi()
        api_iwencai.api_key = ""
        api_iwencai._load_from_config()
        api_iwencai._load_from_env()

        key = api_iwencai.api_key
        if key:
            result["success"] = True
            result["key_masked"] = (key[:14] + "****" + key[-4:]) if len(key) > 18 else "****"
            result["message"] = f"API Key 刷新成功 [{result['method']}]"
        else:
            result["message"] = (
                "无头刷新失败，需打开浏览器登录"
                if not auto_login
                else "刷新失败，请手动登录 skillhub 获取新 Key"
            )

        return result

    # ================================================================
    #  十三、SKILL.md 覆盖检查（自动融入引擎）
    # ================================================================

    def skill_check(self, mode: str = "summary") -> Dict[str, Any]:
        """检查 SKILL.md 端点覆盖情况，列出已融入和缺失的端点。

        自然语言触发词: "检查 SKILL.md" / "数据端点覆盖" / "哪些端点还没融入"
        mode: "summary"(摘要) / "detail"(详细) / "gaps"(缺失+融入计划) / "json"

        返回: {
            success: bool,
            report: str,           # 格式化文本报告
            coverage: {...},       # 原始覆盖数据
            integration_plan: [...],  # 缺失端点的融入计划
        }
        """
        try:
            from scripts.skill_checker import skill_check as _check
            return _check(mode=mode)
        except ImportError:
            return {"success": False, "report": "skill_checker 模块不可用",
                    "error": "ImportError"}
        except Exception as e:
            return {"success": False, "report": f"检查失败: {e}", "error": str(e)}

    # ================================================================
    #  十四、百度K线带MA（§1.3）— 天然带 MA5/10/20
    # ================================================================

    def baidu_kline_ma(self, code: str, start_time: str = "") -> Dict[str, Any]:
        """百度K线 — 天然自带 MA5/MA10/MA20，无需额外计算"""
        return gate.em_baidu_kline_with_ma(code, start_time)

    # ================================================================
    #  十五、东财研报 + PDF下载（§2.1）
    # ================================================================

    def eastmoney_reports(self, code: str, max_pages: int = 5) -> List[Dict]:
        """获取指定股票的研报列表"""
        return gate.em_eastmoney_reports(code, max_pages)

    def download_pdf(self, record: dict, target_dir: str = None) -> str:
        """下载单份研报PDF"""
        return gate.em_download_pdf(record, target_dir)

    def industry_reports(self, industry_code: str = "*", max_pages: int = 5,
                         begin: str = "2024-01-01") -> List[Dict]:
        """获取行业研报列表"""
        return gate.em_industry_reports(industry_code, max_pages, begin)

    # ================================================================
    #  十六、北向资金分钟级快照（§3.2）
    # ================================================================

    def north_flow_minute(self) -> Dict[str, Any]:
        """北向资金当日分钟级快照（同花顺 hexin）。

        返回 {times, hgt_yi, sgt_yi, flags: {hgt_anomaly, sgt_anomaly}}。
        flags.sgt_anomaly=True 时表示深股通分钟数据异常（已知同花顺 SGT 不可靠），
        此时应仅信任 hgt_yi（沪股通真实值）。
        """
        data = gate.ths_hsgt_realtime()
        # SGT 异常检测：单点>100亿 或 日累计>500亿 标记为异常
        sgt_list = data.get("sgt_yi") or []
        hgt_list = data.get("hgt_yi") or []
        sgt_abs_max = max((abs(v) for v in sgt_list), default=0)
        sgt_total = sum(sgt_list)
        hgt_total = sum(hgt_list)
        flags = {
            "sgt_anomaly": sgt_abs_max > 100 or abs(sgt_total) > 500,
            "hgt_anomaly": False,
            "hgt_total_yi": round(hgt_total, 2),
            "sgt_total_yi": round(sgt_total, 2) if not (sgt_abs_max > 100 or abs(sgt_total) > 500) else None,
            "note": "SGT 异常，仅 HGT 可信" if sgt_abs_max > 100 or abs(sgt_total) > 500 else "",
        }
        data["flags"] = flags
        return data

    # ================================================================
    #  十七、打板情绪（§8.3）— 炸板率/连板高度/梯队
    # ================================================================

    def limit_up_sentiment(self, date: str) -> Dict[str, Any]:
        """打板情绪指标 —— 涨停数/炸板率/最高连板/梯队分布。
        返回 {date, zt_count, zb_count, dt_count, break_rate, max_height, ladder}"""
        data = gate.em_limit_up_sentiment(date)
        zt = data["zt_count"]
        label = ("强势" if data["break_rate"] <= 20 and zt >= 40 else
                 "中性" if data["break_rate"] <= 35 else "退潮")
        data["label"] = label
        return data

    # ================================================================
    #  十八、Tushare Pro 全量数据（500元档 — 18个高频方法）
    # ================================================================

    def ts_daily_kline(self, ts_code: str = None, start: str = None, end: str = None,
                       n_days: int = 30, trade_date: str = None) -> Dict[str, Any]:
        """个股/全市场日线行情（前复权）。核心端点，用于均线/趋势/量能计算。
        传 trade_date 取单日，否则按 start/end 或默认取最近 n_days。"""
        from datetime import datetime, timedelta
        if trade_date is None and start is None and end is None:
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=n_days * 2)).strftime("%Y%m%d")
        data = gate.ts_daily(ts_code=ts_code, start=start, end=end, trade_date=trade_date)
        summary = {"count": len(data)} if data else {"count": 0}
        if data and len(data) >= 1:
            latest = data[0]  # Tushare 返回降序(最新在前)
            summary["last_date"] = latest.get("trade_date", "")
            summary["last_close"] = latest.get("close")
            summary["last_vol"] = latest.get("vol")
        return {"summary": summary, "date_range": f"{start or trade_date}-{end or trade_date}", "data": data}

    def ts_weekly_kline(self, ts_code: str = None, n_weeks: int = 52) -> Dict[str, Any]:
        """个股/全市场周线行情。默认最近52周。"""
        from datetime import datetime, timedelta
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(weeks=n_weeks)).strftime("%Y%m%d")
        data = gate.ts_weekly(ts_code=ts_code, start=start, end=end)
        return {"count": len(data), "date_range": f"{start}-{end}", "data": data}

    def ts_monthly_kline(self, ts_code: str = None, n_months: int = 24) -> Dict[str, Any]:
        """个股/全市场月线行情。默认最近24个月。"""
        from datetime import datetime, timedelta
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=n_months * 31)).strftime("%Y%m%d")
        data = gate.ts_monthly(ts_code=ts_code, start=start, end=end)
        return {"count": len(data), "date_range": f"{start}-{end}", "data": data}

    def ts_daily_basic(self, ts_code: str = None, trade_date: str = None) -> Dict[str, Any]:
        """个股每日基本面指标 — PE/PB/市值/换手率/量比（波段选股核心）。
        不传 ts_code=全市场，不传 trade_date=今天。"""
        data = gate.ts_daily_basic(trade_date=trade_date, ts_code=ts_code)
        # 附加汇总
        if data and ts_code is None:
            pe_vals = [d.get("pe_ttm") for d in data if d.get("pe_ttm")]
            summary = {"count": len(data), "pe_median": round(sorted(pe_vals)[len(pe_vals)//2], 1) if pe_vals else None}
        else:
            summary = {"count": len(data)}
        return {"trade_date": trade_date or datetime.now().strftime("%Y%m%d"),
                "summary": summary, "data": data}

    def ts_moneyflow_today(self, ts_code: str = None) -> Dict[str, Any]:
        """今日个股资金流向（主力净流入额/量）。不传 ts_code=全市场。"""
        data = gate.ts_moneyflow(ts_code=ts_code)
        total_net = sum((d.get("net_mf_amount") or 0) for d in data) if data else 0
        return {"date": datetime.now().strftime("%Y%m%d"), "count": len(data),
                "total_net_mf_yi": round(total_net / 1e4, 1),  # 万元→亿
                "data": data}

    def ts_margin_summary(self, ts_code: str = None, n_days: int = 5) -> Dict[str, Any]:
        """融资融券汇总（近N日）。不传 ts_code=全市场汇总。"""
        from datetime import timedelta
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=n_days)).strftime("%Y%m%d")
        data = gate.ts_margin(ts_code=ts_code, start=start, end=end)
        return {"date_range": f"{start}-{end}", "count": len(data), "data": data}

    def ts_margin_detail(self, ts_code: str = None, trade_date: str = None) -> Dict[str, Any]:
        """融资融券交易明细（个股级）。今日融资买入/融券卖出额。"""
        data = gate.ts_margin_detail(ts_code=ts_code, trade_date=trade_date)
        return {"count": len(data), "data": data}

    def ts_forecast(self, ts_code: str = None, period: str = None) -> Dict[str, Any]:
        """业绩预告——预增/略增/续盈/略减/预减/首亏/续亏/扭亏。
        不传 ts_code=全市场最近。"""
        data = gate.ts_forecast(ts_code=ts_code, period=period)
        type_map = {"1": "预增", "2": "略增", "3": "续盈", "4": "略减",
                    "5": "预减", "6": "首亏", "7": "续亏", "8": "扭亏", "9": "不确定"}
        type_stats = {}
        for d in data:
            t = d.get("type", "")
            label = type_map.get(t, t)
            type_stats[label] = type_stats.get(label, 0) + 1
        return {"count": len(data), "type_breakdown": type_stats, "data": data}

    def ts_holder_trend(self, ts_code: str) -> Dict[str, Any]:
        """股东户数变化趋势（筹码集中度分析）。股东户数持续减少=筹码集中=看涨信号。"""
        data = gate.ts_stk_holdernumber(ts_code=ts_code)
        if len(data) >= 2:
            latest = data[0].get("holder_num", 0)
            prev = data[-1].get("holder_num", 0)
            trend = "集中" if latest < prev else ("分散" if latest > prev else "持平")
            change_pct = round((latest / prev - 1) * 100, 2) if prev else 0
        else:
            trend, change_pct = "数据不足", 0
        return {"ts_code": ts_code, "count": len(data),
                "trend": trend, "change_pct": change_pct, "data": data}

    def ts_top10_holders(self, ts_code: str) -> Dict[str, Any]:
        """十大股东——机构持仓透视。"""
        data = gate.ts_top10_holders(ts_code=ts_code)
        # 统计机构占比
        inst_count = sum(1 for d in data if "机构" in str(d.get("holder_type", "")) or
                         "基金" in str(d.get("holder_name", "")) or
                         "社保" in str(d.get("holder_name", "")) or
                         "QFII" in str(d.get("holder_name", "")))
        return {"ts_code": ts_code, "count": len(data),
                "institutional_holders": inst_count, "data": data}

    def ts_dividend_history(self, ts_code: str) -> Dict[str, Any]:
        """分红历史——连续分红年数/年均股息率。"""
        data = gate.ts_dividend(ts_code=ts_code)
        years = sorted(set(d.get("divid_year", "") for d in data if d.get("divid_year")), reverse=True)
        consecutive = 0
        for i, y in enumerate(years):
            if i == 0:
                consecutive = 1
            elif int(years[i-1]) - int(y) == 1:
                consecutive += 1
            else:
                break
        return {"ts_code": ts_code, "count": len(data),
                "consecutive_years": consecutive, "years": years[:5],
                "data": data}

    def ts_factor_realtime(self, ts_code: str, n_days: int = 30) -> Dict[str, Any]:
        """复权因子——含前复权/后复权价格（替代手动复权计算）。"""
        from datetime import timedelta
        data = gate.ts_stk_factor(ts_code=ts_code, start=(datetime.now() - timedelta(days=n_days)).strftime("%Y%m%d"))
        return {"ts_code": ts_code, "count": len(data), "data": data}

    def ts_stock_info(self, ts_code: str) -> Dict[str, Any]:
        """上市公司基本信息——注册地/行业/员工/经营范围。"""
        data = gate.ts_stock_company(ts_code=ts_code)
        return {"ts_code": ts_code, "data": data[0] if data else None}

    def ts_index_weekly(self, ts_code: str, n_weeks: int = 52) -> Dict[str, Any]:
        """指数周K线。ts_code 如 000001.SH。"""
        from datetime import timedelta
        data = gate.ts_index_weekly(ts_code=ts_code,
                                     start=(datetime.now() - timedelta(weeks=n_weeks)).strftime("%Y%m%d"))
        return {"ts_code": ts_code, "count": len(data), "data": data}

    def ts_suspend_check(self, suspend_date: str = None) -> Dict[str, Any]:
        """停牌检查——今日停牌股票列表。"""
        data = gate.ts_suspend(suspend_date=suspend_date)
        return {"date": suspend_date or datetime.now().strftime("%Y%m%d"),
                "count": len(data), "data": data}

    def ts_disclosure_calendar(self, ts_code: str = None) -> Dict[str, Any]:
        """财报披露日历——即将披露财报的股票及日期。"""
        data = gate.ts_disclosure_date(ts_code=ts_code)
        upcoming = [d for d in data if d.get("actual_date") is None
                    and d.get("pre_date", "") >= datetime.now().strftime("%Y%m%d")]
        return {"count": len(data), "upcoming": len(upcoming), "data": data}

    def ts_news(self, ts_code: str = None, n_days: int = 7) -> Dict[str, Any]:
        """个股/全市场新闻公告。"""
        from datetime import timedelta
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=n_days)).strftime("%Y%m%d")
        data = gate.ts_major_news(ts_code=ts_code, start=start, end=end)
        return {"ts_code": ts_code or "全市场", "count": len(data),
                "date_range": f"{start}-{end}", "data": data}

    def ts_ggt_daily(self, trade_date: str = None) -> Dict[str, Any]:
        """港股通日行情——南向资金参考。"""
        data = gate.ts_ggt_daily(trade_date=trade_date)
        return {"date": trade_date or datetime.now().strftime("%Y%m%d"),
                "count": len(data), "data": data}

    # ================================================================
    #  十九、三层波段筛选（大盘 → 板块 → 个股）
    # ================================================================

    def three_layer_screen(self) -> Dict[str, Any]:
        """一键运行三层波段筛选，返回完整结果字典。

        层次:
          L1 大盘: 九指数涨跌比/均值/风格 -> 仓位决策
          L2 板块: 超跌(跌幅前8) + 动量 -> 候选板块池
          L3 个股: 资金面(新浪) + 技术面(腾讯K线) + 量价 + 抗跌 -> 评分排序

        评分满分75: 资金25 + 技术20 + 量价15 + 抗跌15

        Returns:
            {"market": {...}, "sectors": {"all": [...], "candidates": [...]}, "stocks": [...]}
        """
        from scripts.screen_three_layers import ThreeLayerScreen
        s = ThreeLayerScreen()
        return s.run()


# ============================================================
#  全局单例
# ============================================================

api = MarketAPI()


# ============================================================
#  自检
# ============================================================

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("MarketAPI 自检\n" + "=" * 60)

    # 0. 交易时段判断
    ts = api.trading_status()
    freshness_icon = {"实时": "[LIVE]", "收盘": "[CLOSED]", "盘前(可能含隔夜数据)": "[PRE]", "历史(非交易日)": "[OFF]"}
    icon = freshness_icon.get(ts["data_freshness"], "[-]")
    print(f"\n[交易时段] {icon} {ts['session_cn']} | {ts['data_freshness']} | 交易日={'是' if ts['is_trading_day'] else '否'}")
    print(f"  当前时间: {ts['current_time']} 周{('一二三四五六日'[ts['weekday']])}")
    print(f"  下一事件: {ts['next_event']}")
    print(f"  建议: {ts['suggestion']}")
    print(f"  日历来源: {ts['trade_cal_source']}")

    # 1. 指数快照
    idx = api.index_snapshot()
    print(f"\n[指数快照] {len(idx)} 个")
    for i in idx[:3]:
        print(f"  {i['name']}: {i['price']:.2f}  {i['change_pct']:+.2f}%")

    # 2. 成交额
    to = api.turnover()
    print(f"\n[成交额] 两市 {to['total_yi']:.0f}亿 (沪{to['sh_yi']:.0f} 深{to['sz_yi']:.0f})")

    # 3. K线
    kl = api.kline("上证指数", 5)
    print(f"\n[K线] {kl['name']}: {kl['date_range']}  MA5({kl['indicators'].get('ma5','N/A')})")

    # 4. 北向
    nf = api.north_flow(3)
    print(f"\n[北向] {nf['summary']['conclusion']}")

    # 5. 打板
    bs = api.board_summary()
    print(f"\n[打板] 涨停{bs.get('zt_count',0)} 炸板率{bs.get('zr_rate',0):.1f}% 情绪:{bs.get('mood','?')}")

    # 6. 板块
    sc = api.sectors(5)
    print(f"\n[板块TOP5] {' > '.join(s['name'] for s in sc)}")

    # 7. 电报
    tg = api.telegraph(3)
    print(f"\n[电报] 最近{len(tg)}条")
    for t in tg:
        print(f"  {t['time']} | {t['title'][:50]}")

    # 8. 个股
    st = api.stock_realtime(["000001", "600519"])
    print(f"\n[个股]")
    for code, item in st.items():
        print(f"  {item['name']}({code}): {item['price']:.2f} {item['change_pct']:+.2f}%")

    # 9. 审计
    print(f"\n[审计报告]")
    print(api.audit_report())

    # 10. iwencai Key 状态
    key_st = api.iwencai_key_status()
    print(f"\n[iwencai Key] 有效={'是' if key_st['valid'] else '否'} | {key_st['key_masked']} | {key_st['message']}")
