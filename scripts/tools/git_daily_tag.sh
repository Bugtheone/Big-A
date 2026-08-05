#!/bin/bash
# 每日里程碑 tag：为当天创建 `ai-snapshot-YYYYMMDD`（整体回滚点）。
# 用法: bash scripts/tools/git_daily_tag.sh
# 建议: crontab 每日 18:10（盘后）自动运行。
set -e
cd "$(dirname "$0")/../.."

TAG="ai-snapshot-$(date +%Y%m%d)"
git tag -f "$TAG" >/dev/null 2>&1
echo "✅ 每日快照: $TAG"
echo "回滚到今天: git reset --hard $TAG"
