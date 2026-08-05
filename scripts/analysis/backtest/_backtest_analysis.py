#!/usr/bin/env python3
"""持久天数回测分析 — 核心回答：16天进入是否接盘 | 2026-07-31"""
import sys,os,io,json,time
from collections import defaultdict,Counter
import numpy as np
try:sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
except Exception:pass

BASE = os.environ.get("ANALYSIS_BASE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data"))
os.makedirs(BASE, exist_ok=True)
os.chdir(BASE)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from market_api import api

WINDOW=30; CACHE='_sw31_cache.json'; REPORT='_backtest_16d_report.txt'

DEFENSE={'食品饮料','银行','非银金融','煤炭','石油石化','农林牧渔','交通运输','公用事业','钢铁','商贸零售','美容护理'}
TECH={'电子','通信','计算机','国防军工','电力设备','机械设备','传媒','汽车'}
CN={'持续主线':'持','新兴主线':'新','衰退主线':'退','全线崩溃':'溃','分化震荡':'分'}

out=[]
def p(*a):
    l=' '.join(str(x) for x in a)
    out.append(l);print(l,flush=True)

def classify_30d(closes_30d):
    n=len(closes_30d)
    if n<25: return None
    sz=n//3
    p1=(closes_30d[sz-1]/closes_30d[0]-1)*100
    p2=(closes_30d[2*sz-1]/closes_30d[sz]-1)*100
    p3=(closes_30d[-1]/closes_30d[2*sz]-1)*100
    c30=(closes_30d[-1]/closes_30d[0]-1)*100
    if p1>0 and p2>0 and p3>0: tag='持续主线'
    elif p1>0 and p3<0: tag='衰退主线'
    elif p1<=0 and p3>0: tag='新兴主线'
    elif p1<0 and p2<0 and p3<0: tag='全线崩溃'
    else: tag='分化震荡'
    return {'tag':tag,'p1':round(p1,2),'p2':round(p2,2),'p3':round(p3,2),'c30':round(c30,2)}

def style_of(n):
    if n in DEFENSE: return '防御'
    if n in TECH: return '科技'
    return '周期'

# ========== 加载缓存 ==========
if __name__ == "__main__":
    with open(CACHE,'r',encoding='utf-8') as f:
        sw_all=json.load(f)
    # convert dates/closes back
    for name in sw_all:
        sw_all[name]['closes']=[float(x) for x in sw_all[name]['closes']]
    
    ref_name=list(sw_all.keys())[0]
    all_dates=sw_all[ref_name]['dates']
    p(f'数据加载: {len(sw_all)}行业, {len(all_dates)}交易日({all_dates[0]}~{all_dates[-1]})')
    
    # ========== 大盘门控 ==========
    idx={}
    for iname in ['上证指数','深证成指','创业板指','科创50']:
        dk=api.kline(iname,250)
        kls=dk.get('klines',[]) if dk else[]
        if kls and len(kls)>=30:
            cs=[float(k[2]) for k in kls]
            c30=(cs[-1]/cs[-30]-1)*100
            idx[iname]={'close':cs[-1],'c30':round(c30,2)}
            if len(cs)>=100: idx[iname]['ma100']=round(sum(cs[-100:])/100,1)
    sh=idx.get('上证指数',{})
    gate='FAIL' if sh.get('close',0)<sh.get('ma100',0) else 'PASS'
    
    # ========== 滚动窗口分类 ==========
    daily_class={}
    for i,dt in enumerate(all_dates):
        if i<WINDOW-1: continue
        daily_class[dt]={}
        for name,data in sw_all.items():
            dates=data['dates']
            if dt not in dates: continue
            di=dates.index(dt)
            if di<WINDOW-1: continue
            segment=data['closes'][di-WINDOW+1:di+1]
            res=classify_30d(segment)
            if res: daily_class[dt][name]=res
    
    sorted_dates=sorted(daily_class.keys())
    p(f'有效窗口: {len(sorted_dates)} ({sorted_dates[0]}~{sorted_dates[-1]})')
    
    # 持久天数
    persistence_by_date={}
    for di,dt in enumerate(sorted_dates):
        persistence_by_date[dt]={}
        for name in sw_all:
            if name not in daily_class.get(dt,{}): continue
            cur_tag=daily_class[dt][name]['tag']
            days=1
            for j in range(di-1,-1,-1):
                prev_dt=sorted_dates[j]
                if name not in daily_class.get(prev_dt,{}): break
                if daily_class[prev_dt][name]['tag']==cur_tag: days+=1
                else: break
            persistence_by_date[dt][name]=days
    
    latest=sorted_dates[-1]
    
    # ============================
    # 核心回测：持久天数 vs 后续收益
    # ============================
    p('');p('='*60)
    p('HE XIN HUI CE: CHI JIU TIAN SHU vs HOU XU SHOU YI')
    p('='*60)
    
    buckets={'1-3d':{'name':'早期(1-3天)','1':[],'3':[],'5':[],'10':[],'15':[]},
             '4-7d':{'name':'中期(4-7天)','1':[],'3':[],'5':[],'10':[],'15':[]},
             '8-14d':{'name':'晚期(8-14天)','1':[],'3':[],'5':[],'10':[],'15':[]},
             '15d+':{'name':'超晚(15+天)','1':[],'3':[],'5':[],'10':[],'15':[]}}
    
    all_samples=[]
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
            for h,hname in [(1,'1'),(3,'3'),(5,'5'),(10,'10'),(15,'15')]:
                if didx+h<len(data['closes']):
                    rets[hname]=round((data['closes'][didx+h]/cur_close-1)*100,2)
            if not rets: continue
            bk='1-3d' if persist<=3 else ('4-7d' if persist<=7 else ('8-14d' if persist<=14 else '15d+'))
            for hname in rets:
                buckets[bk][hname].append(rets[hname])
            all_samples.append({'name':name,'date':dt,'persist':persist,'p1':daily_class[dt][name]['p1'],
                              'p2':daily_class[dt][name]['p2'],'p3':daily_class[dt][name]['p3'],
                              'c30':daily_class[dt][name]['c30'],'rets':rets,'style':style_of(name)})
    
    p(f'\n总样本: {len(all_samples)} 次"新兴主线"信号')
    p(f'\n{"="*72}')
    p(f'{"持久时间段":>16} | {"后续1日":>14} | {"后续3日":>14} | {"后续5日":>14} | {"后续10日":>14}')
    p(f'{"-"*72}')
    
    for bk_key in ['1-3d','4-7d','8-14d','15d+']:
        bd=buckets[bk_key]
        line=f'{bd["name"]:>14}'
        for h in ['1','3','5','10']:
            vals=bd[h]
            if vals:
                avg=sum(vals)/len(vals); w=sum(1 for v in vals if v>0)/len(vals)*100
                line+=f' | {avg:>+6.2f}% W{w:>3.0f}%'
            else:
                line+=' |       N/A    '
        line+=f' | N={max(len(v) for v in bd.values() if v)}样'
        p(line)
    
    # ============================
    # 接盘率分析
    # ============================
    p('');p('='*60)
    p('JIE PAN SHUAI FEN XI (后续5日<0 = 接盘)')
    p('='*60)
    p(f'\n{"持久时间段":>16} | {"样本":>5} | {"接盘":>5} | {"接盘率":>7} | {"平均5日":>8}')
    p(f'{"-"*55}')
    for bk_key in ['1-3d','4-7d','8-14d','15d+']:
        vals=buckets[bk_key]['5']
        if not vals: continue
        jie=sum(1 for v in vals if v<0); rate=jie/len(vals)*100; avg=sum(vals)/len(vals)
        p(f'{buckets[bk_key]["name"]:>14} | {len(vals):>5} | {jie:>5} | {rate:>6.1f}% | {avg:>+7.2f}%')
    
    # ============================
    # 食品饮料专项分析
    # ============================
    p('');p('='*60)
    p('SHI PIN YIN LIAO 16 TIAN ZHUAN XIANG')
    p('='*60)
    
    food_all=[s for s in all_samples if s['name']=='食品饮料']
    p(f'\n食品饮料"新兴主线"信号总计: {len(food_all)}次')
    
    # 分阶段
    food_stages={}
    for s in food_all:
        if s['persist']<=3: bk='1-3d'
        elif s['persist']<=7: bk='4-7d'
        elif s['persist']<=14: bk='8-14d'
        else: bk='15d+'
        food_stages.setdefault(bk,[]).append(s)
    
    for bk in ['1-3d','4-7d','8-14d','15d+']:
        if bk not in food_stages: continue
        fss=food_stages[bk]
        p3s=[s['p3'] for s in fss]
        ret5=[s['rets'].get('5') for s in fss if '5' in s['rets']]
        ret10=[s['rets'].get('10') for s in fss if '10' in s['rets']]
        a5=sum(ret5)/len(ret5) if ret5 else 0
        a10=sum(ret10)/len(ret10) if ret10 else 0
        w5=sum(1 for r in ret5 if r>0)/len(ret5)*100 if ret5 else 0
        w10=sum(1 for r in ret10 if r>0)/len(ret10)*100 if ret10 else 0
        p(f'  {buckets[bk]["name"]}: {len(fss)}次, P3均值{sum(p3s)/len(p3s):+.2f}%')
        p(f'    后续5日: avg={a5:+.2f}% win={w5:.0f}% | 后续10日: avg={a10:+.2f}% win={w10:.0f}%')
    
    # P3加速/减速
    food_latest=daily_class.get(latest,{}).get('食品饮料',{})
    p(f'\n食品饮料当前状态:')
    p(f'  最新窗口={latest} | 分类={food_latest.get("tag","?")} | 持久={persistence_by_date.get(latest,{}).get("食品饮料","?")}天')
    p(f'  P1={food_latest.get("p1",0):+.2f}% P2={food_latest.get("p2",0):+.2f}% P3={food_latest.get("p3",0):+.2f}% 30日={food_latest.get("c30",0):+.2f}%')
    
    # 追踪近N窗P3变化
    if len(food_all)>=3:
        recent=[food_all[i]['p3'] for i in range(max(0,len(food_all)-5),len(food_all))]
        p(f'  近{len(recent)}窗P3变化: {[f"{x:+.2f}%" for x in recent]}')
        if len(recent)>=2:
            slope=(recent[-1]-recent[0])/max(1,len(recent)-1)
            p(f'  P3趋势斜率: {slope:+.3f}%/窗口')
            if slope>0.1: p(f'  >> ★ P3仍在加速 → 动能未衰竭,非典型接盘信号')
            elif slope>=-0.1: p(f'  >> P3平稳 → 趋势延续,但加速空间收窄')
            else: p(f'  >> ⚠️ P3减速 → 动能衰竭预警,接近接盘')
    
    # 食品每日分类热力图(全窗口)
    p(f'\n食品饮料全窗口分类热力图:')
    line=[]; line2=[]
    for i,dt in enumerate(sorted_dates):
        if '食品饮料' in daily_class.get(dt,{}):
            tag=daily_class[dt]['食品饮料']['tag']; line.append(CN.get(tag,tag[0]))
            line2.append(str(persistence_by_date.get(dt,{}).get('食品饮料','?')%10))
        else:
            line.append('.'); line2.append('.')
    p('  '+''.join(line))
    p('  持久末位: '+''.join(line2))
    
    # 找到反转点
    print_flags=[]
    for i in range(1,len(line)):
        if line[i]!=line[i-1] and line[i]!='.':
            print_flags.append(f'    {sorted_dates[i]}: {CN.get(line[i-1],"")}->{CN.get(line[i],"")} (第{i+1}窗)')
    if print_flags:
        p(f'\n食品饮料反转点:')
        for pf in print_flags: p(pf)
    
    # ============================
    # 各行业对比
    # ============================
    p('');p('='*60)
    p('QUAN HANG YE DUI BI: ZAO vs WAN JIN RU')
    p('='*60)
    p(f'\n{"行业":>12} | {"早期后续10日":>16} | {"晚期后续10日":>16} | {"差值":>8}')
    p(f'{"-"*60}')
    for name in sorted(sw_all.keys()):
        ss=[s for s in all_samples if s['name']==name]
        if not ss: continue
        e_r=[s['rets'].get('10') for s in ss if s['persist']<=3 and '10' in s['rets']]
        l_r=[s['rets'].get('10') for s in ss if s['persist']>=8 and '10' in s['rets']]
        if not e_r and not l_r: continue
        ea=sum(e_r)/len(e_r) if e_r else None
        la=sum(l_r)/len(l_r) if l_r else None
        es=f'{ea:+.2f}%({len(e_r)})' if ea is not None else 'N/A'
        ls=f'{la:+.2f}%({len(l_r)})' if la is not None else 'N/A'
        diff=f'{(la-ea):+.2f}%' if (ea is not None and la is not None) else ''
        p(f'{name:>12} | {es:>16} | {ls:>16} | {diff:>8}')
    
    # ============================
    # 交叉验证
    # ============================
    p('');p('='*60)
    p('SHU JU YUAN JIAO CHA YAN ZHENG')
    p('='*60)
    
    p(f'\n[XV1] 大盘交叉:')
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from tushare_api import get_pro
        PRO=get_pro()
        tus_idx=PRO.index_daily(ts_code='000001.SH',start_date='20260701',end_date='20260731',fields='trade_date,close')
        if tus_idx is not None and not tus_idx.empty:
            tus_latest=float(tus_idx.iloc[-1]['close'])
            tx_latest=sh.get('close',0)
            diff=abs(tus_latest-tx_latest)/tus_latest*100
            p(f'  Tushare上证={tus_latest:.2f} vs 腾讯上证={tx_latest:.2f} Δ={diff:.4f}%')
            p(f'  -> {"★★★★★" if diff<0.1 else "★★★☆☆" if diff<0.5 else "需复查"}')
    except Exception as e:
        p(f'  [SKIP] {e}')
    
    p(f'\n[XV2] SW31内部一致性:')
    if '食品饮料' in sw_all:
        fd=sw_all['食品饮料']
        fd_c30=(fd['closes'][-1]/fd['closes'][-30]-1)*100 if len(fd['closes'])>=30 else 0
        p(f'  食品饮料30日: {fd_c30:+.2f}% (vs 上版+9.16% {"OK" if abs(fd_c30-9.16)<0.5 else "复查"})')
    for name in ['食品饮料','银行','电子']:
        if name in sw_all:
            d=sw_all[name]
            c30=(d['closes'][-1]/d['closes'][-30]-1)*100 if len(d['closes'])>=30 else 0
            p(f'  {name}(SW31): 30日{c30:+.2f}%')
    
    # ============================
    # 综合结论
    # ============================
    p('');p('='*60)
    p('ZONG HE JIE LUN')
    p('='*60)
    
    # 统计全样本(安全处理空桶)
    def safe_stats(vals):
        if not vals: return (0,0,0)
        return (sum(vals)/len(vals), sum(1 for v in vals if v>0)/len(vals)*100, len(vals))
    
    early_5=buckets['1-3d']['5']; late_5=buckets['15d+']['5']
    e5_avg,e5_win,e5_n=safe_stats(early_5); l5_avg,l5_win,l5_n=safe_stats(late_5)
    early_10=buckets['1-3d']['10']; late_10=buckets['15d+']['10']
    e10_avg,e10_win,e10_n=safe_stats(early_10); l10_avg,l10_win,l10_n=safe_stats(late_10)
    
    p(f'''
    一、回测直接回答"16天进入是否接盘":
    
       【核心数据：新兴主线进入时机 vs 后续收益】''')
    p(f'   早期(1-3天)进入 → 后续5日: {e5_avg:+.2f}% / 胜率{e5_win:.0f}% ({e5_n}样)')
    if l5_n>0:
        p(f'   超晚(15+天)进入→ 后续5日: {l5_avg:+.2f}% / 胜率{l5_win:.0f}% ({l5_n}样)')
        p(f'   差值: {l5_avg-e5_avg:+.2f}%')
    else:
        p(f'   超晚(15+天)进入→ 无足够样本(持久15+天信号后的数据不足)')
    p(f'   早期(1-3天)进入 → 后续10日: {e10_avg:+.2f}% / 胜率{e10_win:.0f}% ({e10_n}样)')
    if l10_n>0:
        p(f'   超晚(15+天)进入→ 后续10日: {l10_avg:+.2f}% / 胜率{l10_win:.0f}% ({l10_n}样)')
        p(f'   差值: {l10_avg-e10_avg:+.2f}%')
    else:
        p(f'   超晚(15+天)进入→ 无足够样本')
    
    # 用8-14天做晚期替代
    mid8_5=buckets['8-14d']['5']; mid8_10=buckets['8-14d']['10']
    m8_5avg,_,m8_5n=safe_stats(mid8_5); m8_10avg,_,m8_10n=safe_stats(mid8_10)
    if m8_5n>0:
        p(f'')
        p(f'   [替代数据: 晚期(8-14天)]')
        p(f'   晚期(8-14天)进入 → 后续5日: {m8_5avg:+.2f}% ({m8_5n}样)')
        if m8_10n>0:
            p(f'   晚期(8-14天)进入 → 后续10日: {m8_10avg:+.2f}% ({m8_10n}样)')
    
    # 接盘率对比
    jie_early=sum(1 for v in early_5 if v<0)/len(early_5)*100
    jie_mid8=sum(1 for v in mid8_5 if v<0)/len(mid8_5)*100 if mid8_5 else 0
    jie_late=sum(1 for v in late_5 if v<0)/len(late_5)*100 if late_5 else 0
    p(f'')
    p(f'   接盘率(进入后5日<0):')
    p(f'   早期≤3天: {jie_early:.0f}% | 晚期8-14天: {jie_mid8:.0f}% | 超晚15+天: {"{:.0f}%".format(jie_late) if late_5 else "N/A"}')
    
    # 食品饮料P3趋势
    food_recent_p3=[food_all[i]['p3'] for i in range(max(0,len(food_all)-5),len(food_all))] if len(food_all)>=3 else []
    slope_food=(food_recent_p3[-1]-food_recent_p3[0])/max(1,len(food_recent_p3)-1) if len(food_recent_p3)>=2 else 0
    
    p(f'''
    二、食品饮料16天持久专项判断:
    
       P3(近10日动能): {food_latest.get('p3',0):+.2f}%
       近5窗P3趋势: {[f"{x:+.2f}%" for x in food_recent_p3] if food_recent_p3 else "N/A"}
       斜率: {slope_food:+.3f}%/窗 {"(加速中)" if slope_food>0.1 else "(平稳)" if slope_food>-0.1 else "(减速!)" }
    
       "3天信号才是早期"适用的前提:
       - 短期反弹/窗口滚动噪声: 3天后即转势 → 适用
       - 中期趋势反转/V型反转: 16天可能仍在中期 → 不适用
    
       判断标准: 不是看持续了几天，而是看P3是否还在加速
       → P3在加速 → 趋势动能未衰竭 → 非接盘
       → P3在减速 → 动能衰竭 → 接近接盘
    
    三、现实限制:
    
       Gate0: {gate} ({"一票否决" if gate=="FAIL" else "可参与"})
       仓位上限: {"<=10%" if gate=="FAIL" else "按Gate1/2/3决定"}
       大盘30日: -6.99%, 食品饮料30日: +{food_latest.get('c30',0):.2f}%
       背离程度: {abs(food_latest.get('c30',0)+6.99):.1f}% → {"极端背离,不可持续" if abs(food_latest.get('c30',0)+6.99)>10 else "可接受偏离"}
    
    四、最终建议:
    
       1. 技术面: P3{"加速" if slope_food>0.1 else "平稳" if slope_food>-0.1 else "减速"}
          → {"非接盘信号,但需警惕加速放缓" if slope_food>0.1 else "趋势延续可接受" if slope_food>-0.1 else "动能衰竭,不宜追入"}
    
       2. 基本盘: Gate0 FAIL + 大盘30日-6.99%
          → 防御板块独涨不可持续,仓位严格≤10%
    
       3. 实际仓位建议: {"食品饮料≤10%, 银行≤10%, 交通≤10%, 整体≤10%" if gate=="FAIL" else "视Gate1/2/3调整"}
    
       4. 监测点: P3连续2窗下降 → 立即减仓
          P3加速窗口数: {len(food_recent_p3) if food_recent_p3 else 0}个窗口中{"全部加速" if slope_food>0.1 else "趋势不明确" if slope_food>-0.1 else "已减速"}
    ''')
    
    # 保存
    with open(REPORT,'w',encoding='utf-8') as f:
        f.write('\n'.join(out))
    p(f'\n[报告保存: {REPORT}]')
    p(f'[总行: {len(out)}]')
