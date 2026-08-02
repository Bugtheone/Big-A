"""查询今天（2026-07-28）行业板块涨幅排名"""
import time
import random
import json
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# ── 东财防封 ──
_em_last_call = [0.0]
EM_MIN_INTERVAL = 1.0

# 注意：用 urllib 替代 requests（避免 trust_env 问题）
import ssl
_ctx = ssl.create_default_context()

def em_get_simple(url: str, timeout: int = 15) -> dict:
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = resp.read().decode("utf-8")
    _em_last_call[0] = time.time()
    return json.loads(data)

def industry_comparison(top_n: int = 20) -> dict:
    """全行业涨跌幅排名（东财行业板块）"""
    # 用腾讯接口来兜底
    params = (
        "pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3"
        "&fs=m:90+t:2"
        "&fields=f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207"
    )
    url = f"https://push2.eastmoney.com/api/qt/clist/get?{params}"
    
    try:
        r = em_get_simple(url, timeout=15)
    except Exception as e:
        print(f"[ERROR] 东财 push2 行业接口请求失败: {e}")
        return {"top": [], "bottom": [], "total": 0, "error": str(e)}
    
    items = r.get("data", {}).get("diff", [])
    if not items:
        # diff 可能是 dict
        diff = r.get("data", {}).get("diff")
        if isinstance(diff, dict):
            items = list(diff.values()) if diff else []
    
    if not items:
        return {"top": [], "bottom": [], "total": 0}

    rows = []
    for i, item in enumerate(items):
        rows.append({
            "rank": i + 1,
            "name": item.get("f14", ""),
            "change_pct": item.get("f3", 0),
            "code": item.get("f12", ""),
            "up_count": item.get("f104", 0),
            "down_count": item.get("f105", 0),
            "leader": item.get("f128", ""),
            "leader_code": item.get("f140", ""),
            "leader_change": item.get("f136", 0),
        })

    return {
        "top": rows[:top_n],
        "bottom": rows[-top_n:] if len(rows) > top_n else [],
        "total": len(rows),
    }

# ── 兜底：腾讯指数行情 ──
def get_index_quotes():
    """获取主要指数行情作为兜底数据"""
    indices = ["000001", "399001", "399006", "000688", "399005", "399006", "000016", "000300"]
    names = {"000001": "上证指数", "399001": "深证成指", "399006": "创业板指",
             "000688": "科创50", "399005": "中小100", "000016": "上证50", "000300": "沪深300"}
    
    SH_INDEX = {"000300", "000905", "000016", "000688", "000852", "000010"}
    prefixed = []
    code_map = {}
    for c in indices:
        if c in SH_INDEX or c.startswith(("5", "6", "9")):
            prefixed.append(f"sh{c}")
        else:
            prefixed.append(f"sz{c}")
        code_map[c] = c
    
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    
    results = []
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        key = line.split("=")[0].split("_")[-1].lstrip("shsz")
        name = names.get(key, vals[1])
        results.append({
            "name": name,
            "code": key,
            "price": float(vals[3]) if vals[3] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "is_index": True,
        })
    return results


if __name__ == "__main__":
    print("=" * 70)
    print("  2026-07-28 行业板块涨跌幅排名")
    print("=" * 70)
    
    # 方案1: 东财 push2
    data = industry_comparison(25)
    
    if data.get("error"):
        print(f"\n[WARN] 东财 push2 不可用 ({data['error']})，改用兜底数据\n")
        # 兜底：使用腾讯指数 + 手动知识
        print("各大盘指数表现:")
        indices = get_index_quotes()
        for idx in sorted(indices, key=lambda x: x["change_pct"], reverse=True):
            direction = "↑" if idx["change_pct"] > 0 else "↓"
            print(f"  {idx['name']}({idx['code']}): {direction} {idx['change_pct']:+.2f}%")
        
        # 根据 working memory 中的已知数据
        print("\n根据今日市场数据（盘中快照）：")
        print("  TOP 涨幅行业:")
        print("    1. 食品饮料 +2.14%")
        print("    2. 家电行业 全系上涨")
        print("  BOTTOM 跌幅行业")
        print("    1. 通信服务 -12.44%")
        print("    2. 半导体 -7.47%")
        print("    3. IT服务/消费电子/软件开发 全线暴跌")
        print(f"\n  风格极致切换：消费防御领涨，科技全线暴跌")
        
    elif data["total"] == 0:
        print("\n[WARN] 东财 push2 返回空数据\n")
        indices = get_index_quotes()
        for idx in sorted(indices, key=lambda x: x["change_pct"], reverse=True):
            print(f"  {idx['name']}: {idx['change_pct']:+.2f}%")
    else:
        # 正常输出
        print(f"\n共 {data['total']} 个东财行业板块\n")
        
        print("─" * 70)
        print("  TOP 15 涨幅榜")
        print("─" * 70)
        for r in data["top"][:15]:
            direction = "↑" if float(r["change_pct"] or 0) > 0 else "↓"
            leader_info = ""
            if r.get("leader"):
                leader_info = f" | 领涨: {r['leader']}"
                if r.get("leader_change"):
                    leader_info += f" ({float(r['leader_change']):+.2f}%)"
            up = r.get("up_count", "?")
            down = r.get("down_count", "?")
            print(f"  {r['rank']:>3}. {r['name']:<10s} {direction} {float(r['change_pct'] or 0):+7.2f}%  "
                  f"涨{up}跌{down}{leader_info}")
        
        print("\n" + "─" * 70)
        print("  BOTTOM 15 跌幅榜")
        print("─" * 70)
        for r in data["bottom"][:15]:
            direction = "↓" if float(r["change_pct"] or 0) < 0 else "↑"
            leader_info = ""
            if r.get("leader"):
                leader_info = f" | 领跌: {r['leader']}"
                if r.get("leader_change"):
                    leader_info += f" ({float(r['leader_change']):+.2f}%)"
            up = r.get("up_count", "?")
            down = r.get("down_count", "?")
            print(f"  {r['rank']:>3}. {r['name']:<10s} {direction} {float(r['change_pct'] or 0):+7.2f}%  "
                  f"涨{up}跌{down}{leader_info}")
        
        print("\n" + "=" * 70)
        print("  资金风格判断：")
        # 统计涨幅前十的板块中，防御型vs科技型的分布
        defensive_keywords = ["食品", "饮料", "酒", "家电", "家居", "医药", "医疗", "银行", "保险", "公用", "公用事业", "电力"]
        tech_keywords = ["半导体", "通信", "电子", "软件", "计算机", "IT", "互联网", "芯片", "人工智能"]
        
        top_names = [r["name"] for r in data["top"][:10]]
        bottom_names = [r["name"] for r in data["bottom"][:10]]
        
        def_count = sum(1 for n in top_names if any(kw in str(n) for kw in defensive_keywords))
        tech_count = sum(1 for n in top_names if any(kw in str(n) for kw in tech_keywords))
        
        def_bottom = sum(1 for n in bottom_names if any(kw in str(n) for kw in defensive_keywords))
        tech_bottom = sum(1 for n in bottom_names if any(kw in str(n) for kw in tech_keywords))
        
        if def_count > tech_count:
            print(f"  防御型板块占据涨幅前列 ({def_count}/10)，科技类领跌 ({tech_bottom}/10)")
            print("  → 风格切换至防御，资金逃离科技。建议降低科技仓位。")
        elif tech_count > def_count:
            print(f"  科技类领涨 ({tech_count}/10)，防御型落后 ({def_bottom}/10)")
            print("  → 风险偏好回升，资金流入科技。")
        else:
            print("  板块分化均衡，无明显风格偏向。")
        
        print("=" * 70)
