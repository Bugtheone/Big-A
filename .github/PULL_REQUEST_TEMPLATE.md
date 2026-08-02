## 变更类型

- [ ] feat（新功能/端点）
- [ ] fix（缺陷修复）
- [ ] test（测试）
- [ ] docs（文档）
- [ ] chore（工程化/依赖/工具链）
- [ ] refactor（重构，无行为变化）

## 变更说明
<!-- 一句话说明改了什么、为什么 -->

## 关联 Issue
<!-- 修复 #编号 / 需求 #编号（与 GitHub Issues 形成闭环，对应标准流程①③⑦） -->

## 质量门禁检查清单（合入 main 前必须全绿）

- [ ] `python -m pytest tests/ -q` 全绿（当前 91 例，新增功能应有对应测试）
- [ ] `ruff check scripts tests` 通过（bug 类规则 E9/F63/F7/F82/E722）
- [ ] `mypy` 通过（核心纯函数模块）
- [ ] `python scripts/tools/check_main_entry.py` 通过（主入口合规）
- [ ] `python scripts/verify_a_stock_data_v360.py` 通过（数据源版本保证门禁）
- [ ] 约定式提交信息（`feat:` / `fix:` / `chore:` / `test:` / `docs:` / `refactor:`）
- [ ] 涉及数据源变更时：两源以上交叉验证结论写入 PR 描述

## 测试说明
<!-- 新增/修改的测试用例；数据源联调结果（日期/代码/返回值） -->
