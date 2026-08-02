"""人形机器人产业链研报检索 — iwencai + Tushare + 腾讯行情版"""
import io, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
from datetime import datetime

# ---- 0. 交易时段 ----
from scripts.market_api import api

if __name__ == '__main__':
    ts = api.trading_status()
    print(f"数据时效: {ts['data_freshness']} | {ts['session_cn']} | 交易日={'是' if ts['is_trading_day'] else '否'}")
    
    # ---- 0.5. iwencai 研报检索（pywencai + cookie）----
    print("\n" + "=" * 60)
    print("  iwencai 研报检索（丝杠 & 减速器）")
    print("=" * 60)
    try:
        from scripts.iwencai_cookie import get_iwencai
        iwc = get_iwencai()
    
        # 搜研报
        print("\n  [研报] 人形机器人 丝杠 减速器")
        df_rpt = iwc.search_report("人形机器人 丝杠 减速器")
        if not df_rpt.empty:
            rpt_cols = [c for c in ['title', 'author', 'rating', 'publish_time', 'summary']
                        if c in df_rpt.columns]
            print(f"  找到 {len(df_rpt)} 篇研报")
            for _, row in df_rpt.head(8).iterrows():
                title = row.get('title', '')
                author = row.get('author', '')
                rating = row.get('rating', '')
                pub_time = row.get('publish_time', '')
                print(f"    [{pub_time}] {title}")
                print(f"      {author} · 评级: {rating}")
        else:
            print("  未找到研报")
    
        # 搜个股研报
        for stock_name in ["绿的谐波", "五洲新春", "双环传动"]:
            df_s = iwc.search_report(f"{stock_name} 研报")
            if not df_s.empty and 'title' in df_s.columns:
                latest = df_s.iloc[0]
                print(f"\n  [{stock_name}] {latest.get('title', '')}")
                print(f"    {latest.get('author', '')} · {latest.get('publish_time', '')}")
    except Exception as e:
        print(f"  iwencai 检索失败: {e}")
    
    # ---- 1. 核心个股行情（腾讯直连）----
    print("\n核心个股实时行情（腾讯qt.gtimg.cn）")
    print("-" * 50)
    
    s = requests.Session()
    s.trust_env = False
    
    stocks = {
        "绿的谐波": "sh688017", "双环传动": "sz002472",
        "五洲新春": "sh603667", "北特科技": "sh603009",
        "恒立液压": "sh601100", "汇川技术": "sz300124",
        "拓斯达": "sz300607", "埃斯顿": "sz002747",
        "秦川机床": "sz000837",
    }
    codes_str = ",".join(stocks.values())
    try:
        url = f"https://qt.gtimg.cn/q={codes_str}"
        resp = s.get(url, timeout=10)
        resp.encoding = "gbk"
        lines = resp.text.strip().split("\n")
        stock_data = {}
        for line in lines:
            if "~" not in line:
                continue
            # 解析腾讯行情数据
            # v_sh688017="1~绿的谐波~688017~116.50~..."
            # 字段: 0=市场,1=名称,2=代码,3=现价,4=昨收,5=今开,...,32=涨跌幅,33=最高,34=最低,...39=PE
            clean = line.split('"')[1] if '"' in line else line
            f = clean.split("~")
            if len(f) < 40:
                continue
            name = f[1]
            code = f[2]
            price = f[3]
            pre_close = f[4]
            change_pct = f[32] if len(f) > 32 else "0"
            pe = f[39] if len(f) > 39 else "-"
            high = f[33] if len(f) > 33 else "-"
            low = f[34] if len(f) > 34 else "-"
            vol = f[6] if len(f) > 6 else "-"
            amount = f[37] if len(f) > 37 else "-"
            market_cap = f[45] if len(f) > 45 else "-"
            stock_data[code] = {
                "name": name, "price": price, "pre_close": pre_close,
                "change_pct": change_pct, "pe": pe, "high": high, "low": low,
                "amount": amount, "market_cap": market_cap,
            }
    
        # 按涨跌幅排序输出
        sorted_stocks = sorted(stock_data.items(), key=lambda x: float(x[1]["change_pct"]), reverse=True)
        for code, d in sorted_stocks:
            pct = float(d["change_pct"])
            arrow = "↑" if pct > 0 else ("↓" if pct < 0 else "→")
            print(f"  {d['name']:<8} {d['price']:>8}  {pct:>+7.2f}% {arrow}  PE={d['pe']:<6}  市值≈{d['market_cap']}")
    except Exception as e:
        print(f"  行情获取失败: {e}")
    
    # ---- 2. Tushare 基本面数据 ----
    print("\n核心个股基本面（Tushare）")
    print("-" * 50)
    try:
        from scripts.tushare_api import get_pro
        pro = get_pro()
        ts_codes = ["688017.SH", "002472.SZ", "603667.SH", "603009.SH",
                    "601100.SH", "300124.SZ", "300607.SZ", "002747.SZ", "000837.SZ"]
    
        # 日线
        df_daily = pro.daily(ts_code=",".join(ts_codes), start_date="20260701", end_date="20260724")
        if df_daily is not None and len(df_daily) > 0:
            print("  日线数据获取成功，最近数据:")
            for _, row in df_daily.sort_values("trade_date", ascending=False).head(5).iterrows():
                print(f"    {row['ts_code']} {row['trade_date']} close={row['close']} change={row.get('pct_chg','?')}%")
        else:
            print("  日线无数据")
    
        # 股票基本信息
        df_basic = pro.stock_basic(ts_code=",".join(ts_codes), fields="ts_code,name,industry,market,list_date")
        if df_basic is not None and len(df_basic) > 0:
            print("\n  个股基本信息:")
            for _, row in df_basic.iterrows():
                print(f"    {row['ts_code']} {row['name']:<8}  行业: {row.get('industry','?')}  上市: {row.get('list_date','?')}")
            
    except Exception as e:
        print(f"  Tushare获取失败: {e}")
    
    # ---- 3. 东财行业板块热度 ----
    print("\n人形机器人相关板块热度（东财）")
    print("-" * 50)
    try:
        from scripts.market_api import api as mkt
        # 获取概念板块排名，找人形机器人相关
        from scripts.eastmoney_api import get_eastmoney
        em = get_eastmoney()
    
        # 用概念板块 clist 接口
        import time
        time.sleep(0.5)
        s2 = requests.Session()
        s2.trust_env = False
    
        concept_url = (
            "https://push2.eastmoney.com/api/qt/clist/get?"
            "fid=f3&po=1&np=1&fltt=2&invt=2&"
            "fs=m:90+t:3&pz=200&fields=f2,f3,f4,f12,f14,f20"
        )
        r = s2.get(concept_url, timeout=15)
        data = r.json()
        items = data.get("data", {}).get("diff", [])
    
        # 过滤人形机器人相关概念
        robot_keywords = ["人形", "机器人", "减速器", "丝杠", "工业母机", "自动化", "机器视觉", "传感器", "电机", "稀土永磁", "磁材"]
        robot_sectors = []
        for item in items:
            name = item.get("f14", "")
            if any(kw in name for kw in robot_keywords):
                pct = item.get("f3", 0)
                robot_sectors.append((name, pct))
        robot_sectors.sort(key=lambda x: x[1], reverse=True)
    
        for name, pct in robot_sectors:
            print(f"  {name:<20} {pct:>+8.2f}%")
    
        if not robot_sectors:
            print("  (当前时段东财接口可能无数据)")
    except Exception as e:
        print(f"  板块数据获取失败: {e}")
    
    print("\n检索完成")

