"""用 Playwright 点击社区技能安装按钮，捕获 slug 和安装命令"""
import asyncio, json, io, sys
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Intercept ALL requests to capture API calls
        all_requests = []
        async def on_request(request):
            url = request.url
            if any(kw in url for kw in ['skill', 'install', 'download', 'clawhub', 'asg']):
                all_requests.append({'method': request.method, 'url': url, 'headers': dict(request.headers)})

        async def on_response(response):
            url = response.url
            if any(kw in url for kw in ['skill', 'install', 'download', 'clawhub']):
                try:
                    body = await response.text()
                    all_requests.append({'type': 'response', 'status': response.status, 'url': url, 'body': body[:2000]})
                except Exception:
                    pass

        page.on('request', on_request)
        page.on('response', on_response)

        await page.goto('https://www.iwencai.com/skillhub', wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(5000)

        # Close popup
        try:
            for sel in ['button:has-text("关闭")', '[class*="close"]', '[class*="Close"]', '.modal button']:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    break
        except Exception:
            pass

        # Find all community card install buttons
        cards_data = await page.evaluate('''() => {
            const cards = document.querySelectorAll('.community-card, [class*="community-card"]');
            return Array.from(cards).map((card, i) => {
                const text = card.textContent.trim().substring(0, 150);
                // Find install button
                const btns = card.querySelectorAll('button, a, [class*="install"], [class*="btn"]');
                const btnInfo = Array.from(btns).map(b => ({
                    text: b.textContent.trim(),
                    cls: b.className,
                    href: b.getAttribute('href') || '',
                    data: Object.fromEntries(Array.from(b.attributes).map(a => [a.name, a.value]))
                }));
                return {index: i, text, buttons: btnInfo};
            });
        }''')

        # Find first card with an install button
        target_idx = None
        for cd in cards_data:
            for btn in cd['buttons']:
                if '安装' in btn['text'] or 'install' in btn['cls'].lower():
                    target_idx = cd['index']
                    print(f"Found install button on card [{cd['index']}]: {cd['text'][:80]}")
                    print(f"  Button: {json.dumps(btn, ensure_ascii=False)}")
                    break
            if target_idx is not None:
                break

        if target_idx is not None:
            # Click the install button
            community_cards = page.locator('.community-card, [class*="community-card"]')
            target_card = community_cards.nth(target_idx)
            install_btn = target_card.locator('button, a').first
            
            # Watch for new tabs/popups
            async def on_popup(popup):
                await popup.wait_for_load_state()
                url = popup.url
                print(f"\nPOPUP URL: {url}")
                await popup.close()
            
            page.on('popup', on_popup)

            print(f"\nClicking install button on card [{target_idx}]...")
            await install_btn.click()
            await page.wait_for_timeout(5000)

            # Print captured network requests
            print(f"\n=== Captured requests ({len(all_requests)}) ===")
            for r in all_requests[-20:]:  # Last 20
                if isinstance(r.get('body'), str):
                    print(f"  [{r.get('type','req')}] {r.get('method','')} {r['url'][:120]} body={r.get('body','')[:300]}")
                else:
                    print(f"  [req] {r.get('method','')} {r['url'][:120]}")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
