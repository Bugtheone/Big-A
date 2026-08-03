#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
板块涨幅多源交叉验证工具 — 解决"板块层只有腾讯单源"问题（对标指数层双源做法）。

给定行业关键词，从多源拉取该板块今日涨跌幅并对比：
  ① 腾讯行业板块（api.sectors，实时/收盘，等权板块指数）
  ② 新浪板块资金流 avg_changeratio（成分股平均涨跌幅，实时/收盘）
  ③ 东财 push2 clist（若未被 IP 风控；加权板块指数）—— 被风控时自动跳过并标注
  ④ 申万一级行业指数（Tushare 官方，收盘后，仅一级有日线数据）

用途：
  - 盘中/盘后核对任意板块的跨源一致性（板块层多源交叉）
  - 日报告板块表自动附"交叉源涨幅"列
  - 解释跨源差异（成分股/加权方式不同 → 数值可差 ±1pt 属正常）

用法:
  python scripts/tools/sector_cross_check.py "轨交"
  python scripts/tools/sector_cross_check.py "电力"
"""
import io
import json
import os
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


# 板块名同义词映射（跨源分类命名不同，如腾讯"轨交设备Ⅱ" vs 新浪"铁路、船舶、航空航天…"）
_SYNONYMS = {
    "轨交": ["轨交", "铁路", "运输设备"],
    "电力": ["电力", "电气"],
    "煤炭": ["煤炭"],
    "银行": ["银行", "货币金融"],
    "证券": ["证券", "非银"],
    "医药": ["医药", "生物"],
    "白酒": ["白酒", "饮料"],
    "电子": ["电子", "半导体", "元件"],
    "机械": ["机械", "设备"],
    "汽车": ["汽车", "整车"],
    "军工": ["军工", "国防", "航天"],
    "地产": ["地产", "房地产", "开发"],
    "通信": ["通信", "光模块"],
    "计算机": ["计算机", "软件", "信息"],
    "家电": ["家电"],
}


def _keywords(keyword: str) -> list:
    """返回待匹配关键词集合（原始词 + 同义词）。"""
    return [keyword] + _SYNONYMS.get(keyword, [])


def _match(name: str, kws: list) -> bool:
    return any(k in name for k in kws)


def _tencent(keyword: str) -> list:
    from scripts.market_api import api
    kws = _keywords(keyword)
    out = []
    for s in api.sectors(100) or []:
        if _match(s.get("name") or "", kws):
            out.append({"源": "腾讯", "板块": s["name"], "涨跌%": s.get("change_pct")})
    return out


def _sina(keyword: str) -> list:
    import requests
    s = requests.Session(); s.trust_env = False
    s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"})
    url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           "MoneyFlow.ssl_bkzj_bk")
    kws = _keywords(keyword)
    out, seen = [], set()
    try:
        r = s.get(url, params={"page": 1, "num": 200, "sort": "netamount", "asc": 0, "fenlei": 2}, timeout=10)
        for d in json.loads(r.text):
            nm = d.get("name") or ""
            if _match(nm, kws) and nm not in seen:  # 去重同名分类
                seen.add(nm)
                out.append({"源": "新浪", "板块": nm,
                            "涨跌%": round(float(d.get("avg_changeratio") or 0) * 100, 2)})
    except Exception as e:
        out.append({"源": "新浪", "板块": f"ERROR: {e}", "涨跌%": None})
    return out


def _eastmoney(keyword: str) -> tuple:
    """东财 push2 clist（可能被 IP 风控）。返回 (rows, blocked)。"""
    import requests
    s = requests.Session(); s.trust_env = False
    s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"})
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    kws = _keywords(keyword)
    params = {"pn": "1", "pz": "100", "po": "1", "np": "1",
              "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": "2", "invt": "2",
              "fid": "f3", "fs": "m:90+t:2", "fields": "f12,f14,f3"}
    try:
        d = s.get(url, params=params, timeout=10).json()
        rows = [{"源": "东财", "板块": it.get("f14"), "涨跌%": it.get("f3")}
                for it in (d.get("data", {}).get("diff") or []) if _match(str(it.get("f14")), kws)]
        return rows, False
    except Exception:
        return [], True


def _shenwan(keyword: str) -> list:
    from scripts.tushare_api import get_pro
    pro = get_pro()
    kws = _keywords(keyword)
    out = []
    try:
        cls = pro.index_classify(level="L1", src="SW2021").to_dict("records")
        for it in cls:
            if _match(it.get("industry_name", ""), kws):
                rdf = pro.index_daily(ts_code=it["index_code"], start_date="20260801", end_date="20260803")
                rows = rdf.to_dict("records")
                if rows:
                    rows.sort(key=lambda r: r["trade_date"])
                    out.append({"源": "申万官方", "板块": it["industry_name"],
                                "涨跌%": round(rows[-1].get("pct_chg", 0), 2)})
    except Exception as e:
        out.append({"源": "申万官方", "板块": f"ERROR: {e}", "涨跌%": None})
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python scripts/tools/sector_cross_check.py <关键词>")
        return 1
    kw = sys.argv[1]
    print(f"=== 板块多源交叉验证: 「{kw}」 ({datetime.now():%m-%d %H:%M}) ===\n")

    all_rows = _tencent(kw) + _sina(kw)
    em_rows, em_blocked = _eastmoney(kw)
    all_rows += em_rows
    all_rows += _shenwan(kw)

    if not all_rows:
        print(f"  四源均未匹配「{kw}」——请换关键词（如'电力/医药/机械'）")
        return 1

    for r in all_rows:
        v = f"{r['涨跌%']:+.2f}%" if r["涨跌%"] is not None else "取数失败"
        print(f"  [{r['源']}] {r['板块']}: {v}")
    if em_blocked:
        print("  [东财] 🔴 push2 被 IP 风控，自动跳过（解封后自动纳入）")

    # 判定
    vals = [r["涨跌%"] for r in all_rows if r["涨跌%"] is not None]
    if len(vals) >= 2:
        pos = sum(1 for v in vals if v > 0)
        neg = sum(1 for v in vals if v < 0)
        if pos == len(vals) or neg == len(vals):
            print(f"\n  判定: {'✅ 全部源同向上涨' if pos == len(vals) else '✅ 全部源同向下跌'}（方向一致）")
            spread = max(vals) - min(vals)
            print(f"  数值跨度: {min(vals):+.2f}% ~ {max(vals):+.2f}%（跨源差 {spread:.2f}pt，"
                  f"源于成分股/加权口径不同）")
        else:
            print("\n  判定: ⚠️ 跨源方向分歧——需检查成分股定义差异（同名板块成分不同）")
    else:
        print("\n  判定: 可用源不足（<2），无法交叉——注意单源风险")
    return 0


if __name__ == "__main__":
    sys.exit(main())
