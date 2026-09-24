#!/usr/bin/env bash
# 全市场日K线同步（后台跑）——a-stock-data 免费源路径
# 5562 只 × 250 天，5 并发 + 限流，预计 40~60 分钟
cd /home/dev/grok_code/zettaranc-skill
LOG=/home/dev/grok_code/reports/daily/2026-09-13/sync_full_market.log
mkdir -p "$(dirname "$LOG")"
echo "[START] $(date '+%F %T') 全市场K线同步启动（5562只×250天，5并发）" >> "$LOG"
python -m modules.data_sync sync --days 250 >> "$LOG" 2>&1
echo "[DONE] $(date '+%F %T') 退出码 $?" >> "$LOG"
