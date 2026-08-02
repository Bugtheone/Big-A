#!/usr/bin/env python3
import sys,os,io,numpy as np
from collections import defaultdict,Counter
try:sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
except Exception:pass
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from market_api import api
from tushare_api import get_pro
PRO=get_pro()
TODAY,START='20260731','20260619'
REPORT='_30d_mainline_report.txt'
DEFENSE={'食品饮料','银行','非银金融','煤炭','石油石化','农林牧渔','交通运输','公用事业','钢铁','商贸零售','美容护理'}
TECH={'电子','通信','计算机','国防军工','电力设备','机械设备','传媒','汽车'}
SW31={'801120.SI':'食品饮料','801780.SI':'银行','801790.SI':'非银金融','801950.SI':'煤炭','801960.SI':'石油石化','801150.SI':'医药生物','801010.SI':'农林牧渔','801170.SI':'交通运输','801980.SI':'美容护理','801110.SI':'家用电器','801200.SI':'商贸零售','801160.SI':'公用事业','801040.SI':'钢铁','801760.SI':'传媒','801130.SI':'纺织服饰','801180.SI':'房地产','801210.SI':'社会服务','801880.SI':'汽车','801720.SI':'建筑装饰','801750.SI':'计算机','801140.SI':'轻工制造','801230.SI':'综合','801050.SI':'有色金属','801030.SI':'基础化工','801740.SI':'国防军工','801730.SI':'电力设备','801710.SI':'建筑材料','801890.SI':'机械设备','801080.SI':'电子','801770.SI':'通信','801020.SI':'环保'}
out=[]
def p(*a):l=' '.join(str(x) for x in a);out.append(l);print(l,flush=True)

def style_of(name):
    if name in DEFENSE:return'防御'
    if name in TECH:return'科技'
    return'周期'

def calc_phases(closes):
    n=len(closes)
    if n<25:return None
    sz=n//3
    p1=(closes[sz-1]/closes[0]-1)*100 if sz>0 else 0
    p2=(closes[2*sz-1]/closes[sz]-1)*100 if 2*sz<=n else 0
    p3=(closes[-1]/closes[2*sz]-1)*100 if 2*sz<n else 0
    chg30=(closes[-1]/closes[0]-1)*100
    chg5=(closes[-1]/closes[-5]-1)*100 if n>=5 else 0
    dc=[(closes[i]/closes[i-1]-1)*100 for i in range(1,n)]
    vol=float(np.std(dc)) if dc else 0
    return{'p1':round(p1,2),'p2':round(p2,2),'p3':round(p3,2),'c30':round(chg30,2),'c5':round(chg5,2),'vol':round(vol,2),'n':n}
if __name__ == "__main__":
    
    # ===== S0 大盘验证 =====
    p('='*72)
    p('30RI PAN KUAI ZHU XIAN QUAN JING FEN XI | 2026-07-31 PAN HOU')
    p('='*72)
    p('')
    p('=== S0.1 DA PAN K XIAN (TENG XUN) ===')
    idx={}
    for iname in['上证指数','深证成指','创业板指','科创50']:
        try:
            dk=api.kline(iname,250)
            kls=dk.get('klines',[]) if dk else[]
            if kls and len(kls)>=30:
                cs=[float(k[2]) for k in kls]
                c30=(cs[-1]/cs[-30]-1)*100
                d={'close':cs[-1],'c30':round(c30,2)}
                if len(cs)>=100:d['ma100']=round(sum(cs[-100:])/100,1)
                if len(cs)>=60:d['ma60']=round(sum(cs[-60:])/60,1)
                if len(cs)>=250:d['ma250']=round(sum(cs[-250:])/250,1)
                idx[iname]=d
                p(f'  {iname}: {cs[-1]:.1f} (30RI{c30:+.2f}%)')
        except Exception as e:p(f'  [WARN] {iname}: {e}')
    
    gate0='UNKNOWN';gate1='UNKNOWN'
    if idx.get('上证指数',{}).get('ma100'):
        sh=idx['上证指数']
        gate0='FAIL' if sh['close']<sh['ma100'] else'PASS'
        p(f'  Gate0: 上证{sh["close"]:.1f} vs MA100({sh["ma100"]:.1f}) -> {gate0}')
    if idx.get('上证指数',{}).get('ma60') and idx.get('上证指数',{}).get('ma250'):
        sh=idx['上证指数']
        c=sh['close'];m6=sh['ma60'];m25=sh['ma250']
        if c>m6 and m6>m25:gate1='80~100%';p(f'  Gate1: MA60={m6:.1f}>MA250={m25:.1f} close={c:.1f} -> {gate1}')
        elif c>m25 and m6<m25:gate1='<=50%';p(f'  Gate1: MA60={m6:.1f}<MA250={m25:.1f} close={c:.1f} -> {gate1}')
        else:gate1='<=20%';p(f'  Gate1: MA60={m6:.1f}<MA250={m25:.1f} close={c:.1f}<MA60 -> {gate1}')
    
    p('')
    p('=== S0.2 RE BANG + ZHANG DIE TING ===')
    from scripts.data_gate import gate
    hot_c=Counter()
    hl=[]
    try:
        hl=api.hot_list('hour')
        if hl:
            for it in hl:
                tags=it.get('concepts',it.get('tag',''))
                if isinstance(tags,str):
                    for t in tags.split(','):
                        t=t.strip()
                        if t:hot_c[t]+=1
                elif isinstance(tags,list):
                    for t in tags:hot_c[str(t).strip()]+=1
            p(f'  RE BANG {len(hl)} ZHI GE GU, {len(hot_c)} GAI NIAN BIAO QIAN')
            p(f'  TOP10:')
            for k,v in hot_c.most_common(10):p(f'    {k}: {v}zhi')
    except Exception as e:p(f'  [WARN]:{e}')
    
    zt=dt=0
    try:
        bs=api.board_summary()
        if bs:zt=bs.get('zt_count',0);dt=bs.get('dt_count',0)
        p(f'  ZT{zt} DT{dt}')
        gate3='WARN' if dt>10 else('PASS' if zt<100 else'WARN')
        p(f'  Gate3: {"KONG HUANG" if dt>10 else ("GUO RE" if zt>100 else "ZHENG CHANG")}')
    except Exception as e:p(f'  [WARN]:{e}')
    
    # ===== S1 SW31 HANG YE =====
    p('')
    p('='*72)
    p('S1: SW31 HANG YE 30RI K XIAN')
    p('='*72)
    sw_data={}
    for code,name in SW31.items():
        try:
            df=PRO.sw_daily(ts_code=code,start_date=START,end_date=TODAY,fields='trade_date,close')
            if df is None or df.empty or len(df)<25:continue
            rows=[float(x['close']) for _,x in df.iterrows()][::-1]
            ph=calc_phases(rows[-30:] if len(rows)>=30 else rows)
            if ph:sw_data[name]=ph
        except Exception:pass
    p(f'  CHENG GONG: {len(sw_data)}/31')
    
    # ===== S2 THS GAI NIAN =====
    p('')
    p('='*72)
    p('S2: THS GAI NIAN 30RI K XIAN')
    p('='*72)
    
    c2n={}
    try:
        import pandas as pd
        df=PRO.ths_index(type_='I')
        if df is not None and not df.empty:
            for _,r in df.iterrows():c2n[str(r['ts_code'])]=str(r['name'])
        p(f'  THS GAI NIAN ZONG SHU: {len(c2n)}')
    except Exception as e:p(f'  [WARN]:{e}')
    
    today_c={}
    try:
        r=gate.ts_ths_daily(trade_date=TODAY)
        if r:
            for row in r:
                code=str(row['ts_code']);pct=float(row.get('pct_change',row.get('pct_chg',0))or 0)
                cl=float(row.get('close',0))
                if code and cl:today_c[code]=round(pct,2)
            p(f'  JIN RI YOU SHU JU: {len(today_c)}/{len(c2n)}')
    except Exception as e:p(f'  [WARN]:{e}')
    
    sel={}
    pairs=[(c,p) for c,p in today_c.items()];pairs.sort(key=lambda x:x[1],reverse=True)
    for c,_ in pairs[:40]:
        n=c2n.get(c,c)
        if n not in sel:sel[n]=c
    for c,_ in pairs[-20:]:
        n=c2n.get(c,c)
        if n not in sel and len(sel)<60:sel[n]=c
    for tn,_ in hot_c.most_common(20):
        if tn in sel:continue
        for c,n in c2n.items():
            if n==tn:sel[tn]=c;break
        if tn not in sel and len(sel)<75:sel[tn]=''
    
    c_data={}
    for name,code in sel.items():
        if not code:continue
        try:
            df=PRO.ths_daily(ts_code=code,start_date=START,end_date=TODAY,fields='trade_date,close')
            if df is None or df.empty or len(df)<25:continue
            rows=[float(x['close']) for _,x in df.iterrows()][::-1]
            ph=calc_phases(rows[-30:] if len(rows)>=30 else rows)
            if ph:c_data[name]=ph
        except Exception:pass
    p(f'  LA QU 30RI K XIAN: {len(c_data)}')
    
    # ===== S3 HANG YE SAN JIE DUAN =====
    p('')
    p('='*72)
    p('S3: SW31 SAN JIE DUAN FEN JIE')
    p('='*72)
    
    persist=[];rot_out=[];rot_in=[];decline=[];other=[]
    for n,d in sw_data.items():
        s1=d['p1'];s2=d['p2'];s3=d['p3']
        if s1>0 and s2>0 and s3>0:persist.append((n,d))
        elif s1>0 and s3<0:rot_out.append((n,d))
        elif s1<=0 and s3>0:rot_in.append((n,d))
        elif s1<0 and s2<0 and s3<0:decline.append((n,d))
        else:other.append((n,d))
    
    p('\n  [CHI XU ZHU XIAN] P1+P2+P3+:')
    if persist:
        persist.sort(key=lambda x:x[1]['c30'],reverse=True)
        for n,d in persist:
            t=style_of(n)
            p(f'    {n}[{t}]: P1{d["p1"]:+.2f}% -> P2{d["p2"]:+.2f}% -> P3{d["p3"]:+.2f}% | 30RI{d["c30"]:+.2f}% | JIN5RI{d["c5"]:+.2f}%')
    else:p('    (WU)')
    
    p('\n  [SHUAI TUI] P1+ P3-:')
    rot_out.sort(key=lambda x:x[1]['p3'])
    for n,d in rot_out:
        t=style_of(n)
        p(f'    {n}[{t}]: P1{d["p1"]:+.2f}% -> P2{d["p2"]:+.2f}% -> P3{d["p3"]:+.2f}% | 30RI{d["c30"]:+.2f}%')
    
    p('\n  [XIN XING] P1<=0 P3+:')
    rot_in.sort(key=lambda x:x[1]['p3'],reverse=True)
    for n,d in rot_in:
        t=style_of(n)
        p(f'    {n}[{t}]: P1{d["p1"]:+.2f}% -> P2{d["p2"]:+.2f}% -> P3{d["p3"]:+.2f}% | 30RI{d["c30"]:+.2f}% | JIN5RI{d["c5"]:+.2f}%')
    
    p('\n  [FEN HUA]:')
    for n,d in other:
        t=style_of(n)
        p(f'    {n}[{t}]: P1{d["p1"]:+.2f}% -> P2{d["p2"]:+.2f}% -> P3{d["p3"]:+.2f}% | 30RI{d["c30"]:+.2f}%')
    
    p('\n  [QUAN XIAN KUI] P1-P2-P3-:')
    decline.sort(key=lambda x:x[1]['c30'])
    for n,d in decline:
        t=style_of(n)
        p(f'    {n}[{t}]: P1{d["p1"]:+.2f}% -> P2{d["p2"]:+.2f}% -> P3{d["p3"]:+.2f}% | 30RI{d["c30"]:+.2f}% | JIN5RI{d["c5"]:+.2f}%')
    
    p('\n  [FENG GE JUN ZHI]:')
    for st,names in [('防御',DEFENSE),('科技',TECH)]:
        items=[(n,d) for n,d in sw_data.items() if n in names]
        if not items:continue
        ap1=sum(d['p1'] for _,d in items)/len(items)
        ap2=sum(d['p2'] for _,d in items)/len(items)
        ap3=sum(d['p3'] for _,d in items)/len(items)
        a30=sum(d['c30'] for _,d in items)/len(items)
        av=sum(d['vol'] for _,d in items)/len(items)
        p(f'    {st}({len(items)}): P1{ap1:+.2f}% -> P2{ap2:+.2f}% -> P3{ap3:+.2f}% | 30RI{a30:+.2f}% | BO{av:.2f}%')
    
    p('\n  [SW31 30RI ZHANG DIE PAI MING]:')
    srank=[(n,d['c30'],d['c5'],style_of(n)) for n,d in sw_data.items()]
    srank.sort(key=lambda x:x[1],reverse=True)
    for i,(n,c30,c5,st) in enumerate(srank,1):
        p(f'    {i:2d}. {n}[{st}]: 30RI{c30:+.2f}% JIN5RI{c5:+.2f}%')
    
    # ===== S4 GAI NIAN SAN JIE DUAN =====
    p('')
    p('='*72)
    p('S4: THS GAI NIAN SAN JIE DUAN')
    p('='*72)
    
    c_persist=[];c_rot_out=[];c_rot_in=[];c_decline=[]
    for n,d in c_data.items():
        s1=d['p1'];s2=d['p2'];s3=d['p3']
        if s1>0 and s2>0 and s3>0:c_persist.append((n,d))
        elif s1>0 and s3<0:c_rot_out.append((n,d))
        elif s1<=0 and s3>0:c_rot_in.append((n,d))
        elif s1<0 and s2<0 and s3<0:c_decline.append((n,d))
    
    p('\n  [GAI NIAN CHI XU] P1+P2+P3+:')
    c_persist.sort(key=lambda x:x[1]['c30'],reverse=True)
    for n,d in c_persist[:15]:
        p(f'    {n}: P1{d["p1"]:+.2f}% -> P2{d["p2"]:+.2f}% -> P3{d["p3"]:+.2f}% | 30RI{d["c30"]:+.2f}% JIN5RI{d["c5"]:+.2f}%')
    
    p('\n  [GAI NIAN SHUAI TUI] P1+ P3-:')
    c_rot_out.sort(key=lambda x:x[1]['p3'])
    for n,d in c_rot_out[:8]:
        p(f'    {n}: P1{d["p1"]:+.2f}% -> P2{d["p2"]:+.2f}% -> P3{d["p3"]:+.2f}% | 30RI{d["c30"]:+.2f}%')
    
    p('\n  [GAI NIAN XIN XING] P3+:')
    c_rot_in.sort(key=lambda x:x[1]['p3'],reverse=True)
    for n,d in c_rot_in[:8]:
        p(f'    {n}: P1{d["p1"]:+.2f}% -> P2{d["p2"]:+.2f}% -> P3{d["p3"]:+.2f}% | 30RI{d["c30"]:+.2f}%')
    
    p('\n  [GAI NIAN QUAN XIAN KUI] P1-P2-P3-:')
    c_decline.sort(key=lambda x:x[1]['c30'])
    for n,d in c_decline[:15]:
        p(f'    {n}: P1{d["p1"]:+.2f}% -> P2{d["p2"]:+.2f}% -> P3{d["p3"]:+.2f}% | 30RI{d["c30"]:+.2f}%')
    
    # ===== S5 RE BANG JIAO CHA =====
    p('')
    p('='*72)
    p('S5: RE BANG VS SHI JI ZOU SHI')
    p('='*72)
    for tag,cnt in hot_c.most_common(10):
        found=None
        for n,d in c_data.items():
            if tag in n or n in tag:found=(n,d['c30'],d['c5']);break
        if found:
            flag='XIAN JING!' if found[1]<-15 else('GUAN ZHU' if found[1]>0 else'ZHONG XING')
            p(f'    {tag}({cnt}zhi): 30RI{found[1]:+.2f}% JIN5RI{found[2]:+.2f}% -> {flag}')
        else:p(f'    {tag}({cnt}zhi): WU 30RI K XIAN')
    
    # ===== S6 HANG YE VS GAI NIAN =====
    p('')
    p('='*72)
    p('S6: HANG YE VS GAI NIAN DUI BI')
    p('='*72)
    hw=[(n,d['c30']) for n,d in sw_data.items()];hw.sort(key=lambda x:x[1],reverse=True)
    cw=[(n,d['c30']) for n,d in c_data.items()];cw.sort(key=lambda x:x[1],reverse=True)
    p(f'  HANG YE TOP5: {[(n,f"{v:+.2f}%") for n,v in hw[:5]]}')
    p(f'  GAI NIAN TOP5: {[(n,f"{v:+.2f}%") for n,v in cw[:5]]}')
    p(f'  HANG YE BOT5: {[(n,f"{v:+.2f}%") for n,v in hw[-5:]]}')
    p(f'  GAI NIAN BOT5: {[(n,f"{v:+.2f}%") for n,v in cw[-5:]]}')
    h_set={n for n,_ in hw[:5]};c_set={n for n,_ in cw[:5]}
    overlap=len(h_set&c_set)
    p(f'  TOP5 CHONG DIE: {overlap}/5 -> {"GAO DU YI ZHI" if overlap>=2 else "XU GUAN ZHU"}')
    
    # ===== S7 ZONG HE JIE LUN =====
    p('')
    p('='*72)
    p('S7: ZONG HE JIE LUN')
    p('='*72)
    p(f'')
    p(f'  Gate0: {gate0} {"YI PIAO FOU JUE" if gate0=="FAIL" else ""}')
    p(f'  Gate1: {gate1}')
    p(f'  Gate3: ZT{zt}/DT{dt} {"KONG HUANG" if dt>10 else "GUO RE" if zt>100 else "ZHENG CHANG"}')
    h_main=[n for n,_ in persist];h_down=[n for n,_ in decline]
    h_new=[n for n,_ in rot_in];h_old=[n for n,_ in rot_out]
    c_main=[n for n,_ in c_persist[:5]];c_down=[n for n,_ in c_decline[:5]]
    p(f'')
    p(f'  HANG YE ZHU XIAN: {h_main}')
    p(f'  HANG YE QUAN XIAN KUI: {h_down}')
    if h_new:p(f'  HANG YE XIN XING: {h_new}')
    if h_old:p(f'  HANG YE SHUAI TUI: {h_old}')
    p(f'  GAI NIAN ZHU XIAN: {c_main}')
    p(f'  GAI NIAN QUAN XIAN KUI: {c_down}')
    p(f'')
    p(f'  SHU JU YUAN: A=Tushare SW31({len(sw_data)}/31) B=THS({len(c_data)} concept) C=REBANG{len(hl) if hl else 0}zhi D=TENGXUN 4idx')
    p(f'  SI YUAN JIAO CHA: direction consensus => high reliability')
    p(f'')
    if gate0=='FAIL':
        p(f'  CANG WEI JIAN YI: <=10%')
        p(f'  TUI JIAN: fang yu xiao fei (bank+food+transport) ge <=10%')
        p(f'  HUI BI: ke ji quan xian (communication/electronic/semiconductor/computer/equipment)')
    else:
        p(f'  CANG WEI JIAN YI: an Gate1/2/3 jin yi bu pan duan')
    
    with open(REPORT,'w',encoding='utf-8') as f:
        f.write('\n'.join(out))
    p('')
    p(f'[BAO GAO YI BAO CUN: {REPORT}]')
    p(f'[ZONG HANG SHU: {len(out)}]')
