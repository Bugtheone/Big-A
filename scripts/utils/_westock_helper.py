# -*- coding: utf-8 -*-
"""Westock CLI 统一封装模块
解决两大问题:
  1. --raw 参数在 westock-data-skillhub@1.0.5 中不存在 → 去掉
  2. CLI 输出 Markdown 表格而非 JSON → 通用 Markdown 表格解析器
  3. Windows 环境子进程编码问题 → 显式 encoding='utf-8' + errors='replace'
  4. 多段落输出(如sector ranking含行业/概念/资金三段) → 分段解析

已验证端点:
  - kline:    ✅ npx westock-data-skillhub kline sh000001 --period day --limit 1
  - sector:   ✅ npx westock-data-skillhub sector ranking (含行业/概念/资金三段)
  - fundflow: ✅ npx westock-data-skillhub fund flow sh600000
  - search:   ✅ npx westock-data-skillhub search --query "上证指数"
"""

import subprocess
import re
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WESTOK_CLI = "westock-data-skillhub@1.0.5"


# ═══════════════════════════════════════════
# 通用 Markdown 表格解析器
# ═══════════════════════════════════════════

def _clean_cell(v: str):
    """清洗单元格：去 ** 残留/首尾空白，空串 → None。
    若单元格是纯数字串且原值带百分号，返回原串(由调用方决定转float)。
    """
    if v is None:
        return None
    v = str(v).replace("**", "").strip()
    return v if v else None


def _repair_misaligned(cells: list, headers: list) -> list:
    """错位修复：当数据行列数与表头不一致时对齐。
    - 少列：补 None（记录缺列）
    - 多列：丢弃多余列（记录告警，多为名称列混入相邻单元格导致）
    """
    if len(cells) == len(headers):
        return cells
    if len(cells) < len(headers):
        return cells + [None] * (len(headers) - len(cells))
    return cells[: len(headers)]


def _parse_md_table(text: str) -> list[dict]:
    """解析 Markdown 表格为 list[dict]。
    格式:
      | header1 | header2 | ...
      | --- | --- | ...
      | val1 | val2 | ...
    返回: [{"header1": "val1", "header2": "val2"}, ...]
    鲁棒性:
      - 单元格清洗（** 残留/空白 → None）
      - 列数不一致时对齐修复而非静默丢弃（修复"仅剩6条"问题）
      - 行尾空值列自动剔除（修复"广告营销+9.02%"字段错位）
    """
    lines = text.strip().split('\n')
    rows = []
    headers = None

    for line in lines:
        stripped = line.strip().strip('|')
        # 跳过分隔线: | --- | --- |
        if re.match(r'^[-:\s|]+$', stripped):
            continue
        cells = [_clean_cell(c) for c in stripped.split('|')]

        if headers is None:
            headers = cells
            continue

        cells = _repair_misaligned(cells, headers)
        # 行尾空值列剔除：如 "广告营销 | +9.02% | | |" → 尾部None不影响zip
        if cells != headers:
            rows.append(dict(zip(headers, cells)))

    return rows


def _parse_multi_section(text: str) -> dict[str, list[dict]]:
    """解析多段落 Markdown 输出 (如 sector ranking 含行业/概念/资金三段)
    返回: {"section_name": [rows], ..., "_warnings": [...]}
    段落名来自 `**标题**` 行
    - 某段落解析为空(可能是源端截断或格式异常) → 追加告警到 _warnings
    """
    sections = {}
    warnings = []
    # 确保 text 以 \n 开头，防止第一段 **标题** 被漏掉
    if text and not text.startswith('\n'):
        text = '\n' + text
    # 按 **标题** 分割
    parts = re.split(r'\n\*\*(.+?)\*\*\s*\n', text)
    # parts[0] = 前置文本, parts[1]=标题1, parts[2]=表格1, parts[3]=标题2, ...
    if len(parts) >= 3:
        for i in range(1, len(parts), 2):
            title = parts[i].strip()
            table_text = parts[i + 1] if i + 1 < len(parts) else ""
            rows = _parse_md_table(table_text)
            sections[title] = rows
            if not rows:
                warnings.append(f"段落「{title}」解析为空(源端截断或格式异常)")
    else:
        # 单一段落 → _parse_md_table
        sections["_default"] = _parse_md_table(text)
    if warnings:
        sections["_warnings"] = warnings
    return sections


def _float_or_str(v):
    """尝试转float，失败保留原字符串"""
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return v


# ═══════════════════════════════════════════
# CLI 底层调用
# ═══════════════════════════════════════════

def _run_westock_raw(args: str, timeout: int = 25) -> tuple[str, str]:
    """执行 Westock CLI 并返回 (stdout, stderr)。

    2026-08-02 修复：原实现固定用 `cmd /c "npx ..."` 包装，在 Linux/WSL 上
    cmd 是 Node shim，会把多词子命令（如 `sector ranking`）拆错成 2 个参数，
    导致 CLI 报 "too many arguments" 而静默失败。现改为：
      - POSIX（Linux/macOS）：subprocess 列表调用（shlex 正确处理引号）
      - Windows：保留 cmd /c 包装
    并显式清空 npm 代理（本机 ~/.npmrc 曾硬编码失效代理导致 npx 挂起，见 AGENTS.md）。
    """
    import shlex

    if os.name == "nt":
        cmd: object = f'cmd /c "npx -y {WESTOK_CLI} {args}"'
        shell = True
    else:
        cmd = ["npx", "-y", WESTOK_CLI] + shlex.split(args)
        shell = False

    # 绕过本机可能存在的失效 npm 代理配置（直连 registry 与 westock 接口均可达）
    env = {**os.environ,
           "npm_config_proxy": "", "npm_config_https_proxy": "",
           "NO_PROXY": "*", "no_proxy": "*"}

    try:
        cp = subprocess.run(
            cmd, shell=shell, capture_output=True, encoding='utf-8',
            errors='replace', timeout=timeout, cwd=PROJECT_ROOT, env=env,
        )
        return cp.stdout.strip(), cp.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", "Westock CLI timed out"
    except Exception as e:
        return "", str(e)


def _run_westock(args: str, timeout: int = 25) -> str:
    """执行 Westock CLI 并返回纯文本输出（stdout优先，为空取stderr）"""
    stdout, stderr = _run_westock_raw(args, timeout)
    return stdout if stdout else stderr


def _run_westock_table(args: str, timeout: int = 25) -> list[dict]:
    """执行 Westock CLI 并以 Markdown 表格解析为 list[dict]（单表格场景）"""
    raw = _run_westock(args, timeout)
    if not raw:
        return []
    return _parse_md_table(raw)


def _run_westock_multi(args: str, timeout: int = 25) -> dict[str, list[dict]]:
    """执行 Westock CLI 并解析多段落输出（多表格场景）"""
    raw = _run_westock(args, timeout)
    if not raw:
        return {}
    return _parse_multi_section(raw)


# ═══════════════════════════════════════════
# 各端点的便捷封装
# ═══════════════════════════════════════════

def kline(code: str, period: str = "day", limit: int = 1) -> list[dict]:
    """Westock K线数据
    Args:
        code: 指数代码，如 sh000001, sz399001
        period: day/week/month
        limit: 返回条数
    Returns: [{"date":..., "open":..., "last":..., "high":..., "low":..., ...}]
    """
    return _run_westock_table(
        f'kline {code} --period {period} --limit {limit}'
    )


def _latest_rows(rows: list, n: int) -> list:
    """取最近 n 行 K线（兼容 Westock CLI 降序/升序返回）。

    实测: Westock CLI `kline --limit 2` 返回 **降序**(最新在前)，
    即 rows[0]=今收, rows[1]=昨收。直接按索引取行会取错。
    统一按 date 升序排序后取最后 n 行。
    """
    if not rows:
        return []
    try:
        rows = sorted(rows, key=lambda r: str(r.get("date", "")))
    except Exception:
        pass
    return rows[-n:]


def kline_last(code: str) -> float:
    """获取Westock K线最新收盘价(单值快捷方法)
    Returns: float，失败返回0.0
    """
    rows = _latest_rows(kline(code, limit=2), 1)
    if rows:
        last = rows[-1].get("last", 0)
        return _float_or_str(last) or 0.0
    return 0.0


def kline_prev_last(code: str) -> float:
    """获取Westock K线前一交易日收盘价(用于交叉验证昨收)
    Returns: float，失败返回0.0
    """
    rows = _latest_rows(kline(code, limit=2), 2)
    if len(rows) >= 2:
        last = rows[-2].get("last", 0)
        return _float_or_str(last) or 0.0
    return 0.0


def sector_ranking() -> dict[str, list[dict]]:
    """板块排名（含行业/概念/资金流入 三段）
    Returns: {
        "行业板块涨幅排名": [{"name":..., "changePct":..., ...}],
        "概念板块涨幅排名": [...],
        "行业资金流入 Top5": [...]
    }
    """
    return _run_westock_multi("sector ranking")


def sector_industry_ranking() -> list[dict]:
    """行业板块涨幅排名（便捷方法）"""
    return sector_ranking().get("行业板块涨幅排名", [])


def sector_concept_ranking() -> list[dict]:
    """概念板块涨幅排名（便捷方法）"""
    return sector_ranking().get("概念板块涨幅排名", [])


def fund_flow(code: str, start: str = "", end: str = "") -> list[dict]:
    """个股/板块资金流向
    Args:
        code: 股票代码 sh600000 / 板块代码 pt01801081
        start: 开始日期 YYYY-MM-DD (可选)
        end: 结束日期 YYYY-MM-DD (可选)
    Returns: [{"code":..., "date":..., "MainNetFlow":..., "ClosePrice":..., ...}]
    """
    args = f"fund flow {code}"
    if start:
        args += f" --start {start}"
    if end:
        args += f" --end {end}"
    return _run_westock_table(args)


def fund_flow_range(code: str, start: str, end: str) -> list[dict]:
    """板块资金流日期范围 (便捷方法，固定需start+end)"""
    return fund_flow(code, start=start, end=end)


def search(query: str, search_type: str = "") -> list[dict]:
    """搜索股票/指数/板块
    Args:
        query: 搜索关键词，如 "上证指数", "半导体"
        search_type: 类型过滤, 如 "sector" (可选)
    Returns: [{"code":..., "name":..., ...}]
    """
    cmd = f'search --query "{query}"'
    if search_type:
        cmd += f" --type {search_type}"
    return _run_westock_table(cmd)


def sector_constituent(sector_code: str) -> list[dict]:
    """板块成分股
    Args:
        sector_code: 板块代码
    Returns: [{"code":..., "name":..., ...}]
    """
    return _run_westock_table(f"sector constituent {sector_code}")


def available() -> bool:
    """检测 Westock CLI 是否可用（通过实际kline调用验证）"""
    rows = kline("sh000001", limit=1)
    return len(rows) > 0 and "last" in rows[0]


# ═══════════════════════════════════════════
# __main__: 自检
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import io
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    print("=== Westock CLI 自检 ===\n")
    print(f"CLI 可用: {available()}\n")

    # K线测试
    kl = kline("sh000001", limit=1)
    print(f"K线(sh000001): {kl}")
    print(f"kline_last: {kline_last('sh000001')}")
    print(f"kline_prev_last: {kline_prev_last('sh000001')}\n")

    # Sector测试(多段落)
    sectors = sector_ranking()
    for title, rows in sectors.items():
        print(f"{title}: {len(rows)}条, TOP1={rows[0] if rows else 'None'}")
    print(f"\n行业TOP1: {sector_industry_ranking()[:1]}")
    print(f"概念TOP1: {sector_concept_ranking()[:1]}\n")

    # 资金流测试
    ff = fund_flow("sh600000")
    print(f"资金流(sh600000): {ff[0] if ff else 'None'}")
