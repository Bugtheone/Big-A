# -*- coding: utf-8 -*-
"""
大盘 -> 板块 -> 个股 三层波段筛选引擎
=======================================
复用方式:
  方式1 - 命令行直接跑:
    python scripts/screen_three_layers.py

  方式2 - 在代码中调用:
    from scripts.screen_three_layers import screen
    result = screen.run()
    # result = {"market": {...}, "sectors": [...], "stocks": [...]}

  方式3 - 通过 market_api 总线:
    from scripts.market_api import api
    result = api.three_layer_screen()

架构:
  L1 大盘层: 腾讯实时行情 -> 九指数涨跌比/均值/风格/仓位决策
             + 持续性确认（缓存昨日数据，跨日对比）
             + 陷阱日检测（单日急速反转6→2或2→6）
             + 信号等级：进攻确认/待确认/防御/陷阱日/震荡
  L2 板块层: 腾讯板块指数 -> 超跌(跌幅前15) + 动量(涨幅前8)
  L3 个股层: 预置成分股池 -> 腾讯K线 + 新浪资金流 -> 评分排序
             (东财push2被封，用新浪备胎拉取资金流)

评分体系 (满分75):
  资金面 25分: 20日主力净流入
  技术面 20分: 距20日均线距离
  量价   15分: 缩量下跌/放量上涨信号
  抗跌   15分: 相对板块的强弱

L1 持续性判定规则:
  - 进攻确认: 连续2天≥5红 + 趋势未加速恶化 → 尾盘可介入
  - 进攻待确认: ≥5红但昨日<4红 → 等明天确认后再动手（防假突破）
  - 防御确认: 连续2天≤3红 + 趋势恶化 → 空仓/轻仓
  - 陷阱日: 单日6→2或2→6反转 → 不操作，等待方向确认
  - 回暖/转弱待确认: 4红区间或3→4/4→3变化 → 等连续2天确认

缓存: data/l1_cache.json（自动读写，无需手动管理）

2026-07-24 初版 / 同日更新：L1 持续性确认 + 陷阱日检测
"""

import sys
import os
import urllib.request
import requests
import json
import time
import random
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

# ==============================
# 基础配置
# ==============================
_session = requests.Session()
_session.trust_env = False
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
SH_CODES = frozenset({"000300", "000905", "000016", "000688", "000852", "000010"})

# 路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
L1_CACHE_FILE = os.path.join(DATA_DIR, "l1_cache.json")

# 九个核心指数
INDICES = {
    "000001": "上证指数", "000300": "沪深300",   "000016": "上证50",
    "000905": "中证500",   "000852": "中证1000", "000688": "科创50",
    "399006": "创业板指",   "399001": "深证成指", "399005": "中小100",
}

# 板块 -> 成分股映射（预置，不依赖东财拉取）
SECTOR_STOCKS: Dict[str, List[str]] = {
    "贵金属":   ["600988","600489","601069","002155","600547","000975","001337"],
    "工业金属": ["601899","603993","600362","000630","601600","000603","601168"],
    "有色金属": ["601899","603993","002460","002466","600111","000831"],
    "能源金属": ["002460","002466","603799","300750","688005","002340","002759"],
    "小金属":   ["600111","000831","002378","600259","600392"],
    "煤炭":     ["601088","600188","601225","600348","000983","601699","601898"],
    "钢铁":     ["600019","000932","600808","000898","002756","600782"],
    "化工":     ["600309","002601","002648","600426","000830","002493"],
    "石油":     ["601857","600028","600938","600256","002207","000059"],
}

# 板块 -> 腾讯行业指数代码映射
BOARD_CODE_MAP: Dict[str, str] = {
    "贵金属":   "881160",
    "工业金属": "881161",
    "有色金属": "881162",
    "能源金属": "881163",
    "小金属":   "881164",
    "煤炭":     "881165",
    "钢铁":     "881166",
    "化工":     "881167",
    "石油":     "881168",
}


# ==============================
# 数据源：腾讯行情（GBK编码）
# ==============================
class TencentQuoter:
    """批量拉取腾讯实时行情"""

    @staticmethod
    def _prefix(code: str) -> str:
        """000001 -> sh000001 / 399006 -> sz399006"""
        low = code.lower()
        if low.startswith(("sh", "sz", "bj")):
            return low
        if code in SH_CODES or code.startswith(("5", "6", "9")):
            return f"sh{code}"
        if code.startswith(("4", "8", "92")):
            return f"bj{code}"
        return f"sz{code}"

    @classmethod
    def fetch(cls, codes: List[str]) -> Dict[str, dict]:
        """批量拉取，返回 {code: {name, price, change_pct, ...}}"""
        prefixed = [cls._prefix(c) for c in codes]
        url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", UA)
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read().decode("gbk")
        except Exception as e:
            print(f"[ERROR] 腾讯行情请求失败: {e}")
            return {}

        result = {}
        for line in data.strip().split(";"):
            if not line.strip() or "=" not in line or '"' not in line:
                continue
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            code = vals[2] if vals[2] else ""
            if not code:
                continue
            result[code] = {
                "name": vals[1],
                "code": code,
                "price": float(vals[3]) if vals[3] else 0.0,
                "last_close": float(vals[4]) if vals[4] else 0.0,
                "change_pct": float(vals[32]) if vals[32] else 0.0,
                "high": float(vals[33]) if vals[33] else 0.0,
                "low": float(vals[34]) if vals[34] else 0.0,
                "amount_wan": float(vals[37]) if vals[37] else 0.0,
                "pe_ttm": float(vals[39]) if vals[39] else 0.0,
            }
        return result


# ==============================
# 数据源：新浪资金流
# ==============================
def sina_fund_flow(code: str, days: int = 20) -> List[dict]:
    """拉取个股新浪日资金流，返回 [{date, close, net_amount, turnover}, ...]"""
    pre = ("sh" if code.startswith(("6", "9")) else "sz") + code
    url = (
        f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"MoneyFlow.ssl_qsfx_zjlrqs?page=1&num={days}&sort=opendate&asc=0&daima={pre}"
    )
    headers = {"User-Agent": UA, "Referer": "https://finance.sina.com.cn/"}
    try:
        r = _session.get(url, headers=headers, timeout=15)
        t = r.text
        arr = json.loads(t[t.index("[") : t.rindex("]") + 1])
        return [{
            "date": x.get("opendate", ""),
            "close": float(x.get("trade", 0)),
            "net_amount": float(x.get("netamount", 0)),
            "turnover": float(x.get("turnover", 0)),
        } for x in arr]
    except Exception:
        return []


# ==============================
# 数据源：腾讯K线
# ==============================
def tencent_kline(code: str, n_days: int = 20) -> List[dict]:
    """拉取腾讯前复权日K线"""
    pre = "sh" if code.startswith(("5", "6", "9")) else "sz"
    full = f"{pre}{code}"
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={full},day,,,{n_days},qfq"
    headers = {"User-Agent": UA, "Host": "web.ifzq.gtimg.cn"}
    try:
        r = _session.get(url, headers=headers, timeout=10)
        d = r.json()
        kdata = d.get("data", {}).get(full, {}).get("qfqday", []) or \
                d.get("data", {}).get(full, {}).get("day", [])
        result = []
        for k in kdata[-n_days:]:
            if len(k) >= 6:
                result.append({
                    "date": k[0], "open": float(k[1]), "close": float(k[2]),
                    "high": float(k[3]), "low": float(k[4]), "volume": float(k[5]),
                })
        return result
    except Exception:
        return []


# ==============================
# 核心：三层筛选引擎
# ==============================
class ThreeLayerScreen:
    """大盘 -> 板块 -> 个股 波段筛选"""

    def __init__(self):
        self.indices: Dict[str, dict] = {}
        self.boards: Dict[str, dict] = {}
        self.results: Dict[str, Any] = {}

    # ---------- L1 持续性缓存 ----------
    @staticmethod
    def _load_l1_cache() -> Optional[dict]:
        """加载前一个交易日的L1缓存数据"""
        if os.path.exists(L1_CACHE_FILE):
            try:
                with open(L1_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None
        return None

    @staticmethod
    def _save_l1_cache(result: dict):
        """保存今日L1数据为缓存，供明日对比"""
        os.makedirs(DATA_DIR, exist_ok=True)
        cache = {
            "date": result["date"],
            "up_count": result["up_count"],
            "down_count": result["down_count"],
            "avg_change_pct": result["avg_change_pct"],
            "style": result["style"],
        }
        with open(L1_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

    # ---------- L1: 大盘 ----------
    def layer1_market(self) -> dict:
        """第一层：大盘分析 -> 仓位决策（含持续性确认 + 陷阱日检测）"""
        print("=" * 60)
        print("  L1 大盘层: 拉取九指数实时行情...")
        print("=" * 60)

        self.indices = TencentQuoter.fetch(list(INDICES.keys()))

        up = sum(1 for q in self.indices.values() if q["change_pct"] > 0)
        down = sum(1 for q in self.indices.values() if q["change_pct"] < 0)
        total = max(up + down, 1)
        avg_chg = sum(q["change_pct"] for q in self.indices.values()) / max(len(self.indices), 1)

        sh = self.indices.get("000001", {})
        zz1000 = self.indices.get("000852", {})
        gap = sh.get("change_pct", 0) - zz1000.get("change_pct", 0)

        # 风格
        if gap > 0.5:
            style = "防御（大盘强）"
        elif gap < -0.5:
            style = "进攻（小盘强）"
        else:
            style = "均衡"

        # =====================
        # 持续性确认
        # =====================
        yesterday = self._load_l1_cache()
        y_up = yesterday.get("up_count") if yesterday else None
        y_down = yesterday.get("down_count") if yesterday else None
        y_avg = yesterday.get("avg_change_pct") if yesterday else None
        y_date = yesterday.get("date", "") if yesterday else ""

        # 趋势方向判定
        if yesterday and y_avg is not None:
            if avg_chg < 0 and y_avg < 0:
                trend_dir = "加速恶化" if avg_chg < y_avg else "恶化放缓"
            elif avg_chg < 0 and y_avg >= 0:
                trend_dir = "转弱"
            elif avg_chg >= 0 and y_avg < 0:
                trend_dir = "回暖"
            else:
                trend_dir = "加速回暖" if avg_chg > y_avg else "回暖放缓"
        else:
            trend_dir = "首日无对比"

        # 持续性信号判定
        if yesterday and y_up is not None:
            if up >= 5 and y_up >= 5 and trend_dir not in ("加速恶化", "转弱"):
                signal = "进攻确认"          # 连续2天多头 + 趋势不差
            elif up >= 5 and y_up < 4:
                signal = "进攻待确认"        # 今天很强但昨天弱，等明天验证
            elif up <= 3 and y_up <= 3 and trend_dir in ("加速恶化", "转弱", "恶化放缓"):
                signal = "防御确认"          # 连续2天空头 + 趋势恶化
            elif up <= 3 and y_up <= 3:
                signal = "防御中"            # 连续2天空头但趋势未恶化
            elif up <= 3 and y_up >= 5:
                signal = "陷阱日（进攻→防御反转）"  # 急速转空
            elif up >= 5 and y_up <= 3:
                signal = "陷阱日（防御→进攻反转）"  # 抄底脉冲
            elif up >= 4 and y_up <= 3:
                signal = "回暖待确认"
            elif up <= 3 and y_up >= 4:
                signal = "转弱待确认"
            else:
                signal = "震荡"
        else:
            signal = "首日运行"

        trap_day = signal.startswith("陷阱日")

        # 仓位 + 操作建议（综合持续性）
        if signal == "进攻确认":
            pos = "重仓 70-80%"
            action = "尾盘可确认介入"
        elif signal == "进攻待确认":
            pos = "观察（等明天确认）"
            action = "不急于进场，等明天 L1 确认持续性后再动手"
        elif signal in ("防御确认", "防御中"):
            pos = "空仓/10%试仓"
            action = "防御模式，全部列入观察池，不开新仓"
        elif signal == "陷阱日（进攻→防御反转）":
            pos = "减仓/空仓"
            action = "急速恶化！已持仓应减仓/止损，不开新仓"
        elif signal == "陷阱日（防御→进攻反转）":
            pos = "切勿追高"
            action = "脉冲行情不参与，等回踩确认再考虑"
        elif signal == "回暖待确认":
            pos = "轻仓 20-30%"
            action = "列入观察池，等明日确认回暖信号"
        elif signal == "转弱待确认":
            pos = "防御轻仓 20-30%"
            action = "减仓为主，不开新仓，等明天确认方向"
        elif signal == "震荡":
            if up >= 4 and avg_chg > 0:
                pos = "半仓 40-50%"
                action = "收盘后分析，次日定夺"
            elif up >= 3 and avg_chg > -1.0:
                pos = "轻仓 30-40%"
                action = "观察为主，不宜加仓"
            else:
                pos = "防御轻仓 20-30%"
                action = "列入观察池，等待转暖"
        else:
            # 首日运行，用单日逻辑暂定
            if up >= 6 and avg_chg > 0.5:
                pos = "重仓 70-80%"
            elif up >= 4 and avg_chg > -0.5:
                pos = "半仓 40-50%"
            elif up >= 3 and avg_chg > -1.0:
                pos = "轻仓 30-40%"
            elif up >= 1 and avg_chg > -2.0:
                pos = "防御轻仓 20-30%"
            else:
                pos = "空仓/10%试仓"
            action = "首日运行，无对比数据，明天才具备持续性判定能力"

        result = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "up_count": up, "down_count": down,
            "avg_change_pct": round(avg_chg, 2),
            "style": style,
            "position": pos,
            "signal": signal,
            "trend_direction": trend_dir,
            "trap_day": trap_day,
            "action": action,
            "yesterday": {"date": y_date, "up_count": y_up, "avg_change_pct": y_avg}
                         if yesterday else None,
            "details": {INDICES.get(c, c): q for c, q in self.indices.items()},
        }

        # 保存今日数据供明日对比
        self._save_l1_cache(result)

        # ---------- 输出 ----------
        detail_lines = []
        for code, name in INDICES.items():
            q = self.indices.get(code, {})
            if q:
                a = "[UP]" if q["change_pct"] > 0 else "[DN]"
                detail_lines.append(f"  {a} {name}: {q['change_pct']:+.2f}%")

        if yesterday:
            print(f"  [昨日 {y_date}] {y_up}涨{total - y_up}跌 均值{y_avg:+.2f}%")
            print(f"  [今日] {up}涨{down}跌 均值{avg_chg:+.2f}% | 趋势:{trend_dir} | 信号:{signal}")
        else:
            print(f"  [今日] {up}涨{down}跌 均值{avg_chg:+.2f}% | 信号:{signal}（首日）")

        print(f"  风格:{style} | 仓位:{pos}")
        if trap_day:
            print(f"  *** 陷阱日！{action} ***")
        else:
            print(f"  操作建议: {action}")

        for line in detail_lines:
            print(line)

        self.results["market"] = result
        return result

    # ---------- L2: 板块 ----------
    def layer2_sectors(self) -> List[dict]:
        """第二层：板块筛选 -> 超跌 + 动量"""
        print("\n" + "=" * 60)
        print("  L2 板块层: 拉取行业板块排名...")
        print("=" * 60)

        # 尝试通过腾讯行业指数代码拉取
        board_codes = list(BOARD_CODE_MAP.values())
        board_quotes = TencentQuoter.fetch(board_codes)

        # 反向映射 code -> name
        code_to_name = {v: k for k, v in BOARD_CODE_MAP.items()}

        boards = []
        for code, q in board_quotes.items():
            name = code_to_name.get(code, q.get("name", code))
            boards.append({
                "code": code, "name": name,
                "change_pct": q.get("change_pct", 0),
                "price": q.get("price", 0),
            })

        if not boards:
            print("  [WARN] 腾讯板块指数拉取失败，使用预置数据")
            boards = [
                {"name": "贵金属",   "change_pct": -4.56},
                {"name": "工业金属", "change_pct": -4.54},
                {"name": "有色金属", "change_pct": -4.11},
                {"name": "能源金属", "change_pct": -3.39},
                {"name": "小金属",   "change_pct": -3.20},
                {"name": "煤炭",     "change_pct": -2.80},
                {"name": "钢铁",     "change_pct": -2.50},
            ]

        boards_sorted = sorted(boards, key=lambda x: x["change_pct"])
        boards_top = sorted(boards, key=lambda x: x["change_pct"], reverse=True)

        print("  [超跌维度] 跌幅前列:")
        for i, b in enumerate(boards_sorted[:8]):
            print(f"    {i+1}. {b['name']:<8s} {b['change_pct']:+.2f}%")

        print("  [动量维度] 涨幅前列:")
        for i, b in enumerate(boards_top[:5]):
            print(f"    {i+1}. {b['name']:<8s} {b['change_pct']:+.2f}%")

        # 候选 = 跌幅前5且在我们的成分股池中
        candidates = [b for b in boards_sorted if b["name"] in SECTOR_STOCKS][:5]

        self.results["sectors"] = {"all": boards_sorted, "candidates": candidates}
        return candidates

    # ---------- L3: 个股 ----------
    def layer3_stocks(self, candidate_sectors: List[dict]) -> List[dict]:
        """第三层：个股精选 -> 资金面 + 技术面 + 量价 + 抗跌 综合评分"""
        print("\n" + "=" * 60)
        print("  L3 个股层: 精选标的...")
        print("=" * 60)

        # 收集所有候选股票代码
        all_codes = set()
        for sec in candidate_sectors:
            codes = SECTOR_STOCKS.get(sec["name"], [])
            all_codes.update(codes)

        # 批量拉取实时行情
        all_quotes = TencentQuoter.fetch(list(all_codes))
        print(f"  拉取 {len(all_quotes)}/{len(all_codes)} 只股票实时行情")

        # 逐个分析
        all_stocks = []
        for sec in candidate_sectors:
            sec_name = sec["name"]
            sec_chg = sec["change_pct"]
            codes = SECTOR_STOCKS.get(sec_name, [])
            if not codes:
                continue

            print(f"\n  [{sec_name}] {sec_chg:+.2f}%")
            for code in codes:
                q = all_quotes.get(code)
                if not q:
                    continue

                time.sleep(0.5)  # 限流

                # K线 -> 技术面
                klines = tencent_kline(code, 20)
                # 资金流
                fund_data = sina_fund_flow(code, 20)

                score_result = self._score_stock(q, sec_chg, klines, fund_data)
                score_result["sector"] = sec_name
                score_result["sector_chg"] = sec_chg
                all_stocks.append(score_result)

                sig = ""
                if score_result["score"] >= 40:
                    sig = " ** 关注"
                elif score_result["score"] >= 25:
                    sig = " * 候选"

                print(f"    [{score_result['grade']}级/得分{score_result['score']:>2}] "
                      f"{code} {q['name']:<8s} {q['change_pct']:+.2f}% "
                      f"MA20距:{score_result['ma20_dist']:+.1f}% "
                      f"资金20日:{score_result['net_20d_yi']:+.2f}亿"
                      f"{sig}")
                for r in score_result.get("reasons", []):
                    print(f"        -> {r}")

        # 排序
        all_stocks.sort(key=lambda x: x["score"], reverse=True)

        self.results["stocks"] = all_stocks
        return all_stocks

    # ---------- 评分引擎 ----------
    @staticmethod
    def _score_stock(quote: dict, sector_chg: float,
                     klines: List[dict], fund_data: List[dict]) -> dict:
        """给单只股票打分 (满分75)"""
        score = 0
        reasons = []
        code = quote.get("code", "")
        name = quote.get("name", "")

        # --- 技术面 (20分): MA20距离 ---
        if klines and len(klines) >= 10:
            closes = [k["close"] for k in klines]
            ma20 = sum(closes) / len(closes) if closes else 0
            last_close = closes[-1]
            ma20_dist = (last_close / ma20 - 1) * 100 if ma20 else 0

            if abs(ma20_dist) < 5:
                score += 20
                reasons.append(f"贴近20日线({ma20_dist:+.1f}%) [20分]")
            elif -10 < ma20_dist < 0:
                score += 15
                reasons.append(f"低于20日线({ma20_dist:+.1f}%) 超跌可布局 [15分]")
            elif ma20_dist <= -15:
                score += 5
                reasons.append(f"远离20日线({ma20_dist:+.1f}%) 弱势 [5分]")
            elif ma20_dist > 0:
                score += 10
                reasons.append(f"高于20日线({ma20_dist:+.1f}%) [10分]")
            else:
                score += 10
                reasons.append(f"低于20日线({ma20_dist:+.1f}%) 偏离较大 [10分]")
        else:
            ma20_dist = 0.0
            reasons.append("K线数据不足")

        # --- 量价关系 (15分) ---
        vol_signal = "[N/A]"
        vol_score = 0
        if klines and len(klines) >= 10:
            mid = len(klines) // 2
            vol_first = sum(k["volume"] for k in klines[:mid])
            vol_second = sum(k["volume"] for k in klines[mid:])
            chg_second = (closes[-1] / closes[mid] - 1) * 100 if closes[mid] else 0

            if chg_second < -3 and vol_second < vol_first * 0.8:
                vol_signal = "下跌缩量(健康)"
                vol_score = 15
            elif chg_second > 0 and vol_second > vol_first * 1.2:
                vol_signal = "反弹放量(积极)"
                vol_score = 15
            elif chg_second < -3 and vol_second > vol_first:
                vol_signal = "放量下跌(危险)"
                vol_score = 0
            else:
                vol_signal = "量价平稳"
                vol_score = 8

            score += vol_score
            reasons.append(f"量价:{vol_signal} [{vol_score}分]")

        # --- 资金面 (25分): 20日主力净流入 ---
        total_net = sum(f.get("net_amount", 0) for f in fund_data) if fund_data else 0
        net_yi = total_net / 1e8
        if total_net > 8e8:
            score += 25
            reasons.append(f"主力净买{net_yi:.1f}亿(强力) [25分]")
        elif total_net > 3e8:
            score += 18
            reasons.append(f"主力净买{net_yi:.1f}亿(积极) [18分]")
        elif total_net > 0:
            score += 10
            reasons.append(f"主力微买{net_yi:.2f}亿 [10分]")
        elif total_net > -3e8:
            score += 5
            reasons.append(f"主力微出{abs(net_yi):.2f}亿 [5分]")
        else:
            reasons.append(f"主力流出{abs(net_yi):.1f}亿(减分)")

        # --- 相对强度 (15分): 与板块对比 ---
        rel = quote.get("change_pct", 0) - sector_chg
        if rel > 1:
            score += 15
            reasons.append(f"显著抗跌(+{rel:.1f}%) [15分]")
        elif rel > 0:
            score += 10
            reasons.append(f"略抗跌(+{rel:.1f}%) [10分]")
        elif rel > -2:
            score += 5
            reasons.append(f"跟随板块({rel:+.1f}%) [5分]")

        # --- 评级 ---
        if score >= 55:
            grade = "A"
        elif score >= 40:
            grade = "B"
        elif score >= 25:
            grade = "C"
        else:
            grade = "D"

        return {
            "code": code, "name": name,
            "price": quote.get("price", 0),
            "change_pct": quote.get("change_pct", 0),
            "ma20_dist": round(ma20_dist, 1),
            "vol_signal": vol_signal,
            "net_20d_yi": round(net_yi, 2),
            "score": score,
            "grade": grade,
            "reasons": reasons,
        }

    # ---------- 一键运行 ----------
    def run(self) -> Dict[str, Any]:
        """一键执行三层筛选，返回完整结果字典"""
        market = self.layer1_market()
        candidates = self.layer2_sectors()
        all_stocks = self.layer3_stocks(candidates)

        # --- 最终汇总 ---
        print("\n\n" + "=" * 60)
        print("  [最终汇总]")
        print("=" * 60)

        # L1 持续性信号
        sig = market.get("signal", "—")
        trend = market.get("trend_direction", "—")
        trap = market.get("trap_day", False)
        y = market.get("yesterday")
        if y:
            print(f"  L1: 昨日{y['up_count']}涨 → 今日{market['up_count']}涨{market['down_count']}跌 "
                  f"均值{market['avg_change_pct']:+.2f}%")
            print(f"      趋势:{trend} | 信号:{sig} | {'⚠️ 陷阱日' if trap else market.get('action', '—')}")
        else:
            print(f"  L1: {market['up_count']}涨{market['down_count']}跌 "
                  f"均值{market['avg_change_pct']:+.2f}% | 信号:{sig}")
        print(f"      仓位: {market['position']}")
        print(f"  L2: 候选板块 {len(candidates)} 个")
        print(f"  L3: 入选个股 {len([s for s in all_stocks if s['score'] >= 25])} 只")
        print()

        qualified = [s for s in all_stocks if s["score"] >= 25]
        if qualified:
            print("  优先级排序 (得分 >= 25):")
            for i, s in enumerate(qualified[:10]):
                print(f"    {i+1}. [{s['grade']}级] {s['code']} {s['name']:<8s} "
                      f"[{s['sector']}] 得分{s['score']} "
                      f"{s['change_pct']:+.2f}% "
                      f"MA20:{s['ma20_dist']:+.1f}% "
                      f"资金:{s['net_20d_yi']:+.2f}亿")
        else:
            print("  无符合条件的个股 -> 建议观望")

        # 操作建议根据信号分级
        if trap:
            print(f"\n  *** {sig} -> {market.get('action', '不操作')} ***")
        elif sig == "进攻确认":
            print(f"\n  *** 进攻信号确认！可尾盘介入 ***")
            print(f"  建仓: 分批 1/3 -> 确认止跌 -> 加至 2/3")
            print(f"  止损: 今日低点 -3% / 破20日线")
            print(f"  目标: 10-15% 收益 / 2-4周")
        elif sig in ("防御确认", "防御中"):
            print(f"\n  *** 防御模式 — 不开新仓，持仓设止损 ***")
        elif sig in ("进攻待确认", "回暖待确认"):
            print(f"\n  *** 等明天确认持续性后再决策 ***")
            print(f"  预选标的已列入观察池")
        else:
            print(f"\n  操作建议: {market.get('action', '观望')}")

        print("\n三层筛选完成。")

        return self.results


# ==============================
# 快捷入口
# ==============================
screen = ThreeLayerScreen()


# ==============================
# CLI 入口
# ==============================
if __name__ == "__main__":
    print("三层波段筛选引擎启动...")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    screen.run()
