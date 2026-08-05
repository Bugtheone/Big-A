# -*- coding: utf-8 -*-
"""盘中增强数据工具（2026-08-05 P0/P1/P2 落地）：
  ① 分时确认（回踩买点"缩量企稳"判断）
  ② 港美股 AI 映射（英伟达/台积电/博通/AMD/恒科 → 预判 A股半导体链）
  ③ 盘口封单强度（涨停股买一封单量）
  ④ 人气榜舆情（东财人气榜，热股监测）

模块级函数供 strategy_signal.py 复用（回踩买点自动确认）：
  minute_check(session, code) / global_ai(session) / seal_strength(session, code)

用法:
  python scripts/tools/intraday_enhance.py                # 全量输出
  python scripts/tools/intraday_enhance.py --code 000977  # 单股分时+盘口
"""
import sys, os, argparse
from datetime import datetime

def _rt():
    """真实时间（腾讯 CDN 权威，禁止沿用旧时间戳）。"""
    try:
        from scripts.tools.real_time import get_real_time
        return datetime.strptime(get_real_time()["used"], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return _rt()

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

# 回踩买点重点股（分时确认对象）
_WATCH = [("000977", "浪潮信息"), ("603019", "中科曙光"), ("603501", "韦尔股份"),
          ("688525", "佰维存储"), ("688041", "海光信息"), ("003032", "传智教育")]
# 港美股 AI 映射
_GLOBAL = [("usNVDA", "英伟达"), ("usTSM", "台积电"), ("usAVGO", "博通"),
           ("usAMD", "AMD"), ("hkHSTECH", "恒生科技")]


def _out(*a):
    print(*a, flush=True)


def minute_check(S, code):
    """腾讯分时确认：返回 {price, vol_ratio(最后5分钟量/前30分均量比), pts}。
    缩量企稳 = vol_ratio < 0.8；放量 = vol_ratio > 1.2。"""
    pref = ("sh" if code.startswith(("6", "9")) else "sz") + code
    try:
        r = S.get("https://web.ifzq.gtimg.cn/appstock/app/minute/query",
                  params={"code": pref}, timeout=8)
        d = r.json()["data"][pref]["data"]["data"]
        if len(d) < 5:
            return None
        vols = []
        last_price = 0.0
        prev_vol = 0.0
        for i, row in enumerate(d):
            parts = str(row).split()
            if len(parts) >= 3:
                last_price = float(parts[1])
                if i > 0:
                    vols.append(max(float(parts[2]) - prev_vol, 0))
                prev_vol = float(parts[2])
        if not vols:
            return None
        last5 = sum(vols[-5:]) / 5
        prev30 = sum(vols[-30:-5]) / 25 if len(vols) > 30 else last5
        ratio = last5 / prev30 if prev30 > 0 else 1
        return {"price": last_price, "vol_ratio": round(ratio, 2), "pts": len(d)}
    except Exception:
        return None


def global_ai(S):
    """港美股 AI 映射：返回 {名称: {price, chg}}，及四巨头均值。"""
    out = {}
    for code, nm in _GLOBAL:
        try:
            r = S.get(f"https://qt.gtimg.cn/q={code}", timeout=8)
            r.encoding = "gbk"
            f = r.text.split('"')[1].split("~")
            if len(f) > 5 and float(f[4]):
                out[nm] = {"price": float(f[3]),
                           "chg": round((float(f[3]) - float(f[4])) / float(f[4]) * 100, 2)}
        except Exception:
            continue
    ai4 = [v["chg"] for k, v in out.items() if k != "恒生科技"]
    out["_ai4_avg"] = round(sum(ai4) / len(ai4), 2) if ai4 else None
    return out


def seal_strength(S, code):
    """盘口封单强度：返回 {price, chg, buy1_vol(买一量手), sell1_vol}。"""
    pref = ("sh" if code.startswith(("6", "9")) else "sz") + code
    try:
        r = S.get(f"https://qt.gtimg.cn/q={pref}", timeout=8)
        r.encoding = "gbk"
        f = r.text.split('"')[1].split("~")
        if len(f) > 32:
            return {"price": float(f[3]), "chg": float(f[32]),
                    "buy1_vol": int(f[8]) if f[8] else 0,
                    "sell1_vol": int(f[18]) if f[18] else 0}
    except Exception:
        pass
    return None


def hot_top():
    """东财人气榜 TOP5（舆情热股）。"""
    try:
        from scripts.market_api import api
        return (api.hot_rank(top=5) or [])
    except Exception:
        return []


def a50_check(S):
    """富时A50期货（新浪）：返回 {price, prev_close, chg}——A股隔夜/盘前方向预判。"""
    try:
        r = S.get("https://hq.sinajs.cn/list=hf_CHA50CFD", timeout=6,
                  headers={"Referer": "https://finance.sina.com.cn/"})
        r.encoding = "gbk"
        f = r.text.split('"')[1].split(",")
        if len(f) > 6 and float(f[5]):
            price = float(f[0])
            prev = float(f[5])
            return {"price": price, "prev_close": prev,
                    "chg": round((price - prev) / prev * 100, 2)}
    except Exception:
        pass
    return None


def money_rate(S):
    """资金面：国债逆回购利率（GC001 沪 / R-001 深），高利率=资金紧张。"""
    out = {}
    mapping = {"sh204001": "GC001", "sz131810": "R-001"}
    for code, nm in mapping.items():
        try:
            r = S.get(f"https://qt.gtimg.cn/q={code}", timeout=6)
            r.encoding = "gbk"
            f = r.text.split('"')[1].split("~")
            if len(f) > 3 and f[3]:
                out[nm] = {"rate": float(f[3])}
        except Exception:
            continue
    return out


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", help="单股代码（分时+盘口）")
    args = ap.parse_args()

    import requests
    S = requests.Session()
    S.trust_env = False
    S.headers.update({"User-Agent": "Mozilla/5.0"})
    now = _rt()
    _out(f"=== 盘中增强 {now:%H:%M:%S} ===")
    lines = []  # 收集输出供写文件

    def emit(t=""):
        _out(t)
        lines.append(t)

    if args.code:
        c = args.code
        nm = next((n for cc, n in _WATCH if cc == c), c)
        emit(f"\n[个股 {nm}({c})]")
        m = minute_check(S, c)
        s = seal_strength(S, c)
        if m:
            emit(f"  分时: 价{m['price']} 量比{m['vol_ratio']}（<0.8=缩量企稳, >1.2=放量）")
        if s:
            emit(f"  盘口: 价{s['price']} {s['chg']:+.2f}% 买一封单{s['buy1_vol']}手")
    else:
        emit("\n[① 分时确认·回踩买点]")
        for c, n in _WATCH:
            m = minute_check(S, c)
            if m:
                st = "缩量企稳✅" if m["vol_ratio"] < 0.8 else ("放量⚠️" if m["vol_ratio"] > 1.2 else "平稳")
                emit(f"  {n}: 价{m['price']} 量比{m['vol_ratio']} {st}")

        emit("\n[② 港美股 AI 映射]")
        g = global_ai(S)
        for nm, d in g.items():
            if nm == "_ai4_avg":
                emit(f"  → 美股AI四巨头均值 {d:+.2f}%（映射A股半导体链方向）")
            else:
                emit(f"  {nm}: {d['price']} {d['chg']:+.2f}%")

        emit("\n[③ 盘口封单·连板监控]")
        for c, n in _WATCH:
            s = seal_strength(S, c)
            if s and s["chg"] >= 9.9:
                emit(f"  {n}: 涨停 {s['price']} 封单 {s['buy1_vol']}手" + ("（巨单封死）" if s["buy1_vol"] > 50000 else ""))
            elif s:
                emit(f"  {n}: {s['chg']:+.2f}% 买一 {s['buy1_vol']}手")

        emit("\n[④ 人气榜·舆情热股]")
        try:
            hot = hot_top()
            if hot:
                emit("  " + ", ".join(f"{x.get('name')}({x.get('code')})" for x in hot))
        except Exception as e:
            emit(f"  失败: {e}")

        emit("\n[⑤ 富时A50·盘前预判]")
        a50 = a50_check(S)
        if a50:
            st = "偏多🟢" if a50["chg"] > 0.5 else ("偏空🔴" if a50["chg"] < -0.5 else "中性")
            emit(f"  富时A50: {a50['price']} {a50['chg']:+.2f}%（昨结{a50['prev_close']}）{st}")

        emit("\n[⑥ 资金面·国债逆回购]")
        m = money_rate(S)
        if m:
            gc = m.get("GC001", {}).get("rate")
            r_ = m.get("R-001", {}).get("rate")
            emit(f"  GC001 {gc}% · R-001 {r_}%" + (" ⚠️利率偏高(资金紧)" if gc and gc > 4 else ""))

    # 写文件（供快照/对话读取）
    dstr = now.strftime("%Y-%m-%d")
    outdir = os.path.join(_PROJECT_ROOT, "reports", "daily", dstr)
    os.makedirs(outdir, exist_ok=True)
    out_path = os.path.join(outdir, f"intraday_enhance_{now.strftime('%H%M')}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# 盘中增强 — {now.strftime('%Y-%m-%d %H:%M')}\n\n" + "\n".join(lines) + "\n")
    emit(f"\n[已写入] {os.path.relpath(out_path, _PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
