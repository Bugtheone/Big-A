#!/usr/bin/env python3
"""主入口合规检查 — scripts/ 下非库模块必须包含 `if __name__ == '__main__'`。

质量门禁（AGENTS.md 约定 + CI 调用）：
  - 遍历 git 跟踪的 scripts/ 下所有 .py（排除 __init__.py）
  - 纯库模块（被其他模块 import、无顶层执行）豁免，见 LIB_ALLOWLIST
  - 其余脚本若缺主入口则报错退出（exit 1）
用法：python scripts/tools/check_main_entry.py
"""
import os
import subprocess
import sys

# 纯库模块豁免（被 import 使用，顶层无副作用，主入口非必需）
# 豁免依据（防止滥豁免，新增条目必须同步补充理由）：
#   cninfo_api.py        巨潮公告/互动易 API 封装库（仅被其他模块 import）
#   eastmoney_info.py    东财 F10 信息封装库（仅被其他模块 import）
#   index_constants.py   九指数常量/价格区间纯数据定义（零副作用）
#   mootdx_api.py        通达信行情客户端封装库（仅被其他模块 import）
#   sina_api.py          新浪财经 API 封装库（仅被其他模块 import）
#   tushare_pro_data.py  Tushare Pro 38 函数封装库（仅被其他模块 import）
#   valuation.py         估值计算纯函数模块（被 market_api 等 import）
LIB_ALLOWLIST = {
    "scripts/cninfo_api.py",
    "scripts/eastmoney_info.py",
    "scripts/index_constants.py",
    "scripts/mootdx_api.py",
    "scripts/sina_api.py",
    "scripts/tushare_pro_data.py",
    "scripts/valuation.py",
}


def main() -> int:
    """执行主入口合规检查，返回进程退出码。"""
    out = subprocess.check_output(["git", "ls-files", "scripts/"], text=True)
    files = [f for f in out.splitlines() if f.endswith(".py") and not f.endswith("__init__.py")]
    bad = []
    for f in files:
        if f in LIB_ALLOWLIST:
            continue
        with open(f, encoding="utf-8") as fh:
            src = fh.read()
        if "__main__" not in src:
            bad.append(f)
    if bad:
        print(f"主入口检查未通过：{len(bad)} 个脚本缺少 if __name__ == '__main__' 保护：")
        for f in bad:
            print(f"  - {f}")
        return 1
    print(f"主入口检查通过（{len(files) - len(LIB_ALLOWLIST)} 个脚本全部合规）")
    return 0


if __name__ == '__main__':
    sys.exit(main())
