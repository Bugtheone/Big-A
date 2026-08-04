# -*- coding: utf-8 -*-
"""策略信号自动核验 — 核验 docs/当前策略.md 的 C/D/E 条件清单（15 分钟快照自动触发）。

每次盘中快照后运行，拉取最新数据核验：
  升级信号: C1 AI算力3连阳 / C2 广度≥60% / C3 上证50翻红 / C4 传智晋级+炸板率<15%
  中军信号: D1 中军续涨 / D2 中军杀跌
  撤退信号: E1 广度<55% / E2 涨停断层<80 / E3 上证破5日线
输出策略信号表（升级/持有/冻结/撤退判定）+ 写入 reports/daily/<日期>/strategy_signal_<HHMM>.md

用法:
  python scripts/tools/strategy_signal.py            # 核验并输出
  python scripts/tools/strategy_signal.py --json     # 机器可读 JSON
"""
import sys, os, json, argparse
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

# 中军（AI 算力主线温度计）
_ZJ = [("300308", "中际旭创"), ("300857", "协创数据"), ("300502", "新易盛"), ("601138", "工业富联")]
# 算力题材关键词（涨停归因 reason 匹配）
_AI_KW = ["AI应用", "算力租赁", "AI算力", "算力", "CPO", "光模块", "光通信", "PCB", "存储", "先进封装"]
_STRATEGY_MD = "docs/当前策略.md"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    now = datetime.now()
    dstr = now.strftime("%Y-%m-%d")
    hhmm = now.strftime("%H%M")
    from scripts.market_api import api
    from scripts.data_gate import gate

    res = {"ts": now.strftime("%Y-%m-%d %H:%M:%S")}

    # ── 数据拉取 ──────────────────────────────────────────
    # 指数（腾讯）
    idx = {s["name"]: s for s in api.index_snapshot()}
    sh = idx.get("上证指数", {}).get("change_pct")
    sh50 = idx.get("上证50", {}).get("change_pct")

    # 广度（腾讯全市场）
    bd = api.breadth()
    breadth = bd.get("up_pct")

    # 涨停池（东财→同花顺降级链）
    zt = api.zt_pool(now.strftime("%Y%m%d"))
    zt_cnt = len(zt)
    from collections import Counter
    rc = Counter()
    for x in zt:
        for r in str(x.get("reason") or "").replace("+", "|").split("|"):
            if r.strip():
                rc[r.strip()] += 1
    ai_cnt = sum(v for k, v in rc.items() if k in _AI_KW)
    max_days = max((x.get("limit_days", 1) for x in zt), default=0)
    cz = next((x for x in zt if str(x.get("code")) == "003032"), None)
    cz_days = cz.get("limit_days") if cz else 0

    # 打板汇总（炸板率）
    zr = None
    try:
        bs = gate.em_fetch_board_summary(date=now.strftime("%Y%m%d"))
        if bs:
            zr = bs.get("zr_rate")
    except Exception:
        pass

    # 中军行情（腾讯）
    import scripts.tencent_api as ta
    tc = ta.get_tencent()
    zj_q = tc.fetch_realtime([("sh" if c.startswith(("6", "9")) else "sz") + c for c, _ in _ZJ])
    zj_pct = []
    for c, nm in _ZJ:
        q = zj_q.get(("sh" if c.startswith(("6", "9")) else "sz") + c)
        if q:
            zj_pct.append((nm, round(float(q.get("change_pct", 0)), 2)))
    zj_avg = round(sum(v for _, v in zj_pct) / len(zj_pct), 2) if zj_pct else None

    # CPO 概念涨幅（东财，验证 C1 主线强度）
    cpo = None
    try:
        import requests
        S = requests.Session(); S.trust_env = False
        S.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"})
        for host in ("push2.eastmoney.com", "push2delay.eastmoney.com"):
            try:
                r = S.get(f"https://{host}/api/qt/clist/get",
                          params={"pn": "1", "pz": "50", "po": "1", "np": "1",
                                  "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": "2", "invt": "2",
                                  "fid": "f3", "fs": "m:90+t:3", "fields": "f12,f14,f3"}, timeout=8)
                d = (r.json().get("data") or {}).get("diff") or []
                for it in d:
                    if str(it.get("f14")) == "CPO概念":
                        cpo = round(float(it.get("f3") or 0), 2)
                break
            except Exception:
                continue
    except Exception:
        pass

    # 上证 5 日线（Tushare，E3 用）
    ma5 = None
    try:
        rows = gate.ts_index_daily(ts_code="000001.SH", start="20260601", end=now.strftime("%Y%m%d"))
        rows = rows if isinstance(rows, list) else rows.to_dict("records")
        closes = [float(r["close"]) for r in rows[:5]]
        ma5 = round(sum(closes) / len(closes), 1)
    except Exception:
        pass

    # ── 信号判定 ──────────────────────────────────────────
    def _judge(sig, cond, detail):
        return {"signal": sig, "pass": bool(cond), "detail": detail}

    signals = {}
    signals["C1"] = _judge("C1 AI算力3连阳", ai_cnt is not None and ai_cnt >= 30 and (cpo or 0) > 0,
                           f"算力题材涨停 {ai_cnt}/30 · CPO {cpo}%")
    signals["C2"] = _judge("C2 广度≥60%", (breadth or 0) >= 60, f"广度 {breadth}%/60")
    signals["C3"] = _judge("C3 上证50翻红", (sh50 or -99) > 0, f"上证50 {sh50}%")
    signals["C4"] = _judge("C4 传智晋级+炸板率<15%", cz_days >= 8 and (zr or 99) < 15,
                           f"传智 {cz_days}板/需8 · 炸板率 {zr}%")
    signals["D1"] = _judge("D1 中军续涨", (zj_avg or -99) > 0, f"中军均涨幅 {zj_avg}% ({','.join(f'{n}{v}%' for n, v in zj_pct)})")
    signals["D2"] = _judge("D2 中军杀跌", (zj_avg or 99) < 0, f"中军均涨幅 {zj_avg}%")
    signals["E1"] = _judge("E1 广度<55%", (breadth or 100) < 55, f"广度 {breadth}%")
    signals["E2"] = _judge("E2 涨停断层<80", (zt_cnt or 999) < 80, f"涨停 {zt_cnt}/80")
    signals["E3"] = _judge("E3 上证破5日线", False, "见下方上证价")

    # E3 特殊处理：需上证现价 vs MA5
    sh_price = idx.get("上证指数", {}).get("price")
    e3_pass = (sh_price is not None and ma5 is not None and sh_price < ma5)
    signals["E3"] = _judge("E3 上证破5日线", e3_pass, f"上证 {sh_price} vs MA5 {ma5}")

    # ── 综合判定 ──────────────────────────────────────────
    c_pass = sum(1 for k in ("C1", "C2", "C3", "C4") if signals[k]["pass"])
    e_pass = sum(1 for k in ("E1", "E2", "E3") if signals[k]["pass"])
    d2 = signals["D2"]["pass"]
    if e_pass >= 1 or d2:
        action = "🔴 撤退/冻结" if e_pass >= 1 else "🟠 中军杀跌·减仓预警"
        detail = f"撤退信号 E×{e_pass}" if e_pass else "中军杀跌 D2"
    elif c_pass >= 3:
        action = "🟢 升级信号·可上调仓位(20~40%)"
        detail = f"C 信号 {c_pass}/4"
    elif c_pass >= 2:
        action = "🟡 部分确认·持有/试错"
        detail = f"C 信号 {c_pass}/4"
    else:
        action = "⚪ 未确认·维持0~20%观察"
        detail = f"C 信号 {c_pass}/4"

    res.update({
        "指数": {"上证": sh, "上证50": sh50, "上证价": sh_price},
        "量能情绪": {"广度": breadth, "涨停": zt_cnt, "最高板": max_days, "炸板率": zr},
        "主线": {"算力涨停": ai_cnt, "CPO": cpo, "中军": zj_pct, "中军均值": zj_avg},
        "信号": signals,
        "综合": {"C通过": c_pass, "E通过": e_pass, "动作": action, "说明": detail},
    })

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0

    # ── 文本输出 + 写入文件 ────────────────────────────────
    lines = [f"# 策略信号核验 — {now:%Y-%m-%d %H:%M}",
             f"> 依据 docs/当前策略.md · 撤退优先（E > D > C）",
             "", "## 市场状态",
             f"- 上证 {sh}% · 上证50 {sh50}% · 广度 {breadth}% · 涨停 {zt_cnt}（最高 {max_days}板）· 炸板率 {zr}%",
             f"- 算力题材涨停 {ai_cnt} 家 · CPO {cpo}% · 中军均值 {zj_avg}%（{'、'.join(f'{n}{v}%' for n, v in zj_pct)}）",
             "", "## 信号判定"]
    for k in ("C1", "C2", "C3", "C4", "D1", "D2", "E1", "E2", "E3"):
        s = signals[k]
        mark = "✅" if s["pass"] else ("⚠️" if k.startswith(("D", "E")) else "—")
        lines.append(f"- {mark} {s['signal']}: {s['detail']}")
    lines += ["", f"## 综合判定：{action}", f"> {detail}",
              "", "### 执行建议（对照 docs/当前策略.md）",
              "1. 🟢 升级（C≥3/4）：仓位 0~20% → 20~40%，主线回踩加仓",
              "2. 🟡 部分确认（C=2/4）：持有/试错，不追加",
              "3. ⚪ 未确认（C<2/4）：维持 0~20%，只观察",
              "4. 🔴 撤退（E≥1）：清仓，全面防守",
              "5. 🟠 中军杀跌（D2）：主线减仓预警，防题材退潮"]
    text = "\n".join(lines)
    print(text)
    outdir = os.path.join(_PROJECT_ROOT, "reports", "daily", dstr)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"strategy_signal_{hhmm}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(f"\n[已写入] {os.path.relpath(out, _PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
