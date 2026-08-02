# -*- coding: utf-8 -*-
"""乳业验证：获取同花顺板块成分股 + 腾讯实时行情 + 差异分析"""
import sys, os, json

if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    import requests
    sess = requests.Session()
    sess.trust_env = False

    print("=" * 70)
    print(" 乳业板块数据验证 - 最终分析")
    print("=" * 70)

    # ========================================
    # Part 1: Tushare 乳业板块成分股
    # ========================================
    print("\n--- 同花顺 乳业(885462.TI) 成分股 ---")
    try:
        from scripts.tushare_api import get_pro
        pro = get_pro()
        members = pro.ths_member(ts_code="885462.TI")
        dairy_members = []
        if members is not None and len(members) > 0:
            for _, row in members.iterrows():
                code = str(row.get("con_code", "")).split(".")[0]
                name = row.get("name", "")
                dairy_members.append({"code": code, "name": name})
            print(f"  成分股数量: {len(dairy_members)}")
            for m in dairy_members[:15]:
                print(f"    {m['code']} {m['name']}")
    except Exception as e:
        print(f"  失败: {e}")
        dairy_members = []

    # ========================================
    # Part 2: 腾讯实时行情 — 批量拉取所有成分股
    # ========================================
    print("\n--- 腾讯实时行情 ---")
    quotes = []

    if dairy_members:
        codes = ",".join([f"sh{m['code']}" if m['code'].startswith("6") else f"sz{m['code']}" for m in dairy_members])
    else:
        # fallback
        codes = "sh600887,sz002946,sh600882,sz002329,sz300106,sh600419,sz002770,sh600597,sh600429,sz300898"
        dairy_members = [{"code": c.replace("sh","").replace("sz",""), "name": "?"} for c in codes.split(",")]

    try:
        r = sess.get(f"http://qt.gtimg.cn/q={codes}", timeout=10)
        r.encoding = "gbk"
        code_map = {}
        for line in r.text.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("~")
            if len(parts) < 40:
                continue
            code = parts[2]
            name = parts[1]
            price = float(parts[3]) if parts[3] else 0
            preclose = float(parts[4]) if parts[4] else 0
            mc_yi = float(parts[45]) / 1e8 if len(parts) > 45 and parts[45] else 0  # 总市值
            pct = round((price - preclose) / preclose * 100, 2) if preclose > 0 else 0

            code_map[code] = {
                "code": code, "name": name,
                "price": price, "preclose": preclose,
                "pct": pct, "mc_yi": mc_yi,
            }

        # 配对
        for m in dairy_members:
            if m["code"] in code_map:
                quotes.append(code_map[m["code"]])
                m.update(code_map[m["code"]])

        print(f"  匹配成功: {len(quotes)}/{len(dairy_members)} 只")

        # 排序
        quotes.sort(key=lambda x: x["pct"], reverse=True)

        print(f"\n  {'代码':<8} {'名称':<10} {'涨跌幅':<8} {'市值(亿)':<10}")
        print("  " + "-" * 40)

        w_total = 0
        w_pct = 0
        eq_pct = 0
        up = 0
        down = 0

        for q in quotes:
            print(f"  {q['code']:<8} {q['name']:<10} {q['pct']:>+6.2f}%   {q['mc_yi']:>8.1f}")
            eq_pct += q["pct"]
            if q["mc_yi"] > 0:
                w_pct += q["pct"] * q["mc_yi"]
                w_total += q["mc_yi"]
            if q["pct"] > 0:
                up += 1
            elif q["pct"] < 0:
                down += 1

        eq_avg = round(eq_pct / len(quotes), 2) if quotes else 0
        mc_weighted = round(w_pct / w_total, 2) if w_total > 0 else 0

        print(f"\n  {'='*40}")
        print(f"  成分股数: {len(quotes)} (涨{up}/跌{down})")
        print(f"  等权平均: {eq_avg:+.2f}%")
        print(f"  市值加权: {mc_weighted:+.2f}%")

    except Exception as e:
        print(f"  失败: {e}")
        eq_avg = None
        mc_weighted = None

    # ========================================
    # Part 3: 交叉验证汇总
    # ========================================
    print("\n" + "=" * 70)
    print(" 交叉验证结论")
    print("=" * 70)

    # S3 同花顺板块指数数据
    s3_pct = 6.18  # 885462.TI 乳业

    print(f"""
      [S3] 同花顺板块指数(885462.TI)  +{s3_pct}%  — 官方板块指数，流通市值加权
      [S5] 腾讯等权             {eq_avg:+.2f}%  — {len(quotes)}只成分股算术平均
      [S5] 腾讯市值加权         {mc_weighted:+.2f}%  — 按总市值加权""" if eq_avg else """
      [S3] 同花顺板块指数(885462.TI)  +{s3_pct}%  — 官方板块指数，流通市值加权""")

    if eq_avg and mc_weighted:
        diff_eq = abs(s3_pct - eq_avg)
        diff_mc = abs(s3_pct - mc_weighted)
        print(f"""
      差异分析:
        S3 vs 等权: {diff_eq:.2f}%
        S3 vs 市值加权: {diff_mc:.2f}%

      {"" if diff_mc < 1.0 else "同花顺板块指数 vs 腾讯市值加权的差异可能来自:&#10;  1. 同花顺用流通市值加权(非总市值)&amp;#10;  2. 样本股范围不同(同花顺可能有更多小票不在此次查询中)&amp;#10;  3. 板块指数是盘中实时计算，包含盘中波动&amp;#10;  4. 总市值与流通市值的区别"}""")
    elif eq_avg:
        print(f"\n  差异: {abs(s3_pct - eq_avg):.2f}% (S3 vs 等权, 因无市值数据)")
