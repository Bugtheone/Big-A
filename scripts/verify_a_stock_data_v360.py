#!/usr/bin/env python3
"""
a-stock-data V3.6.1 数据源保证门禁（本地可执行，无网络依赖）

对应 AGENTS.md「数据源版本保证（强制）」的机器可查实现，保证 AI agent 对话中
自动调用的一定是 a-stock-data V3.6.1（并覆盖 Tushare.pro / westock-data / 问财 SkillHub）。

保证点：
  G1 双份 SKILL.md 存在且版本 == 3.6.1（用户级 ~/.grok/skills/a-stock-data + 项目级 a-stock-data-main/）
  G2 双份 SKILL.md 内容一致（md5 相同）
  G3 V3.6.1 API 面完整（norm_ticker / tencent_quote(is_stale) / eastmoney_reports(老码抛错) /
     em_get / em_stock_monitor / em_price_anomaly / tdx_client / eastmoney_datacenter /
     board_fund_flow / iwencai_search）
  G4 无 V3.5 及更早接口残留（def baidu_fund_flow_history / import akshare，SKILL.md 与 scripts/ 均查）
  G5 四大数据源技能在位（a-stock-data / tushare-pro / westock-data / 问财三件套）
  G6 本地密钥配置在位（config/*.json；gitignored 不入库，CI 缺失属正常 → INFO 不阻断）

可选 --live：联网冒烟验证真实链路（腾讯行情 + scripts/verify_v360_sources.py 三源验证）。
退出码：0=通过（SKIP/INFO 不阻断）；1=有 FAIL。

用法:
  python scripts/verify_a_stock_data_v360.py          # 本地门禁
  python scripts/verify_a_stock_data_v360.py --live   # 本地门禁 + 联网冒烟
"""
import hashlib
import os
import re
import subprocess
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_USER_SKILL = os.path.expanduser("~/.grok/skills/a-stock-data/SKILL.md")
_PROJ_SKILL = os.path.join(_PROJECT_ROOT, "a-stock-data-main", "SKILL.md")
_EXPECTED_VERSION = "3.6.1"

_IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"

# V3.6.1 关键 API 面（函数定义或标志，必须在 SKILL.md 中出现）
_API_SURFACE = [
    ("def norm_ticker", "ticker 归一化（解析失败抛 ValueError）"),
    ("def tencent_quote", "腾讯行情（带 is_stale 僵尸报价标志）"),
    ("is_stale", "tencent_quote 僵尸报价标志"),
    ("def em_get", "东财统一节流入口（防封）"),
    ("def eastmoney_reports", "东财研报（老码抛 ValueError 不静默空）"),
    ("norm_ticker(code, stock_only=True)", "研报层已接入 norm_ticker 归一化"),
    ("def em_stock_monitor", "重点监控池（V3.6.1 新增）"),
    ("def em_price_anomaly", "日内异动池（V3.6.1 新增）"),
    ("def tdx_client", "mootdx 客户端（规避 BESTIP bug + 验活）"),
    ("def eastmoney_datacenter", "东财数据中心统一查询"),
    ("def board_fund_flow", "板块资金流向（V3.5）"),
    ("def iwencai_search", "问财 NL 语义搜索"),
]

# V3.5 及更早接口残留（定义即违规；changelog 历史说明文字除外，故只查 def/import）
_BANNED_PATTERNS = [
    ("def baidu_fund_flow_history", "V3.1 已删函数仍被定义"),
    ("import akshare", "V3.0 已移除 akshare 依赖"),
    ("from akshare", "V3.0 已移除 akshare 依赖"),
]

# 四大数据源配套技能（项目级 .grok/skills/，已入库）
_COMPANION_SKILLS = [
    "tushare-pro",
    "westock-data",
    "hithink-astock-selector",
    "hithink-finance-query",
    "hithink-market-query",
]

_CONFIG_FILES = ["feishu_config.json", "iwencai_config.json", "proxies.json",
                 "router_config.json", "tushare_config.json"]

_PASS, _FAIL, _SKIP, _INFO = "PASS", "FAIL", "SKIP", "INFO"
_results: list[tuple[str, str, str]] = []  # (check_id, status, message)


def _record(cid: str, status: str, msg: str) -> None:
    _results.append((cid, status, msg))


def _read_skill_version(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^version:\s*(\S+)", line.strip())
                if m:
                    return m.group(1)
    except OSError:
        pass
    return ""


def _md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def _scan_banned(root: str) -> list[str]:
    """在 root 下递归扫描 .py 中的禁用 API 残留，返回违规文件清单。"""
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("_archive", "__pycache__", ".git")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            # 自排除：本检查器必须定义禁用模式字符串，属元代码而非 API 使用
            if fn == "verify_a_stock_data_v360.py":
                continue
            p = os.path.join(dirpath, fn)
            try:
                src = open(p, "r", encoding="utf-8").read()
            except OSError:
                continue
            for pat, _label in _BANNED_PATTERNS:
                if pat in src:
                    hits.append(f"{os.path.relpath(p, _PROJECT_ROOT)}: {pat}")
    return hits


# ==================== 各保证点 ====================

def check_g1_version() -> None:
    proj_v = _read_skill_version(_PROJ_SKILL)
    user_v = _read_skill_version(_USER_SKILL)
    if proj_v != _EXPECTED_VERSION:
        _record("G1", _FAIL, f"项目级 a-stock-data-main/SKILL.md 版本={proj_v or '(无)'}，期望 {_EXPECTED_VERSION}")
        return
    if not os.path.exists(_USER_SKILL):
        if _IN_CI:
            _record("G1", _SKIP, "CI 环境无用户级技能目录（~/.grok/skills），跳过用户级版本校验")
        else:
            _record("G1", _FAIL, f"用户级技能缺失：{_USER_SKILL}（AI agent 无法自动加载）")
        return
    if user_v != _EXPECTED_VERSION:
        _record("G1", _FAIL, f"用户级 SKILL.md 版本={user_v or '(无)'}，期望 {_EXPECTED_VERSION}")
        return
    _record("G1", _PASS, f"双份 SKILL.md 版本均为 {_EXPECTED_VERSION}")


def check_g2_consistency() -> None:
    if not os.path.exists(_USER_SKILL):
        _record("G2", _SKIP, "用户级技能缺失，跳过一致性校验")
        return
    if _md5(_USER_SKILL) == _md5(_PROJ_SKILL):
        _record("G2", _PASS, "双份 SKILL.md md5 一致")
    else:
        _record("G2", _FAIL, "双份 SKILL.md 内容不一致（md5 不同），需同步")


def check_g3_api_surface() -> None:
    if not os.path.exists(_PROJ_SKILL):
        _record("G3", _FAIL, "项目级 SKILL.md 缺失")
        return
    with open(_PROJ_SKILL, "r", encoding="utf-8") as fh:
        src = fh.read()
    missing = [(m, label) for m, label in _API_SURFACE if m not in src]
    if missing:
        detail = "; ".join(f"{m}({label})" for m, label in missing)
        _record("G3", _FAIL, f"V3.6.1 API 面缺失 {len(missing)} 项: {detail}")
    else:
        _record("G3", _PASS, f"V3.6.1 API 面完整（{len(_API_SURFACE)} 项关键函数/标志）")


def check_g4_no_old_api() -> None:
    skill_hits = []
    if os.path.exists(_PROJ_SKILL):
        with open(_PROJ_SKILL, "r", encoding="utf-8") as fh:
            src = fh.read()
        for pat, _label in _BANNED_PATTERNS:
            if pat in src:
                skill_hits.append(f"SKILL.md: {pat}")
    scripts_hits = _scan_banned(os.path.join(_PROJECT_ROOT, "scripts"))
    all_hits = skill_hits + scripts_hits
    if all_hits:
        _record("G4", _FAIL, f"旧 API 残留 {len(all_hits)} 处: {'; '.join(all_hits[:5])}")
    else:
        _record("G4", _PASS, "无 V3.5 及更早接口残留（SKILL.md + scripts/ 均干净）")


def check_g5_skills_in_place() -> None:
    proj_skills_dir = os.path.join(_PROJECT_ROOT, ".grok", "skills")
    missing = []
    for name in _COMPANION_SKILLS:
        if not os.path.exists(os.path.join(proj_skills_dir, name, "SKILL.md")):
            missing.append(f".grok/skills/{name}")
    # a-stock-data 项目级载体为 a-stock-data-main/SKILL.md（已入库），用户级为 ~/.grok/skills
    a_stock_present = (os.path.exists(_USER_SKILL)
                       or os.path.exists(os.path.join(proj_skills_dir, "a-stock-data", "SKILL.md"))
                       or os.path.exists(os.path.join(_PROJECT_ROOT, "a-stock-data-main", "SKILL.md")))
    if not a_stock_present:
        missing.append("a-stock-data（用户级 ~/.grok/skills 或项目级 a-stock-data-main/ 至少一份）")
    if missing:
        _record("G5", _FAIL, "配套技能缺失: " + ", ".join(missing))
        return
    if os.path.exists(_USER_SKILL):
        _record("G5", _PASS, f"四源技能在位（a-stock-data 用户级 + {len(_COMPANION_SKILLS)} 个项目级）")
    else:
        _record("G5", _SKIP, "用户级 a-stock-data 缺失（CI 环境正常），项目级四源技能 + a-stock-data-main/ 在位")


def check_g6_config() -> None:
    cfg_dir = os.path.join(_PROJECT_ROOT, "config")
    present = [f for f in _CONFIG_FILES if os.path.exists(os.path.join(cfg_dir, f))]
    missing = [f for f in _CONFIG_FILES if f not in present]
    if missing:
        note = "（gitignored，CI 缺失属正常，本地需手工配置）" if _IN_CI else "（gitignored，请本机手工配置）"
        _record("G6", _INFO, f"config/ 缺失 {len(missing)} 项: {', '.join(missing)} {note}")
    else:
        _record("G6", _INFO, f"config/ 密钥配置在位（{len(present)} 项）")


# ==================== --live 联网冒烟 ====================

def live_tencent_smoke() -> bool:
    """腾讯行情链路冒烟（a-stock-data 主源，不封 IP）。"""
    sys.path.insert(0, _PROJECT_ROOT)
    try:
        from scripts.market_api import api  # 延迟导入，避免本地门禁依赖重模块

        data = api.stock_realtime(["600519"])
        ok = bool(data) and any(str(k).endswith("600519") for k in data)
        if ok:
            _record("LIVE", _PASS, f"腾讯行情链路 OK: {list(data)[:2]}")
        else:
            _record("LIVE", _FAIL, "api.stock_realtime(['600519']) 返回空")
        return ok
    except Exception as exc:  # 显式捕获，杜绝裸 except
        _record("LIVE", _FAIL, f"腾讯行情链路异常: {exc}")
        return False


def live_three_sources() -> bool:
    """Tushare.pro / westock-data / 问财 SkillHub 三源连通性（复用 verify_v360_sources.py）。"""
    script = os.path.join(_PROJECT_ROOT, "scripts", "verify_v360_sources.py")
    if not os.path.exists(script):
        _record("LIVE", _SKIP, "scripts/verify_v360_sources.py 不存在，跳过三源验证")
        return True
    try:
        r = subprocess.run([sys.executable, script], cwd=_PROJECT_ROOT,
                           timeout=180, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        _record("LIVE", _FAIL, "三源验证超时（180s）")
        return False
    if r.returncode == 0:
        _record("LIVE", _PASS, "Tushare.pro / westock / 问财 三源链路全部通过")
        return True
    tail = "\n".join((r.stdout or "").splitlines()[-15:])
    _record("LIVE", _FAIL, f"三源验证未全通过（exit={r.returncode}）:\n{tail}")
    return False


# ==================== 主流程 ====================

def main() -> int:
    live = "--live" in sys.argv
    check_g1_version()
    check_g2_consistency()
    check_g3_api_surface()
    check_g4_no_old_api()
    check_g5_skills_in_place()
    check_g6_config()

    if live:
        live_tencent_smoke()
        live_three_sources()

    print("=" * 66)
    print("a-stock-data V3.6.1 数据源保证门禁" + ("（含 --live 联网冒烟）" if live else "（本地）"))
    print("=" * 66)
    n_fail = 0
    for cid, status, msg in _results:
        mark = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]", "INFO": "[INFO]"}[status]
        print(f"  {mark} {cid}  {msg}")
        if status == _FAIL:
            n_fail += 1
    summary = f"\n结果: {sum(1 for _, s, _ in _results if s == 'PASS')} PASS / {n_fail} FAIL" \
              f" / {sum(1 for _, s, _ in _results if s == 'SKIP')} SKIP"
    print(summary)
    if n_fail:
        print("✗ 保证门禁未通过，禁止将 a-stock-data 视为 V3.6.1 可用。")
    else:
        print("✓ 保证门禁通过：AI agent 将自动调用 a-stock-data V3.6.1（含 Tushare/westock/问财 路由）。")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
