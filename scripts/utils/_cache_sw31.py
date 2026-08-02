"""S1: 收集SW31数据缓存 (供后续分析使用)"""
import sys,os,io,json,time

if __name__ == '__main__':
    try:sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
    except Exception: pass

    BASE=r'C:\Users\PC-One\Desktop\整理后\股票相关\零散临时\1112345'
    os.chdir(BASE)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tushare_api import get_pro
    PRO=get_pro()

    TODAY='20260731'; START='20260401'
    CACHE='_sw31_cache.json'

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

    sw_all={}
    ok=0
    for code,name in SW31.items():
        try:
            df=PRO.sw_daily(ts_code=code,start_date=START,end_date=TODAY,fields='trade_date,close')
            if df is not None and not df.empty:
                rows=[(str(x['trade_date']),float(x['close'])) for _,x in df.iterrows()]
                rows.sort(key=lambda x:x[0])
                sw_all[name]={'dates':[r[0] for r in rows],'closes':[r[1] for r in rows]}
                ok+=1
                print(f'  [{ok}/31] {name}: {len(rows)} rows', flush=True)
            else:
                print(f'  [{ok}/31] {name}: EMPTY', flush=True)
            time.sleep(1.3)
        except Exception as e:
            print(f'  [{ok}/31] {name}: ERROR {e}', flush=True)
            time.sleep(1.0)

    with open(CACHE,'w',encoding='utf-8') as f:
        json.dump(sw_all,f,ensure_ascii=False,indent=2)
    print(f'DONE: {ok}/31 saved to {CACHE}', flush=True)
