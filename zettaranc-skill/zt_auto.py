#!/usr/bin/env python
"""zettaranc-skill 一键自动调用入口（AI 对话专用）。

用法（AI 对话中命中需求即调用，用户无需知道命令行）:
    python zt_auto.py analyze 600519.SH          # 自动 sync（若缺数据）+ analyze，输出人话报告
    python zt_auto.py analyze 600519.SH --json   # JSON 输出
    python zt_auto.py diagnose 000001.SZ         # 持仓诊断（自动 sync）
    python zt_auto.py score 600519.SH            # 综合评分（自动 sync）
    python zt_auto.py backtest shaofu 600519.SH  # 回测（自动 sync 250 天）
    python zt_auto.py screen B1 --limit 10       # 全市场选股（不 sync，需先批量同步）

设计目标：把「先查库有没有→没有就 sync→再跑命令」的三步链路封成一个调用，
AI 对话中一条 bash 命令即可，用户全程无感。
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_ROOT))
os.chdir(SKILL_ROOT)

DB_PATH = SKILL_ROOT / "data" / "stock_data.db"


def _is_synced(ts_code: str, need_days: int = 120) -> bool:
    """检查 DB 中该代码是否已有足够近期数据（最近 K 线距今 ≤ 7 天 且 条数 ≥ need_days*0.6）"""
    if not DB_PATH.exists():
        return False
    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            row = conn.execute(
                "SELECT COUNT(*), MAX(trade_date) FROM daily_kline WHERE ts_code = ?",
                (ts_code,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return False
    if not row:
        return False
    count, latest = row[0], row[1]
    if not latest or not count:
        return False
    # 条数足够 + 最近 K 线 7 天内（容忍节假日）
    if count < int(need_days * 0.6):
        return False
    try:
        latest_dt = datetime.strptime(str(latest)[:8], "%Y%m%d")
    except ValueError:
        return False
    return (datetime.now() - latest_dt).days <= 7


def _auto_sync(ts_code: str, days: int = 250) -> str:
    """自动同步单只股票 + 指标缓存"""
    print(f"[zt-auto] 本地无 {ts_code} 数据或已过期，自动同步 {days} 天...", file=sys.stderr)
    r = subprocess.run(
        [sys.executable, "-m", "modules.data_sync", "sync",
         "--ts_code", ts_code, "--days", str(days), "--indicators"],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        print(r.stderr[-500:], file=sys.stderr)
        raise RuntimeError(f"sync {ts_code} 失败")
    return f"synced {ts_code} {days}d"


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1

    cmd = args[0]

    # 需要 ts_code 的子命令：倒数第 1 个非 flag 参数即代码（--days 等开关已排除其值）
    ts_cmd = {"analyze", "diagnose", "score"}
    bt_cmd = {"backtest"}

    if cmd in ts_cmd or cmd in bt_cmd:
        # 找出第一个像代码的参数（6位数字.SH/.SZ 或 6位数字）
        import re
        code = None
        for a in args[1:]:
            if re.fullmatch(r"\d{6}(\.(SH|SZ|BJ))?", a, re.I):
                code = a
                break
        if not code:
            print(f"[zt-auto] 未找到股票代码参数: {args}", file=sys.stderr)
            return 2
        code = code if "." in code else (code + (".SH" if code[0] in "69" else ".SZ"))
        # backtest 用 250 天，analyze/diagnose/score 用 120 天门槛
        need = 250 if cmd in bt_cmd else 120
        if not _is_synced(code, need):
            _auto_sync(code, days=250)
        else:
            print(f"[zt-auto] {code} 本地数据已就绪，跳过同步", file=sys.stderr)

    # 转发给 CLI：python -m modules.cli <原始参数>
    cli_args = ["-m", "modules.cli"] + args
    r = subprocess.run([sys.executable] + cli_args, timeout=900)
    return r.returncode


if __name__ == "__main__":
    if __name__ == "__main__":
        sys.exit(main())
