#!/bin/bash
# AI 动手前快照：为当前工作区创建可回滚点（tag + stash）。
# 用法:
#   bash scripts/tools/git_snapshot.sh              # 普通快照 ai-snapshot-<ts>
#   bash scripts/tools/git_snapshot.sh --label 主线改造  # 带标签
# 说明: 创建轻量 tag 指向当前 HEAD（回滚点）；若有无提交改动则 stash 保留。
set -e
cd "$(dirname "$0")/../.."

LABEL="${2:-}"
TS=$(date +%Y%m%d-%H%M%S)
TAG="ai-snapshot-${TS}${LABEL:+-${LABEL}}"

# 1. 快照 tag（指向当前 HEAD）
git tag -f "$TAG" >/dev/null 2>&1
echo "✅ 快照点: $TAG"

# 2. 若有未提交改动，stash 保存（保留 --keep-index 不动暂存）
if ! git diff --quiet 2>/dev/null; then
  git stash push -m "ai-snapshot-$TS" >/dev/null 2>&1 || true
  echo "⚠️ 未提交改动已 stash（可 git stash pop 恢复）"
else
  echo "ℹ️ 工作区干净"
fi

echo ""
echo "回滚到该快照: git reset --hard $TAG"
echo "查看快照列表: git tag -l 'ai-snapshot-*'"
