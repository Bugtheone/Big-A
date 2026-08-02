"""诊断第三轮: 所有可用的热点/资金流替代端点"""
import sys, os, time, json, io
sys.path.insert(0, r'c:\Users\PC-One\Desktop\整理后\股票相关\零散临时\1112345')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from scripts.market_api import api

result = {}

def test(name, fn, *args, **kwargs):
    """通用测试包装器"""
    global result
    t0 = time.time()
    try:
        data = fn(*args, **kwargs)
        t1 = time.time()
        if data is None:
            result[name] = "NULL: returned None"
            print("  [NULL] %s — returned None" % name)
            return
        if isinstance(data, list):
            n = len(data)
            if n == 0:
                result[name] = "EMPTY: list length 0, %.2fs" % (t1-t0)
                print("  [WARN] %s — empty list, %.2fs" % (name, t1-t0))
            else:
                # sample first item
                first = data[0]
                keys = list(first.keys()) if isinstance(first, dict) else []
                ks = ','.join(keys[:5])
                result[name] = "OK: %d items, keys=[%s...], %.2fs" % (n, ks, t1-t0)
                print("  [OK] %s — %d items, keys=[%s...], %.2fs" % (name, n, ks, t1-t0))
                # print first 2 items for inspection
                for i, item in enumerate(data[:2]):
                    print("    [%d] %s" % (i, str(item)[:200]))
        elif isinstance(data, dict):
            keys = list(data.keys())
            ks = ','.join(keys[:5])
            n = len(data)
            result[name] = "OK: dict %d keys [%s...], %.2fs" % (n, ks, t1-t0)
            print("  [OK] %s — dict %d keys [%s...], %.2fs" % (name, n, ks, t1-t0))
            # sample values
            for k in keys[:3]:
                v = data[k]
                if isinstance(v, list):
                    print("    [%s] list(len=%d)" % (k, len(v)))
                elif isinstance(v, dict):
                    print("    [%s] dict(keys=%s)" % (k, list(v.keys())[:5]))
                else:
                    print("    [%s] = %s" % (k, str(v)[:100]))
        else:
            result[name] = "OK: type=%s, %.2fs" % (type(data).__name__, t1-t0)
            print("  [OK] %s — type=%s, %.2fs" % (name, type(data).__name__, t1-t0))
    except Exception as e:
        result[name] = "FAIL: %s" % str(e)[:200]
        print("  [FAIL] %s — %s" % (name, str(e)[:200]))

# ===== 热点类 =====
if __name__ == "__main__":
    print("="*60)
    print("A. 热点/人气/热榜 可用端点")
    print("="*60)

    test("hot_rank", api.hot_rank, 10)           # 同花顺人气榜
    test("hot_list(hour)", api.hot_list, "hour")  # 同花顺热榜(小时)
    test("hot_list(day)", api.hot_list, "day")    # 同花顺热榜(日)
    test("hot_reason", api.hot_reason)            # 同花顺强势股归因
    #test("hot_concept", api.hot_concept, "BK0736")  # 概念板块热度 (需要概念代码)

    # ===== 资金流类 =====
    print("\n" + "="*60)
    print("B. 资金流 可用端点")
    print("="*60)

    test("fund_flow_120d", api.fund_flow_120d, "000001")       # 东财120日(已确认OK)
    test("ts_moneyflow_today", api.ts_moneyflow_today, "000001.SZ")  # Tushare当日资金流
    test("board_fund_flow(行业)", api.board_fund_flow, "行业", "今日", 10)  # 板块资金流
    test("north_flow", api.north_flow, 5)                     # 北向资金
    test("north_flow_minute", api.north_flow_minute)          # 北向资金分钟级

    # ===== 涨跌停/情绪类(替代热点) =====
    print("\n" + "="*60)
    print("C. 涨跌停/情绪类(盘中替代热点)")
    print("="*60)

    test("zt_pool", api.zt_pool)                    # 涨停池
    test("dt_pool", api.dt_pool)                    # 跌停池
    test("zb_pool", api.zb_pool)                    # 炸板池
    test("board_summary", api.board_summary)        # 打板看板(含重点监控池+日内异动)
    test("telegraph", api.telegraph, 10)            # 财联社电报(盘中消息)

    # ===== 汇总 =====
    print("\n" + "="*60)
    print("FINAL DIAGNOSIS:")
    print("="*60)
    for k, v in result.items():
        if v.startswith("OK"):
            mark = "[PASS]"
        elif v.startswith("EMPTY") or v.startswith("NULL"):
            mark = "[WARN]"
        else:
            mark = "[FAIL]"
        print("  %s %s: %s" % (mark, k, v))

    print("\n" + "="*60)
    print("SOLUTION MAP:")
    print("  同花顺热榜 -> hot_rank (人气榜) 或 board_summary (涨停池)")
    print("  东财资金流 -> fund_flow_120d (120日OK) + ts_moneyflow_today (Tushare) + north_flow (北向)")
    print("  东财分钟流 -> fund_flow_120d (日级替代) + board_fund_flow (板块资金)")
    print("="*60)
