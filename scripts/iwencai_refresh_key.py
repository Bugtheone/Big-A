#!/usr/bin/env python3
"""
iwencai SkillHub API Key 自动刷新脚本

策略：Playwright persistent_context（浏览器状态自动持久化到磁盘）
- 首次：打开浏览器 → 手动登录 → 自动进入技能页 → 提取 API Key → 保存
- 后续：恢复会话（无头模式）→ 自动提取 Key（零人工）
- 过期：会话过期 → 打开浏览器 → 登录一次 → 再次全自动

用法：
    python scripts/iwencai_refresh_key.py          # 自动刷新（先无头，失败则启动浏览器）
    python scripts/iwencai_refresh_key.py --reset  # 清除会话，重新登录
    python scripts/iwencai_refresh_key.py --check  # 仅检查 Key 是否有效
"""
from __future__ import annotations

import json
import os
import sys
import re
import logging
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── 路径 ──────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

PROFILE_DIR = os.path.join(PROJECT_ROOT, "data", "iwencai_browser_profile")
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config", "iwencai_config.json")
os.makedirs(PROFILE_DIR, exist_ok=True)

SKILLHUB_URL = "https://www.iwencai.com/skillhub"

# 技能名列表（按优先级尝试）
SKILL_NAMES = [
    "announcement-search", "report-search", "news-search",
    "公告搜索", "研报搜索", "新闻搜索",
]

# API Key 正则
_KEY_RE = re.compile(r'sk-proj-01-[A-Za-z0-9_-]{30,60}')


# ═══════════════════════════════════════════════════════════════
#  页面交互
# ═══════════════════════════════════════════════════════════════

def check_logged_in(page) -> bool:
    """检查 skillhub 是否已登录。"""
    try:
        body = page.locator("body").inner_text()[:1000]
        # 已登录：没有"登录"按钮
        has_login_btn = "\u767b\u5f55" in body  # 登录
        # 已登录：有用户头像/名称等
        has_user = bool(page.evaluate("""
            () => document.querySelectorAll(
                '[class*=avatar], [class*=username], [class*=nickname], '
                + '[class*=user-info], [class*=profile]'
            ).length
        """))
        return not has_login_btn or has_user > 0
    except Exception:
        return False


def extract_api_key_from_page(page) -> str | None:
    """从当前页面提取 sk-proj-01-* 格式的 API Key。"""
    try:
        # 策略1: body 文本
        body = page.locator("body").inner_text()
        m = _KEY_RE.search(body)
        if m:
            return m.group(0)

        # 策略2: input 元素的 value
        inputs = page.evaluate("""
            () => {
                const keys = [];
                document.querySelectorAll('input, textarea, pre, code').forEach(el => {
                    const v = el.value || el.textContent || '';
                    const m = v.match(/sk-proj-01-[A-Za-z0-9_-]{30,60}/);
                    if (m) keys.push(m[0]);
                });
                return keys;
            }
        """)
        if inputs:
            return inputs[0]

        # 策略3: 所有 div/span 文本
        texts = page.evaluate("""
            () => {
                const keys = [];
                const all = document.querySelectorAll('div, span, p');
                for (const el of all) {
                    if (el.children.length === 0) {
                        const t = el.textContent || '';
                        const m = t.match(/sk-proj-01-[A-Za-z0-9_-]{30,60}/);
                        if (m) keys.push(m[0]);
                    }
                }
                return keys;
            }
        """)
        if texts:
            return texts[0]

        return None
    except Exception:
        return None


def click_api_key_tab(page) -> bool:
    """点击 'Agent 用户' 或 'CLI 用户' 标签页，这些页面直接显示 API Key。"""
    tab_names = ["Agent", "CLI", "API", "Key", "SDK", "接入"]
    try:
        btns = page.evaluate("""
            () => {
                const all = document.querySelectorAll('button, a, span, div[class*=tab], [role=tab]');
                return Array.from(all).slice(0, 30).map(el => ({
                    text: (el.textContent || '').trim().substring(0, 30),
                    tag: el.tagName,
                }));
            }
        """)
        for btn in btns:
            text_lower = btn["text"].lower()
            for name in tab_names:
                if name.lower() in text_lower:
                    logger.info(f"点击标签: {btn['text']}")
                    page.locator(f"text={btn['text']}").first.click()
                    page.wait_for_timeout(2000)
                    key = extract_api_key_from_page(page)
                    if key:
                        return True
                    # 也尝试点击"复制"按钮
                    copy_btn = page.locator("text=复制").first
                    if copy_btn.count() > 0:
                        copy_btn.click()
                        page.wait_for_timeout(1000)
                        key = extract_api_key_from_page(page)
                        if key:
                            return True
        return False
    except Exception as e:
        logger.debug(f"标签页点击失败: {e}")
        return False


def find_and_click_skill(page) -> bool:
    """在 skillhub 首页找到并点击任意已安装技能卡片。"""
    for skill_name in SKILL_NAMES:
        try:
            # 方式1: eval 全局搜索 + click
            clicked = page.evaluate(f"""
                () => {{
                    const all = document.querySelectorAll('*');
                    for (const el of all) {{
                        // 找文本包含技能名且可点击的元素
                        if (el.children.length <= 3 && el.textContent.includes('{skill_name}')) {{
                            // 向上找到可点击容器
                            let clickable = el;
                            while (clickable && clickable !== document.body) {{
                                const tag = clickable.tagName.toLowerCase();
                                const cls = (clickable.className || '').toLowerCase();
                                if (tag === 'a' || tag === 'button' ||
                                    cls.includes('card') || cls.includes('item') ||
                                    cls.includes('skill') || clickable.onclick) {{
                                    clickable.click();
                                    return true;
                                }}
                                clickable = clickable.parentElement;
                            }}
                            el.click();
                            return true;
                        }}
                    }}
                    return false;
                }}
            """)
            if clicked:
                page.wait_for_timeout(2000)
                # 检查是否打开了详情（页面出现 API key 或弹窗）
                if extract_api_key_from_page(page):
                    return True
                # 即使没找到 key，也可能是打开了详情弹窗
                if page.evaluate("""
                    () => document.querySelectorAll(
                        '[class*=modal], [class*=dialog], [class*=drawer], [class*=detail], [class*=overlay]'
                    ).length > 0
                """):
                    return True

        except Exception as e:
            logger.debug(f"点击 {skill_name} 失败: {e}")

    # 方式2: 尝试通过 skills square API 获取 UUID 后直接构造 URL
    try:
        skill_uuids = page.evaluate("""
            async () => {
                try {
                    const resp = await fetch('/gateway/market/api/v1/skills/square?current=1&size=10');
                    const data = await resp.json();
                    const records = data?.data?.records || [];
                    return records.map(r => ({
                        uuid: r.skill_uuid,
                        name: r.name,
                        slug: r.slug,
                    }));
                } catch(e) {
                    return [];
                }
            }
        """)
        for skill in skill_uuids:
            if skill.get("uuid"):
                page.goto(
                    f"{SKILLHUB_URL}/skill/{skill['uuid']}",
                    wait_until="networkidle", timeout=10000
                )
                page.wait_for_timeout(2000)
                if extract_api_key_from_page(page):
                    return True
    except Exception:
        pass

    return False


def extract_and_save_key(page) -> bool:
    """从页面提取 Key 并保存到配置文件。"""
    api_key = extract_api_key_from_page(page)
    if not api_key:
        # 等 3 秒再试一次（弹窗可能还在加载）
        page.wait_for_timeout(3000)
        api_key = extract_api_key_from_page(page)

    if not api_key:
        logger.warning("未在页面中找到 API Key")
        return False

    logger.info(f"找到 API Key: {api_key[:30]}...")

    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)

    config["IWENCAI_API_KEY"] = api_key
    config["base_url"] = "https://openapi.iwencai.com"
    config["last_refreshed"] = datetime.now().isoformat()

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    try:
        subprocess.run(
            ["setx", "IWENCAI_API_KEY", api_key],
            capture_output=True, timeout=5
        )
    except Exception:
        pass

    logger.info("API Key 已保存")
    return True


# ═══════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════

def open_browser_and_refresh(reset: bool = False) -> bool:
    """有头模式：打开浏览器 → 等用户登录 → 提取 Key。"""
    from playwright.sync_api import sync_playwright

    if reset:
        import shutil
        if os.path.exists(PROFILE_DIR):
            try:
                shutil.rmtree(PROFILE_DIR)
            except Exception:
                pass
        os.makedirs(PROFILE_DIR, exist_ok=True)
        logger.info("已清除旧浏览器会话")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = context.pages[0] if context.pages else context.new_page()

        # ── 检查是否已登录 ──
        page.goto(SKILLHUB_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        if not check_logged_in(page):
            logger.info("=" * 50)
            logger.info("请在打开的浏览器中登录 skillhub")
            logger.info("支持：手机号+短信 / 账号密码 / 扫码")
            logger.info("登录后脚本自动继续……")
            logger.info("=" * 50)

            for i in range(180):  # 6 分钟超时
                page.wait_for_timeout(2000)
                page.goto(SKILLHUB_URL, wait_until="networkidle", timeout=15000)
                page.wait_for_timeout(1000)
                if check_logged_in(page):
                    logger.info("检测到登录成功")
                    break
                if (i + 1) % 30 == 0:
                    logger.info(f"等待登录……({(i+1)*2}s)")
            else:
                logger.error("登录超时")
                context.close()
                return False

        # ── 打开技能详情提取 Key ──
        page.goto(SKILLHUB_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        # 优先尝试标签页方式（Agent用户/CLI用户直接显示Key）
        success = click_api_key_tab(page) or find_and_click_skill(page)
        if not success:
            # 让用户手动点击，60秒窗口
            logger.info("请手动点击任意技能卡片或标签页，脚本会在60秒内自动提取 Key")
            for _ in range(30):
                page.wait_for_timeout(2000)
                key = extract_api_key_from_page(page)
                if key:
                    success = True
                    break

        if success:
            extract_and_save_key(page)
        else:
            # 最后一搏：用户可能已经复制了 key，尝试从剪贴板获取
            logger.warning("未能自动提取 Key，请手动写入 config/iwencai_config.json")

        result = verify_saved_key()
        context.close()
        return result


def refresh_key_from_saved_session() -> bool:
    """无头模式：恢复已保存的浏览器会话，提取 Key。"""
    from playwright.sync_api import sync_playwright

    # 检查是否有已保存的 profile
    if not os.path.exists(PROFILE_DIR) or not os.listdir(PROFILE_DIR):
        logger.info("没有已保存的浏览器会话")
        return False

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=True,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = context.pages[0] if context.pages else context.new_page()

        page.goto(SKILLHUB_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        if not check_logged_in(page):
            logger.info("会话已过期")
            context.close()
            return False

        logger.info("会话有效，自动提取……")
        page.wait_for_timeout(2000)
        success = click_api_key_tab(page) or find_and_click_skill(page)
        if success:
            extract_and_save_key(page)

        context.close()
        return verify_saved_key()


def verify_saved_key() -> bool:
    """验证配置文件中的 Key 是否有效（用独立实例，不受全局单例干扰）。"""
    try:
        from scripts.iwencai_openapi import IwencaiOpenAPI
        api = IwencaiOpenAPI()  # 独立实例，从 config/env 重新读取
        ok = api.health_check(auto_refresh=False)
        if ok:
            logger.info("API Key 验证通过")
        return ok
    except Exception as e:
        logger.error(f"验证失败: {e}")
        return False


def auto_refresh_or_raise() -> bool:
    """统一入口：先无头，失败则启动浏览器。"""
    if refresh_key_from_saved_session():
        return True
    logger.info("无头刷新失败，启动浏览器……")
    return open_browser_and_refresh(reset=False)


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="iwencai SkillHub API Key 自动刷新")
    parser.add_argument("--reset", action="store_true", help="清除会话重新登录")
    parser.add_argument("--check", action="store_true", help="仅检查 Key 有效性")
    parser.add_argument("--auto", action="store_true",
                        help="先无头后浏览器（默认行为）")
    parser.add_argument("--login", action="store_true",
                        help="强制打开浏览器登录")
    args = parser.parse_args()

    if args.check:
        ok = verify_saved_key()
        logger.info("状态: %s", "有效" if ok else "失效/未配置")
        sys.exit(0 if ok else 1)

    if args.login:
        ok = open_browser_and_refresh(reset=args.reset)
        sys.exit(0 if ok else 1)

    if args.auto or True:  # 默认行为
        if refresh_key_from_saved_session():
            logger.info("自动刷新成功")
            sys.exit(0)
        logger.info("无头刷新失败，启动浏览器……")

    ok = open_browser_and_refresh(reset=args.reset)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
