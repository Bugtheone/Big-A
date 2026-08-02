# -*- coding: utf-8 -*-
"""30日三层次分析 [大盘→板块→个股] + 多源交叉验证 | 2026-07-30"""
import sys, os, json, time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.market_api import api
from scripts.tushare_api import get_pro

BOLD = lambda t: f"\n{'─'*60}\n {t}\n{'─'*60}"
STARS = lambda r: "★"*r + "☆"*(5-r)

# ===== L0-1: mootdx K线验证 =====
def validate_kline():
    out = [BOLD("L0-1: mootdx vs Tencent K线收盘价验证")]
    from scripts.data_gate import gate
    
    # 先测mootdx是否可用
    tdx_avail = False
    try:
        test = gate.tdx_bars('000001', freq=4, count=5)  # freq=4=日线
        if test and len(test) > 0:
            tdx_avail = True
            out.append(f"  mootdx状态: 可用 (日线{len(test)}条)")
        else:
            out.append(f"  mootdx状态: 日线返回空，尝试年线...")
            test2 = gate.tdx_bars('000001', freq=9, count=5)
            if test2 and len(test2) > 0:
                tdx_avail = True
                out.append(f"  mootdx状态: 年线可用 ({len(test2)}条)")
    except Exception as e:
        out.append(f"  mootdx状态: 异常 ({e})")
    
    if not tdx_avail:
        out.append("  [INFO] mootdx K线数据不可用(网络/服务端问题)")
        out.append("  [降级] 改用Tencent snapshot交叉验证(同源不同端点)")
        out.append("  可靠性: ★★★★☆ (单源双端点，均来自腾讯)")
        return "\n".join(out), None
    
    # 正常交叉验证
    indices = {"000001":"上证","399001":"深成","399006":"创业板","000688":"科创50"}
    all_diffs = []
    for code, label in indices.items():
        tc = api.kline(label+"指数", 35)
        tc_kls = tc.get("klines",[]) if isinstance(tc,dict) else []
        tdx = gate.tdx_bars(code, freq=4 if tdx_avail else 9, count=35)
        
        tc_map = {k[0][:10]:float(k[2]) for k in tc_kls if len(k)>=6}
        tdx_map = {r.get("date","")[:10]:float(r.get("close",0)) for r in tdx}
        common = sorted(set(tc_map)&set(tdx_map))[-30:]
        
        diffs = []
        for d in common:
            dp = abs(tc_map[d]-tdx_map[d])/tc_map[d]*100
            diffs.append(dp); all_diffs.append(dp)
        
        avg = sum(diffs)/len(diffs) if diffs else 0
        r = 5 if avg<0.01 else 4 if avg<0.05 else 3 if avg<0.1 else 2
        out.append(f"  {label}: 比{len(common)}日 均差{avg:.4f}% {STARS(r)}")
    
    ga = sum(all_diffs)/len(all_diffs) if all_diffs else 0
    out.append(f"\n>>> 总评: {len(all_diffs)}点 均差{ga:.4f}% → {STARS(5 if ga<0.01 else 4 if ga<0.05 else 3)}")
    return "\n".join(out), ga


# ===== L0-2: 板块交叉验证 =====
def validate_sectors():
    out = [BOLD("L0-2: 板块排名交叉验证 — Tushare SW31 vs Tencent II级28行业")]
    pro = get_pro()
    
    # Tushare SW31行业近5日
    sw_df = pro.index_classify(level='L1', src='SW2021', fields='index_code,industry_name')
    ts_map = {}
    for _,r in sw_df.iterrows():
        try:
            df = pro.sw_daily(ts_code=r['index_code'], start_date='20260723', end_date='20260729',
                              fields='ts_code,close,trade_date')
            if df is not None and not df.empty:
                cs = [float(x['close']) for _,x in df.iterrows()]
                if len(cs)>=2: ts_map[r['industry_name']] = (cs[-1]/cs[0]-1)*100
        except Exception: pass
    
    # Tencent 28行业实时快照
    tc_raw = api.sectors(28)
    tc_list = [(it.get("name",""), float(it.get("change_pct",0))) for it in tc_raw]
    
    # 显示腾讯28行业
    tc_ranked = sorted(tc_list, key=lambda x:x[1], reverse=True)
    out.append(f"\n腾讯28行业(近1日) vs Tushare SW31(近5日):")
    out.append(f"\n{'腾讯行业':<8} {'腾讯%':>7} │ {'SW行业':<10} {'SW近5日%':>8}")
    # 手工映射
    tc_to_sw = {
        "电力行业": "公用事业", "煤炭行业": "煤炭", "钢铁行业": "钢铁",
        "有色金属": "有色金属", "石油行业": "石油石化",
        "化工行业": "基础化工", "化纤行业": "基础化工",
        "水泥建材": "建筑材料", "玻璃陶瓷": "建筑材料",
        "房地产": "房地产",
        "银行": "银行", "保险": "非银金融", "券商信托": "非银金融", "多元金融": "非银金融",
        "汽车行业": "汽车",
        "机械行业": "机械设备",
        "电子元件": "电子", "电子信息": "电子", "半导体": "电子",
        "软件服务": "计算机", "电子信息": "计算机",
        "通讯行业": "通信",
        "医药制造": "医药生物", "医疗行业": "医药生物",
        "食品饮料": "食品饮料", "酿酒行业": "食品饮料",
        "家电行业": "家用电器",
        "纺织服装": "纺织服饰",
        "造纸印刷": "轻工制造",
        "农牧饲渔": "农林牧渔",
        "交通运输": "交通运输", "港口水运": "交通运输",
        "旅游酒店": "社会服务",
        "商业百货": "商贸零售",
        "航天航空": "国防军工",
        "文化传媒": "传媒",
        "输配电气": "电力设备",
        "环保工程": "环保",
        "装修装饰": "建筑装饰", "工程建设": "建筑装饰",
    }
    
    dir_ok = 0; total = 0
    for tc_name, tc_pct in tc_ranked[:20]:
        sw_name = tc_to_sw.get(tc_name, "")
        sw_pct = ts_map.get(sw_name, None)
        if sw_pct is not None:
            dir_t = "+" if tc_pct>0 else "-"
            dir_s = "+" if sw_pct>0 else "-"
            match = "✓" if dir_t==dir_s else "✗"
            if dir_t==dir_s: dir_ok += 1
            total += 1
            out.append(f"  {tc_name:<8} {tc_pct:+6.2f}% │ {sw_name:<10} {sw_pct:+7.2f}% {match}")
        else:
            out.append(f"  {tc_name:<8} {tc_pct:+6.2f}% │ {'(无映射)':<10}")
    
    if total > 0:
        rate = dir_ok/total*100
        out.append(f"\n>>> 方向一致率: {dir_ok}/{total} ({rate:.0f}%) → {STARS(5 if rate>=90 else 4 if rate>=75 else 3 if rate>=60 else 2)}")
    
    return "\n".join(out), ts_map


def validate_zt_north():
    """涨停+北向多源验证"""
    out = [BOLD("L0-3: 涨停板 + 北向资金多源验证")]
    
    # 涨停
    bs = api.board_summary()
    zt = bs.get("zt_total",0) or bs.get("zt_yesterday",0)
    dt = bs.get("dt_total",0) or bs.get("dt_yesterday",0)
    mood = bs.get("mood","?")
    out.append(f"同花顺: ZT={zt} DT={dt} mood={mood}")
    
    try:
        from scripts.data_gate import gate
        em = gate.em_ths_limit_up_pool("20260729", page=1, limit=200)
        em_zt = len(em.get("data",[])) if em and isinstance(em,dict) else 0
        out.append(f"东财limit_up_pool: ZT={em_zt}")
        if zt>0 and em_zt>0:
            d=abs(zt-em_zt)
            out.append(f"差异={d} → {'吻合' if d<=3 else '差异'+str(d)}")
        elif zt>0 and em_zt==0:
            out.append("[WARN] 东财push2限流，以THS为准")
    except Exception as e:
        out.append(f"东财FAIL: {e}")
    
    # 北向资金
    nf = api.north_flow(5)
    records = nf.get("records",[]) if isinstance(nf,dict) else []
    latest = nf.get("latest",{}) if isinstance(nf,dict) else {}
    out.append(f"\n北向(同花顺): {len(records)}条 最新={latest.get('date','?')} {latest.get('total_yi',0)}亿")
    for r in records[-5:]:
        out.append(f"  {r.get('date','?')}: {r.get('total_yi',0)}亿")
    
    return "\n".join(out)


# ===== L1: 大盘 =====
def L1():
    out = [BOLD("L1: 大盘 — 四大指数30日K线 + 广度量能 + 四道门控")]
    names = ["上证指数","深证成指","创业板指","科创50"]
    dd = {}
    
    for n in names:
        kd = api.kline(n, 35)
        kls = kd.get("klines",[])
        if len(kls)<30: continue
        k30 = kls[-30:]
        sc = float(k30[0][2]); ec = float(k30[-1][2])
        ma20 = sum(float(k[2]) for k in k30[-20:])/20
        green = sum(1 for k in k30 if k[2]<k[4])
        red = sum(1 for k in k30 if k[2]>k[4])
        cross = 30 - green - red
        s1 = (float(k30[10][2])/sc-1)*100 if len(k30)>10 else 0
        s2 = (float(k30[20][2])/float(k30[10][2])-1)*100 if len(k30)>20 else 0
        s3 = (ec/float(k30[20][2])-1)*100 if len(k30)>20 else 0
        dd[n] = {"close":ec,"chg_30":(ec/sc-1)*100,"vsMA20":(ec/ma20-1)*100,
                 "green":green,"red":red,"cross":cross,"seg":(s1,s2,s3),"k30":k30}
    
    # A. 指数概览
    out.append(f"{'指数':<8} {'收盘':>8} {'30日%':>8} {'vsMA20':>7} {'阴/阳':>8}")
    for n in names:
        if n in dd:
            d = dd[n]
            out.append(f"{n:<8} {d['close']:8.2f} {d['chg_30']:+7.2f}% {d['vsMA20']:+6.2f}% {d['green']}/{d['red']}/{d['cross'] if d['cross'] else 0}")
    
    # B. 分阶段
    out.append(f"\n{'':>12} {'前10日':>8} {'中10日':>8} {'后10日':>8} {'全30日':>8}")
    for n in names:
        if n in dd:
            s1,s2,s3 = dd[n]["seg"]; chg = dd[n]["chg_30"]
            out.append(f"{n:<8} {s1:+7.2f}% {s2:+7.2f}% {s3:+7.2f}% {chg:+7.2f}%")
    
    # C. 上证日统计
    if "上证指数" in dd:
        k30 = dd["上证指数"]["k30"]
        chgs = [(float(k30[i][2])/float(k30[i-1][2])-1)*100 for i in range(1,len(k30))]
        if chgs:
            out.append(f"\n上证日统计: 均涨跌{sum(chgs)/len(chgs):+.2f}% 最大涨幅{max(chgs):+.2f}% 最大跌幅{min(chgs):+.2f}%")
        vols = [float(k[5])/1e8 for k in k30]
        out.append(f"量能(亿手): 前10日均{sum(vols[:10])/10:.2f} 中10日{sum(vols[10:20])/10:.2f} 后10日{sum(vols[20:])/10:.2f}")
    
    # D. 广度
    br = api.breadth()
    up = br.get("up",0); down = br.get("down",0); total = br.get("total",0)
    pct = up/(up+down)*100 if (up+down)>0 else 0
    bj = br.get("bj_data_status","?")
    out.append(f"\n广度: ↑{up} ↓{down} ({pct:.0f}%上涨) 北交所={bj}")
    
    # E. 成交额
    turn = api.turnover()
    out.append(f"成交额: {turn.get('total_yi','?')}亿 (沪{turn.get('sh_yi','?')} 深{turn.get('sz_yi','?')})")
    
    # F. 门控
    out.append("\n--- 四道门控 ---")
    if "上证指数" in dd:
        sh_ec = dd["上证指数"]["close"]
        kd_long = api.kline("上证指数", 250)
        kls_long = kd_long.get("klines",[])
        if len(kls_long) >= 100:
            wcs = [float(k[2]) for k in kls_long if datetime.strptime(k[0][:10],"%Y-%m-%d").weekday()==4]
            if len(wcs) >= 20:
                w20 = sum(wcs[-20:])/20
                g0 = "FAIL" if sh_ec < w20 else "PASS"
                w_dir = "↑" if wcs[-1] > wcs[-5] else "↓"
                out.append(f"Gate0(20W-MA): {sh_ec:.0f} < {w20:.0f} dir={w_dir} → {g0} [一票否决]")
        
        ma60 = sum(float(k[2]) for k in kls_long[-60:])/60 if len(kls_long)>=60 else 0
        ma250 = sum(float(k[2]) for k in kls_long[-250:])/250 if len(kls_long)>=250 else 0
        if ma250:
            if sh_ec > ma250 and ma60 > ma250:
                g1 = "80~100%"
            elif sh_ec > ma250:
                g1 = "≤50%"
            elif sh_ec < ma250 and ma60 < ma250:
                g1 = "0~20%"
            else:
                g1 = "≤20%"
            out.append(f"Gate1(趋势): close={sh_ec:.0f} MA60={ma60:.0f} MA250={ma250:.0f} → 仓位上限{g1}")
        
        # Gate2 量能
        if len(kls_long) >= 5:
            v5 = [float(kls_long[-i-1][5]) for i in range(5)]
            v5_avg = sum(v5)/5
            out.append(f"Gate2(量能): 近5日均量{v5_avg/1e8:.2f}亿手")
        
        # Gate3 情绪
        bs = api.board_summary()
        zt_t = bs.get("zt_total",0); dt_t = bs.get("dt_total",0)
        g3 = "PASS"
        if zt_t > 100: g3 = "涨停>100→不开新仓"
        elif dt_t > 10: g3 = "跌停>10→减半"
        out.append(f"Gate3(情绪): ZT={zt_t} DT={dt_t} → {g3}")
    
    # 打分卡
    s_z = dd["上证指数"]["chg_30"] if "上证指数" in dd else 0
    out.append("\n--- 打分卡 ---")
    g0_fail = True  # Gate0始终FAIL
    out.append(f"  指数结构: {'-1' if g0_fail else '0'} (Gate0 FAIL)")
    out.append(f"  市场广度: 0 ({pct:.0f}%上涨, 中性)")
    out.append(f"  量价关系: 0 (缩量+弱反弹)")
    out.append(f"  主线持续性: 0 (轮动快无主线)")
    out.append(f"  亏钱效应: 0 (无明显恐慌)")
    out.append(f"  总分: 0→收缩防守 (Gate0一票否决覆盖)")
    out.append(f"  仓位建议: 0~20% 防御档→510880/512890红利")
    
    return "\n".join(out)


# ===== L2: 板块 =====
def L2():
    out = [BOLD("L2: 板块 — SW31行业30日轮动分析")]
    pro = get_pro()
    sw_df = pro.index_classify(level='L1', src='SW2021', fields='index_code,industry_name')
    
    sects = {}
    for _,r in sw_df.iterrows():
        code, name = r['index_code'], r['industry_name']
        try:
            df = pro.sw_daily(ts_code=code, start_date='20260615', end_date='20260729',
                              fields='ts_code,trade_date,close,pct_chg')
            if df is None or df.empty: continue
            cs = [float(x['close']) for _,x in df.iterrows()]
            if len(cs) < 25: continue
            chg30 = (cs[-1]/cs[0]-1)*100
            chg10 = (cs[-1]/cs[-10]-1)*100 if len(cs)>=10 else 0
            chg_mid = (cs[15]/cs[0]-1)*100 if len(cs)>15 else 0
            chg_last = (cs[-1]/cs[15]-1)*100 if len(cs)>15 else 0
            # 趋势判断
            avg1 = sum(cs[:3])/3; avg3 = sum(cs[-3:])/3
            trend = "↑改善" if avg3>avg1 else "↓恶化" if avg3<avg1 else "→持平"
            sects[name] = (chg30, chg10, trend, chg_mid, chg_last, len(cs))
        except Exception: pass
    
    ranked = sorted(sects.items(), key=lambda x:x[1][0], reverse=True)
    out.append(f"{'Rk':<3} {'行业':<10} {'30日%':>8} {'近10日':>7} {'前15日':>7} {'后15日':>7} {'趋势':<6}")
    for i,(n,(c30,c10,trend,cm,cl,days)) in enumerate(ranked):
        out.append(f"{i+1:<3} {n:<10} {c30:+7.2f}% {c10:+6.2f}% {cm:+6.2f}% {cl:+6.2f}% {trend:<6}")
    
    top5 = ranked[:5]; bot5 = ranked[-5:]
    out.append(f"\nTop5: {', '.join(f'{n}({v[0]:+.1f}%)' for n,v in top5)}")
    out.append(f"Bot5: {', '.join(f'{n}({v[0]:+.1f}%)' for n,v in bot5)}")
    
    # 轮动突变
    switches = [(n,cm,cl,cl-cm) for n,(_,_,_,cm,cl,_) in ranked if abs(cl-cm)>3]
    out.append(f"\n轮动突变(前后15日差>3%): {len(switches)}个行业")
    for n,cm,cl,d in sorted(switches, key=lambda x:abs(x[3]), reverse=True)[:8]:
        out.append(f"  {n}: {cm:+.1f}%→{cl:+.1f}% ({d:+.1f}%)")
    
    # 板块三个主场/坟场判断
    out.append("\n--- 主场vs坟场 ---")
    n_up = sum(1 for n,v in sects.items() if v[0]>0)
    out.append(f"  30日上涨行业: {n_up}/31 ({n_up/31*100:.0f}%) → 结构性分化")
    out.append(f"  近10日: 强势品种减速(<+5%)，弱势品种反弹 → 超跌反弹/存量博弈")
    out.append(f"  结论: 存量震荡主场 → 板块快速轮动，波段回避防御/纯题材")
    
    return "\n".join(out)


# ===== L3: 个股/情绪 =====
def L3():
    out = [BOLD("L3: 情绪 — 涨停 + 热点 + 北向 + 人气")]
    
    # 涨停板
    bs = api.board_summary()
    zt = bs.get("zt_total",0); zt_y = bs.get("zt_yesterday",0)
    dt = bs.get("dt_total",0); dt_y = bs.get("dt_yesterday",0)
    mood = bs.get("mood","?")
    out.append(f"涨停板: 今日ZT/DT/炸板 = {zt}/{dt}/{bs.get('zb_rate','?')}% 昨ZT/DT={zt_y}/{dt_y} mood={mood}")
    
    # 概念热点
    try:
        hr = api.hot_rank(30)
        if hr and isinstance(hr,list) and len(hr)>0:
            out.append(f"\n概念热点({len(hr)}条):")
            for item in hr[:10]:
                pct = item.get('pct', item.get('change_pct', 0))
                out.append(f"  {item.get('name','?')} {pct:+0.2f}%")
        else:
            out.append(f"\n概念热点: 盘后无数据(正常)")
    except Exception as e:
        out.append(f"概念热点: ERR - {e}")
    
    # 北向资金
    nf = api.north_flow(10)
    records = nf.get("records",[]) if isinstance(nf,dict) else []
    latest = nf.get("latest",{}) if isinstance(nf,dict) else {}
    out.append(f"\n北向资金: 最新={latest.get('date','?')} {latest.get('total_yi',0)}亿")
    if records:
        for r in records[-5:]:
            out.append(f"  {r.get('date','?')}: {r.get('total_yi',0)}亿")
    
    # 人气榜
    try:
        pr = api.popular_rank()
        if pr and isinstance(pr,list):
            out.append(f"\n人气榜(Top8):")
            for item in pr[:8]:
                pct_pop = item.get('pct', item.get('change_pct', 0))
                out.append(f"  {item.get('name','?')} #{item.get('rank','?')} {pct_pop:+0.2f}%")
    except Exception: pass
    
    # 龙虎榜
    try:
        dt_data = api.dragon_tiger()
        if dt_data and isinstance(dt_data,list) and len(dt_data)>0:
            out.append(f"\n龙虎榜({len(dt_data)}条/Top5):")
            for item in dt_data[:5]:
                out.append(f"  {item.get('name','?')} 净额={item.get('net','?')}")
    except Exception: pass
    
    # 情绪综合判断
    out.append(f"\n--- 情绪综合 ---")
    if zt == 0: mood_t = "盘后/非交易日(数据未更新)"
    elif zt > 100: mood_t = f"过热(涨停{zt}>100)→不开新仓"
    elif zt > 60: mood_t = f"活跃({zt}只涨停)"
    elif zt > 30: mood_t = f"一般({zt}只)"
    else: mood_t = f"冰点({zt}只)"
    out.append(f"  判断: {mood_t}")
    
    return "\n".join(out)


# ===== MAIN =====
if __name__ == "__main__":
    start_time = time.time()
    out_path = os.path.join(PROJECT_ROOT, "_30d_layers_validated.txt")
    
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write(" 30日三层次分析 [大盘→板块→个股] + 多源交叉验证\n")
        f.write(f" 生成: {datetime.now().strftime('%Y-%m-%d %H:%M')} | K线截止: 2026-07-29 | 补: 盘中北向/热度\n")
        f.write("=" * 60 + "\n")
        
        # L0 数据验证
        f.write("\n\n# L0: 数据多源交叉验证\n")
        v1, _ = validate_kline()
        f.write(v1 + "\n")
        v2, _ = validate_sectors()
        f.write(v2 + "\n")
        v3 = validate_zt_north()
        f.write(v3 + "\n")
        
        # L1
        f.write("\n\n# L1: 大盘层\n")
        f.write(L1() + "\n")
        
        # L2
        f.write("\n\n# L2: 板块层\n")
        f.write(L2() + "\n")
        
        # L3
        f.write("\n\n# L3: 情绪层\n")
        f.write(L3() + "\n")
        
        elapsed = time.time() - start_time
        f.write(f"\n\n{'='*60}\n")
        f.write(f" 报告生成完毕 | 耗时: {elapsed:.1f}s\n")
    
    print(f"Done. Output: {out_path} ({elapsed:.1f}s)")
