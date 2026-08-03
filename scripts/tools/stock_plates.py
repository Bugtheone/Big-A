#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个股四维板块归属工具（adata get_plate_east）

给定个股代码，返回其四维板块归属：行业 + 地域 + 风格 + 概念（题材）。
数据源：adata 2.9.5（东财公开数据，多源封装；东财 IP 风控期间不可用，其余功能正常）。

用法:
  python scripts/tools/stock_plates.py 600519          # 单只
  python scripts/tools/stock_plates.py 600519 300059   # 多只

输出：行业 / 地域 / 风格（大盘·权重·消费风格等）/ 概念（题材标签）
"""
import io
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 风格类概念关键词（东财将风格归入概念，按名称区分）
_STYLE_KW = ("风格", "大盘", "小盘", "权重", "龙头", "指数", "百元", "茅指数",
             "富时", "标普", "MSCI", "上证180", "上证50", "沪深300", "HS300",
             "中证500", "中证1000", "融资融券", "机构重仓", "标准普尔", "央视50",
             "沪股通", "深股通", "AH", "券商重仓", "基金重仓", "证金持股", "央行持股",
             "汇金持股", "转融券", "注册制", "核准制", "破净", "破发")


def get_plates(code: str) -> dict:
    """个股四维板块归属。返回 {行业:[], 地域:[], 风格:[], 概念:[]}。"""
    import adata
    df = adata.stock.info.get_plate_east(stock_code=code)
    out = {"行业": [], "地域": [], "风格": [], "概念": []}
    for _, r in df.iterrows():
        ptype = str(r.get("plate_type", ""))
        name = str(r.get("plate_name", ""))
        if "行业" in ptype:
            out["行业"].append(name)
        elif "板块" in ptype:  # 东财"板块"= 地域板块（如贵州板块）
            out["地域"].append(name)
        elif "概念" in ptype:
            if any(k in name for k in _STYLE_KW):
                out["风格"].append(name)
            else:
                out["概念"].append(name)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python scripts/tools/stock_plates.py <代码> [代码...]")
        return 1
    for code in sys.argv[1:]:
        try:
            p = get_plates(code)
            print(f"=== {code} 四维板块归属 ===")
            print(f"  行业: {'、'.join(p['行业']) or '—'}")
            print(f"  地域: {'、'.join(p['地域']) or '—'}")
            print(f"  风格: {'、'.join(p['风格']) or '—'}")
            print(f"  概念: {'、'.join(p['概念']) or '—'}")
            print()
        except Exception as e:
            print(f"  {code} 失败: {e}（东财被封或代码错误）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
