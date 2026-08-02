# -*- coding: utf-8 -*-
"""近30日大盘全景报告 + 多源交叉验证 | 2026-07-31 盘后 (v2增强版)
修复: 日期动态计算 / XV③盘后自动切Tushare.pro / 报告存reports/txt/ / 输出UTF-8
"""
import sys, os, io, subprocess
from datetime import datetime, timedelta

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.market_api import api
from scripts.tushare_api import get_pro

BOLD = lambda t: f"\n{'─'*60}\n {t}\n{'─'*60}"
STARS = lambda r: "★"*r + "☆"*(5-r)
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")
TDAY = "20260731"
# 近30个交易日 ≈ 自然日42天 (约6周) 的起始
START_30D = (datetime.now() - timedelta(days=45)).strftime("%Y%m%d")
INDICES = [
    ("上证指数", "000001", "sh", "000001.SH"),
    ("深证成指", "399001", "sz", "399001.SZ"),
    ("创业板指", "399006", "sz", "399006.SZ"),
    ("科创50",  "000688", "sh", "000688.SH"),
]


def pct_chg(a, b):
    return (b/a - 1) * 100 if a else 0


def avg(lst):
    return sum(lst)/len(lst) if lst else 0


def safe_div(a, b, default=0):
    return a/b if b else default


# ============================================================
# S0: 腾讯K线30日 (主源A)
# ============================================================
def fetch_tencent_30d():
    out = [BOLD(f"S0: 数据获取 — 腾讯K线(主源A)·近30个交易日 (截至{TDAY})")]
    tc = {}
    for name, code, mkt, ts_code in INDICES:
        try:
            kd = api.kline(name, 40)
            kls = kd.get("klines", [])
            if len(kls) < 25:
                out.append(f"  {name}: 数据不足({len(kls)}条)")
                continue
            k30 = kls[-30:]
            c = [float(k[2]) for k in k30]; o = [float(k[4]) for k in k30]
            v = [float(k[5]) for k in k30]
            dates = [k[0][:10] for k in k30]
            chgs = [pct_chg(c[i-1], c[i]) for i in range(1, len(c))]

            gr = sum(1 for i in range(len(k30)) if c[i] < o[i])
            rd = sum(1 for i in range(len(k30)) if c[i] > o[i])

            mg, mr, cg, cr = 0, 0, 0, 0
            for i in range(len(k30)):
                if c[i] < o[i]: cg += 1; cr = 0; mg = max(mg, cg)
                elif c[i] > o[i]: cr += 1; cg = 0; mr = max(mr, cr)
                else: cg = cr = 0

            tc[name] = {
                "code": code, "k30": k30, "dates": dates, "close": c[-1],
                "first_close": c[0], "chg_30d": pct_chg(c[0], c[-1]),
                "seg1": pct_chg(c[0], c[9]), "seg2": pct_chg(c[10], c[19]),
                "seg3": pct_chg(c[20], c[-1]),
                "ma5": avg(c[-5:]), "ma10": avg(c[-10:]), "ma20": avg(c[-20:]),
                "green": gr, "red": rd, "cross": 30-gr-rd,
                "max_green": mg, "max_red": mr,
                "max_up": max(chgs), "max_dn": min(chgs),
                "avg_daily": avg(chgs),
                "std_daily": (sum((x-avg(chgs))**2 for x in chgs)/len(chgs))**0.5 if chgs else 0,
                "vol_trend": "↑放量" if avg(v[-10:]) > avg(v[:10])*1.05 else "↓缩量" if avg(v[-10:]) < avg(v[:10])*0.95 else "→持平",
                "vol_10d_avg": avg(v[-10:])
            }
            out.append(f"  {name}: {dates[0]}~{dates[-1]} {c[0]:.2f}→{c[-1]:.2f} ({tc[name]['chg_30d']:+.2f}%)")
        except Exception as e:
            out.append(f"  {name}: 失败 - {e}")
    out.append(f"\n  成功: {len(tc)}/4")
    return "\n".join(out), tc


# ============================================================
# S1: 交叉验证 (XV①腾讯双端点 / XV②Westock / XV③Tushare.pro盘后)
# ============================================================
def cross_validate(tc):
    out = [BOLD("S1: 多源交叉验证")]
    snap = api.index_snapshot()
    xv1_ok, xv2_ok, xv3_ok = 0, 0, 0
    xv1_t, xv2_t, xv3_t = 0, 0, 0

    # XV①: 腾讯双端点 — K线昨收 vs 快照推算昨收
    out.append("\n  XV① 昨收硬数据 (腾讯双端点):")
    for name, code, mkt, ts_code in INDICES:
        if name not in tc:
            continue
        prev_c = float(tc[name]["k30"][-2][2])
        key = f"{'sh' if mkt=='sh' else 'sz'}{code}"
        for s in snap:
            if s.get("code", "") == key:
                p = float(s.get("price", 0)); chg = float(s.get("change", 0))
                calc_prev = p - chg
                diff = abs(calc_prev-prev_c)/prev_c*100 if prev_c else 999
                xv1_t += 1
                if diff < 0.01:
                    xv1_ok += 1
                out.append(f"    {name}: K昨收={prev_c:.2f} vs 快推算昨收={calc_prev:.2f} Δ{diff:.4f}% {'✓' if diff<0.01 else '⚠'}")
                break

    # XV②: Westock独立源 (用_helper统一入口)
    out.append("\n  XV② 现价独立源 (Westock K线):")
    w_map = {"上证指数": "sh000001", "深证成指": "sz399001", "创业板指": "sz399006", "科创50": "sh000688"}
    try:
        from scripts.utils._westock_helper import kline_last
        for nm, code in w_map.items():
            if nm not in tc:
                continue
            ws_c = kline_last(code)
            if ws_c <= 0:
                out.append(f"    {nm}: Westock 返回0")
                continue
            tc_c = float(tc[nm]["k30"][-1][2])
            if tc_c > 0:
                diff = abs(ws_c-tc_c)/tc_c*100
                xv2_t += 1
                if diff < 0.15:
                    xv2_ok += 1
                out.append(f"    {nm}: Westock={ws_c:.2f} vs TC_K={tc_c:.2f} Δ{diff:.3f}% {'✓' if diff<0.15 else '⚠'}")
    except FileNotFoundError:
        out.append(f"    Westock: Node.js不可用")
    except subprocess.TimeoutExpired:
        out.append(f"    Westock: 超时")
    except Exception as e:
        out.append(f"    Westock: {e}")

    # XV③: 盘后首选Tushare.pro (mootdx盘后TCP不通, 2026-07-31验证)
    out.append("\n  XV③ 收盘硬数据 (Tushare.pro 指数日线):")
    try:
        from scripts.data_gate import gate
        for name, code, mkt, ts_code in INDICES:
            if name not in tc:
                continue
            try:
                rows = gate.ts_index_daily(ts_code=ts_code, start=TDAY, end=TDAY)
                if rows and len(rows) > 0:
                    ts_c = float(rows[0].get("close", 0))
                    tc_c = float(tc[name]["k30"][-1][2])
                    if ts_c > 0 and tc_c > 0:
                        diff = abs(ts_c-tc_c)/tc_c*100
                        xv3_t += 1
                        if diff < 0.05:
                            xv3_ok += 1
                        out.append(f"    {name}: Tushare={ts_c:.2f} vs TC_K={tc_c:.2f} Δ{diff:.4f}% {'✓' if diff<0.05 else '⚠'}")
            except Exception as e:
                out.append(f"    {name}: Tushare失败 - {e}")
    except Exception as e:
        out.append(f"    Tushare: {e}")

    r1 = 5 if xv1_t and xv1_ok == xv1_t else 4 if xv1_t and xv1_ok >= xv1_t*0.75 else 3
    r2 = 5 if xv2_t and xv2_ok == xv2_t else 4 if xv2_t and xv2_ok >= xv2_t*0.75 else 3
    r3 = 5 if xv3_t and xv3_ok >= xv3_t*0.9 else 4 if xv3_t and xv3_ok > 0 else 3
    out.append(f"\n  XV①: {xv1_ok}/{xv1_t} {STARS(r1)} | XV②: {xv2_ok}/{xv2_t} {STARS(r2)} | XV③: {xv3_ok}/{xv3_t} {STARS(r3)}")

    overall = 5 if xv1_ok >= 3 and xv2_ok >= 3 else 4 if xv1_ok >= 3 and xv2_ok >= 2 else 3 if xv1_ok >= 3 else 2
    out.append(f"  >>> 综合评级: {STARS(overall)}")
    return "\n".join(out), overall


# ============================================================
# S2: 大盘全景分析
# ============================================================
def market_analysis(tc):
    out = [BOLD("S2: 大盘层 — 四大指数30日全景")]
    if not tc:
        return "\n".join(out) + "\n  无数据"

    out.append(f"\n  {'指数':<8} {'收盘':>9} {'30日':>8} {'vsMA20':>7} {'MA5':>9} {'MA10':>9} {'阴/阳/平':>8} {'连阴':>5} {'连阳':>5}")
    out.append(f"  {'─'*8} {'─'*9} {'─'*8} {'─'*7} {'─'*9} {'─'*9} {'─'*8} {'─'*5} {'─'*5}")
    for n, _, _, _ in INDICES:
        if n in tc:
            d = tc[n]
            out.append(f"  {n:<8} {d['close']:>9.2f} {d['chg_30d']:>+7.2f}% {safe_div(d['close'], d['ma20'])-1:>+6.2f}% {d['ma5']:>9.2f} {d['ma10']:>9.2f} {d['green']:>2}/{d['red']:>2}/{d['cross']:>1} {d['max_green']:>5} {d['max_red']:>5}")

    out.append(f"\n  三阶段分解 (前10日/中10日/后10日):")
    out.append(f"  {'指数':<8} {'阶段1':>8} {'阶段2':>8} {'阶段3':>8} {'全30日':>8} {'量能':>6}")
    for n, _, _, _ in INDICES:
        if n in tc:
            d = tc[n]
            out.append(f"  {n:<8} {d['seg1']:>+7.2f}% {d['seg2']:>+7.2f}% {d['seg3']:>+7.2f}% {d['chg_30d']:>+7.2f}% {d['vol_trend']:>6}")

    out.append(f"\n  波动率:")
    out.append(f"  {'指数':<8} {'日均涨跌':>9} {'标准差':>8} {'最大日涨':>9} {'最大日跌':>9}")
    for n, _, _, _ in INDICES:
        if n in tc:
            d = tc[n]
            out.append(f"  {n:<8} {d['avg_daily']:>+8.3f}% {d['std_daily']:>7.3f}% {d['max_up']:>+8.2f}% {d['max_dn']:>+8.2f}%")
    return "\n".join(out)


# ============================================================
# S3: 四道门控
# ============================================================
def gate_check(tc):
    out = [BOLD("S3: 四道门控 + 打分卡")]
    if "上证指数" not in tc:
        return "\n".join(out) + "\n  无上证数据"
    sh = tc["上证指数"]; sh_c = sh["close"]

    try:
        kdl = api.kline("上证指数", 250)
        kls = kdl.get("klines", [])
        if len(kls) >= 100:
            wc = [float(k[2]) for k in kls if datetime.strptime(k[0][:10], "%Y-%m-%d").weekday() == 4]
            if len(wc) >= 20:
                w20 = sum(wc[-20:])/20
                wdir = "↑" if wc[-1] > wc[-5] else "↓"
                g0 = "PASS" if sh_c > w20 else "FAIL"
                out.append(f"\n  Gate0: 上证{sh_c:.0f} vs 20周线{w20:.0f}({wdir}) → {g0} {'[一票否决!]' if g0=='FAIL' else ''}")
            else:
                out.append(f"  Gate0: 周线不足({len(wc)}条)")
        else:
            out.append(f"  Gate0: K线不足({len(kls)}条)")
    except Exception as e:
        out.append(f"  Gate0: 失败 - {e}")

    try:
        kdl = api.kline("上证指数", 250)
        kls = kdl.get("klines", [])
        if len(kls) >= 250:
            cs = [float(k[2]) for k in kls]
            m60 = sum(cs[-60:])/60; m250 = sum(cs[-250:])/250
            if sh_c > m250 and m60 > m250:
                g1 = "80~100%"
            elif sh_c > m250:
                g1 = "≤50%"
            elif sh_c < m250 and m60 < m250:
                g1 = "0~20%"
            else:
                g1 = "≤20%"
            out.append(f"  Gate1: close={sh_c:.0f} MA60={m60:.0f} MA250={m250:.0f} → 仓位上限: {g1}")
        else:
            out.append(f"  Gate1: K线不足")
    except Exception as e:
        out.append(f"  Gate1: 失败 - {e}")

    try:
        br = api.breadth(); up = br.get("up", 0); dn = br.get("down", 0)
        pct = safe_div(up, up+dn)*100 if up+dn else 0
        turn = api.turnover(); ty = turn.get("total_yi", 0)
        out.append(f"\n  Gate2: 上涨{up}↑{dn}↓({pct:.0f}%) 成交额{ty}亿")
        g2_ok = up > 2500 and pct > 60
        out.append(f"    → {'PASS' if g2_ok else '调整降档'} (需上涨>2500+占比60%)")
    except Exception as e:
        out.append(f"  Gate2: 失败 - {e}")

    try:
        bs = api.board_summary()
        zt = bs.get("zt_total", bs.get("zt_yesterday", 0))
        dt = bs.get("dt_total", bs.get("dt_yesterday", 0))
        out.append(f"\n  Gate3: ZT={zt} DT={dt}")
        if zt > 100:
            out.append(f"    → 涨停>100 不开新仓")
        elif dt > 10:
            out.append(f"    → 跌停>10 减半")
        else:
            out.append(f"    → PASS")
    except Exception as e:
        out.append(f"  Gate3: 失败 - {e}")

    return "\n".join(out)


# ============================================================
# S4: 北向 + 资金面
# ============================================================
def fund_flow():
    out = [BOLD("S4: 北向资金 + 资金面")]
    try:
        nf = api.north_flow(10)
        recs = nf.get("records", []) if isinstance(nf, dict) else []
        recent5 = sum(r.get("total_yi", 0) for r in recs[-5:]) if recs else 0
        all10 = sum(r.get("total_yi", 0) for r in recs[-10:]) if recs else 0
        in_days = sum(1 for r in recs[-10:] if r.get("total_yi", 0) > 0) if len(recs) >= 10 else 0
        out.append(f"\n  近5日:{recent5:+.1f}亿 | 近10日:{all10:+.1f}亿 | 净流入{in_days}/10天")
        if recs:
            out.append(f"  逐日(近10日):")
            for r in recs[-10:]:
                out.append(f"    {r.get('date','?')}: {r.get('total_yi',0):+.1f}亿")
        else:
            out.append(f"  (无明细数据，2024.8.19起不再披露每日净买入)")
    except Exception as e:
        out.append(f"  获取失败: {e}")

    try:
        bff = api.board_fund_flow_robust("行业", "今日", 10)
        if bff.get("status") == "OK" and bff.get("items"):
            src_tag = bff["source"]
            note_tag = f" ({bff.get('note','')})" if bff.get("note") else ""
            out.append(f"\n  行业资金流 [{src_tag}]{note_tag}:")
            for it in bff["items"][:10]:
                nm = it.get("name", it.get("板块名称", "?"))
                pct = it.get("change_pct", it.get("涨跌幅", 0))
                net = float(it.get("main_net_yi", it.get("主力净流入", 0)) or 0)
                out.append(f"    {nm:16s} {pct:+6.2f}%  主力{net:+8.2f}亿")
        else:
            out.append(f"\n  行业资金流不可用: {bff.get('note','')}")
    except Exception as e:
        out.append(f"\n  行业资金流异常: {e}")
    return "\n".join(out)


# ============================================================
# S5: SW31板块30日轮动 (Tushare)
# ============================================================
def sector_rotation():
    out = [BOLD("S5: 板块层 — SW31行业30日轮动 + Tushare交叉验证")]
    pro = get_pro()
    try:
        sw = pro.index_classify(level='L1', src='SW2021', fields='index_code,industry_name')
    except Exception:
        try:
            sw = pro.index_classify(level='L1', fields='index_code,industry_name')
        except Exception:
            out.append("  SW31分类获取失败")
            return "\n".join(out)

    results = []
    first_date, last_date = "", ""
    for _, r in sw.iterrows():
        code, name = r['index_code'], r['industry_name']
        try:
            df = pro.sw_daily(ts_code=code, start_date=START_30D, end_date=TDAY,
                              fields='ts_code,trade_date,close,pct_chg')
            if df is None or df.empty or len(df) < 20:
                continue
            rows = [(x['trade_date'], float(x['close'])) for _, x in df.iterrows()]
            rows.reverse()  # 升序: 最早→最新
            dates = [d for d, _ in rows]
            cs = [c for _, c in rows]
            k30_c = cs[-30:] if len(cs) >= 30 else cs
            k30_d = dates[-30:] if len(dates) >= 30 else dates
            first_date = k30_d[0]; last_date = k30_d[-1]
            chg30 = pct_chg(k30_c[0], k30_c[-1])
            chg15 = pct_chg(k30_c[-min(16, len(k30_c))], k30_c[-1])
            avg_f3 = sum(k30_c[:3])/3; avg_l3 = sum(k30_c[-3:])/3
            results.append((chg30, name, chg15, avg_l3 > avg_f3, k30_c[-1], len(k30_c)))
        except Exception:
            pass

    results.sort(reverse=True)
    n = len(results)
    date_head = f"日期范围: {first_date}~{last_date} (近{n}行业/31)" if first_date else f"({n}/31行业)"
    out.append(f"\n  {date_head}")
    out.append(f"\n  Top5 涨幅:")
    for chg, nm, c15, up, cl, _ in results[:5]:
        d = "↑" if up else "↓"
        out.append(f"    {nm:<6} {chg:>+7.2f}% (近15日{c15:+.2f}%, 趋势{d}) (收盘{cl:.2f})")
    out.append(f"\n  Bottom5 跌幅:")
    for chg, nm, c15, up, cl, _ in results[-5:]:
        d = "↑" if up else "↓"
        out.append(f"    {nm:<6} {chg:>+7.2f}% (近15日{c15:+.2f}%, 趋势{d}) (收盘{cl:.2f})")

    out.append(f"\n  完整排名 (SW31):")
    out.append(f"  {'排名':<4} {'行业':<12} {'30日涨跌':>9} {'近15日':>8} {'方向':>4} {'收盘':>9}")
    for i, (chg, nm, c15, up, cl, _) in enumerate(results, 1):
        d = "↑" if up else "↓"
        out.append(f"  {i:<4} {nm:<12} {chg:>+8.2f}% {c15:>+7.2f}% {d:>4} {cl:>9.2f}")
    out.append(f"\n  获取成功: {len(results)}/{len(sw)} 行业")
    return "\n".join(out)


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    lines = []

    def p(s=""):
        lines.append(s)
        print(s)

    p(f"近30日大盘全景报告 (盘后) | 生成时间: {NOW}")
    p(f"数据源: 腾讯K线(主)+Westock+Tushare.pro | 报告日期: {TDAY}")
    p()

    s0, tc = fetch_tencent_30d()
    p(s0)
    s1, rating = cross_validate(tc)
    p(s1)
    s2 = market_analysis(tc)
    p(s2)
    s3 = gate_check(tc)
    p(s3)
    s4 = fund_flow()
    p(s4)
    s5 = sector_rotation()
    p(s5)

    p()
    p("="*60)
    p(f" 报告结束 | 数据可靠性: {STARS(rating)} | {NOW}")
    p("="*60)

    report_dir = os.path.join(PROJECT_ROOT, "reports", "txt")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"_30d_comprehensive_{TDAY}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[报告已保存至: {report_path}]")
