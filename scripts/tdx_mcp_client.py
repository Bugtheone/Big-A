# -*- coding: utf-8 -*-
"""
TDX MCP 客户端 — 通达信问小达 MCP 数据接口封装。

通达信官方 MCP 服务（wenda-mcp-server），单工具 tdx_wenda_quotes（自然语言问答）。
与项目四源（a-stock-data/tushare/westock/问财）+ FTShare 组成完整取数链路，
定位为补充验证源：筹码分布（获利比例/平均成本）、概念成分股、涨停原因揭秘等。

用法:
    from scripts.tdx_mcp_client import tdx_mcp

    # 单次查询（返回 dict: meta/headers/data/summary）
    r = tdx_mcp.query("贵州茅台600519 筹码分布 获利比例 平均成本")

    # 自动翻页合并
    r = tdx_mcp.query_all("存储芯片概念板块成分股 今日涨跌幅", page_size=50)

    # 便捷：转 dict 列表
    rows = tdx_mcp.query(...).to_dicts()

环境变量: TDX_API_KEY（或 config/tdx_config.json 的 tdx_api_key 字段）

数据纪律: 仅作补充验证源，实时行情仍以 a-stock-data 主源为准；
关键结论必须 ≥2 源交叉验证，禁止以本接口为唯一数据源。
"""

import json
import os
import time
from typing import Any, Optional

import httpx

MCP_URL = "https://mcp.tdx.com.cn:3001/mcp"
_DEFAULT_KEY = os.getenv("TDX_API_KEY", "")


def _load_config_key() -> str:
    """从项目 config 读取 TDX API Key（config 优先于环境变量）。"""
    if _DEFAULT_KEY:
        return _DEFAULT_KEY
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "tdx_config.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            return json.load(f).get("tdx_api_key", "")
    except Exception:
        return ""


class TdxQueryResult:
    """解析后的查询结果。"""

    def __init__(self, raw: dict):
        self.raw = raw
        self.code: int = (raw.get("meta") or {}).get("code", -1)
        self.total: int = (raw.get("meta") or {}).get("total", 0)
        self.message: str = (raw.get("meta") or {}).get("message", "")
        self.headers: list = raw.get("headers", [])
        self.data: list = raw.get("data", [])
        self.summary: str = raw.get("summary", "")

    def ok(self) -> bool:
        return self.code == 0

    def to_dicts(self) -> list[dict]:
        """data 行 → 字段名->值的 dict 列表。"""
        return [dict(zip(self.headers, row)) for row in self.data]


class TdxMcpClient:
    """通达信问小达 MCP 客户端（JSON-RPC over HTTP，SSE 响应）。"""

    def __init__(self, api_key: str = "", timeout: int = 30):
        self.api_key = api_key or _load_config_key()
        if not self.api_key:
            raise ValueError(
                "缺少 TDX API Key：请设环境变量 TDX_API_KEY 或写 config/tdx_config.json "
                "（申请入口：https://vip.tdx.com.cn/site/app/pc-mall/main.html#/aiKey）"
            )
        self.timeout = timeout
        self._session_id: Optional[str] = None
        self._req_id = 0

    # ------------------------------------------------------------------
    # 内部：JSON-RPC over HTTP
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _post(self, payload: dict) -> dict:
        headers = {
            "tdx-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        resp = httpx.post(MCP_URL, json=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self._session_id = sid
        ct = resp.headers.get("content-type", "")
        if "text/event-stream" in ct:
            return self._parse_sse(resp.text)
        return resp.json()

    @staticmethod
    def _parse_sse(text: str) -> dict:
        for line in text.splitlines():
            if line.startswith("data: "):
                try:
                    obj = json.loads(line[6:])
                    if "result" in obj or "error" in obj:
                        return obj
                except json.JSONDecodeError:
                    continue
        return {}

    # ------------------------------------------------------------------
    # MCP 握手
    # ------------------------------------------------------------------

    def initialize(self) -> dict:
        result = self._post({
            "jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "tdx-mcp-client", "version": "1.0"}},
        })
        try:
            headers = {
                "tdx-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if self._session_id:
                headers["Mcp-Session-Id"] = self._session_id
            httpx.post(MCP_URL,
                       json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                       headers=headers, timeout=10)
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------
    # 工具调用
    # ------------------------------------------------------------------

    def call_tool(self, name: str, arguments: dict) -> dict:
        if self._session_id is None:
            self.initialize()
        resp = self._post({
            "jsonrpc": "2.0", "id": self._next_id(), "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        if "result" in resp:
            for item in resp["result"].get("content", []):
                if item.get("type") == "text":
                    try:
                        return json.loads(item["text"])
                    except json.JSONDecodeError:
                        return {"raw_text": item["text"]}
        if "error" in resp:
            raise RuntimeError(f"TDX MCP 错误: {resp['error']}")
        return resp

    def query(self, question: str, range: str = "AG", size: int = 10,
              page: int = 1) -> TdxQueryResult:
        """调用 tdx_wenda_quotes。range: AG(A股)/HK-GP(港股)/JJ(基金)/ZS(指数)。"""
        raw = self.call_tool("tdx_wenda_quotes",
                             {"question": question, "range": range, "size": size, "page": page})
        return TdxQueryResult(raw)

    def query_all(self, question: str, range: str = "AG", page_size: int = 50,
                  max_pages: int = 10, delay: float = 0.3) -> TdxQueryResult:
        """自动翻页合并（限流 100 次/分钟，delay 防过频）。"""
        first = self.query(question, range, size=page_size, page=1)
        if not first.ok() or first.total <= page_size:
            return first
        all_data = list(first.data)
        total_pages = min(max_pages, -(-first.total // page_size))
        for p in range(2, total_pages + 1):
            time.sleep(delay)
            pr = self.query(question, range, size=page_size, page=p)
            if not pr.ok() or not pr.data:
                break
            all_data.extend(pr.data)
        merged = dict(first.raw)
        merged["data"] = all_data
        return TdxQueryResult(merged)


tdx_mcp = TdxMcpClient()


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "上证指数 最新行情"
    result = tdx_mcp.query(q)
    if result.ok():
        for row in result.to_dicts()[:10]:
            print(row)
    else:
        print(f"查询失败: {result.message}")
