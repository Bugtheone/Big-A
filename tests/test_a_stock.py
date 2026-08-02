"""
a-stock-data 部署验证脚本
测试核心依赖和基础数据源连接
"""
import sys
import importlib

# 测试所有依赖包
packages = {
    "mootdx": "mootdx",
    "requests": "requests",
    "pandas": "pandas",
    "stockstats": "stockstats",
}

print("=" * 50)
print("[依赖包验证]")
print("=" * 50)
all_ok = True
for name, module_name in packages.items():
    try:
        mod = importlib.import_module(module_name)
        version = getattr(mod, "__version__", "unknown")
        print(f"  [OK] {name:<15} {version}")
    except ImportError as e:
        print(f"  [FAIL] {name:<15} import failed: {e}")
        all_ok = False

print()
print("=" * 50)
if all_ok:
    print("[RESULT] All dependencies installed successfully!")
else:
    print("[RESULT] Some dependencies have issues, please check")
print("=" * 50)

# 测试 data source 连接（使用腾讯财经/新浪等 HTTP 源，不需要国内IP）
print()
print("=" * 50)
print("[Data Source Test - Tencent Finance]")
print("=" * 50)

try:
    import requests
    # 测试腾讯财经接口（获取平安银行 K 线）
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz000001,day,,,10"
    s = requests.Session()
    s.trust_env = False  # 绕过企业代理
    resp = s.get(url, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("data"):
            print("  [OK] Tencent Finance K-line API connected")
            # 显示最近几天的数据
            kline = data["data"]["sz000001"]
            if "day" in kline:
                print(f"  [DATA] Recent {len(kline['day'])} trading days available")
                for row in kline["day"][-3:]:
                    print(f"     {row}")
        else:
            print("  [WARN] Tencent Finance returned empty data")
    else:
        print(f"  [FAIL] HTTP {resp.status_code}")
except Exception as e:
    print(f"  [FAIL] Connection error: {e}")

print()
print("=" * 50)
print("[Usage Reference]")
print("=" * 50)
print("""
1. With AI assistant (CodeBuddy/Cursor/Claude Code):
   Inject SKILL.md as context for the AI assistant.

2. Direct Python usage:
   from mootdx.quotes import Quotes
   client = Quotes.factory(market='std')
   df = client.bars(symbol='000001', frequency=9, offset=10)
   print(df)

3. See SKILL.md for all 43 endpoints available.
""")
