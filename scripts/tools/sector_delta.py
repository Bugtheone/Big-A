# -*- coding: utf-8 -*-
"""板块盘中变化摘要 — 对比上一快照输出板块涨跌变化（供 15 分钟调度调用）。

用途：每次盘中快照后运行，输出与上一状态相比的板块变化摘要：
  ① 行业 TOP15 涨幅变化（Δ≥1.0pt 或新进/退出）
  ② 概念 TOP15 涨幅变化（Δ≥1.5pt 或新进/退出）
  ③ 涨停家数变化
  ④ 行业资金流 TOP5 变化
状态存于 reports/daily/<日期>/sector_state.json（首跑仅建基线，无对比）。

用法:
  python scripts/tools/sector_delta.py            # 对比+输出摘要+写 delta 文件
  python scripts/tools/sector_delta.py --baseline # 强制重建基线（不对比）
输出: stdout 摘要 + reports/daily/<日期>/sector_delta_<HHMM>.md
"""
import sys, os, json, argparse
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

def _out(*a):
    print(*a, flush=True)

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", action="store_true", help="强制重建基线")
    args = ap.parse_args()

    now = datetime.now()
    dstr = now.strftime("%Y-%m-%d")
    date_s = now.strftime("%Y%m%d")
    hhmm = now.strftime("%H%M")
    state_path = os.path.join(_PROJECT_ROOT, "reports", "daily", dstr, "sector_state.json")

    from scripts.market_api import api
    from scripts.data_gate import gate

    # ── 取数 ──────────────────────────────────────────────
    # ① 行业（腾讯主源）
    try:
        secs = api.sectors(20) or []
    except Exception as e:
        secs = []
        _out(f"[WARN] 行业拉取失败: {e}")
    cur_ind = {s["name"]: round(float(s.get("change_pct") or 0), 2) for s in secs}

    # ② 概念（东财 clist m:90+t:3，push2→push2delay 容错）
    import requests
    S = requests.Session(); S.trust_env = False
    S.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"})
    cur_con = {}
    params = {"pn": "1", "pz": "20", "po": "1", "np": "1",
              "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": "2", "invt": "2",
              "fid": "f3", "fs": "m:90+t:3", "fields": "f12,f14,f3"}
    for host in ("push2.eastmoney.com", "push2delay.eastmoney.com"):
        try:
            r = S.get(f"https://{host}/api/qt/clist/get", params=params, timeout=8)
            rows = (r.json().get("data") or {}).get("diff") or []
            if rows:
                cur_con = {str(it.get("f14") or ""): round(float(it.get("f3") or 0), 2)
                           for it in rows}
                break
        except Exception:
            continue

    # ③ 涨停家数（东财打板汇总，失效自动降级同花顺）
    zt_cnt = None
    try:
        bs = gate.em_fetch_board_summary(date=date_s)
        if bs:
            zt_cnt = int(bs.get("zt_count") or 0)
    except Exception:
        pass
    if zt_cnt is None:
        try:
            zt_cnt = len(api.zt_pool(date_s))
        except Exception:
            zt_cnt = None

    # ④ 行业资金流 TOP5（东财→westock 鲁棒）
    cur_ff = {}
    try:
        bf = api.board_fund_flow_robust("行业", "今日", 5)
        for it in (bf.get("items") or []):
            cur_ff[it.get("name")] = round(float(it.get("main_net_yi") or 0), 1)
    except Exception as e:
        _out(f"[WARN] 资金流拉取失败: {e}")

    new_state = {
        "ts": now.strftime("%Y-%m-%d %H:%M:%S"),
        "行业": cur_ind, "概念": cur_con, "涨停": zt_cnt, "资金流": cur_ff,
    }

    # ── 首跑基线 ──────────────────────────────────────────
    if args.baseline or not os.path.exists(state_path):
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(new_state, f, ensure_ascii=False, indent=1)
        _out(f"=== {now:%H:%M:%S} 板块基线已建立（{len(cur_ind)} 行业 / {len(cur_con)} 概念 / 涨停 {zt_cnt}）===")
        return 0

    with open(state_path, "r", encoding="utf-8") as f:
        old = json.load(f)
    old_ind, old_con = old.get("行业", {}), old.get("概念", {})
    old_ff, old_zt = old.get("资金流", {}), old.get("涨停")

    # ── 对比逻辑 ──────────────────────────────────────────
    lines = []
    lines.append(f"# 板块变化摘要 — {now:%Y-%m-%d %H:%M}")
    lines.append(f"> 对比 {old.get('ts', '?')} → {now:%H:%M:%S}")

    # ① 行业变化
    ind_chg = []
    for nm, pct in cur_ind.items():
        if nm in old_ind and abs(pct - old_ind[nm]) >= 1.0:
            ind_chg.append((nm, old_ind[nm], pct, pct - old_ind[nm]))
        elif nm not in old_ind:
            ind_chg.append((nm, None, pct, None))  # 新进
    ind_left = [nm for nm in old_ind if nm not in cur_ind]
    ind_chg.sort(key=lambda x: -abs(x[3] or 0))
    lines.append("")
    lines.append("## 行业变化（Δ≥1.0pt 或新进）")
    if ind_chg:
        for nm, o, n, d in ind_chg:
            if d is None:
                lines.append(f"- 🆕 {nm}: {n:+.2f}%（新进 TOP20）")
            else:
                arrow = "↑" if d > 0 else "↓"
                lines.append(f"- {nm}: {o:+.2f}% → {n:+.2f}%（{arrow}{abs(d):.2f}pt）")
    else:
        lines.append("- 无显著行业变化")
    if ind_left:
        lines.append(f"- ⤵️ 退出 TOP20: {', '.join(ind_left)}")

    # ② 概念变化
    con_chg = []
    for nm, pct in cur_con.items():
        if nm in old_con and abs(pct - old_con[nm]) >= 1.5:
            con_chg.append((nm, old_con[nm], pct, pct - old_con[nm]))
        elif nm not in old_con:
            con_chg.append((nm, None, pct, None))
    con_chg.sort(key=lambda x: -abs(x[3] or 0))
    lines.append("")
    lines.append("## 概念变化（Δ≥1.5pt 或新进）")
    if con_chg:
        for nm, o, n, d in con_chg[:12]:
            if d is None:
                lines.append(f"- 🆕 {nm}: {n:+.2f}%（新进 TOP20）")
            else:
                arrow = "↑" if d > 0 else "↓"
                lines.append(f"- {nm}: {o:+.2f}% → {n:+.2f}%（{arrow}{abs(d):.2f}pt）")
    else:
        lines.append("- 无显著概念变化")

    # ③ 涨停变化
    lines.append("")
    lines.append("## 涨停家数")
    if old_zt is not None and zt_cnt is not None:
        d = zt_cnt - old_zt
        arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
        lines.append(f"- {old_zt} → {zt_cnt}（{arrow}{abs(d)}，手册过热线 100）")
    else:
        lines.append(f"- {zt_cnt}")

    # ④ 资金流变化
    lines.append("")
    lines.append("## 行业主力净流入 TOP5（东财今日）")
    if cur_ff:
        for nm, v in sorted(cur_ff.items(), key=lambda kv: -kv[1])[:5]:
            o = old_ff.get(nm)
            d = f"（Δ{round(v - o, 1):+.1f}亿）" if o is not None else "（新进）"
            lines.append(f"- {nm}: {v:+.1f}亿 {d}")
    else:
        lines.append("- 资金流不可用")

    summary = "\n".join(lines)
    _out(summary)
    _out("")
    _out("---")

    # ── 写 delta 文件 + 更新状态 ─────────────────────────
    outdir = os.path.join(_PROJECT_ROOT, "reports", "daily", dstr)
    os.makedirs(outdir, exist_ok=True)
    delta_path = os.path.join(outdir, f"sector_delta_{hhmm}.md")
    with open(delta_path, "w", encoding="utf-8") as f:
        f.write(summary + "\n")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=1)
    _out(f"[已写入] {delta_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
