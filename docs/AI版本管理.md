# AI 代码版本管理手册（防改乱 + 随时回滚）

> **版本**：2026-08-05 v1.0｜**适用**：所有 AI 对话、子代理、调度任务写代码时
> **核心**：**AI 只写代码，不碰历史**——改动前留基线、小步提交、review 才留、门禁拦截、tag 里程碑

---

## 一、核心原则（4 条）

1. **AI 动手前，必须有干净基线**（可回滚点）
2. **AI 改动后，必须 review diff 才留**（不满意即回滚）
3. **回滚是"一条命令"**（checkout / reset / reflog 三选一）
4. **AI 禁止破坏性操作**（config.toml 已 deny：git reset --hard / git push -f / rm -rf）

## 二、AI 改动标准工作流（5 步）

```
① 动手前: bash scripts/tools/git_snapshot.sh（快照 tag + stash 未提交）
② 小步改: 一个任务一个 commit（feat/fix/docs 语义化）
③ 改完: git diff 逐行 review → 满意 commit / 不满意 git checkout -- 回滚
④ 门禁: pre-commit（ruff/mypy/main-entry/测试）通过才推送
⑤ 里程碑: bash scripts/tools/git_daily_tag.sh（每日 tag，crontab 自动）
```

## 三、回滚命令速查表

| 场景 | 命令 | 说明 |
|---|---|---|
| 撤销 AI 未提交改动 | `git checkout -- <文件>` / `git stash` | 最常用 |
| 撤销已 commit（未推送）| `git reset --soft HEAD~1` | 改动保留 |
| 撤销已 commit（彻底）| `git reset --hard HEAD~1` | ⚠️ **用户手动**（AI 已 deny）|
| 回到快照点 | `git reset --hard ai-snapshot-YYYYMMDD-HHMMSS` | 用户执行 |
| 回到当日 | `git reset --hard ai-snapshot-20260805` | 每日 tag |
| 误删文件 | `git checkout HEAD -- <路径>` | 恢复 |
| **找回丢弃改动** | `git reflog` → `git cherry-pick <hash>` | **终极保险** |

> **只要 commit 过就丢不了**（reflog 兜底）——勤提交 + 标记是回滚前提。

## 四、三道机器防线

| 防线 | 配置 | 状态 |
|---|---|---|
| deny 破坏操作 | `~/.grok/config.toml`（禁 reset --hard/push -f/rm -rf）| ✅ |
| pre-commit 门禁 | ruff + mypy + main-entry + 测试 | ✅ |
| CI 质量门禁 | `.github/workflows/ci.yml`（push 自动跑）| ✅ |

## 五、快照工具

```bash
# 动手前快照（推荐每次 AI 改代码前跑）
bash scripts/tools/git_snapshot.sh
bash scripts/tools/git_snapshot.sh --label 主线改造   # 带标签

# 每日里程碑（crontab 18:10 自动）
bash scripts/tools/git_daily_tag.sh
```

## 六、GitHub main 分支保护（替代方案：本地 pre-push hook）

> ⚠️ **GitHub 免费版私有仓库不支持服务器端分支保护**（需 Pro 或公开仓库，实测 API 返回 403）。

**本地替代已落地（`.githooks/pre-push` + `git config core.hooksPath .githooks`）**：
- 禁止 force push 到 main（历史重写）
- 禁止删除 main 分支
- 普通 push 放行（正常提交，可回滚）
- hook 入库（版本可控）+ deny 规则防 AI 删除 hook

**如需 GitHub 服务器级保护**（更强）：仓库公开或升级 Pro 后，按以下配置：
1. GitHub → Settings → Branches → Add rule
2. Branch name pattern: `main`
3. 勾选：
   - ✅ Require pull request reviews before merging
   - ✅ Require status checks（勾选 `quality`、`integration`）
   - ✅ Do not allow bypassing
4. 效果：**直接 push main 被拦，必须 PR + 门禁 + review**

## 七、大任务隔离（worktree）

```bash
# 大改造用独立 worktree（AI 实验不影响主工作区）
git worktree add ../ai-experiment -b feature/xxx
# 实验满意后合并，不满意直接删除 worktree（主工作区无损）
```

## 八、违规示例 vs 正解

| ❌ 违规 | ✅ 正解 |
|---|---|
| AI 直接改 20 个文件一把 commit | 一个任务一个 commit（小步）|
| AI 执行 git reset --hard | 用户手动执行（AI 已 deny）|
| 改乱后无法恢复 | 动手前跑 git_snapshot.sh → reset 回快照 |
| 大改造直接在 main 上 | worktree/feature 分支隔离 |

---
**归档**：本手册与 `scripts/tools/git_snapshot.sh`、`git_daily_tag.sh`、`~/.grok/config.toml` deny、AGENTS.md 版本纪律 构成完整版本管理体系。
