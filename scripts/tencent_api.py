#!/usr/bin/env python3
"""
腾讯数据源统一模块（单例模式）
- 提供统一的 requests.Session 和所有腾讯 API 端点封装
- 对标 tushare_api.py 的 get_pro() 模式：import 即用，无需重复构造 Session

端点:
  qt.gtimg.cn/q={codes}         — 实时行情（最多批量查询）
  web.ifzq.gtimg.cn/...         — 日K线
  ifzq.gtimg.cn/...             — 分时成交额

用法:
  from scripts.tencent_api import get_tencent
  tc = get_tencent()
  idx = tc.fetch_realtime(["sh000001", "sz399001"])
  kl = tc.fetch_kline("000001", market="sz")
"""

import re
import time
from typing import Optional

import requests

# ============================
# 全局单例
# ============================

_tencent_instance: Optional["TencentAPI"] = None


def get_tencent() -> "TencentAPI":
    """获取腾讯数据源单例（懒加载，线程不安全但脚本场景够用）"""
    global _tencent_instance
    if _tencent_instance is None:
        _tencent_instance = TencentAPI()
    return _tencent_instance


# ============================
# 指数代码映射
# ============================

INDEX_MAP = {
    "上证指数":    "sh000001",
    "深证成指":    "sz399001",
    "创业板指":    "sz399006",
    "科创50":     "sh000688",
    "上证50":     "sh000016",
    "沪深300":    "sh000300",
    "中证500":    "sh000905",
    "中证1000":   "sh000852",
    "中证全指":    "sh000985",
}

# 大盘指数代码（按常见排序）
MAJOR_INDEX_CODES = [
    "sh000001", "sz399001", "sz399006",
    "sh000688", "sh000016", "sh000300",
    "sh000905", "sh000852", "sh000985",
]

# ============================
# 行业板块代码（腾讯 pt 前缀，覆盖主要行业）
# ============================

# 腾讯行业板块代码 pt01801XXX（070~120，与 daily_feishu_report 一致）
SECTOR_CODES = [f"pt01801{i:03d}" for i in range(70, 121)]  # 51个板块

# ============================
# TencentAPI 类
# ============================


class TencentAPI:
    """腾讯行情 API 统一入口"""

    def __init__(self):
        self._session: Optional[requests.Session] = None

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
                "Referer": "https://gu.qq.com/",
            })
            s.timeout = 15  # 提示：requests.Session 无此属性，请求需显式 timeout=（各方法已传）
            self._session = s
        return self._session

    # ---------- 实时行情 ----------

    def fetch_realtime(self, codes: list) -> dict:
        """
        批量获取实时行情
        codes: ["sh000001", "sz399001", "000001", ...]
        返回: {code: {name, price, change_pct, high, low, volume, turnover, ...}}
        """
        if not codes:
            return {}
        url = "http://qt.gtimg.cn/q=" + ",".join(codes)
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            raw = resp.content.decode("gbk", errors="replace")
        except Exception as e:
            print(f"[TencentAPI] 实时行情请求失败: {e}")
            return {}

        results = {}
        lines = raw.strip().split("\n")
        for line in lines:
            match = re.search(r'v_(\w+)="(.+)"', line)
            if not match:
                continue
            code_raw = match.group(1)
            data_str = match.group(2)
            fields = data_str.split("~")
            if len(fields) < 50:
                continue

            try:
                name = fields[1]
                price = float(fields[3]) if fields[3] else 0.0
                change = float(fields[31]) if fields[31] else 0.0
                change_pct = float(fields[32]) if fields[32] else 0.0
                high = float(fields[33]) if fields[33] else 0.0
                low = float(fields[34]) if fields[34] else 0.0
                volume = int(float(fields[6])) if fields[6] else 0
                turnover = float(fields[37]) if fields[37] else 0.0  # 万元
                pe = float(fields[39]) if fields[39] else 0.0
            except (ValueError, IndexError):
                continue

            results[code_raw] = {
                "name": name,
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "high": high,
                "low": low,
                "volume": volume,
                "turnover": turnover,
                "pe": pe,
            }
        return results

    # ---------- 大盘指数 ----------

    def fetch_indices(self, codes: list = None, names: list = None) -> list:
        """
        获取大盘指数列表（现货）
        codes: ["sh000001", ...] 或 names: ["上证指数", ...]
        返回: [{code, name, price, change_pct, ...}] 保持请求顺序
        """
        if codes is None and names is None:
            codes = MAJOR_INDEX_CODES
        if names:
            codes = [INDEX_MAP[n] for n in names if n in INDEX_MAP]
        data = self.fetch_realtime(codes)
        result = []
        for c in codes:
            if c in data:
                item = data[c]
                item["code"] = c
                result.append(item)
        return result

    def fetch_index_snapshot(self) -> list:
        """获取九大指数快照（与 _daily_review.py 格式一致）"""
        return self.fetch_indices(MAJOR_INDEX_CODES)

    # ---------- 日K线 ----------

    def fetch_kline(self, code: str, n_days: int = 120, market: str = None) -> list:
        """
        获取日K线数据
        code: 纯数字代码，如 "000001"
        market: "sh" 或 "sz"，不传则自动推断（6开头→sh，0/3开头→sz）
        n_days: 请求天数（腾讯通常返回最近~120天）
        返回: [[date, open, close, high, low, volume], ...]
        """
        if market is None:
            market = "sh" if code.startswith("6") else "sz"
        code_full = f"{market}{code}"

        url = (
            f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            f"?param={code_full},day,,,{n_days},qfq"
        )
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[TencentAPI] K线请求失败 {code}: {e}")
            return []

        try:
            klines_raw = data["data"][code_full].get("day", [])
            if not klines_raw and "qfqday" in data["data"][code_full]:
                klines_raw = data["data"][code_full]["qfqday"]
        except (KeyError, TypeError):
            return []

        result = []
        for row in klines_raw:
            if len(row) < 6:
                continue
            try:
                date = row[0]
                o = float(row[1])
                c = float(row[2])
                h = float(row[3])
                l = float(row[4])
                v = int(float(row[5]))
                result.append([date, h, c, l, o, v])  # [date, high, close, low, open, vol]
            except (ValueError, IndexError):
                continue
        return result

    def fetch_kline_batch(self, codes: list, n_days: int = 120):
        """批量获取K线，返回 {code: [klines]}"""
        results = {}
        for code in codes:
            klines = self.fetch_kline(code, n_days)
            if klines:
                results[code] = klines
            time.sleep(0.15)  # 宽松限流
        return results

    # ---------- 成交额 ----------

    def fetch_turnover(self) -> tuple:
        """
        获取上证+深证当日成交额
        返回: (sh_turnover_yi, sz_turnover_yi) 单位：亿元
        """
        url = "http://ifzq.gtimg.cn/appstock/app/index/amount"
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            raw = resp.content.decode("utf-8", errors="replace")
            # 腾讯分时格式：提取最后一笔累计成交额
            sh_amount = 0.0
            sz_amount = 0.0
            for line in raw.strip().split("\n"):
                if "sh" in line.lower() or "1A0001" in line:
                    sh_amount = self._parse_last_amount(line)
                elif "sz" in line.lower() or "399001" in line:
                    sz_amount = self._parse_last_amount(line)
            # 备用方案：用正则匹配
            if sh_amount == 0.0 and sz_amount == 0.0:
                sh_match = re.search(r'sh[^"]*"[^"]*"', raw)
                sz_match = re.search(r'sz[^"]*"[^"]*"', raw)
            return (round(sh_amount / 1e8, 2), round(sz_amount / 1e8, 2))
        except Exception as e:
            print(f"[TencentAPI] 成交额请求失败: {e}")
            return (0.0, 0.0)

    def fetch_turnover_simple(self) -> float:
        """
        获取上证+深证合计成交额（更简单的实现）
        返回: 合计成交额（亿元）
        """
        # 用实时行情的成交额字段计算
        idx_data = self.fetch_indices(["sh000001", "sz399001"])
        total = 0.0
        for idx in idx_data:
            # turnover 字段单位万元 → 亿元
            total += idx.get("turnover", 0.0) / 10000
        return round(total, 2)

    @staticmethod
    def _parse_last_amount(line: str) -> float:
        """从分时数据行提取最后一个成交额值"""
        parts = line.replace("~", ",").split(",")
        for p in reversed(parts):
            try:
                return float(p)
            except (ValueError, TypeError):
                continue
        return 0.0

    # ---------- 行业板块 ----------

    def fetch_sectors(self, top_n: int = 5) -> list:
        """
        获取行业板块涨跌幅排名（用腾讯 pt 板块代码批量查询后排序）
        返回: [{name, code, change_pct}, ...] 涨跌幅降序，"--" 表示无数据

        说明：腾讯 qt.gtimg.cn 对板块代码部分支持，部分板块可能无数据。
              无数据的板块返回 change_pct="--"，会被过滤掉。
        """
        if not SECTOR_CODES:
            return []

        # 批量查询（每次最多查一批，减少请求次数）
        batch_size = 40
        all_data = {}
        for i in range(0, len(SECTOR_CODES), batch_size):
            batch = SECTOR_CODES[i:i + batch_size]
            data = self.fetch_realtime(batch)
            all_data.update(data)
            time.sleep(0.1)

        results = []
        for code in SECTOR_CODES:
            if code not in all_data:
                continue
            d = all_data[code]
            results.append({
                "name": d["name"],
                "code": code,
                "change_pct": d["change_pct"],
            })

        # 过滤无效板块（必须有名称），保留涨跌幅为0的真实板块
        results = [r for r in results if r["name"]]
        results.sort(key=lambda x: x["change_pct"], reverse=True)
        return results[:top_n]

    # ---------- 全市场涨跌比（含北交所）----------

    @classmethod
    def _generate_a_codes(cls) -> list:
        """生成沪深京A股代码列表（含北交所）。

        覆盖范围：沪市主板(600/601/603/605)、科创板(688/689)、
        深市主板(000/001/002/003)、创业板(300/301)、北交所(82/83/87/88)。
        """
        codes = []
        # 沪市主板
        for prefix in ["sh600", "sh601", "sh603", "sh605"]:
            codes.extend([f"{prefix}{i:03d}" for i in range(1, 1000)])
        # 科创板
        for prefix in ["sh688", "sh689"]:
            codes.extend([f"{prefix}{i:03d}" for i in range(1, 1000)])
        # 深市主板
        for prefix in ["sz000", "sz001", "sz002", "sz003"]:
            codes.extend([f"{prefix}{i:03d}" for i in range(1, 1000)])
        # 创业板
        for prefix in ["sz300", "sz301"]:
            codes.extend([f"{prefix}{i:03d}" for i in range(1, 1000)])
        # 北交所（bj 前缀，代码范围 830000-839999）
        for start in [830000, 831000, 832000, 833000, 834000, 835000, 836000, 837000, 838000]:
            codes.extend([f"bj{i}" for i in range(start, start + 1000)])
        return codes

    def fetch_breadth(self, verbose: bool = False) -> dict:
        """全市场涨跌比（含北交所）。

        通过腾讯 qt.gtimg.cn 批量扫描全A股代码，
        按 fields[32]（涨跌幅%）正负统计涨/跌/平数量。

        返回:
            {total, up, down, flat, up_pct, down_pct,
             markets: {sh:{up,down,flat,total}, sz:{...}, bj:{...}},
             elapsed_s}
        """
        all_codes = self._generate_a_codes()
        batch_size = 80
        up = down = flat = 0
        markets = {"sh": {"up": 0, "down": 0, "flat": 0, "total": 0},
                   "sz": {"up": 0, "down": 0, "flat": 0, "total": 0},
                   "bj": {"up": 0, "down": 0, "flat": 0, "total": 0}}
        t0 = time.time()
        total_scanned = 0

        for i in range(0, len(all_codes), batch_size):
            batch = all_codes[i:i + batch_size]
            data = self.fetch_realtime(batch)
            for code, d in data.items():
                if not d.get("name") or d.get("price", 0) <= 0:
                    continue
                pct = d["change_pct"]
                market = code[:2]  # sh/sz/bj
                if market not in markets:
                    market = code[:2]
                markets[market]["total"] += 1
                if pct > 0:
                    up += 1
                    markets[market]["up"] += 1
                elif pct < 0:
                    down += 1
                    markets[market]["down"] += 1
                else:
                    flat += 1
                    markets[market]["flat"] += 1
            total_scanned += len(batch)
            if verbose and i % 1600 == 0:
                elapsed = time.time() - t0
                print(f"  [breadth] 已扫描 {total_scanned}/{len(all_codes)} "
                      f"({elapsed:.1f}s) 涨{up} 跌{down} 平{flat}")
            time.sleep(0.08)

        total = up + down + flat
        elapsed = time.time() - t0
        # 北交所数据新鲜度检测：收盘后腾讯API会清零涨跌幅（实测 2026-08-09 周日 170 只全平）
        bj_flat_ratio = markets["bj"]["flat"] / max(markets["bj"]["total"], 1)
        bj_fresh = "ok" if bj_flat_ratio < 0.5 else "stale_post_close"
        if bj_fresh != "ok":
            bj_fixed = self._fetch_bj_breadth_em()
            if bj_fixed:
                # 用东财北交所全量重算市场/全局涨跌比
                delta = {k: bj_fixed[k] - markets["bj"][k] for k in ("up", "down", "flat")}
                up += delta["up"]; down += delta["down"]; flat += delta["flat"]
                markets["bj"] = bj_fixed
                bj_fresh = "fixed_via_eastmoney"
        return {
            "total": total,
            "up": up,
            "down": down,
            "flat": flat,
            "up_pct": round(up / total * 100, 1) if total else 0,
            "down_pct": round(down / total * 100, 1) if total else 0,
            "markets": markets,
            "elapsed_s": round(elapsed, 1),
            "bj_data_status": bj_fresh,
        }

    def _fetch_bj_breadth_em(self) -> dict:
        """北交所广度回退源：东财 push2 clist（fs=m:0+t:81 北交所全量）。

        腾讯收盘后清空北交所涨跌幅（全平），用东财一次请求补全。
        返回 {up, down, flat, total}；失败返回空 dict（保持腾讯原值）。
        """
        try:
            from scripts.eastmoney_api import em_get
        except Exception:
            return {}
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1", "pz": "200", "po": "1", "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2", "invt": "2", "fid": "f3",
            "fs": "m:0+t:81+s:2048", "fields": "f12,f14,f3",
        }
        try:
            all_diff = []
            for pn in (1, 2, 3):  # 北交所 ~300 只，fid=f3 降序，须翻页取全量
                params["pn"] = str(pn)
                data = em_get(url, params=params, timeout=15)
                diff = (data.get("data") or {}).get("diff") or []
                if isinstance(diff, dict):
                    diff = list(diff.values())
                all_diff.extend(diff)
                if len(diff) < 100:  # 东财单页上限 100 条（pz=200 也被截断）
                    break
        except Exception:
            return {}
        up = down = flat = 0
        for row in all_diff:
            try:
                pct = float(row.get("f3"))
            except (TypeError, ValueError):
                flat += 1
                continue
            if pct > 0:
                up += 1
            elif pct < 0:
                down += 1
            else:
                flat += 1
        total = up + down + flat
        if total == 0:
            return {}
        return {"up": up, "down": down, "flat": flat, "total": total}

    # ---------- 自测 ----------

    def test_connection(self) -> dict:
        """自检所有端点的连通性"""
        results = {}
        # 实时行情
        t0 = time.time()
        rt = self.fetch_realtime(["sh000001"])
        results["realtime(sh000001)"] = f"{'OK' if rt else 'FAIL'} ({time.time()-t0:.2f}s)"

        # K线
        t0 = time.time()
        kl = self.fetch_kline("000001", n_days=5)
        results[f"kline(000001)"] = f"{'OK' if kl else 'FAIL'} ({time.time()-t0:.2f}s)"

        # 板块
        t0 = time.time()
        sec = self.fetch_sectors(top_n=3)
        results[f"sectors(top3)"] = f"{'OK' if sec else 'FAIL'} ({time.time()-t0:.2f}s)"

        return results


# ============================
# 命令行自检
# ============================

if __name__ == "__main__":
    tc = get_tencent()
    print("腾讯数据源连通性测试:\n")
    for endpoint, status in tc.test_connection().items():
        print(f"  {endpoint}: {status}")
