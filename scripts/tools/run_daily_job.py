#!/usr/bin/env python3
"""
每日生产调度入口 — 收盘后运行本仓库每日分析流水线。

由 crontab 调用（配置见 docs/运维与调度.md）：
    0 18 * * 1-5 cd /home/dev/grok_code && \
        /home/dev/miniforge3/envs/dsa_env/bin/python scripts/tools/run_daily_job.py \
        >> log/daily_job.log 2>&1

流水线（任一步失败不阻断后续步骤，退出码 = 失败步骤数）：
    1. 每日复盘 v2（多源交叉验证 + 全市场复盘）→ scripts/analysis/daily/_daily_review_v2.py
    2. 飞书日报推送（大盘/涨停/板块/成交额）    → scripts/tools/daily_feishu_report.py

用法:
    python scripts/tools/run_daily_job.py             # 正常运行
    python scripts/tools/run_daily_job.py --dry-run   # 仅执行复盘，跳过飞书推送
"""
import os
import subprocess
import sys
import time
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 单步超时（秒）：多源交叉验证在弱网下可能较慢，1800s 上限防止无限挂起
_STEP_TIMEOUT = 1800


def _log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def run_step(name: str, script: str) -> bool:
    """运行单个流水线步骤（子进程，cwd=项目根），返回是否成功。"""
    cmd = [sys.executable, script]
    _log(f"=== 步骤: {name} ===  $ {' '.join(cmd)}")
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=_PROJECT_ROOT, timeout=_STEP_TIMEOUT)
        ok = r.returncode == 0
    except subprocess.TimeoutExpired:
        _log(f"[ERROR] {name} 超时（>{_STEP_TIMEOUT}s），已终止")
        ok = False
    except Exception as exc:  # 显式捕获启动异常，杜绝裸 except
        _log(f"[ERROR] {name} 启动失败: {exc}")
        ok = False
    _log(f"--- {name} -> {'OK' if ok else 'FAIL'} ({time.time() - t0:.1f}s)")
    return ok


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    steps = [("每日复盘 v2", "scripts/analysis/daily/_daily_review_v2.py")]
    if dry_run:
        _log("--dry-run 模式：跳过飞书推送")
    else:
        steps.append(("飞书日报推送", "scripts/tools/daily_feishu_report.py"))
    # 盘后复核更新：每次复盘执行时重新拉取 Tushare 官方数据，更新收盘总结（2026-08-05）
    steps.append(("盘后复核更新", "scripts/tools/post_close_update.py"))
    # 业绩预告情报：盘后 Tushare forecast 刷新后自动生成（AI 对话可读 earnings_forecast_*.md）
    steps.append(("业绩预告情报", "scripts/tools/earnings_forecast.py"))

    fails = 0
    for name, script in steps:
        if not run_step(name, script):
            fails += 1
    _log(f"流水线结束：{len(steps) - fails}/{len(steps)} 步骤成功（退出码={fails}）")
    return fails


if __name__ == "__main__":
    sys.exit(main())
