# -*- coding: utf-8 -*-
"""2026-07-31 盘后三层全景分析 v3 — 大盘→板块→个股 + 数据源真实性验证
基于 _full_review_v2 修复链路: Westock降序bug已修 + 北向脏值清洗 + 涨停池同花顺备胎
新增: 问财选股 / 龙虎榜 / Westock概念板块 / 数据源审计明细
"""
import sys
import io
import json

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from scripts.market_api import api
from scripts.data_gate import gate
from scripts.utils import _westock_helper as wh

DATE = "2026-07-31"
TDAY = "20260731"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "reports", "txt", "three_layer_20260731.txt")

INDICES = [
    ("sh000001", "上证指数", "000001.SH", "sh000001"),
    ("sz399001", "深证成指", "399001.SZ", "sz399001"),
    ("sz399006", "创业板指", "399006.SZ", "sz399006"),
    ("sh000688", "科创50", "000688.SH", "sh000688"),
]
EXTRA = [("sh000016", "上证50"), ("sh000852", "中证1000")]

_LINES = []


def log(*args):
    s = " ".join(str(a) for a in args)
    print(s)
    _LINES.append(s)


def sec(title):
    log("")
    log("=" * 72)
    log(title)
    log("=" * 72)


def fmt_n(v, nd=2):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


# ═══════════════════════════════════════════
# ① L1 大盘层
# ═══════════════════════════════════════════
if __name__ == "__main__":
    sec("① L1 大盘层 — 指数快照 + 成交额")
    snap_map = {}
    try:
        snaps = api.index_snapshot()
        for s in snaps:
            snap_map[s.get("code")] = s
            log(f"  {s.get('name','?'):<6} {s.get('code')}  现价 {fmt_n(s.get('price'))}  "
                f"涨跌 {s.get('change_pct')}%  成交额 {fmt_n(s.get('turnover_yi'))}亿")
    except Exception as e:
        log(f"  [ERROR] index_snapshot: {e}")

    try:
        tv = api.turnover()
        log(f"  两市成交额: 沪 {fmt_n(tv.get('sh_yi'))}亿 + 深 {fmt_n(tv.get('sz_yi'))}亿"
            f" = 合计 {fmt_n(tv.get('total_yi'))}亿")
    except Exception as e:
        log(f"  [ERROR] turnover: {e}")

    sec("①b 上证50/中证1000 (风格对比)")
    for code, name in EXTRA:
        try:
            s = snap_map.get(code)
            if s:
                log(f"  {name}: {fmt_n(s.get('price'))}  {s.get('change_pct')}%  "
                    f"成交 {fmt_n(s.get('turnover_yi'))}亿")
        except Exception:
            pass

    sec("①c K线均线 (260根)")
    klines = {}
    for tc_code, name, ts_code, w_code in INDICES:
        try:
            kl = api.kline(name, 260)
            raw = kl.get("klines") or []
            closes = [r[2] for r in raw if isinstance(r, (list, tuple)) and len(r) >= 3]
            if len(closes) >= 2:
                ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
                ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None
                ma250 = sum(closes[-250:]) / 250 if len(closes) >= 250 else None
                klines[tc_code] = {"name": name, "close": closes[-1], "prev": closes[-2],
                                   "ma20": ma20, "ma60": ma60, "ma250": ma250,
                                   "w20": sum(closes[-100:]) / 100 if len(closes) >= 100 else None,
                                   "n": len(closes),
                                   "vols": [r[5] for r in raw if isinstance(r, (list, tuple)) and len(r) >= 6]}
                log(f"  {name}: 收盘 {fmt_n(closes[-1])} | MA20 {fmt_n(ma20) if ma20 else '—'} "
                    f"MA60 {fmt_n(ma60) if ma60 else '—'} MA250 {fmt_n(ma250) if ma250 else '—'} "
                    f"({len(closes)}根)")
            else:
                log(f"  {name}: K线不足({len(closes)}根)")
        except Exception as e:
            log(f"  [ERROR] kline({name}): {e}")

    # ═══════════════════════════════════════════
    # ② 数据源交叉验证 XV①/②/③
    # ═══════════════════════════════════════════
    sec("② XV① 腾讯双端点 — K线昨收 vs 快照推算昨收")
    for tc_code, name, ts_code, w_code in INDICES:
        try:
            s = snap_map.get(tc_code)
            if not s or tc_code not in klines:
                log(f"  {name}: 数据缺失, 跳过")
                continue
            price = float(s.get("price", 0))
            chg = float(s.get("change_pct", 0))
            inferred_prev = price / (1 + chg / 100) if abs(chg) < 25 else 0
            k_prev = klines[tc_code]["prev"]
            delta = abs(inferred_prev - k_prev) / k_prev * 100 if k_prev else -1
            status = "PASS" if delta < 0.05 else "FAIL"
            log(f"  {name}: K线昨收 {fmt_n(k_prev)} vs 快照推算昨收 {fmt_n(inferred_prev)}"
                f"  Δ={fmt_n(delta, 4)}% [{status}]")
        except Exception as e:
            log(f"  [ERROR] XV① {name}: {e}")

    sec("③ XV② Westock 独立验证 — 4大指数昨收")
    try:
        avail = wh.available()
        log(f"  Westock CLI available: {avail}")
    except Exception as e:
        log(f"  [ERROR] wh.available: {e}")
        avail = False

    for tc_code, name, ts_code, w_code in INDICES:
        try:
            w_prev = wh.kline_prev_last(w_code)
            k_prev = klines.get(tc_code, {}).get("prev")
            if w_prev and k_prev:
                delta = abs(k_prev - w_prev) / w_prev * 100
                status = "PASS" if delta < 0.05 else "FAIL"
                log(f"  {name}: 腾讯昨收 {fmt_n(k_prev)} vs Westock昨收 {fmt_n(w_prev)}"
                    f"  Δ={fmt_n(delta, 4)}% [{status}]")
            else:
                log(f"  {name}: Westock昨收缺失(w_prev={w_prev}, k_prev={k_prev})")
        except Exception as e:
            log(f"  [ERROR] XV② {name}: {e}")

    sec("④ XV③ Tushare.pro 指数日线验证")
    for tc_code, name, ts_code, w_code in INDICES:
        try:
            rows = gate.ts_index_daily(ts_code=ts_code, start=TDAY, end=TDAY)
            if rows and len(rows) > 0:
                last = rows[0]
                ts_close = float(last.get("close"))
                k_close = klines.get(tc_code, {}).get("close")
                if k_close:
                    delta = abs(k_close - ts_close) / ts_close * 100
                    status = "PASS" if delta < 0.05 else "FAIL"
                    log(f"  {name}: 腾讯收盘 {fmt_n(k_close)} vs Tushare收盘 {fmt_n(ts_close)}"
                        f"  Δ={fmt_n(delta, 4)}% [{status}]  (Tushare {last.get('pct_chg')}%)")
            else:
                log(f"  {name}: Tushare无当日数据")
        except Exception as e:
            log(f"  [ERROR] XV③ {name}: {e}")

    # ═══════════════════════════════════════════
    # ③ L2 板块层
    # ═══════════════════════════════════════════
    sec("⑤ L2 板块层 — 腾讯行业TOP + Westock互证")
    sectors_tx = []
    try:
        sectors_tx = api.sectors(10)
        log("  腾讯行业TOP10:")
        for i, s in enumerate(sectors_tx, 1):
            log(f"    {i}. {s.get('name','?'):<8} {fmt_n(s.get('change_pct'))}%")
    except Exception as e:
        log(f"  [ERROR] sectors: {e}")

    try:
        wi = wh.sector_industry_ranking()
        log(f"  Westock行业排名(共{len(wi)}条) TOP8:")
        for i, s in enumerate(wi[:8], 1):
            log(f"    {i}. {s.get('name','?'):<10} {s.get('changePct','?')}%")
    except Exception as e:
        log(f"  [ERROR] Westock sector: {e}")

    try:
        wc = wh.sector_concept_ranking()
        log(f"  Westock概念板块TOP6:")
        for i, s in enumerate(wc[:6], 1):
            log(f"    {i}. {s.get('name','?'):<12} {s.get('changePct','?')}%")
    except Exception as e:
        log(f"  [ERROR] Westock concept: {e}")

    sec("⑤b 板块资金流 (东财→Westock鲁棒)")
    try:
        bff = api.board_fund_flow_robust("行业", "今日", 8)
        items = (bff or {}).get("items") or []
        log(f"  板块资金流TOP8(源: {bff.get('source')}, 状态: {bff.get('status')}):")
        for i, s in enumerate(items[:8], 1):
            log(f"    {i}. {s.get('name','?'):<10} 涨跌 {fmt_n(s.get('change_pct'))}%"
                f"  主力净 {fmt_n(s.get('main_net_yi'))}亿")
    except Exception as e:
        log(f"  [ERROR] board_fund_flow: {e}")

    sec("⑥ 涨跌广度(腾讯全A扫描)")
    try:
        bd = api.breadth()
        log(f"  上涨 {bd.get('up')} / 下跌 {bd.get('down')} / 平 {bd.get('flat')}"
            f" / 总 {bd.get('total')}  上涨占比 {fmt_n(bd.get('up_pct'))}%"
            f"  评级: {bd.get('broad_rating')}")
    except Exception as e:
        log(f"  [ERROR] breadth: {e}")

    # ═══════════════════════════════════════════
    # ④ L3 个股层
    # ═══════════════════════════════════════════
    sec("⑦ L3 个股层 — 人气榜 + 涨停池 + 打板汇总")
    try:
        hl = api.hot_list("day")
        rows = hl if isinstance(hl, list) else []
        log(f"  同花顺人气榜(日榜, {len(rows)}条) TOP12:")
        for i, s in enumerate(rows[:12], 1):
            log(f"    {i}. {s.get('name','?')}  {s.get('code','')}  涨跌 {fmt_n(s.get('pct'))}%")
    except Exception as e:
        log(f"  [ERROR] hot_list: {e}")

    try:
        zt = gate.em_ths_limit_up_pool(TDAY)
        log(f"  涨停池(同花顺@{TDAY}): total={zt.get('total')} "
            f"炸板={zt.get('zb_count','?')} 跌停={zt.get('dt_count')} "
            f"炸板率={zt.get('zr_rate')}%")
        names = zt.get("zt_names") or zt.get("names") or []
        if isinstance(names, list) and names:
            log(f"    涨停名单(前25): {', '.join(str(n) for n in names[:25])}")
    except Exception as e:
        log(f"  [ERROR] limit_up_pool: {e}")

    try:
        bs = api.board_summary()
        log(f"  打板汇总: 涨停 {bs.get('zt_count')} | 炸板 {bs.get('zb_count')}"
            f" | 跌停 {bs.get('dt_count')} | 炸板率 {bs.get('zr_rate')}%"
            f" | 连板高度 {bs.get('zt_high_lb')}({bs.get('zt_high_name')})"
            f" | 情绪: {bs.get('mood')}")
        reasons = bs.get("zt_top_reasons") or []
        if isinstance(reasons, list) and reasons:
            log(f"    涨停原因TOP: {', '.join(str(r) for r in reasons[:5])}")
    except Exception as e:
        log(f"  [ERROR] board_summary: {e}")

    sec("⑦b 龙虎榜 (东财/Westock)")
    try:
        dt = api.dragon_tiger()
        if isinstance(dt, list) and dt:
            log(f"  龙虎榜(共{len(dt)}条) TOP8(按净买):")
            for i, s in enumerate(dt[:8], 1):
                log(f"    {i}. {s.get('name','?')}  {s.get('code','')}"
                    f"  涨跌 {fmt_n(s.get('pct'))}%  净买 {fmt_n(s.get('net_buy_yi'))}亿"
                    f"  [{s.get('reason','')}]")
        else:
            log("  龙虎榜: 无数据或接口不可用")
    except Exception as e:
        log(f"  [ERROR] dragon_tiger: {e}")

    sec("⑦c 问财选股 (SkillHub验证)")
    try:
        iw = api.iwencai_query("主力资金净流入大于5亿且今日涨幅大于3%的股票", limit=8)
        if iw and iw.get("success"):
            lst = iw.get("items") or iw.get("data") or []
            log(f"  问财查询命中 {len(lst)} 条:")
            for i, s in enumerate(lst[:8], 1):
                log(f"    {i}. {s.get('name','?')}  {s.get('code','')}"
                    f"  涨跌 {fmt_n(s.get('pct'))}%  {s.get('extra','')}")
        else:
            log(f"  问财查询: {iw.get('msg') if iw else 'no response'}")
    except Exception as e:
        log(f"  [ERROR] iwencai: {e}")

    # ═══════════════════════════════════════════
    # 北向资金
    # ═══════════════════════════════════════════
    sec("⑧ 北向资金 (脏值清洗验证)")
    try:
        nf = api.north_flow(5)
        log(f"  数据源: {nf.get('source')}")
        for r in nf.get("records", []):
            note = f" [note:{r['note']}]" if r.get("note") else ""
            log(f"    {r['date']}  净 {fmt_n(r['total_yi'])}亿"
                f" 沪 {fmt_n(r['hgt_yi']) if r.get('hgt_yi') is not None else '—'}"
                f" 深 {fmt_n(r['sgt_yi']) if r.get('sgt_yi') is not None else '—'}"
                f"  {r['direction']}{note}")
        sm = nf.get("summary", {})
        if sm:
            log(f"  小结: {sm.get('conclusion')} | 连续{sm.get('streak_direction')}"
                f"{sm.get('streak_days')}天")
        dirty = [r for r in nf.get("records", [])
                 if r.get("sgt_yi") is not None and abs(float(r["sgt_yi"])) > 150]
        log(f"  脏值审计: 残留脏值 {len(dirty)} 条 {'[CLEAN]' if not dirty else '[DIRTY!]'}")
    except Exception as e:
        log(f"  [ERROR] north_flow: {e}")

    # ═══════════════════════════════════════════
    # 门控评估
    # ═══════════════════════════════════════════
    sec("⑨ 四道门控评估")
    sh = klines.get("sh000001", {})
    if sh:
        close = sh["close"]
        above_w20 = sh.get("w20") is not None and close > sh["w20"]
        above_ma250 = sh.get("ma250") is not None and close > sh["ma250"]
        above_ma60 = sh.get("ma60") is not None and close > sh["ma60"]
        w20s = fmt_n(sh["w20"]) if sh.get("w20") is not None else "—"
        log(f"  Gate0 周线: 上证 {fmt_n(close)} vs 20周均线(约{w20s})"
            f" → {'在20周线上方 [PASS]' if above_w20 else '在20周线下方 [FAIL→减仓]'}")
        if above_ma250 and above_ma60:
            log("  Gate1 趋势: 站上MA250且MA60上方 → 仓位上限80~100%")
        elif above_ma250 or above_ma60:
            log("  Gate1 趋势: MA60~MA250之间 → 仓位≤50%")
        else:
            log("  Gate1 趋势: MA250下方且MA60下方 → 仓位0~20%")
        vols = sh.get("vols") or []
        if len(vols) >= 6:
            avg5 = sum(vols[-6:-1]) / 5
            vr = vols[-1] / avg5 if avg5 else 1.0
            log(f"  Gate2 量能: 今日量比 {fmt_n(vr, 2)} (vs前5日均量)"
                f" → {'放量 [PASS]' if vr >= 1.2 else '缩量 [中性]'}")
        else:
            log("  Gate2 量能: K线量数据不足")
    else:
        log("  上证K线缺失, 门控跳过")

    # 输出
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_LINES))
    log("")
    log(f"[SAVED] {OUT}")
    log("DONE — 三层全景分析完成")
