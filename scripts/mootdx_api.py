#!/usr/bin/env python3
"""通达信mootdx接口层 — K线/盘口/逐笔/财务快照/F10 (SKILL.md §1.1/§6.1/§6.2)

修复记录 (2026-07-24):
- 替换裸 Quotes.factory() 为 tdx_client()，规避 mootdx 0.11.x BESTIP.HQ 空串 bug
- 10台备选服务器顺序探测 + 真实取数验活（_tdx_validate 兜底静默空表）
- 3级回退: 自定义server → bestip测速 → 裸factory
"""
import os, json, time, socket
from datetime import datetime, timedelta
from scripts.eastmoney_api import UA

try:
    from mootdx.quotes import Quotes
    from mootdx.reader import Reader
    MOOTDX_AVAILABLE = True
except ImportError:
    MOOTDX_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════
# tdx_client() — 规避 BESTIP 空串 bug + 坏服务器静默空表
# ═══════════════════════════════════════════════════════════════

# 实测可用的备选服务器（按延迟排序，2026-06 验证）
_TDX_SERVERS = [
    ('119.97.185.59', 7709), ('124.70.133.119', 7709), ('116.205.183.150', 7709),
    ('123.60.73.44', 7709),  ('116.205.163.254', 7709), ('121.36.225.169', 7709),
    ('123.60.70.228', 7709), ('124.71.9.153', 7709),    ('110.41.147.114', 7709),
    ('124.71.187.122', 7709),
    # 2026-08-09 实测补入（真实取数验活通过，close=11.19 平安银行当前价）
    ('115.238.56.198', 7709), ('218.75.126.9', 7709),   ('180.153.18.170', 7709),
    ('115.238.90.165', 7709),
]


def _tdx_probe(ip, port, timeout=2.0):
    """TCP 握手探测（快速粗筛）。握手成功 ≠ 能取数，必须再经 _tdx_validate 验活。"""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


_TDX_DATE_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")


def _tdx_valid_datetime(df) -> bool:
    """时间戳合法性校验：坏服务器对指数返回垃圾时间戳（实测 '7058-34-83 15:00'），
    非空但不合法——必须显式校验日期格式，不能只查非空。"""
    try:
        d = str(df["datetime"].iloc[-1])[:10]
        return bool(_TDX_DATE_RE.match(d))
    except Exception:
        return False


def _tdx_validate(client) -> bool:
    """真实取数验活：坏服务器可 TCP 握手通过却回 2 字节空 body → 静默空表。
    2026-08-09 增强：① 个股通道真实取数 + 时间戳合法性；② 指数通道验活
    （index_bars 走 get_index_bars，实测存在个股正常但指数返回垃圾的坏服务器）。
    """
    try:
        df = client.bars(symbol='000001', frequency=9, offset=1)
        if df is None or df.empty or not _tdx_valid_datetime(df):
            return False
    except Exception:
        return False
    try:
        idx = client.index_bars(symbol='999999', frequency=9, offset=1)
        if idx is None or idx.empty or not _tdx_valid_datetime(idx):
            return False
    except Exception:
        return False
    return True


def tdx_client(market='std'):
    """
    创建 mootdx 客户端，规避 0.11.x BESTIP.HQ 空串 bug + 坏服务器静默空表。
    每个候选都必须「真实取数验活」通过才采用：
      1) 顺序探测 _TDX_SERVERS，对 probe 通过者再 _validate 真实取数，取第一个验活成功的；
      2) 全部失败 → 回退 mootdx 自带 bestip 测速选优（同样验活）；
      3) 再回退裸 factory（老用户 config 已有可用 BESTIP 时成立）；
      4) 仍失败 → 抛 RuntimeError。
    """
    should_validate = market == 'std'                # V3.5.1: 非 std 市场跳过验活
    for ip, port in _TDX_SERVERS:
        if not _tdx_probe(ip, port):
            continue
        try:
            c = Quotes.factory(market=market, server=(ip, port))
            if not should_validate or _tdx_validate(c):
                return c
        except Exception:
            continue                                # 握手过但取数崩 → 跳过下一台
    for kwargs in ({'bestip': True}, {}):           # fallback: bestip 测速 / 裸 factory
        try:
            c = Quotes.factory(market=market, **kwargs)
            if not should_validate or _tdx_validate(c):
                return c
        except Exception:
            continue
    raise RuntimeError(
        "所有 mootdx 服务器均无法取到数据（TCP 可达但返回空 / 被 reset）。"
        "海外网络通常全部超时（TCP 7709），请走国内代理或更新 _TDX_SERVERS 列表。"
    )

# 本地数据路径
TDX_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tdx")


class MootdxAPI:
    def __init__(self):
        self._client = None
        self._client_error = None
        if not MOOTDX_AVAILABLE:
            self._client_error = "mootdx 未安装 (pip install mootdx)"

    @property
    def client(self):
        if self._client is None and self._client_error is None:
            try:
                self._client = tdx_client()
            except RuntimeError:
                # 最终回退：裸 factory（老用户已有可用 BESTIP）
                try:
                    self._client = Quotes.factory(market="std")
                except Exception as e:
                    self._client_error = str(e)
        return self._client

    def bars(self, code: str, freq: int = 9, start: int = 0, count: int = 100) -> list:
        """K线数据。freq: 0=5分钟 1=15分钟 2=30分钟 3=1小时 4=日线 5=周线 6=月线 7=1分钟 8=季线 9=年线"""
        if not self.client:
            return []
        try:
            df = self.client.bars(symbol=code, frequency=freq, start=start, offset=count)
            if df is None or df.empty: return []
        except Exception: return []
        return [{"date": str(d), "open": r[0], "high": r[1], "low": r[2],
                 "close": r[3], "volume": int(r[4]), "amount": r[5]} 
                for d, r in df.iterrows()]

    def quotes(self, codes: list) -> list:
        """批量盘口快照。返回 [{code,name,price,open,high,low,volume,amount,bid/ask...}, ...]"""
        if not self.client: return []
        try:
            df = self.client.quotes(symbol=codes)
            if df is None or df.empty: return []
        except Exception: return []
        out = []
        for _, r in df.iterrows():
            out.append({"code": r.get("code",""),"name": r.get("name",""),
                "price": r.get("price",0),"open": r.get("open",0),"high": r.get("high",0),
                "low": r.get("low",0),"volume": int(r.get("volume",0)),
                "amount": r.get("amount",0),"bid1": r.get("bid1",0),"ask1": r.get("ask1",0)})
        return out

    def transaction(self, code: str, count: int = 100) -> list:
        """逐笔成交（仅当日盘中）。返回 [{time,price,volume,amount,buy_or_sell(0=卖1=买2=中性)}, ...]
        ⚠️ 非交易时间/周末返回空属正常；历史逐笔用 transaction_history()。"""
        if not self.client: return []
        try:
            df = self.client.transaction(symbol=code, offset=count)
            if df is None or df.empty: return []
        except Exception: return []
        return [{"time": str(d), "price": r[0], "volume": int(r[1]),
                 "amount": r[2], "buy_or_sell": int(r[3])} for d, r in df.iterrows()]

    def transaction_history(self, code: str, date: str, count: int = 100) -> list:
        """历史逐笔成交（2026-08-09 实测补全）。
        用 mootdx transactions()（带 date，走 get_history_transaction_data），
        此前只有当日 transaction()，周日/盘后无法取历史。date=YYYYMMDD。
        返回 [{time,price,volume,buy_or_sell}, ...]（含收盘集合竞价 15:00-15:30 记录，vol 可能为 0）。
        """
        if not self.client: return []
        try:
            df = self.client.transactions(symbol=code, date=date, offset=count)
            if df is None or df.empty: return []
        except Exception: return []
        out = []
        for _, r in df.iterrows():
            try:
                out.append({"time": str(r["time"]), "price": float(r["price"]), "volume": int(r["vol"]),
                            "buy_or_sell": int(r["buyorsell"])})
            except (ValueError, TypeError, KeyError, IndexError):
                continue
        return out

    def finance(self, code: str) -> dict:
        """财务快照（PE/PB/ROE/股东权益/营业收入等）。"""
        if not self.client: return {}
        try:
            df = self.client.finance(symbol=code)
            if df is None or df.empty: return {}
        except Exception: return {}
        fields = ["pe_ttm","pb","roe","total_shares","float_shares","total_mcap",
                  "oper_rev","oper_profit","total_profit","net_profit","eps","undistributed",
                  "net_asset","holder_num","net_asset_per_share"]
        return {f: r.get(f,None) for f, r in zip(fields, df.iloc[0]) if hasattr(df,'iloc')}

    def f10(self, code: str) -> dict:
        """F10 公司概况（全称/注册地/主营业务/成立日期/上市日期/高管等）。"""
        if not self.client: return {}
        try:
            info = self.client.f10(symbol=code)
            if not info: return {}
            return {"raw": str(info)[:500]} if isinstance(info, dict) else {}
        except Exception: return {}


_mootdx = None
def get_mootdx() -> MootdxAPI:
    global _mootdx
    if _mootdx is None: _mootdx = MootdxAPI()
    return _mootdx
