"""爬取 skillhub 全部技能 slug + 批量安装。"""
import os, sys, json, subprocess, re

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


if __name__ == '__main__':
    CLI = os.path.join(os.path.expanduser("~"), ".iwencai-skillhub", "aime_skillhub_cli.py")
    SKILLS_DIR = os.path.join(project_root, "skills")
    USER_DATA = os.path.join(project_root, "data", "iwencai_browser_profile")
    
    print("=" * 50)
    print("步骤1: Playwright 有头浏览器提取全部技能")
    print("=" * 50)
    
    from playwright.sync_api import sync_playwright
    
    slugs = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA,
            headless=False,
            channel="chrome",
        )
        page = ctx.new_page()
    
        page.goto("https://www.iwencai.com/skillhub", timeout=30000, wait_until="networkidle")
    
        # 等 React 渲染
        print("等待页面渲染 (8s) ...")
        page.wait_for_timeout(8000)
    
        # 滚屏加载全部内容
        print("滚屏加载全部技能卡片 ...")
        prev_count = 0
        for i in range(10):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            # 检查是否有新内容
            links_now = page.query_selector_all("a")
            if len(links_now) == prev_count and i > 2:
                print(f"  第{i+1}次无新链接，可能已加载完毕")
                break
            prev_count = len(links_now)
    
        # 提取所有链接
        all_links = page.query_selector_all("a")
        print(f"页面共 {len(all_links)} 个链接")
    
        for link in all_links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip() if link.inner_text() else ""
        
            # 匹配 skillhub slug 模式
            m = re.search(r'/skillhub/([a-zA-Z0-9_-]+)', href)
            if m:
                s = m.group(1)
                if s not in slugs and s not in ("skill", "search", "market", "myself"):
                    slugs.append(s)
                    print(f"  [{len(slugs)}] {s}  -- {text[:50]}")
    
        ctx.close()
    
    print(f"\n共提取 {len(slugs)} 个技能")
    
    if not slugs:
        print("提取失败，请确认浏览器中 skillhub 页面是否正常显示技能列表")
        sys.exit(1)
    
    # 保存
    slug_file = os.path.join(project_root, "data", "skillhub_slugs.json")
    os.makedirs(os.path.dirname(slug_file), exist_ok=True)
    with open(slug_file, "w", encoding="utf-8") as f:
        json.dump({"slugs": slugs, "total": len(slugs)}, f, ensure_ascii=False, indent=2)
    
    # ── 步骤2: 批量安装 ──
    print(f"\n{'='*50}")
    print(f"步骤2: 批量安装 {len(slugs)} 个技能 -> {SKILLS_DIR}")
    print("=" * 50)
    
    already = set(os.listdir(SKILLS_DIR)) if os.path.isdir(SKILLS_DIR) else set()
    success, failed, skipped = [], [], []
    
    for i, slug in enumerate(slugs):
        if slug in already:
            print(f"[{i+1}/{len(slugs)}] {slug} - 已存在，跳过")
            skipped.append(slug)
            continue
    
        print(f"[{i+1}/{len(slugs)}] {slug} ...", end=" ", flush=True)
        try:
            result = subprocess.run(
                ["python", CLI, "--dir", SKILLS_DIR, "install", slug, "--force"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 or "Installed" in result.stdout:
                print("OK")
                success.append(slug)
            else:
                print(f"FAIL (rc={result.returncode})")
                err = result.stderr.strip()
                if err:
                    for line in err.splitlines()[:3]:
                        print(f"      {line}")
                failed.append(slug)
        except subprocess.TimeoutExpired:
            print("TIMEOUT")
            failed.append(slug)
        except Exception as e:
            print(f"ERROR: {e}")
            failed.append(slug)
    
    print(f"\nOK: {len(success)} | SKIP: {len(skipped)} | FAIL: {len(failed)} | TOTAL: {len(slugs)}")
    if success:
        print(f"成功: {success}")
    if failed:
        print(f"失败: {failed}")
    
    with open(os.path.join(project_root, "data", "skillhub_install_log.json"), "w", encoding="utf-8") as f:
        json.dump({"success": success, "failed": failed, "skipped": skipped}, f, ensure_ascii=False, indent=2)

