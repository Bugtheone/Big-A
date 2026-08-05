# -*- coding: utf-8 -*-
"""2026-07-31 盘后三层全景分析 v2 — 修复后数据链路版
大盘→板块→个股 + 数据源真实性验证(四源交叉)
修复项: 北向脏数据清洗(379.75→真实) + Westock解析器鲁棒化 + 涨停池同花顺备胎
"""
import sys
import io

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from scripts.market_api import api
from scripts.data_gate import gate
from scripts.utils import _westock_helper as wh

DATE = "2026-07-31"
TDAY = "20260731"

# 指数: (腾讯代码, 名称, Tushare代码, Westock代码)
INDICES = [
    ("sh000001", "上证指数", "000001.SH", "sh000001"),
    ("sz399001", "深证成指", "399001.SZ", "sz399001"),
    ("sz399006", "创业板指", "399006.SZ", "sz399006"),
    ("sh000688", "科创50", "000688.SH", "sh000688"),
]


def sec(title):
    print(f"\n{'='*70}\n{title}\n{'='*70}")


def fmt_n(v, nd=2):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


# ═══════════════════════════════════════════
# L1 大盘层
# ═══════════════════════════════════════════
if __name__ == "__main__":
    sec("① L1 大盘层 — 指数快照 + 成交额 + K线均线")
    snap_map = {}
    try:
        snaps = api.index_snapshot()
        for s in snaps:
            snap_map[s.get("code")] = s
            print(f"  {s.get('name','?'):<6} {s.get('code')}  现价 {fmt_n(s.get('price'))}  "
                  f"涨跌 {s.get('change_pct')}%  成交额 {fmt_n(s.get('turnover_yi'))}亿")
    except Exception as e:
        print(f"  [ERROR] index_snapshot: {e}")

    try:
        tv = api.turnover()
        print(f"  两市成交额: 沪 {fmt_n(tv.get('sh_yi'))}亿 + 深 {fmt_n(tv.get('sz_yi'))}亿"
              f" = 合计 {fmt_n(tv.get('total_yi'))}亿")
    except Exception as e:
        print(f"  [ERROR] turnover: {e}")

    klines = {}
    for tc_code, name, ts_code, w_code in INDICES:
        try:
            kl = api.kline(name, 260)
            raw = kl.get("klines") or []
            # klines格式: [date, high, close, low, open, vol] → close在索引[2]
            closes = [r[2] for r in raw if isinstance(r, (list, tuple)) and len(r) >= 3]
            if len(closes) >= 2:
                ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
                ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None
                ma250 = sum(closes[-250:]) / 250 if len(closes) >= 250 else None
                klines[tc_code] = {"name": name, "close": closes[-1], "prev": closes[-2],
                                   "ma20": ma20, "ma60": ma60, "ma250": ma250,
                                   "w20": sum(closes[-100:]) / 100 if len(closes) >= 100 else None,
                                   "n": len(closes), "vols": [r[5] for r in raw if isinstance(r, (list, tuple)) and len(r) >= 6]}
                print(f"  {name}: 收盘 {fmt_n(closes[-1])} | MA20 {fmt_n(ma20) if ma20 else '—'} "
                      f"MA60 {fmt_n(ma60) if ma60 else '—'} MA250 {fmt_n(ma250) if ma250 else '—'}"
                      f" ({len(closes)}根K线)")
            else:
                print(f"  {name}: K线数据不足({len(closes)}根)")
        except Exception as e:
            print(f"  [ERROR] kline({name}): {e}")

    # ═══════════════════════════════════════════
    # XV① 腾讯双端点 (K线昨收 vs 快照推算昨收)
    # ═══════════════════════════════════════════
    sec("② XV① 腾讯双端点交叉 — K线昨收 vs 快照推算昨收")
    for tc_code, name, ts_code, w_code in INDICES:
        try:
            s = snap_map.get(tc_code)
            if not s or tc_code not in klines:
                print(f"  {name}: 数据缺失, 跳过")
                continue
            price = float(s.get("price", 0))
            chg = float(s.get("change_pct", 0))
            inferred_prev = price / (1 + chg / 100) if abs(chg) < 25 else 0
            k_prev = klines[tc_code]["prev"]
            delta = abs(inferred_prev - k_prev) / k_prev * 100 if k_prev else -1
            status = "PASS" if delta < 0.05 else "FAIL"
            print(f"  {name}: K线昨收 {fmt_n(k_prev)} vs 快照推算昨收 {fmt_n(inferred_prev)}"
                  f"  Δ={fmt_n(delta, 4)}% [{status}]")
        except Exception as e:
            print(f"  [ERROR] XV① {name}: {e}")

    # ═══════════════════════════════════════════
    # XV② Westock 交叉验证
    # ═══════════════════════════════════════════
    sec("③ XV② Westock 独立验证 — 4大指数昨收")
    xv2 = {}
    try:
        if not wh.available():
            print("  [FAIL] Westock CLI 不可用")
        for tc_code, name, ts_code, w_code in INDICES:
            try:
                w_last = wh.kline_last(w_code)
                w_prev = wh.kline_prev_last(w_code)
                k_prev = klines.get(tc_code, {}).get("prev")
                if w_prev and k_prev:
                    delta = abs(k_prev - w_prev) / w_prev * 100
                    status = "PASS" if delta < 0.05 else "FAIL"
                    xv2[tc_code] = {"w_prev": w_prev, "delta": delta}
                    print(f"  {name}: 腾讯昨收 {fmt_n(k_prev)} vs Westock昨收 {fmt_n(w_prev)}"
                          f"  Δ={fmt_n(delta, 4)}% [{status}]")
                else:
                    print(f"  {name}: Westock昨收缺失(w_prev={w_prev}, k_prev={k_prev})")
            except Exception as e:
                print(f"  [ERROR] XV② {name}: {e}")
    except Exception as e:
        print(f"  [ERROR] XV② 整体: {e}")

    # ═══════════════════════════════════════════
    # XV③ Tushare 指数日线验证 (盘后独立数据链)
    # ═══════════════════════════════════════════
    sec("④ XV③ Tushare.pro 指数日线验证")
    xv3 = {}
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
                    xv3[tc_code] = {"ts_close": ts_close, "delta": delta}
                    print(f"  {name}: 腾讯收盘 {fmt_n(k_close)} vs Tushare收盘 {fmt_n(ts_close)}"
                          f"  Δ={fmt_n(delta, 4)}% [{status}]")
            else:
                print(f"  {name}: Tushare无数据(可能非交易日或接口延迟)")
        except Exception as e:
            print(f"  [ERROR] XV③ {name}: {e}")

    # ═══════════════════════════════════════════
    # L2 板块层
    # ═══════════════════════════════════════════
    sec("⑤ L2 板块层 — 行业板块排名 + 互证 + 板块资金流")
    sectors_tx = []
    try:
        sectors_tx = api.sectors(10)
        print("  腾讯行业TOP10:")
        for i, s in enumerate(sectors_tx, 1):
            print(f"    {i}. {s.get('name','?'):<8} {fmt_n(s.get('change_pct'))}%")
    except Exception as e:
        print(f"  [ERROR] sectors: {e}")

    try:
        wi = wh.sector_industry_ranking()
        print(f"  Westock行业排名(共{len(wi)}条):")
        for i, s in enumerate(wi[:6], 1):
            print(f"    {i}. {s.get('name','?'):<10} {s.get('changePct','?')}%")
    except Exception as e:
        print(f"  [ERROR] Westock sector: {e}")

    try:
        bff = api.board_fund_flow_robust("行业", "今日", 8)
        items = (bff or {}).get("items") or []
        print(f"  板块资金流TOP8(源: {bff.get('source')}, 状态: {bff.get('status')}):")
        for i, s in enumerate(items[:8], 1):
            print(f"    {i}. {s.get('name','?'):<10} 涨跌 {fmt_n(s.get('change_pct'))}%"
                  f"  主力净 {fmt_n(s.get('main_net_yi'))}亿")
    except Exception as e:
        print(f"  [ERROR] board_fund_flow: {e}")

    # ═══════════════════════════════════════════
    # 涨跌广度
    # ═══════════════════════════════════════════
    sec("⑥ 涨跌广度(腾讯全A扫描)")
    try:
        bd = api.breadth()
        print(f"  上涨 {bd.get('up')} / 下跌 {bd.get('down')} / 平 {bd.get('flat')}"
              f" / 总 {bd.get('total')}  上涨占比 {fmt_n(bd.get('up_pct'))}%"
              f"  评级: {bd.get('broad_rating')}")
    except Exception as e:
        print(f"  [ERROR] breadth: {e}")

    # ═══════════════════════════════════════════
    # L3 个股层 + 打板情绪
    # ═══════════════════════════════════════════
    sec("⑦ L3 个股层 — 人气榜 + 涨停池 + 打板汇总")
    try:
        hl = api.hot_list("day")
        print(f"  同花顺人气榜(日榜, {len(hl) if isinstance(hl, list) else 'N/A'}条) TOP10:")
        for i, s in enumerate(hl[:10] if isinstance(hl, list) else [], 1):
            print(f"    {i}. {s.get('name','?')}  {s.get('code','')}"
                  f"  涨跌 {fmt_n(s.get('pct'))}%")
    except Exception as e:
        print(f"  [ERROR] hot_list: {e}")

    try:
        zt = gate.em_ths_limit_up_pool(TDAY)
        print(f"  涨停池(同花顺@{TDAY}): total={zt.get('total')} "
              f"炸板={zt.get('zb_count','?')} 跌停={zt.get('dt_count')} "
              f"炸板率={zt.get('zr_rate')}%")
        names = zt.get("zt_names") or zt.get("names") or []
        if isinstance(names, list) and names:
            print(f"    涨停名单(前20): {', '.join(str(n) for n in names[:20])}")
    except Exception as e:
        print(f"  [ERROR] limit_up_pool: {e}")

    try:
        bs = api.board_summary()
        print(f"  打板汇总: 涨停 {bs.get('zt_count')} | 炸板 {bs.get('zb_count')}"
              f" | 跌停 {bs.get('dt_count')} | 炸板率 {bs.get('zr_rate')}%"
              f" | 连板高度 {bs.get('zt_high_lb')}({bs.get('zt_high_name')})"
              f" | 情绪: {bs.get('mood')}")
        reasons = bs.get("zt_top_reasons") or []
        if isinstance(reasons, list) and reasons:
            print(f"    涨停原因TOP: {', '.join(str(r) for r in reasons[:5])}")
    except Exception as e:
        print(f"  [ERROR] board_summary: {e}")

    # ═══════════════════════════════════════════
    # 北向资金审计 (修复后)
    # ═══════════════════════════════════════════
    sec("⑧ 北向资金 (修复后: 脏值379.75已清洗)")
    try:
        nf = api.north_flow(5)
        print(f"  数据源: {nf.get('source')}")
        for r in nf.get("records", []):
            note = f" [note:{r['note']}]" if r.get("note") else ""
            print(f"    {r['date']}  净 {fmt_n(r['total_yi'])}亿"
                  f" 沪 {fmt_n(r['hgt_yi']) if r.get('hgt_yi') is not None else '—'}"
                  f" 深 {fmt_n(r['sgt_yi']) if r.get('sgt_yi') is not None else '—'}"
                  f"  {r['direction']}{note}")
        sm = nf.get("summary", {})
        if sm:
            print(f"  小结: {sm.get('conclusion')} | 连续{sm.get('streak_direction')}"
                  f"{sm.get('streak_days')}天")
        # 脏值审计
        dirty = [r for r in nf.get("records", [])
                 if r.get("sgt_yi") is not None and abs(float(r["sgt_yi"])) > 150]
        print(f"  脏值审计: 残留脏值 {len(dirty)} 条 {'[CLEAN]' if not dirty else '[DIRTY!]'}")
    except Exception as e:
        print(f"  [ERROR] north_flow: {e}")

    # ═══════════════════════════════════════════
    # 门控评估
    # ═══════════════════════════════════════════
    sec("⑨ 四道门控评估 (基于上述真实数据)")
    sh = klines.get("sh000001", {})
    if sh:
        close = sh["close"]
        above_w20 = sh.get("w20") is not None and close > sh["w20"]
        above_ma250 = sh.get("ma250") is not None and close > sh["ma250"]
        above_ma60 = sh.get("ma60") is not None and close > sh["ma60"]
        w20s = fmt_n(sh["w20"]) if sh.get("w20") is not None else "—"
        print(f"  Gate0 周线: 上证 {fmt_n(close)} vs 20周均线(约{w20s})"
              f" → {'在20周线上方 [PASS]' if above_w20 else '在20周线下方 [FAIL→减仓]'}")
        if above_ma250 and above_ma60:
            print("  Gate1 趋势: 站上MA250且MA60上方 → 仓位上限80~100%")
        elif above_ma250 or above_ma60:
            print("  Gate1 趋势: MA60~MA250之间 → 仓位≤50%")
        else:
            print("  Gate1 趋势: MA250下方且MA60下方 → 仓位0~20%")
        # Gate2 量能: 今日成交量 vs 前5日均量
        vols = sh.get("vols") or []
        if len(vols) >= 6:
            avg5 = sum(vols[-6:-1]) / 5
            vr = vols[-1] / avg5 if avg5 else 1.0
            print(f"  Gate2 量能: 今日量比 {fmt_n(vr, 2)} (vs前5日均量)"
                  f" → {'放量 [PASS]' if vr >= 1.2 else '缩量 [中性]'}")
        else:
            print("  Gate2 量能: K线量数据不足")
    else:
        print("  上证K线数据缺失, 门控评估跳过")

    sec("DONE — 数据采集完成")
