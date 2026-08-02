---
name: 🐛 Bug 报告
about: 数据取数 / 分析脚本 / 工程链路的问题报告
title: "[Bug] "
labels: bug
assignees: ''
---

## 问题描述
<!-- 清晰描述：什么功能/端点/脚本，表现是什么 -->

## 复现步骤
1. 调用：`python scripts/...`（或对话提问：...）
2. 预期：
3. 实际：

## 数据源与取数信息（重要）
- 涉及数据源：腾讯 / 东财 / 同花顺 / Tushare / westock / 问财（删去不适用）
- 日期/代码：
- 返回内容（JSON 或报错片段）：

## 环境
- Python 环境：`dsa_env` / 其他
- a-stock-data 版本：`python scripts/verify_a_stock_data_v360.py` 输出
- 网络：直连 / 代理（WSL 网关 IP）

## 日志 / 审计
<!-- data_gate 审计输出、log/daily_job.log 片段等 -->

## 排查建议（可选）
<!-- 是否已定位根因 / 怀疑点 -->

> 提交规范：修复用 `fix: ...` 约定式提交；修完需过全部门禁（pytest + ruff + mypy + 主入口 + V3.6.0 门禁）方可合入。
