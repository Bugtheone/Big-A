#!/usr/bin/env python3
"""
东财数据源统一模块（单例模式）
- 封装东财 push2 / 同花顺 data.10jqka 已验证端点
- 对标 tushare_api.py 的 get_pro() / tencent_api.py 的 get_tencent() 模式

端点（均已验证可用 2026-07-23）:
  push2.eastmoney.com        — kamt.kline (北向资金，v2 格式 hk2sh/hk2sz)
  data.10jqka.com.cn         — limit_up_pool (同花顺涨停揭秘、涨停原因/封板率)

已弃用端点（IP 封禁）:
  push2ex.eastmoney.com     — getTopicZTPool/ZBPool/DTPool → 用 ths_limit_up_pool() 替代
  push2.eastmoney.com       — ulist.np (涨跌家数) → Tencent fetch_realtime()
  push2.eastmoney.com       — clist (热门板块)  → Tencent fetch_sectors()

用法:
  from scripts.eastmoney_api import get_eastmoney
  em = get_eastmoney()
  nf = em.fetch_north_flow()               # 北向资金，返回 [{date, total_yi, buy_yi, sell_yi}]
  zt = em.ths_limit_up_pool("20260723")    # 同花顺涨停揭秘 [{code, name, reason, board_type, ...}]
"""

import csv
import json
import os
import time
from typing import Optional
from datetime import datetime, timedelta

import requests

# 模块级 session（trust_env=False 防止系统代理干扰）
_em_session = requests.Session()
_em_session.trust_env = False

# 项目根目录（scripts/ 的上层）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================
# 全局单例
# ============================

_eastmoney_instance: Optional["EastMoneyAPI"] = None


def get_eastmoney() -> "EastMoneyAPI":
    global _eastmoney_instance
    if _eastmoney_instance is None:
        _eastmoney_instance = EastMoneyAPI()
    return _eastmoney_instance


class EastMoneyAPI:
    """东财 + 同花顺行情 API 统一入口"""

    PUSH2_URL = "https://push2.eastmoney.com"
    PUSH2EX_URL = "https://push2ex.eastmoney.com"
    THS_URL = "https://data.10jqka.com.cn"

    # push2ex 共同参数（已弃用，保留备用）
    _POOL_UT = "7eea3edcaed734bea9cbfce24459ed535"

    def __init__(self, cooldown: float = 0.5):
        self._session: Optional[requests.Session] = None
        self._cooldown = cooldown
        self._last_call = 0.0

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            s = requests.Session()
            s.trust_env = False
            s.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://data.eastmoney.com/",
            })
            s.timeout = 15
            self._session = s
        return self._session

    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < self._cooldown:
            time.sleep(self._cooldown - elapsed)
        self._last_call = time.time()

    # ========== 北向资金（2026-07-24 数据栈重构） ==========
    # 背景：2024年8月19日起，沪深港交易所不再披露北向每日净买入交易额，
    # 东财 kamt 北向（hk2sh/hk2sz）永久归零。
    #
    # 新数据栈（优先级从高到低）：
    #   ① 同花顺 hexin hgt — 沪股通分钟级真实值（主源）
    #   ② Tushare ggt_sz        — 深股通估算值（补充）
    #   ③ Tushare moneyflow_hsgt — 沪+深全量估算（降级）
    #   ④ 本地 CSV 缓存          — 历史数据回查
    #   ⑤ 东财 kamt              — 回退检测（永久归零）

    # ── 本地 CSV 缓存 ──────────────────────────────────────────────
    _NB_CACHE = os.path.join(BASE_DIR, "data", "northbound_cache.csv")

    # 北向单日净买入异常阈值(亿元)：真实极值一般 |x| < 150，
    # 超过视为接口坏点/占位值（如 hexin 深股通 379.75 坏点）
    _NB_SUSPECT_ABS = 150.0

    @staticmethod
    def _is_suspect_nb_value(v) -> bool:
        """北向数值质量检查：超阈值/不可解析 → 判定为脏数据。
        None/空值视为缺失(跳过，由调用方决定)，不误标为脏。
        """
        if v is None or v == "":
            return False
        try:
            return abs(float(v)) > EastMoneyAPI._NB_SUSPECT_ABS
        except (ValueError, TypeError):
            return True

    def _load_northbound_cache(self) -> list:
        """从本地 CSV 加载北向历史数据，并做质量清洗。
        - 异常阈值过滤：|hgt|/|sgt| > 150 亿 → 置 None（接口坏点/占位值）
        - 连续重复检测：连续 ≥2 天与前一交易日完全相同 → 占位重复，置 None
        （真实资金流逐日相等概率≈0）
        返回: [{date, hgt_yi, sgt_yi, total_yi, source, note}, ...]
        """
        if not os.path.exists(self._NB_CACHE):
            return []
        rows = []
        try:
            with open(self._NB_CACHE, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    hgt = None
                    if row.get("hgt_yi") not in ("", "None", None):
                        try:
                            hgt = round(float(row["hgt_yi"]), 2)
                        except (ValueError, TypeError):
                            hgt = None
                    sgt = None
                    if row.get("sgt_yi") not in ("", "None", None):
                        try:
                            sgt = round(float(row["sgt_yi"]), 2)
                        except (ValueError, TypeError):
                            sgt = None
                    total = 0.0
                    try:
                        total = round(float(row.get("total_yi", 0)), 2)
                    except (ValueError, TypeError):
                        total = 0.0
                    rows.append({
                        "date": row["date"],
                        "hgt_yi": hgt,
                        "sgt_yi": sgt,
                        "total_yi": total,
                        "source": row.get("source", "cache"),
                        "note": row.get("note", ""),
                    })
        except Exception as e:
            print(f"[cache] 加载北向缓存失败: {e}")
            return []

        # ── 质量清洗①：异常阈值过滤 ──────────────────────────────
        dirty_cnt = 0
        for r in rows:
            for key in ("hgt_yi", "sgt_yi"):
                if self._is_suspect_nb_value(r[key]):
                    r[key] = None
                    r["note"] = (r["note"] + f"; {key}超阈值已清洗").strip("; ")
                    dirty_cnt += 1
        if dirty_cnt:
            print(f"[cache] 北向缓存质量清洗: {dirty_cnt} 个字段超阈值已置空")

        # ── 质量清洗②：连续重复占位检测（按日期升序扫描）─────────
        rows_sorted = sorted(rows, key=lambda x: x["date"])
        for i in range(1, len(rows_sorted)):
            prev, cur = rows_sorted[i - 1], rows_sorted[i]
            for key in ("hgt_yi", "sgt_yi"):
                if cur[key] is None:
                    continue
                if cur[key] == prev[key] and prev[key] is not None:
                    cur[key] = None
                    cur["note"] = (cur["note"] + f"; {key}连续重复占位已清洗").strip("; ")
        return rows_sorted

    def _save_northbound_cache(self, items: list):
        """保存北向数据到本地 CSV 缓存（按日期去重覆盖）。"""
        existing = {}
        nb_fieldnames = ["date", "hgt_yi", "sgt_yi", "total_yi", "source", "note"]
        if os.path.exists(self._NB_CACHE):
            try:
                with open(self._NB_CACHE, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        d = row.get("date", "")
                        if d:
                            # 规范化字段：仅保留已知列，忽略多余列(BOM/脏列)
                            existing[d] = {
                                k: row.get(k, "") for k in nb_fieldnames
                            }
            except Exception:
                pass
        for item in items:
            d = item.get("date", "")
            if not d:
                continue
            # 写入前清洗：超阈值坏点/占位值 → 置空，防止脏数据入库
            hgt_v = item.get("hgt_yi")
            sgt_v = item.get("sgt_yi")
            note = item.get("note", "")
            cleaned = False
            if self._is_suspect_nb_value(hgt_v):
                hgt_v, cleaned = "", True
            if self._is_suspect_nb_value(sgt_v):
                sgt_v, cleaned = "", True
            if cleaned:
                note = (note + "; 写入前清洗:坏点已置空").strip("; ")
            existing[d] = {
                "date": d,
                "hgt_yi": hgt_v if hgt_v not in ("", None) else "",
                "sgt_yi": sgt_v if sgt_v not in ("", None) else "",
                "total_yi": item.get("total_yi", ""),
                "source": item.get("source", ""),
                "note": note,
            }
        fieldnames = ["date", "hgt_yi", "sgt_yi", "total_yi", "source", "note"]
        try:
            os.makedirs(os.path.dirname(self._NB_CACHE), exist_ok=True)
            with open(self._NB_CACHE, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for d in sorted(existing.keys(), reverse=True):
                    writer.writerow(existing[d])
            print(f"[cache] 北向缓存已更新，共 {len(existing)} 条")
        except Exception as e:
            print(f"[cache] 保存北向缓存失败: {e}")

    # ── ① 同花顺 hexin API（主源 沪股通分钟级真实值）───────────────
    def _fetch_north_flow_hexin(self) -> list:
        """主源：同花顺 hexin API 沪股通分钟级真实值。

        2024.8.19 后交易所不再披露北向净买入，此端点是目前唯一可靠数据源。

        端点返回分钟级累计净买入（单位亿元），每天约262个数据点：
        - hgt（沪股通）：262点，最新点=当日累计净买入
        - sgt（深股通）：仅35点，不可靠，需用 Tushare 补充

        返回: [{date, hgt_yi, sgt_yi, total_yi, source, note}] 或 []
        """
        url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as e:
            print(f"[hexin] API 请求失败: {e}")
            return []

        try:
            if isinstance(raw, dict) and "data" in raw:
                data_list = raw["data"]
                if isinstance(data_list, list) and len(data_list) > 0:
                    data = data_list[0]
                else:
                    data = raw
            else:
                data = raw

            hgt_vals = data.get("hgt", [])
            sgt_vals = data.get("sgt", [])
            time_vals = data.get("time", [])

            if not hgt_vals or not time_vals:
                print("[hexin] hgt 或 time 数据为空")
                return []

            hgt_yi = hgt_vals[-1] if hgt_vals else 0
            sgt_yi = sgt_vals[-1] if sgt_vals else None

            today = time.strftime("%Y-%m-%d")
            items = [{
                "date": today,
                "hgt_yi": round(float(hgt_yi), 2),
                "sgt_yi": round(float(sgt_yi), 2) if sgt_yi is not None else None,
                "total_yi": round(float(hgt_yi), 2),
                "source": "hexin_hgt",
                "note": (
                    f"同花顺沪股通分钟级({len(hgt_vals)}点)，"
                    f"sgt({len(sgt_vals)}点仅参考)"
                ),
            }]

            self._save_northbound_cache(items)
            return items

        except Exception as e:
            print(f"[hexin] 数据解析失败: {e}")
            return []

    # ── ② Tushare moneyflow_hsgt（补充深股通 / 降级全量）─────────
    def _fetch_north_flow_tushare(self, lmt: int = 1) -> list:
        """降级源：Tushare moneyflow_hsgt（估算值，沪市+深市）。
        返回: [{date, hgt_yi, sgt_yi, total_yi, source, note}, ...]
        """
        results = []
        try:
            from scripts.tushare_api import get_pro
            pro = get_pro()
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=max(14, lmt * 3))
            df = pro.moneyflow_hsgt(
                start_date=start_dt.strftime("%Y%m%d"),
                end_date=end_dt.strftime("%Y%m%d"),
            )
            if df is not None and not df.empty:
                df = df.sort_values("trade_date", ascending=False)
                for _, row in df.head(lmt).iterrows():
                    ggt_ss = float(row.get("ggt_ss", 0) or 0) / 10000
                    ggt_sz = float(row.get("ggt_sz", 0) or 0) / 10000
                    total = ggt_ss + ggt_sz
                    date_raw = str(row.get("trade_date", ""))
                    if len(date_raw) == 8:
                        date_fmt = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}"
                    else:
                        date_fmt = date_raw
                    results.append({
                        "date": date_fmt,
                        "hgt_yi": round(ggt_ss, 2),
                        "sgt_yi": round(ggt_sz, 2),
                        "total_yi": round(total, 2),
                        "source": "tushare",
                        "note": "Tushare估算值（沪市ggt_ss+深市ggt_sz，免费用户精度受限）",
                    })
        except Exception:
            pass
        return results

    # ── ⑤ 东财 kamt（降级 / 回退检测）──────────────────────────────
    def _fetch_north_flow_kamt(self, lmt: int = 1) -> list:
        """降级源：东财 kamt.kline (2024.8.19后北向永久归零，仅作回退检测)
        返回: [{date, hgt_yi, sgt_yi, total_yi, source, note}, ...]
        """
        self._throttle()
        url = f"{self.PUSH2_URL}/api/qt/kamt.kline/get"
        params = {
            "fields1": "f1,f2,f3,f4",
            "fields2": "f51,f52,f53,f54",
            "klt": "101",
            "lmt": str(lmt),
        }
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[EastMoneyAPI] 北向资金请求失败: {e}")
            return []

        if not data or "data" not in data:
            return []

        inner = data["data"]

        # --- v1 旧格式：klines ---
        klines = inner.get("klines", [])
        if klines:
            results = []
            for row in klines:
                parts = row.split(",")
                if len(parts) < 4:
                    continue
                try:
                    net = float(parts[1]) if parts[1] and parts[1] != "-" else 0.0
                    results.append({
                        "date": parts[0],
                        "hgt_yi": None,
                        "sgt_yi": None,
                        "total_yi": round(net / 10000, 2),
                        "source": "kamt_kline",
                        "note": "2024.8.19后北向永久归零，此数据不可靠",
                    })
                except (ValueError, IndexError):
                    continue
            return results

        # --- v2 新格式：hk2sh / hk2sz ---
        hk2sh = inner.get("hk2sh", [])
        hk2sz = inner.get("hk2sz", [])

        if not hk2sh and not hk2sz:
            return []

        date_map = {}
        for label, rows in [("sh", hk2sh), ("sz", hk2sz)]:
            for row in rows:
                parts = row.split(",")
                if len(parts) < 2:
                    continue
                date = parts[0]
                try:
                    net = float(parts[1]) if parts[1] and parts[1] != "-" else 0.0
                except (ValueError, IndexError):
                    net = 0.0
                if date not in date_map:
                    date_map[date] = {"sh_net": 0.0, "sz_net": 0.0}
                if label == "sh":
                    date_map[date]["sh_net"] = net
                else:
                    date_map[date]["sz_net"] = net

        results = []
        for date in sorted(date_map.keys()):
            item = date_map[date]
            net = item["sh_net"] + item["sz_net"]
            results.append({
                "date": date,
                "hgt_yi": round(item["sh_net"] / 10000, 2),
                "sgt_yi": round(item["sz_net"] / 10000, 2),
                "total_yi": round(net / 10000, 2),
                "source": "kamt_hk2sh_hk2sz",
                "note": "2024.8.19后北向永久归零，此数据不可靠",
            })
        return results

    # ========== 北向资金主入口 ======================================
    def fetch_north_flow(self, lmt: int = 1, use_cache: bool = True) -> list:
        """获取北向资金日度数据（多源合并优先级链）。

        优先级:
          ① 同花顺 hexin hgt（沪股通分钟级真实值，主源）
          ② + Tushare ggt_sz（深股通估算，补充）
          ③ Tushare moneyflow_hsgt（沪+深全量估算，降级）
          ④ 本地 CSV 缓存（历史回查）
          ⑤ 东财 kamt（回退检测）

        返回: [{date, hgt_yi, sgt_yi, total_yi, source, note}, ...]
        """
        results = []
        today = datetime.now().strftime("%Y-%m-%d")

        # === ① + ② 主源: hexin hgt + Tushare sgt ===
        try:
            hexin_data = self._fetch_north_flow_hexin()
            if hexin_data:
                hgt_item = hexin_data[0]
                hgt_yi = hgt_item.get("hgt_yi", 0) or 0

                # 补充 Tushare 深股通
                sgt_yi = None
                tushare_note = ""
                try:
                    ts_all = self._fetch_north_flow_tushare(lmt=1)
                    if ts_all:
                        sgt_yi = ts_all[0].get("sgt_yi")
                except Exception:
                    pass

                if sgt_yi is not None:
                    total_yi = round(hgt_yi + sgt_yi, 2)
                    source = "hexin+tushare"
                    note = (
                        f"沪(同花顺分钟级:{hgt_yi}亿)"
                        f" + 深(Tushare估算:{sgt_yi}亿)"
                    )
                else:
                    total_yi = round(hgt_yi, 2)
                    source = "hexin_hgt"
                    note = (
                        f"仅沪股通(同花顺分钟级:{hgt_yi}亿)，"
                        f"深股通数据暂缺"
                    )

                results.append({
                    "date": today,
                    "hgt_yi": hgt_item["hgt_yi"],
                    "sgt_yi": sgt_yi,
                    "total_yi": total_yi,
                    "source": source,
                    "note": note,
                })

                # 如果请求多天，补缓存中的历史数据
                if lmt > 1:
                    cached = self._load_northbound_cache()
                    cached_dates = {r["date"] for r in results}
                    for c in cached:
                        if c["date"] not in cached_dates:
                            c["source"] = c.get("source", "cache")
                            results.append(c)
                            if len(results) >= lmt:
                                break

                return results[:lmt]
        except Exception:
            pass

        # === ③ 降级: Tushare 全量 ===
        ts_results = self._fetch_north_flow_tushare(lmt=lmt)
        if ts_results:
            for r in ts_results:
                r["source"] = r.get("source", "tushare")
            return ts_results[:lmt]

        # === ④ 降级: CSV 缓存 ===
        if use_cache:
            cached = self._load_northbound_cache()
            if cached:
                for c in cached:
                    c["note"] = f"离线缓存({c.get('source', 'cache')})"
                return cached[:lmt]

        # === ⑤ 降级: 东财 kamt（最后手段） ===
        kamt_results = self._fetch_north_flow_kamt(lmt=lmt)
        if kamt_results:
            return kamt_results[:lmt]

        # === 最终降级: 强制读缓存 ===
        cached = self._load_northbound_cache()
        if cached:
            for c in cached:
                c["note"] = f"离线缓存-{c.get('date', '?')}({c.get('source', 'cache')})"
            return cached[:lmt]

        return [{
            "date": today,
            "hgt_yi": None,
            "sgt_yi": None,
            "total_yi": 0,
            "source": "none",
            "note": "所有数据源均不可用",
        }]

    def fetch_north_flow_latest(self) -> Optional[dict]:
        """获取最新一条北向资金数据。
        返回: {date, hgt_yi, sgt_yi, total_yi, source, note} 或 None
        """
        rows = self.fetch_north_flow(lmt=1)
        return rows[0] if rows else None

    # ========== 同花顺涨停揭秘（替代 push2ex 打板池） ==========

    _THS_LIMIT_UP_FIELDS = (
        "199112,10,9001,330323,330324,330325,"
        "9002,330329,133971,133970,1968584,3475914,9003,9004"
    )

    def ths_limit_up_pool(self, date: str, page: int = 1, limit: int = 200) -> dict:
        """
        同花顺涨停揭秘 — 涨停池 + 炸板/跌停统计。
        替代 push2ex getTopicZTPool/ZBPool/DTPool（IP 级封禁）。

        参数:
          date: 日期 YYYYMMDD（如 "20260723"）
          page: 分页（1 起）
          limit: 每页条数（最大 200）

        返回: dict {
            "total": int,                   # 实际封板数
            "zb_count": int,               # 炸板数（触及但未封板）
            "dt_count": int,               # 跌停数
            "zr_rate": float,              # 炸板率 %
            "zt_open": int,                # 一字板数
            "zt_yesterday": int,           # 昨日涨停数
            "zt_list": list,               # [{code, name, limit_up_type, reason_type,
                                           #   high_days, high_days_value, first_time,
                                           #   change_rate, turnover_rate, suc_rate,
                                           #   order_amount, is_again, ...}]
        }
        """
        self._throttle()
        url = f"{self.THS_URL}/dataapi/limit_up/limit_up_pool"
        params = {
            "page": str(page),
            "limit": str(limit),
            "field": self._THS_LIMIT_UP_FIELDS,
            "filter": "HS,GEM2STAR",
            "order_field": "330324",
            "order_type": "0",
            "date": date,
        }
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[EastMoneyAPI] 同花顺涨停揭秘请求失败: {e}")
            return {"total": 0, "zb_count": 0, "dt_count": 0, "zr_rate": 0.0,
                    "zt_open": 0, "zt_yesterday": 0, "zt_list": []}

        if not data or data.get("status_code") != 0:
            code = data.get("status_code", "?") if data else "?"
            msg = data.get("status_msg", "未知错误") if data else "无数据"
            print(f"[EastMoneyAPI] 同花顺涨停揭秘返回异常: code={code} msg={msg}")
            return {"total": 0, "zb_count": 0, "dt_count": 0, "zr_rate": 0.0,
                    "zt_open": 0, "zt_yesterday": 0, "zt_list": []}

        inner = data.get("data", {})

        # 涨跌停统计
        lu = inner.get("limit_up_count", {})
        ld = inner.get("limit_down_count", {})
        today_lu = lu.get("today", {})
        yesterday_lu = lu.get("yesterday", {})
        today_ld = ld.get("today", {})

        total = int(today_lu.get("num", 0) or 0)             # 实际封板数
        zt_history = int(today_lu.get("history_num", 0) or 0)  # 触及涨停总数
        zt_open = int(today_lu.get("open_num", 0) or 0)       # 一字板
        zt_yesterday = int(yesterday_lu.get("num", 0) or 0)    # 昨日涨停数
        dt_count = int(today_ld.get("num", 0) or 0)            # 跌停数
        dt_yesterday = int(ld.get("yesterday", {}).get("num", 0) or 0)

        # 炸板 = 触及涨停但未封板
        zb_count = max(0, zt_history - total)
        total_attempt = zt_history if zt_history > 0 else 1
        zr_rate = round(zb_count / total_attempt * 100, 1)

        # 涨停列表
        items = inner.get("info", [])
        zt_list = []
        for item in items:
            try:
                code = str(item.get("code", ""))
                name = str(item.get("name", ""))
                limit_up_type = str(item.get("limit_up_type", ""))    # 换手板/一字板/T字板
                reason_type = str(item.get("reason_type", ""))        # 涨停原因
                high_days_str = str(item.get("high_days", ""))        # "首板"/"2板"...
                high_days_enc = int(item.get("high_days_value", 0) or 0)
                high_days_value = high_days_enc >> 16 if high_days_enc > 0 else 0  # 解码板数
                first_time = str(item.get("first_limit_up_time", ""))
                change_rate = float(item.get("change_rate", 0) or 0)       # 涨幅%
                turnover_rate = float(item.get("turnover_rate", 0) or 0)   # 换手率%
                suc_rate = float(item.get("limit_up_suc_rate", 0) or 0)    # 封板成功率
                order_amount = float(item.get("order_amount", 0) or 0)     # 封单额(元)
                is_again = int(item.get("is_again_limit", 0) or 0)         # 是否回封
                change_tag = str(item.get("change_tag", ""))               # FIRST_LIMIT等
                time_preview = item.get("time_preview", [])                # 日内涨幅走势

                zt_list.append({
                    "code": code,
                    "name": name,
                    "limit_up_type": limit_up_type,
                    "reason_type": reason_type,
                    "high_days": high_days_str,
                    "high_days_value": high_days_value,
                    "first_time": first_time,
                    "change_rate": change_rate,
                    "turnover_rate": turnover_rate,
                    "suc_rate": suc_rate,
                    "order_amount": order_amount,
                    "is_again": is_again,
                    "change_tag": change_tag,
                    "time_preview": time_preview,
                })
            except Exception:
                continue

        return {
            "total": total,
            "zb_count": zb_count,
            "dt_count": dt_count,
            "zr_rate": zr_rate,
            "zt_open": zt_open,
            "zt_yesterday": zt_yesterday,
            "dt_yesterday": dt_yesterday,
            "zt_list": zt_list,
        }

    def ths_limit_up_all(self, date: str) -> dict:
        """
        分页拉取当日全部涨停数据（单页上限 200）。
        返回同 ths_limit_up_pool()，但 zt_list 包含全部涨停。
        """
        first = self.ths_limit_up_pool(date, page=1, limit=200)
        total = first["total"]
        zt_list = list(first["zt_list"])

        if total > len(zt_list):
            num_pages = (total + 199) // 200
            for p in range(2, num_pages + 1):
                page_data = self.ths_limit_up_pool(date, page=p, limit=200)
                zt_list.extend(page_data["zt_list"])

        return {
            "total": total,
            "zb_count": first["zb_count"],
            "dt_count": first["dt_count"],
            "zr_rate": first["zr_rate"],
            "zt_open": first["zt_open"],
            "zt_yesterday": first["zt_yesterday"],
            "dt_yesterday": first["dt_yesterday"],
            "zt_list": zt_list[:total],
        }

    # ========== 打板统计汇总 ==========

    def fetch_board_summary(self, date: str = None) -> dict:
        """
        打板统计（基于同花顺涨停揭秘）。
        date: 日期 YYYYMMDD，默认今天

        返回: {
            zt_count, zb_count, dt_count, zr_rate,
            zt_open, zt_yesterday, dt_yesterday,
            zt_high_lb, zt_top_reasons, zt_top_types, zt_names
        }
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        data = self.ths_limit_up_pool(date, page=1, limit=200)
        zt_list = data["zt_list"]

        zt_count = data["total"]
        zb_count = data["zb_count"]
        dt_count = data["dt_count"]
        zr_rate = data["zr_rate"]
        zt_open = data["zt_open"]
        zt_yesterday = data["zt_yesterday"]
        dt_yesterday = data.get("dt_yesterday", 0)

        # 最高连板（high_days_value 已在 ths_limit_up_pool 中解码为纯板数）
        zt_high_lb = 0
        zt_high_name = ""
        zt_names = []
        for z in zt_list:
            hd = z.get("high_days_value", 0)
            if hd > zt_high_lb:
                zt_high_lb = hd
                zt_high_name = z.get("name", "")
            zt_names.append(z.get("name", ""))

        # 涨停原因分布 Top 5
        from collections import Counter
        reason_counter = Counter()
        type_counter = Counter()
        for z in zt_list:
            rt = z.get("reason_type", "")
            lt = z.get("limit_up_type", "")
            if rt:
                reason_counter[rt] += 1
            if lt:
                type_counter[lt] += 1

        return {
            "zt_count": zt_count,
            "zb_count": zb_count,
            "dt_count": dt_count,
            "zr_rate": zr_rate,
            "zt_open": zt_open,
            "zt_yesterday": zt_yesterday,
            "dt_yesterday": dt_yesterday,
            "zt_high_lb": zt_high_lb,
            "zt_high_name": zt_high_name,
            "zt_top_reasons": reason_counter.most_common(8),
            "zt_top_types": type_counter.most_common(5),
            "zt_names": zt_names,
        }

    # ========== 自测 ==========

    def test_connection(self) -> dict:
        """自检所有已验证端点的连通性"""
        results = {}

        # 北向资金
        t0 = time.time()
        nf = self.fetch_north_flow(lmt=1)
        delta = time.time() - t0
        status = "OK" if nf else "EMPTY"
        results["north_flow(multi-source)"] = (
            f"{status} net={nf[0].get('total_yi', 0):.1f}亿 "
            f"src={nf[0].get('source', '?')} ({delta:.2f}s)" if nf
            else f"{status} ({delta:.2f}s)"
        )

        # 同花顺涨停揭秘
        date = datetime.now().strftime("%Y%m%d")
        t0 = time.time()
        summary = self.fetch_board_summary(date)
        delta = time.time() - t0
        status = "OK" if summary["zt_count"] > 0 else "EMPTY"
        results["board_summary(ths)"] = (
            f"{status} {summary['zt_count']}涨停/{summary['zb_count']}炸板 "
            f"炸板率{summary['zr_rate']}% ({delta:.2f}s)"
        )

        return results


    # ========== 板块资金流向 (V3.5.1) ==========

    _BOARD_FS = {
        "行业": "m:90+t:2",       # BK2（fs 格式必须带冒号，m:90+t2 会返回空）
        "概念": "m:90+t:3",       # BK3
        "地域": "m:90+t:1",       # BK1
    }
    _BOARD_PERIOD = {"今日": 1, "5日": 5, "10日": 10}

    _BFF_COLUMNS = {
        "f3": "涨跌幅", "f20": "最新价", "f2": "总市值",
        "f62": "主力净流入", "f66": "超大单净流入", "f72": "大单净流入",
        "f78": "中单净流入", "f84": "小单净流入",
        "f184": "主力净占比", "f174": "超大单净占比", "f175": "大单净占比",
        "f12": "板块代码", "f14": "板块名称", "f128": "领涨股",
    }

    def board_fund_flow(self, board_type: str = "行业",
                        period: str = "今日", top_n: int = 10) -> list:
        """板块资金流向 — 行业/概念/地域 × 今日/5日/10日

        V3.5.1: 行业/概念板块自动翻页（最多10页×200条），避免单页200条截断。

        Returns:
            [{name, code, change_pct, main_net_yi, super_large_yi, large_yi,
              mid_yi, small_yi, main_net_ratio, lead_stock, ...}]
        """
        if board_type not in self._BOARD_FS:
            raise ValueError(f"板块类型必须是: {list(self._BOARD_FS.keys())}")
        if period not in self._BOARD_PERIOD:
            raise ValueError(f"周期必须是: {list(self._BOARD_PERIOD.keys())}")

        fs = self._BOARD_FS[board_type]
        period_num = self._BOARD_PERIOD[period]
        page_size = min(top_n, 100)
        # 2026-08-03 修复：板块资金流周期由 fid 编码（今日 f62/5日 f164/10日 f174），
        # 旧写法 `fs=m:90+t:2&p:1` 已返回 rc:102 失效
        secid = fs
        fid = {"今日": "f62", "5日": "f164", "10日": "f174"}.get(period, "f62")
        url = "https://push2.eastmoney.com/api/qt/clist/get"

        def _make_params(pn, pz):
            return {
                "pn": str(pn), "pz": str(pz), "po": "1", "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2", "invt": "2", "fid": fid,
                "fs": secid,
                "fields": "f12,f14,f2,f3,f20,f62,f66,f72,f78,f84,f128,f184,f174,f175",
                "_": str(int(time.time() * 1000)),
            }

        def _parse_rows(data):
            items = []
            if data.get("data") and data["data"].get("diff"):
                for row in data["data"]["diff"]:
                    def _f(key, default=0.0):
                        v = row.get(key)
                        try:
                            return float(v) if v not in (None, "", "-", "--") else default
                        except (TypeError, ValueError):
                            return default
                    items.append({
                        "name": row.get("f14", ""),
                        "code": row.get("f12", ""),
                        "price": round(_f("f20"), 2),
                        "change_pct": round(_f("f3"), 2),
                        "market_cap_yi": round(_f("f2") / 1e8, 2),
                        "main_net_yi": round(_f("f62") / 1e8, 2),
                        "super_large_yi": round(_f("f66") / 1e8, 2),
                        "large_yi": round(_f("f72") / 1e8, 2),
                        "mid_yi": round(_f("f78") / 1e8, 2),
                        "small_yi": round(_f("f84") / 1e8, 2),
                        "main_net_ratio": round(_f("f184"), 2),
                        "lead_stock": row.get("f128", ""),
                    })
            return items

        def _paginate():
            """V3.5.1: 自动翻页，最多10页×200条"""
            all_items = []
            for pn in range(1, 10):
                params = _make_params(pn, 200)
                data = em_get(url, params=params, timeout=15)
                if not data:
                    break
                page_items = _parse_rows(data)
                all_items.extend(page_items)
                if len(page_items) < 200:
                    break
            return all_items

        if board_type in ("行业", "概念"):
            items = _paginate()
        else:
            # 地域板块数量少，单页即可
            params = _make_params(1, page_size)
            data = em_get(url, params=params, timeout=15)
            if not data:
                return []
            items = _parse_rows(data)
        return items


# ========== 东财公共辅助函数（供其他模块复用）===========================

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# ═══════════════════════════════════════════════════════════════
# 代理轮换池（2026-07-24 新增：东财 push2 IP 风控绕过）
# ═══════════════════════════════════════════════════════════════

# 用户自配代理列表：[("http://host:port", "http"), ...] 或 ["http://host:port", ...]
# 优先级：用户配置 > 免费代理源
_USER_PROXIES = []

# 免费代理源（仅在无用户配置时启用）
_FREE_PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
    "https://proxylist.geonode.com/api/proxy-list?limit=20&page=1&sort_by=lastChecked&sort_type=desc&protocols=http",
]

# 代理配置持久化路径
_PROXY_CACHE_FILE = os.path.join(BASE_DIR, "config", "proxies.json")


def load_proxies() -> list:
    """加载代理池：用户配置 > proxy文件 > 免费源探测。返回 [{"http": "http://ip:port"}, ...]"""
    proxies = []
    # 1. 用户内存配置
    if _USER_PROXIES:
        for p in _USER_PROXIES:
            if isinstance(p, dict):
                proxies.append(p)
            elif isinstance(p, str):
                proxies.append({"http": p, "https": p} if p.startswith("http") else {"http": f"http://{p}"})
        return proxies
    # 2. 文件缓存
    if os.path.exists(_PROXY_CACHE_FILE):
        try:
            with open(_PROXY_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if isinstance(cached, list) and len(cached) > 0:
                    return [{"http": p, "https": p} if isinstance(p, str) else p for p in cached]
        except Exception:
            pass
    # 3. 探测免费源（耗时，仅在需要时执行）
    return _fetch_free_proxies()


def _fetch_free_proxies() -> list:
    """从免费源拉取代理列表（约 5-10 秒）。"""
    valid = []
    for src in _FREE_PROXY_SOURCES[:1]:  # 只试第一个源避免太慢
        try:
            s = requests.Session()
            s.trust_env = False
            r = s.get(src, timeout=10,
                      headers={"User-Agent": "curl/8.0"})
            if r.status_code != 200:
                continue
            if "proxyscrape" in src:
                ips = [line.strip() for line in r.text.split("\n") if ":" in line]
                for ip in ips[:15]:
                    prox = {"http": f"http://{ip}", "https": f"http://{ip}"}
                    if _test_proxy(prox):
                        valid.append(prox)
            elif "geonode" in src:
                data = r.json().get("data", [])
                for item in data[:15]:
                    ip = item.get("ip"); port = item.get("port")
                    if ip and port:
                        prox = {"http": f"http://{ip}:{port}", "https": f"http://{ip}:{port}"}
                        if _test_proxy(prox):
                            valid.append(prox)
        except Exception:
            continue
    # 缓存
    if valid:
        try:
            os.makedirs(os.path.dirname(_PROXY_CACHE_FILE), exist_ok=True)
            with open(_PROXY_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump([p["http"] for p in valid], f, ensure_ascii=False)
        except Exception:
            pass
    return valid


def _test_proxy(proxy: dict, timeout: float = 4.0) -> bool:
    """测试代理是否可用（访问 push2 首页验活）。"""
    try:
        sess = requests.Session()
        sess.trust_env = False
        r = sess.get("https://push2.eastmoney.com",
                       proxies=proxy, timeout=timeout,
                       headers={"User-Agent": UA})
        return r.status_code in (200, 302, 301)
    except Exception:
        return False


# 东财统一请求入口：限流 + UA + 代理回退（GET/POST 均走此）
_EM_GET_SESSION = None

def em_get(url: str, params: dict = None, headers: dict = None, timeout: int = 10,
           method: str = "GET", data=None, json_body=None) -> dict:
    """东财统一请求（内建限流防封 + UA + Referer + 代理回退 + 会话复用）。
    method: "GET"/"POST"；POST 时 body 走 data（表单）或 json_body（JSON）。
    返回 response.json() 或 {}。
    """
    import time as _time
    import random as _random
    global _EM_GET_SESSION
    if _EM_GET_SESSION is None:
        _EM_GET_SESSION = requests.Session()
        _EM_GET_SESSION.trust_env = False
    h = {"User-Agent": UA, "Referer": "https://data.eastmoney.com/"}
    if headers:
        h.update(headers)
    # 尝试序号: ①直连 ②静态代理 ③动态代理池
    proxies_list = [None]
    try:
        pool = load_proxies()
        if pool:
            proxies_list.extend(pool)
    except Exception as e:
        # 代理池探测失败不致命（直连仍会尝试），记录一次便于诊断
        import logging
        logging.getLogger(__name__).debug("load_proxies 失败: %s", str(e)[:120])
    for attempt, proxy in enumerate(proxies_list[:8]):  # 最多8次
        try:
            _time.sleep(0.5 + _random.uniform(0, 0.3))  # 限流 + 随机抖动
            if method.upper() == "POST":
                if json_body is not None:
                    resp = _EM_GET_SESSION.post(url, params=params, headers=h,
                                                json=json_body, timeout=timeout, proxies=proxy)
                else:
                    resp = _EM_GET_SESSION.post(url, params=params, headers=h,
                                                data=data, timeout=timeout, proxies=proxy)
            else:
                resp = _EM_GET_SESSION.get(url, params=params, headers=h,
                                           timeout=timeout, proxies=proxy)
            if resp.status_code == 200:
                return resp.json()
            # 非200: 切换代理重试
        except Exception:
            continue
    # ── push2delay 主机回退（2026-08-03 实测：push2delay 绕开 push2 WAF 封锁，数据延迟约15分钟）──
    for _orig, _delay in (("push2.eastmoney.com", "push2delay.eastmoney.com"),
                          ("push2his.eastmoney.com", "push2hisdelay.eastmoney.com")):
        if _orig in url:
            delay_url = url.replace(_orig, _delay)
            try:
                _time.sleep(0.4)
                if method.upper() == "POST":
                    resp = _EM_GET_SESSION.post(delay_url, params=params, headers=h,
                                                data=data, timeout=timeout, proxies=None)
                else:
                    resp = _EM_GET_SESSION.get(delay_url, params=params, headers=h,
                                               timeout=timeout, proxies=None)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                continue
    # 全部失败
    return {}


def eastmoney_datacenter(params: dict, m: str = None, timeout: int = 10) -> dict:
    """东财数据中心通用查询（/api/data/get）。
    必填: params 含 type/sty/sr/filter/p 等。
    可选: m（模块，如 m:90+t2）。
    返回 response.json()["result"]["data"] 或 {}。
    """
    base = {"type": "RPTA_WEB_THEME_DETAIL",
            "sty": "ALL",
            "sr": "-1", "st": "12",
            "filter": "(MARKET=ALL)",
            "p": "1", "ps": "200",
            "source": "WEB", "client": "WEB",
            "token": "894050c76af8597a853f5b408b759f5d",
            "rt": str(int(time.time() * 1000))}
    if m:
        base["m"] = m
    base.update(params)
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    data = em_get(url, params=base, timeout=timeout)
    if data and data.get("data"):
        return data["data"]
    return data if data else {}


# ========== 百度K线带MA（§1.3）===========================

def baidu_kline_with_ma(code: str, start_time: str = "") -> dict:
    """百度股市通K线 — 独有能力: 返回时自带 ma5/ma10/ma20 均价"""
    url = "https://finance.pae.baidu.com/selfselect/getstockquotation"
    params = {
        "all": "1", "isIndex": "false", "isBk": "false", "isBlock": "false",
        "isFutures": "false", "isStock": "true", "newFormat": "1",
        "group": "quotation_kline_ab", "finClientType": "pc",
        "code": code, "start_time": start_time, "ktype": "1",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    }
    try:
        s = requests.Session()
        s.trust_env = False
        r = s.get(url, params=params, headers=headers, timeout=10)
        d = r.json()
        result = d.get("Result", {})
        md = result.get("newMarketData", {})
        keys = md.get("keys", [])
        rows = md.get("marketData", "").split(";")
        return {"keys": keys, "rows": rows}
    except Exception as e:
        print(f"[baidu_kline_with_ma] {code} 失败: {e}")
        return {"keys": [], "rows": []}


# ========== 东财研报 + PDF下载（§2.1）===========================

REPORT_API = "https://reportapi.eastmoney.com/report/list"
PDF_TPL = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"


def eastmoney_reports(code: str, max_pages: int = 5, limit: int = None) -> list:
    """拉取指定股票的研报列表
    limit: 兼容 README 调用习惯（limit=N → max_pages 近似换算，pageSize=100）
    """
    all_records = []
    if limit is not None:
        max_pages = max(1, -(-limit // 100))  # limit 条 → 每页100向上取整页数
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "100", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": "2000-01-01", "endTime": "2030-01-01",
            "pageNo": str(page), "fields": "", "qType": "0",
            "orgCode": "", "code": code, "rcode": "",
            "p": str(page), "pageNum": str(page), "pageNumber": str(page),
        }
        r = em_get(REPORT_API, params=params,
                   headers={"Referer": "https://data.eastmoney.com/"}, timeout=30)
        d = r if isinstance(r, dict) else {}
        rows = d.get("data") or []
        if not rows:
            break
        all_records.extend(rows)
        if page >= (d.get("TotalPage", 1) or 1):
            break
    return all_records


def download_pdf(record: dict, target_dir: str = None) -> Optional[str]:
    """下载单份研报PDF，返回保存路径或None"""
    import re
    info_code = record.get("infoCode", "")
    if not info_code:
        return None
    date = (record.get("publishDate") or "")[:10]
    org = re.sub(r'[\\/:*?"<>|]', "_", record.get("orgSName") or "未知")[:40]
    title = re.sub(r'[\\/:*?"<>|]', "_", record.get("title", ""))[:80]
    fname = f"{date}_{org}_{title}.pdf"
    from pathlib import Path
    if target_dir is None:
        target_dir = str(Path(__file__).parent.parent / "data" / "reports")
    target = Path(target_dir) / fname
    if target.exists():
        return str(target)
    url = PDF_TPL.format(info_code=info_code)
    try:
        s = requests.Session()
        s.trust_env = False
        resp = s.get(url, headers={"Referer": "https://data.eastmoney.com/",
                                    "User-Agent": UA}, timeout=60)
        if resp.status_code == 200 and len(resp.content) >= 1024:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(resp.content)
            return str(target)
    except Exception as e:
        print(f"[download_pdf] {info_code} 下载失败: {e}")
    return None


def eastmoney_industry_reports(industry_code: str = "*", max_pages: int = 5,
                               begin: str = "2024-01-01") -> list:
    """拉取行业研报列表（qType=1）。
    industry_code="*" = 全行业；传东财行业码（如 "1238"=IT服务II）"""
    all_records = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": industry_code, "pageSize": "100", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": begin, "endTime": "2030-01-01",
            "pageNo": str(page), "fields": "", "qType": "1",
        }
        r = em_get(REPORT_API, params=params,
                   headers={"Referer": "https://data.eastmoney.com/"}, timeout=30)
        d = r if isinstance(r, dict) else {}
        rows = d.get("data") or []
        if not rows:
            break
        all_records.extend(rows)
        if page >= (d.get("TotalPage", 1) or 1):
            break
    return all_records


if __name__ == "__main__":
    em = get_eastmoney()
    print("东财数据源连通性测试:\n")
    for endpoint, status in em.test_connection().items():
        print(f"  {endpoint}: {status}")
