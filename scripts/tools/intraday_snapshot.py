#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘中快照工具 — 拉取当前市场快照并写入 reports/daily/<日期>/intraday_<HHMM>.md。

用途：盘中定时刷新（调度器/后台任务调用），快速记录：
  指数实时 / 广度 / 成交 / 涨停池 / 行业TOP / 热门题材 / 红利龙头 / 机器人链

用法:
  python scripts/tools/intraday_snapshot.py          # 拉快照并写报告
  python scripts/tools/intraday_snapshot.py --json   # 仅打印 JSON，不写文件

注：Tushare 日线/HKEX 北向收盘后才生成，盘中快照以实时源（腾讯/同花顺/东财/westock）交叉为主。
"""
import io
import json
import os
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from scripts.market_api import api  # noqa: E402
from scripts.eastmoney_info import em_zt_pool  # noqa: E402

_WATCH_INDEX = ["上证指数", "深证成指", "创业板指", "科创50", "上证50", "沪深300", "中证500", "中证1000"]
_DIVIDEND_LEAD = ["601088", "601398", "601939", "600519", "601857", "600900"]
_ROBOT_CHAIN = ["603728", "002896", "300024", "688017", "002472"]
_OBS_POOL = ["300088", "300454", "688222"]  # 观察池（docs/观察池.md：长信科技/深信服/成都先导）


def in_trading_hours(dt: datetime) -> bool:
    """交易时段门控（以本机真实北京时间为准，防调度后端时钟漂移导致的乱触发）。

    周一到周五：9:30–11:30 与 13:00–15:00（含边界）；午休 11:30–13:00 不算。
    节假日以行情为准（脚本无法内置放假表，若休假当天数据为空属正常）。
    """
    if dt.weekday() >= 5:  # 周六周日
        return False
    hm = dt.hour * 60 + dt.minute
    am = 9 * 60 + 30 <= hm <= 11 * 60 + 30
    pm = 13 * 60 <= hm <= 15 * 60
    return am or pm


def _selfcheck_gate() -> int:
    """门控逻辑自测（--check-gate）：断言关键边界时间点。"""
    from datetime import datetime as _dt
    cases = [
        ("2026-08-03 09:29", False),  # 周一开盘前 1 分钟
        ("2026-08-03 09:30", True),   # 开盘
        ("2026-08-03 11:30", True),   # 上午收盘（含边界）
        ("2026-08-03 11:31", False),  # 午休
        ("2026-08-03 12:59", False),  # 午休
        ("2026-08-03 13:00", True),   # 下午开盘
        ("2026-08-03 14:59", True),   # 收盘前
        ("2026-08-03 15:00", True),   # 收盘（含边界）
        ("2026-08-03 15:01", False),  # 收盘后
        ("2026-08-02 10:00", False),  # 周日
        ("2026-08-01 10:00", False),  # 周六
    ]
    ok = True
    for ts, want in cases:
        got = in_trading_hours(_dt.strptime(ts, "%Y-%m-%d %H:%M"))
        mark = "✅" if got == want else "❌"
        if got != want:
            ok = False
        print(f"  {mark} {ts} → {got}（期望 {want}）")
    print(f"\n门控自测: {'全部通过' if ok else '存在失败项'}")
    return 0 if ok else 1


def snapshot() -> dict:
    now = datetime.now()
    snap = {s["name"]: s for s in (api.index_snapshot() or [])}
    b = api.breadth()
    zp = em_zt_pool() or []
    secs = api.sectors(6) or []
    hr = api.hot_reason() or []
    dq = api.stock_realtime(_DIVIDEND_LEAD)
    rq = api.stock_realtime(_ROBOT_CHAIN)
    op = api.stock_realtime(_OBS_POOL)
    return {
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "indices": {n: {"price": snap.get(n, {}).get("price"),
                        "pct": snap.get(n, {}).get("change_pct")} for n in _WATCH_INDEX},
        "turnover_yi": (api.turnover() or {}).get("total_yi"),
        "breadth": {k: b.get(k) for k in ("total", "up", "down", "flat", "up_pct")} if b else None,
        "zt_count": len(zp),
        "sectors_top": [(x.get("name"), x.get("change_pct")) for x in secs],
        "hot_top": [(x.get("name"), str(x.get("reason"))[:26]) for x in hr[:5]],
        "dividend_lead": {it.get("name"): (it.get("price"), it.get("change_pct")) for it in dq.values()},
        "robot_chain": {it.get("name"): (it.get("price"), it.get("change_pct")) for it in rq.values()},
        "obs_pool": {it.get("name"): (it.get("price"), it.get("change_pct")) for it in op.values()},
    }


def render(d: dict) -> str:
    lines = [f"# 盘中快照 — {d['time']}", ""]
    lines.append("## 指数")
    for n in _WATCH_INDEX:
        it = d["indices"].get(n, {})
        if it.get("price") is not None:
            lines.append(f"- {n}: {it['price']} {it['pct']}%")
    lines.append("")
    lines.append(f"## 成交 {d['turnover_yi']}亿 | 广度 {d['breadth']['up_pct']}% "
                 f"(涨{d['breadth']['up']}/跌{d['breadth']['down']}) | 涨停 {d['zt_count']}只")
    lines.append("")
    lines.append("## 行业TOP")
    for n, p in d["sectors_top"]:
        lines.append(f"- {n}: {p}%")
    lines.append("")
    lines.append("## 热门题材")
    for n, r in d["hot_top"]:
        lines.append(f"- {n}: {r}")
    lines.append("")
    lines.append("## 红利龙头 / 机器人链")
    lines.append("- 红利: " + ", ".join(f"{n} {p[1]}%" for n, p in d["dividend_lead"].items()))
    lines.append("- 机器人: " + ", ".join(f"{n} {p[1]}%" for n, p in d["robot_chain"].items()))
    return "\n".join(lines)


def main() -> int:
    if "--check-gate" in sys.argv:
        return _selfcheck_gate()
    now = datetime.now()
    if not in_trading_hours(now) and "--force" not in sys.argv:
        print(f"[SKIP] {now:%Y-%m-%d %H:%M:%S} 非交易时段（9:30-11:30/13:00-15:00），"
              f"不生成盘中快照。需强制生成请加 --force")
        return 0
    d = snapshot()
    if "--json" in sys.argv:
        print(json.dumps(d, ensure_ascii=False))
        return 0
    text = render(d)
    print(text)
    # 写入 reports/daily/<日期>/intraday_<HHMM>.md
    dt = datetime.now()
    outdir = os.path.join(_PROJECT_ROOT, "reports", "daily", dt.strftime("%Y-%m-%d"))
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"intraday_{dt.strftime('%H%M')}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"\n[已写入] {os.path.relpath(out, _PROJECT_ROOT)}")
    # 板块变化对比（对比上一快照，15 分钟调度每轮必跑）
    if "--no-delta" not in sys.argv:
        try:
            import subprocess
            subprocess.run([sys.executable, os.path.join(_PROJECT_ROOT, "scripts", "tools",
                          "sector_delta.py")], timeout=120, cwd=_PROJECT_ROOT)
        except Exception as e:
            print(f"[WARN] 板块变化对比失败: {e}")
    # 策略信号核验（docs/当前策略.md 的 C/D/E 条件清单，15 分钟调度每轮必跑）
    if "--no-delta" not in sys.argv:
        try:
            import subprocess
            subprocess.run([sys.executable, os.path.join(_PROJECT_ROOT, "scripts", "tools",
                          "strategy_signal.py")], timeout=120, cwd=_PROJECT_ROOT)
        except Exception as e:
            print(f"[WARN] 策略信号核验失败: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
