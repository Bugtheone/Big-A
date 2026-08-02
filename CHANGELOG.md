# Changelog

本项目遵循语义化版本（SemVer）。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased] — 2026-08-02

### 新增

- **核心模块单测 46 例**（Issue #1，测试覆盖率提升）：`tests/test_market_api.py`（29 例：_safe_float/_calc_ma/_is_weekend_date/_resolve_index/_ma_position）+ `tests/test_market_router.py`（4 例：load_config）+ `test_data_gate.py` 扩展（13 例：audit_summary/audit_markdown/diagnose_zero_traps）。全套测试 91 → **137 例全绿**。

### 工程化

- 接入 GitHub Issues 模板（bug/feature）+ PR 模板（质量门禁检查清单）+ `docs/需求与任务.md` Backlog（`d7de019`，补标准流程 ①③⑦）

## [v0.1.0] — 2026-08-02

首个工程化基线版本：引入质量门禁工具链，修复存量真实 bug。

### 新增

- **工程化工具链**（`pyproject.toml` + `.pre-commit-config.yaml`）：
  - ruff 质量门禁：启用真实 bug 类规则 `E9 / F63 / F7 / F82 / E722`（裸 except 为项目铁律）
  - mypy 类型检查：核心纯函数模块 `data_validator / index_constants / valuation`
  - pre-commit 本地钩子：ruff + mypy + 主入口检查（`repo: local`，GitHub 不可达环境可用）
- **主入口合规检查脚本** `scripts/tools/check_main_entry.py`（CI 与 pre-commit 共用）
- **CI 质量门禁新增三项**：主入口合规、ruff 检查、mypy 检查（`.github/workflows/ci.yml`）

### 修复

- `eastmoney_news.py`：个股新闻 / 全球宏观新闻接口 `params` 未定义导致运行时 NameError，
  已按 SKILL.md §5.1 契约补全参数（`page_index / page_size / stock_list / ann_type` 等）
- `_entry_sectors.py`：Gate0 分支引用未定义变量 `klines`（应为 `kls`），数据不足时必然 NameError
- `_30d_mainline_b1.py`：恢复被注释掉的 `import sys, os, io`（顶层代码实际使用）
- `_fund_flow_601136.py` / `_topic_attribution.py`：补齐缺失的 `import os`
- `data_validator.py`：`date: str = None` 隐式 Optional → 显式 `Optional[str]`（mypy 修复）
- `test_tushare_pro.py`：模块级 `sys.stdout = io.TextIOWrapper(...)` 副作用破坏 pytest 捕获（
  收集全目录即 `I/O operation on closed file` 崩溃）、辅助函数命名 `test` 与 pytest 收集规则
  冲突（误收集为用例报错）、硬编码 Windows 路径 —— 均移入 `if __name__ == '__main__'` 并改为可移植写法
- 23 个一次性分析脚本补 `if __name__ == '__main__'` 保护，杜绝被 import 时顶层副作用

### 工程化约定（生效中）

- 提交规范：约定式提交（`feat: / fix: / chore: / test: / refactor:`），每个功能点一个 commit
- 质量门禁：CI 全绿（语法 + ruff + mypy + pytest + 主入口）方可合入 `main`
- 密钥管理：`config/` 不纳入版本控制，API Key 走环境变量（`IWENCAI_API_KEY` 等）
