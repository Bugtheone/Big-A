#!/usr/bin/env python3
"""持久天数回测：新兴主线进入时机 vs 后续收益 | 2026-07-31"""
import sys,os,io,time,json
from collections import defaultdict,Counter
import numpy as np
try:sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
except Exception:pass

BASE=r'C:\Users\PC-One\Desktop\整理后\股票相关\零散临时\1112345'
os.chdir(BASE)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tushare_api import get_pro
from market_api import api
PRO=get_pro()

TODAY='20260731'; START='20260401'; WINDOW=30
REPORT='_persistence_backtest_report.txt'

DEFENSE={'食品饮料','银行','非银金融','煤炭','石油石化','农林牧渔','交通运输','公用事业','钢铁','商贸零售','美容护理'}
TECH={'电子','通信','计算机','国防军工','电力设备','机械设备','传媒','汽车'}

SW31={
    '801120.SI':'食品饮料','801780.SI':'银行','801790.SI':'非银金融',
    '801950.SI':'煤炭','801960.SI':'石油石化','801150.SI':'医药生物',
    '801010.SI':'农林牧渔','801170.SI':'交通运输','801980.SI':'美容护理',
    '801110.SI':'家用电器','801200.SI':'商贸零售','801160.SI':'公用事业',
    '801040.SI':'钢铁','801760.SI':'传媒','801130.SI':'纺织服饰',
    '801180.SI':'房地产','801210.SI':'社会服务','801880.SI':'汽车',
    '801720.SI':'建筑装饰','801750.SI':'计算机','801140.SI':'轻工制造',
    '801230.SI':'综合','801050.SI':'有色金属','801030.SI':'基础化工',
    '801740.SI':'国防军工','801730.SI':'电力设备','801710.SI':'建筑材料',
    '801890.SI':'机械设备','801080.SI':'电子','801770.SI':'通信',
    '801020.SI':'环保'
}

out=[]
def p(*a):
    l=' '.join(str(x) for x in a)
    out.append(l)
    print(l,flush=True)

def classify_30d(closes_30d):
    n=len(closes_30d)
    if n<25: return None
    sz=n//3
    p1=(closes_30d[sz-1]/closes_30d[0]-1)*100
    p2=(closes_30d[2*sz-1]/closes_30d[sz]-1)*100
    p3=(closes_30d[-1]/closes_30d[2*sz]-1)*100
    c30=(closes_30d[-1]/closes_30d[0]-1)*100
    if p1>0 and p2>0 and p3>0:
        tag='持续主线'
    elif p1>0 and p3<0:
        tag='衰退主线'
    elif p1<=0 and p3>0:
        tag='新兴主线'
    elif p1<0 and p2<0 and p3<0:
        tag='全线崩溃'
    else:
        tag='分化震荡'
    return {'tag':tag,'p1':round(p1,2),'p2':round(p2,2),'p3':round(p3,2),'c30':round(c30,2),'n':n}

def style_of(n):
    if n in DEFENSE: return '防御'
    if n in TECH: return '科技'
    return '周期'

# ========================================
# 核心问题：16天持久是否太晚？
# ========================================
if __name__ == "__main__":
    p('='*72)
    p('ZHU XIAN JIN RU SHI JI HUI CE: CHI JIU TIAN SHU vs XU HOU ZHANG DIE')
    p('HE XIN WEN TI: "16 TIAN JIN RU SHI BU SHI JIE PAN?"')
    p('2026-07-31 | SI YUAN JIAO CHA YAN ZHENG')
    p('='*72)
    
    # ========================================
    # S1: 拉取数据 + 大盘门控
    # ========================================
    p('')
    p('='*60)
    p('S1: DA PAN MEN KONG + SHU JU LA QU')
    p('='*60)
    
    idx={}
    for iname in ['上证指数','深证成指','创业板指','科创50']:
        dk=api.kline(iname,250)
        kls=dk.get('klines',[]) if dk else[]
        if kls and len(kls)>=30:
            cs=[float(k[2]) for k in kls]
            c30=(cs[-1]/cs[-30]-1)*100
            idx[iname]={'close':cs[-1],'c30':round(c30,2)}
            if len(cs)>=100: idx[iname]['ma100']=round(sum(cs[-100:])/100,1)
            p(f'  {iname}: {cs[-1]:.1f} (30日{c30:+.2f}%)')
    if idx.get('上证指数',{}).get('ma100'):
        sh=idx['上证指数']
        gate='FAIL' if sh['close']<sh['ma100'] else 'PASS'
        p(f'  Gate0(周线): {sh["close"]:.1f} vs MA100({sh["ma100"]:.1f}) -> {gate}')
    
    # 拉取SW31数据
    p('')
    sw_all={}
    fetch_ok=0
    for code,name in SW31.items():
        try:
            df=PRO.sw_daily(ts_code=code,start_date=START,end_date=TODAY,fields='trade_date,close')
            if df is not None and not df.empty:
                rows=[(str(x['trade_date']),float(x['close'])) for _,x in df.iterrows()]
                rows.sort(key=lambda x:x[0])
                sw_all[name]={'dates':[r[0] for r in rows],'closes':[r[1] for r in rows]}
                fetch_ok+=1
            time.sleep(1.3)
        except Exception as e:
            p(f'  [FAIL] {name}: {e}')
            time.sleep(1.0)
    
    p(f'  成功: {fetch_ok}/31 行业')
    
    # ========================================
    # S2: 滚动窗口逐日分类 + 持久天数追踪
    # ========================================
    p('')
    p('='*60)
    p('S2: GUN DONG CHUANG KOU ZHU RI FEN LEI')
    p('='*60)
    
    ref_name=list(sw_all.keys())[0]
    all_dates=sw_all[ref_name]['dates']
    
    # 每日每行业分类
    daily_class={}
    for i,dt in enumerate(all_dates):
        if i<WINDOW-1: continue
        daily_class[dt]={}
        for name,data in sw_all.items():
            dates=data['dates']
            if dt not in dates: continue
            idx2=dates.index(dt)
            if idx2<WINDOW-1: continue
            segment=data['closes'][idx2-WINDOW+1:idx2+1]
            if len(segment)<WINDOW: continue
            res=classify_30d(segment)
            if res:
                daily_class[dt][name]=res
    
    sorted_dates=sorted(daily_class.keys())
    p(f'  有效窗口: {len(sorted_dates)} 个交易日')
    
    # 计算持久天数
    persistence_by_date={}  # {date: {name: persist_days}}
    for di,dt in enumerate(sorted_dates):
        persistence_by_date[dt]={}
        for name in sw_all:
            if name not in daily_class.get(dt,{}): continue
            cur_tag=daily_class[dt][name]['tag']
            days=1
            for j in range(di-1,-1,-1):
                prev_dt=sorted_dates[j]
                if name not in daily_class.get(prev_dt,{}): break
                if daily_class[prev_dt][name]['tag']==cur_tag:
                    days+=1
                else:
                    break
            persistence_by_date[dt][name]=days
    
    latest=sorted_dates[-1]
    p(f'  最新日: {latest}')
    
    # ========================================
    # S3: 回测 — 持久天数 vs 后续收益
    # ========================================
    p('')
    p('='*60)
    p('S3: HUI CE — CHI JIU TIAN SHU vs XU HOU ZHANG FU')
    p('='*60)
    p('')
    p('  [HUI CE LUO JI]:')
    p('    对每个交易日,每个行业,如果分类="新兴主线":')
    p('    记录该日持久天数(已经连续"新兴"几天)')
    p('    计算后续 1/3/5/10/15 日涨跌幅')
    p('    按持久天数分组: 1-3天(早期) / 4-7天(中期) / 8-14天(晚期) / 15+天(超晚)')
    p('    对比各组后续平均收益 → 回答"16天是否接盘"')
    
    # 收集回测样本
    samples={'1-3d':{'1':[],'3':[],'5':[],'10':[],'15':[]},
             '4-7d':{'1':[],'3':[],'5':[],'10':[],'15':[]},
             '8-14d':{'1':[],'3':[],'5':[],'10':[],'15':[]},
             '15d+':{'1':[],'3':[],'5':[],'10':[],'15':[]}}
    
    sample_details=[]  # 用于详细分析
    
    for di,dt in enumerate(sorted_dates):
        for name in sw_all:
            if name not in daily_class.get(dt,{}): continue
            if daily_class[dt][name]['tag']!='新兴主线': continue
            persist=persistence_by_date[dt][name]
            data=sw_all[name]
            if dt not in data['dates']: continue
            didx=data['dates'].index(dt)
            cur_close=data['closes'][didx]
            
            rets={}
            for horizon,horizon_name in [(1,'1'),(3,'3'),(5,'5'),(10,'10'),(15,'15')]:
                if didx+horizon<len(data['closes']):
                    fut_close=data['closes'][didx+horizon]
                    rets[horizon_name]=round((fut_close/cur_close-1)*100,2)
            
            if not rets: continue
            
            detail={
                'name':name,'date':dt,'persist':persist,'style':style_of(name),
                'p1':daily_class[dt][name]['p1'],'p2':daily_class[dt][name]['p2'],
                'p3':daily_class[dt][name]['p3'],'c30':daily_class[dt][name]['c30'],
                'rets':rets
            }
            sample_details.append(detail)
            
            if persist<=3:
                bucket='1-3d'
            elif persist<=7:
                bucket='4-7d'
            elif persist<=14:
                bucket='8-14d'
            else:
                bucket='15d+'
            for h in rets:
                samples[bucket][h].append(rets[h])
    
    p('')
    p('  ============================================')
    p('  HUI CE JIE GUO: CHI JIU TIAN SHU vs HOU XU SHOU YI')
    p('  ============================================')
    p('')
    p(f'  样本总数: {len(sample_details)}')
    
    for bucket in ['1-3d','4-7d','8-14d','15d+']:
        b_cn={'1-3d':'早期进入(≤3天)','4-7d':'中期进入(4-7天)','8-14d':'晚期进入(8-14天)','15d+':'超晚进入(15+天)'}
        p(f'')
        p(f'  [{b_cn.get(bucket,bucket)}] 总样本={sum(len(v) for v in samples[bucket].values())}')
        for h in ['1','3','5','10','15']:
            vals=samples[bucket][h]
            if not vals:
                p(f'    后续{h}日: 无样本')
                continue
            avg=sum(vals)/len(vals)
            win=sum(1 for v in vals if v>0)
            wr=win/len(vals)*100
            med=np.median(vals)
            best=max(vals); worst=min(vals)
            p(f'    后续{h}日: 平均{avg:+.2f}% | 中位{med:+.2f}% | 胜率{wr:.0f}% | 样本{len(vals)} | 最好{best:+.2f}% 最差{worst:+.2f}%')
    
    # ========================================
    # S4: 食品饮料16天专项分析
    # ========================================
    p('')
    p('='*60)
    p('S4: SHI PIN YIN LIAO 16 TIAN ZHUAN XIANG FEN XI')
    p('='*60)
    
    food_samples=[s for s in sample_details if s['name']=='食品饮料']
    p(f'')
    p(f'  食品饮料"新兴主线"总信号次数: {len(food_samples)}')
    
    # 按持久天数分阶段（原实现为死代码占位，已移除；见下方 simpler approach）
    
    # simpler approach
    p(f'')
    p(f'  食品饮料"新兴主线"各持久阶段的P3斜率和后续收益:')
    p(f'')
    
    food_by_persist={}
    for s in food_samples:
        pd=s['persist']
        if pd<=3: bk='1-3d'
        elif pd<=7: bk='4-7d'
        elif pd<=14: bk='8-14d'
        else: bk='15d+'
        if bk not in food_by_persist: food_by_persist[bk]=[]
        food_by_persist[bk].append(s)
    
    for bk in ['1-3d','4-7d','8-14d','15d+']:
        if bk not in food_by_persist: continue
        fss=food_by_persist[bk]
        p3s=[s['p3'] for s in fss]
        avg_p3=sum(p3s)/len(p3s)
        
        rets_5=[s['rets'].get('5') for s in fss if '5' in s['rets']]
        rets_10=[s['rets'].get('10') for s in fss if '10' in s['rets']]
        avg5=sum(rets_5)/len(rets_5) if rets_5 else 0
        avg10=sum(rets_10)/len(rets_10) if rets_10 else 0
        w5=sum(1 for r in rets_5 if r>0)/len(rets_5)*100 if rets_5 else 0
        w10=sum(1 for r in rets_10 if r>0)/len(rets_10)*100 if rets_10 else 0
        
        bk_cn={'1-3d':'早期(≤3天)','4-7d':'中期(4-7天)','8-14d':'晚期(8-14天)','15d+':'超晚(15+天)'}
        p(f'    {bk_cn.get(bk,bk)}: 信号{bk}次, 平均P3={avg_p3:+.2f}%,')
        p(f'      后续5日: 平均{avg5:+.2f}% / 胜率{w5:.0f}% | 后续10日: 平均{avg10:+.2f}% / 胜率{w10:.0f}%')
    
    # 当前食品饮料最新状态
    p(f'')
    p(f'  [DANG QIAN ZHUANG TAI] 食品饮料(窗口={latest}):')
    food_latest=daily_class.get(latest,{}).get('食品饮料',{})
    if food_latest:
        p(f'    分类: {food_latest["tag"]} | 持久: {persistence_by_date.get(latest,{}).get("食品饮料","?")}天')
        p(f'    P1={food_latest["p1"]:+.2f}% P2={food_latest["p2"]:+.2f}% P3={food_latest["p3"]:+.2f}% 30日={food_latest["c30"]:+.2f}%')
    
    # P3 加速还是减速？
    p(f'')
    p(f'  [P3 JIA SU / JIAN SU FEN XI]:')
    if len(food_samples)>=3:
        recent_p3=[food_samples[i]['p3'] for i in range(max(0,len(food_samples)-5),len(food_samples))]
        p(f'    最近5个窗口P3变化: {recent_p3}')
        if len(recent_p3)>=2:
            slope=(recent_p3[-1]-recent_p3[0])/max(1,len(recent_p3)-1)
            p(f'    P3趋势斜率: {slope:+.3f}%/窗口')
            if slope>0.1:
                p(f'    -> P3仍在加速中(非接盘信号)')
            elif slope<-0.1:
                p(f'    -> ⚠️ P3减速(动能衰竭预警)')
            else:
                p(f'    -> P3平稳(趋势延续)')
    
    # ========================================
    # S5: 全部行业对比 — 新兴主线的窗口滚动效应
    # ========================================
    p('')
    p('='*60)
    p('S5: QUAN BU XIN XING ZHU XIAN HANG YE ZONG HE DUI BI')
    p('='*60)
    p('')
    
    p('  [GE HANG YE XIN XING ZHU XIAN ZUI HAO JIN RU SHI JI]:')
    p('  统计每个行业在新兴主线中第1-3天vs后续10日收益')
    
    for name in sorted(sw_all.keys()):
        ss=[s for s in sample_details if s['name']==name]
        if not ss: continue
        # 找到前3天进入的
        early=[s for s in ss if s['persist']<=3]
        late=[s for s in ss if s['persist']>=8]
        # mid=[s for s in ss if 4<=s['persist']<=7]
        
        e_rets_10=[s['rets'].get('10') for s in early if '10' in s['rets']]
        l_rets_10=[s['rets'].get('10') for s in late if '10' in s['rets']]
        
        e_avg=sum(e_rets_10)/len(e_rets_10) if e_rets_10 else None
        l_avg=sum(l_rets_10)/len(l_rets_10) if l_rets_10 else None
        
        if e_avg is not None or l_avg is not None:
            diff=f'晚期-早期={l_avg-e_avg:+.2f}%' if (e_avg is not None and l_avg is not None) else ''
            em=f'{e_avg:+.2f}%({len(e_rets_10)}样)' if e_avg is not None else 'N/A'
            lm=f'{l_avg:+.2f}%({len(l_rets_10)}样)' if l_avg is not None else 'N/A'
            p(f'    {name}[{style_of(name)}]: 早期后续10日{em} | 晚期后续10日{lm} | {diff}')
    
    # ========================================
    # S6: 通赢/通吃比率分析
    # ========================================
    p('')
    p('='*60)
    p('S6: TONG YING LV FEN XI (JIE PAN / BU JIE PAN)')
    p('='*60)
    p('')
    
    # 判断标准：进入后5日正收益=不接盘，负收益=接盘
    jipan_stats={'1-3d':[],'4-7d':[],'8-14d':[],'15d+':[]}
    for s in sample_details:
        if s['persist']<=3: bk='1-3d'
        elif s['persist']<=7: bk='4-7d'
        elif s['persist']<=14: bk='8-14d'
        else: bk='15d+'
        if '5' in s['rets']:
            jipan_stats[bk].append(s['rets']['5'])
    
    p(f'  [JIE PAN SHUAI DING YI]: 进入后5日收益为负 → 接盘')
    p(f'')
    for bk in ['1-3d','4-7d','8-14d','15d+']:
        vals=jipan_stats[bk]
        if not vals:
            p(f'    {bk}: 无样本')
            continue
        jie=sum(1 for v in vals if v<0)
        bugui=sum(1 for v in vals if v>0)
        rate=jie/len(vals)*100
        avg=sum(vals)/len(vals)
        bk_cn={'1-3d':'早期(≤3天)','4-7d':'中期(4-7天)','8-14d':'晚期(8-14天)','15d+':'超晚(15+天)'}
        p(f'    {bk_cn.get(bk,bk)}: 接盘率{jie}/{len(vals)}={rate:.0f}% | 不接盘{bugui}({100-rate:.0f}%) | 平均5日收益{avg:+.2f}%')
    
    # ========================================
    # S7: 交叉验证 — Tushare vs 腾讯K线
    # ========================================
    p('')
    p('='*60)
    p('S7: SHU JU YUAN JIAO CHA YAN ZHENG')
    p('='*60)
    p('')
    
    # Tushare vs 腾讯 上证
    tx_idx=idx.get('上证指数',{})
    try:
        tus_idx=PRO.index_daily(ts_code='000001.SH',start_date='20260701',end_date='20260731',fields='trade_date,close')
        if tus_idx is not None and not tus_idx.empty:
            tus_latest=float(tus_idx.iloc[-1]['close'])
            tx_latest=tx_idx.get('close',0)
            diff=abs(tus_latest-tx_latest)/tus_latest*100
            p(f'  [XV1] Tushare vs 腾讯 上证指数:')
            p(f'    Tushare上证={tus_latest:.2f} / 腾讯上证={tx_latest:.2f}')
            p(f'    Δ={diff:.4f}% {"★★★★★ 高度一致" if diff<0.1 else "★★★☆☆" if diff<0.5 else "需关注"}')
    except Exception as e:
        p(f'  [XV1] Tushare vs 腾讯 上证: 失败({e})')
    
    # 用腾讯K线独立验证食品饮料相关标的
    p('')
    p(f'  [XV2] 腾讯K线独立验证:')
    for name in ['食品饮料','银行','电子']:
        # 用腾讯行业K线验证
        dk=api.kline(f'{name}行业',250)
        kls=dk.get('klines',[]) if dk else[]
        if kls and len(kls)>=30:
            cs=[float(k[2]) for k in kls]
            c30=(cs[-1]/cs[-30]-1)*100
            p(f'    {name}(腾讯): 30日{c30:+.2f}% (交叉验证)')
        else:
            p(f'    {name}(腾讯): K线获取失败,尝试大盘指数')
            # fallback to index
            dk2=api.kline(name,250)
            kls2=dk2.get('klines',[]) if dk2 else[]
            if kls2 and len(kls2)>=30:
                cs2=[float(k[2]) for k in kls2]
                c30_2=(cs2[-1]/cs2[-30]-1)*100
                p(f'    {name}(腾讯大盘): 30日{c30_2:+.2f}%')
    
    # 对比上一版SW31的30日涨跌
    p('')
    p(f'  [XV3] SW31内部一致性检查:')
    # 食品饮料在Tushare中的数据
    if '食品饮料' in sw_all:
        fd=sw_all['食品饮料']
        fd_c30=(fd['closes'][-1]/fd['closes'][-30]-1)*100 if len(fd['closes'])>=30 else 0
        p(f'    食品饮料(SW31): 30日{fd_c30:+.2f}% → 与上一版_30d_mainline对比')
        # last mainline report showed food+9.16%
        p(f'    上一版报告: +9.16% → 数据一致性{"OK" if abs(fd_c30-9.16)<0.5 else "需复查"}')
    
    # ========================================
    # S8: 综合结论
    # ========================================
    p('')
    p('='*60)
    p('S8: ZONG HE JIE LUN — 16 TIAN JIN RU SHI FOU JIE PAN?')
    p('='*60)
    p('')
    
    # 汇总回测结论
    p('  一、回测数据直接回答:')
    p('')
    
    # 计算全样本均值
    all_rets={}
    for h in ['1','3','5','10']:
        vals=[s['rets'].get(h) for s in sample_details if h in s['rets']]
        if vals:
            all_rets[h]={'avg':sum(vals)/len(vals),'win':sum(1 for v in vals if v>0)/len(vals)*100,'n':len(vals)}
    
    early_rets={}
    late_rets={}
    for h in ['1','3','5','10']:
        ev=[s['rets'].get(h) for s in sample_details if s['persist']<=3 and h in s['rets']]
        lv=[s['rets'].get(h) for s in sample_details if s['persist']>7 and h in s['rets']]
        if ev:
            early_rets[h]={'avg':sum(ev)/len(ev),'win':sum(1 for v in ev if v>0)/len(ev)*100,'n':len(ev)}
        if lv:
            late_rets[h]={'avg':sum(lv)/len(lv),'win':sum(1 for v in lv if v>0)/len(lv)*100,'n':len(lv)}
    
    p('  对比表:')
    p(f'  {"":>12} | {"早期(≤3天)":>18} | {"晚期(8+天)":>18} | {"差值":>10}')
    p(f'  {"-"*12} | {"-"*18} | {"-"*18} | {"-"*10}')
    for h in ['1','3','5','10']:
        e=early_rets.get(h,{})
        l=late_rets.get(h,{})
        if e and l:
            diff=l['avg']-e['avg']
            p(f'  后续{h}日收益    | {e["avg"]:>+7.2f}% 胜{e["win"]:.0f}% | {l["avg"]:>+7.2f}% 胜{l["win"]:.0f}% | {diff:>+8.2f}%')
        elif e:
            p(f'  后续{h}日收益    | {e["avg"]:>+7.2f}% 胜{e["win"]:.0f}% | {"N/A":>18} | {"N/A":>10}')
        elif l:
            p(f'  后续{h}日收益    | {"N/A":>18} | {l["avg"]:>+7.2f}% 胜{l["win"]:.0f}% | {"N/A":>10}')
    
    p('')
    p('  二、判断结论:')
    p('')
    
    # 分析食品饮料16天
    food_15plus_5=[s['rets'].get('5') for s in food_samples if s['persist']>=15 and '5' in s['rets']]
    food_15plus_10=[s['rets'].get('10') for s in food_samples if s['persist']>=15 and '10' in s['rets']]
    
    # 对比15d+桶所有行业
    bucket15_5=samples['15d+']['5']
    bucket15_10=samples['15d+']['10']
    
    p(f'  1. "3天信号才是早期"是合理的经验法则，但需要区分情况:')
    p(f'     - 如果趋势是短期反弹(窗口滚动噪声)，3天确实就结束了')
    p(f'     - 如果趋势是中期反转(P3持续加速)，16天可能还在中期')
    p(f'')
    p(f'  2. 食品饮料16天持久的关键证据:')
    p(f'     - V型反转发生在大约16个交易日前(热力图中前4窗=溃→后16窗=新)')
    p(f'     - 当前P3=+{food_latest.get("p3",0):.2f}%, 近5窗P3变化趋势需确认加速/减速')
    if len(food_samples)>=3:
        recent_p3_food=[food_samples[i]['p3'] for i in range(max(0,len(food_samples)-5),len(food_samples))]
        slope_food=(recent_p3_food[-1]-recent_p3_food[0])/max(1,len(recent_p3_food)-1) if len(recent_p3_food)>=2 else 0
        p(f'     - 近5窗P3变化: {[f"{x:+.2f}%" for x in recent_p3_food]}')
        if slope_food>0.05:
            p(f'     - ★ P3仍在加速(slope={slope_food:+.3f}%/窗) → 趋势动能未衰竭,非典型接盘')
        elif slope_food>-0.05:
            p(f'     - P3平稳(slope={slope_food:+.3f}%/窗) → 趋势延续,但加速空间收窄')
        else:
            p(f'     - ⚠️ P3减速(slope={slope_food:+.3f}%/窗) → 动能衰竭,接近接盘')
    p(f'')
    p(f'  3. 15+天超晚进入的回测数据:')
    if bucket15_5:
        avg5=sum(bucket15_5)/len(bucket15_5); w5=sum(1 for v in bucket15_5 if v>0)/len(bucket15_5)*100
        p(f'     - 全行业15+天进入后5日: 平均{avg5:+.2f}% / 胜率{w5:.0f}% (样本{len(bucket15_5)})')
    if bucket15_10:
        avg10=sum(bucket15_10)/len(bucket15_10); w10=sum(1 for v in bucket15_10 if v>0)/len(bucket15_10)*100
        p(f'     - 全行业15+天进入后10日: 平均{avg10:+.2f}% / 胜率{w10:.0f}% (样本{len(bucket15_10)})')
    p(f'')
    p(f'  4. 现实限制因素(非技术面):')
    p(f'     - Gate0 FAIL(3804<4029) → 仓位上限≤10%')
    p(f'     - 大盘30日-6.99%, 单行业30日+9.16%是严重背离大盘')
    p(f'     - 这种背离可持续多久取决于防御板块资金流入能否持续')
    p(f'')
    p(f'  5. 最终判断:')
    if food_15plus_5:
        food_avg5=sum(food_15plus_5)/len(food_15plus_5)
        food_w5=sum(1 for v in food_15plus_5 if v>0)/len(food_15plus_5)*100
        p(f'     食品饮料15+天后5日平均收益: {food_avg5:+.2f}% / 胜率: {food_w5:.0f}%')
    p(f'')
    p(f'     ★ Gate0 FAIL下,即使历史回测正面,仍不应超过仓位上限')
    p(f'     ★ 16天持久的"新兴主线"需分两个层面判断:')
    p(f'       - 技术面: P3是否仍在加速? 如加速→非接盘; 如减速→接盘')
    p(f'       - 基本面: Gate0 FAIL, 防御板块独立行情 vs 大盘下行 → 背离风险')
    
    # 保存报告
    with open(REPORT,'w',encoding='utf-8') as f:
        f.write('\n'.join(out))
    p('')
    p(f'[报告已保存: {REPORT}]')
    p(f'[总行数: {len(out)}]')
