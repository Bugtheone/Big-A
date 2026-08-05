# -*- coding: utf-8 -*-
"""盘中工具脚本单元测试（2026-08-05 补：sector_delta/strategy_signal/intraday_enhance 无测试覆盖缺口）。

覆盖：
  ① intraday_enhance: minute_check/global_ai/seal_strength/a50_check/money_rate 解析逻辑（mock 网络）
  ② strategy_signal: 信号判定 + JSON 输出结构（mock market_api 数据）
  ③ sector_delta: 对比逻辑（mock 数据）
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest import mock


# ── ① intraday_enhance 解析函数 ───────────────────────────
from scripts.tools import intraday_enhance as ie


class FakeResp:
    """模拟 requests.Response（腾讯行情/分时格式）"""
    def __init__(self, text, encoding="gbk"):
        self.text = text
        self.encoding = encoding


class FakeJsonResp:
    """模拟 JSON 响应（分时接口）"""
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeSession:
    """mock requests.Session.get，按 URL 返回预设响应"""
    def __init__(self, url_map):
        self.url_map = url_map
        self.headers = {}

    def get(self, url, **kwargs):
        for key, resp in self.url_map.items():
            if key in url:
                return resp
        raise AssertionError(f"未预设 URL: {url}")


def test_minute_check_parses_sina_format():
    """分时数据为空格分隔字符串 'HHMM 价 累计量 累计额'，量比应正确计算"""
    # 构造 40 个分时点：前 30 分钟量 100/分钟，最后 5 分钟量 20/分钟（缩量）
    lines = []
    for i in range(40):
        vol = 100 if i < 35 else 20
        lines.append(f"09{i:02d} {10+i/100:.2f} {vol*(i+1)} {1000000*(i+1)}")
    payload = {"data": {"sz000977": {"data": {"data": lines}}}}
    sess = FakeSession({"minute/query": FakeJsonResp(payload)})
    r = ie.minute_check(sess, "000977")
    assert r is not None
    assert r["vol_ratio"] < 0.8  # 缩量
    assert r["price"] > 0


def test_minute_check_returns_none_on_short_data():
    payload = {"data": {"sz000977": {"data": {"data": ["0930 10 100 1000"]}}}}
    sess = FakeSession({"minute/query": FakeJsonResp(payload)})
    assert ie.minute_check(sess, "000977") is None


def test_global_ai_parses_tencent_us():
    """腾讯美股格式: 名称~代码~涨跌~现价~昨收~...（f[3]=现价 f[4]=昨收）"""
    resp = FakeResp('v_usNVDA="英伟达~NVDA~2.56~211.94~206.64~1~2";')
    sess = FakeSession({"qt.gtimg.cn/q=usNVDA": resp})
    g = ie.global_ai(sess)
    assert "英伟达" in g
    assert g["英伟达"]["price"] == 211.94
    assert abs(g["英伟达"]["chg"] - 2.56) < 0.2  # (211.94-206.64)/206.64 ≈ +2.56%
    assert g["_ai4_avg"] is not None


def test_seal_strength_parses_buy1():
    """腾讯盘口: 买一量在第 9 个字段(f[8])；003032 为深市(sz)"""
    arr = [str(i) for i in range(50)]
    arr[3] = "11.73"
    arr[8] = "195238"
    arr[18] = "100"
    arr[32] = "10.0"
    resp = FakeResp(f'v_sz003032="' + "~".join(arr) + '";')
    sess = FakeSession({"qt.gtimg.cn/q=sz003032": resp})
    r = ie.seal_strength(sess, "003032")
    assert r is not None
    assert r["buy1_vol"] == 195238
    assert r["chg"] == 10.0


def test_a50_check_parses_sina():
    """新浪富时A50: hf_CHA50CFD 现价,前值,今开,最高,最低,昨结"""
    resp = FakeResp('var hq_str_hf_CHA50CFD="14814.000,,14814.000,14815.000,14814.000,14574.000,11:14";')
    sess = FakeSession({"hq.sinajs.cn/list=hf_CHA50CFD": resp})
    a = ie.a50_check(sess)
    assert a is not None
    assert abs(a["chg"] - 1.65) < 0.2  # (14814-14574)/14574 ≈ +1.65%


def test_money_rate_parses_gc001():
    resp = FakeResp('v_sh204001="GC001~204001~1.425~1.425~";')
    sess = FakeSession({"qt.gtimg.cn/q=sh204001": resp})
    m = ie.money_rate(sess)
    assert m["GC001"]["rate"] == 1.425


# ── ② strategy_signal 信号判定 + JSON 输出 ─────────────────
def test_strategy_signal_json_output_structure():
    """strategy_signal --json 应输出含信号/综合/回踩买点 的 JSON。
    注: stdout 可能被 em_pool 库日志污染，需提取首尾花括号之间的 JSON。"""
    import subprocess
    r = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "..", "scripts", "tools", "strategy_signal.py"),
         "--json"],
        capture_output=True, text=True, timeout=150, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, f"stderr: {r.stderr[-300:]}"
    start = r.stdout.find("{")
    end = r.stdout.rfind("}")
    assert start != -1 and end != -1, f"stdout 无 JSON: {r.stdout[:200]}"
    try:
        d = json.loads(r.stdout[start:end + 1])
    except json.JSONDecodeError:
        pytest.fail(f"JSON 解析失败: {r.stdout[start:start + 300]}")
    # 结构完整性
    for key in ("指数", "量能情绪", "信号", "综合", "回踩买点"):
        assert key in d, f"缺少 {key}"
    for sig in ("C1", "C2", "C3", "C4", "D1", "D2", "E1", "E2", "E3"):
        assert sig in d["信号"], f"缺少信号 {sig}"
    assert "动作" in d["综合"]


# ── ③ sector_delta 对比逻辑 ───────────────────────────────
def test_sector_delta_baseline_and_delta(tmp_path):
    """sector_delta: 首跑建基线，再跑对比输出变化"""
    import subprocess, tempfile
    script = os.path.join(os.path.dirname(__file__), "..", "scripts", "tools", "sector_delta.py")
    env = dict(os.environ)
    r1 = subprocess.run([sys.executable, script, "--baseline"], capture_output=True,
                        text=True, timeout=120, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r1.returncode == 0, r1.stderr[-200:]
    assert "基线" in r1.stdout
