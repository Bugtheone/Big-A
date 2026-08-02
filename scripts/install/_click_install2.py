"""用 Playwright 点击社区技能安装按钮，捕获 slug — 写入文件避免编码问题"""
import asyncio, json, io, sys, os
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    log_lines = []

    def log(msg):
        log_lines.append(str(msg))
        print(msg, flush=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Collect all requests
        api_calls = []

        async def on_request(request):
            url = request.url
            if 'skill' in url.lower() or 'clawhub' in url.lower() or 'install' in url.lower():
                try:
                    post_data = request.post_data
                except Exception:
                    post_data = None
                api_calls.append({
                    'type': 'request',
                    'method': request.method,
                    'url': url,
                    'post_data': str(post_data)[:500]
                })

        async def on_response(response):
            url = response.url
            if 'skill' in url.lower() or 'clawhub' in url.lower():
                try:
                    body = await response.text()
                    api_calls.append({
                        'type': 'response',
                        'status': response.status,
                        'url': url,
                        'body': body[:3000]
                    })
                except Exception:
                    pass

        page.on('request', on_request)
        page.on('response', on_response)

        await page.goto('https://www.iwencai.com/skillhub', wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(5000)

        # Close popup
        try:
            await page.click('button:has-text("关闭")', timeout=3000)
            await page.wait_for_timeout(1000)
        except Exception:
            try:
                await page.click('[class*="close"]', timeout=2000)
                await page.wait_for_timeout(1000)
            except Exception:
                pass

        # Get community cards with their data
        cards_raw = await page.evaluate('''() => {
            const cards = document.querySelectorAll('.community-card, [class*="community-card"]');
            return Array.from(cards).map((card, i) => {
                const text = card.querySelector('[class*="title"], h3, h4, [class*="name"]')?.textContent?.trim() || card.textContent.trim().substring(0, 60);
                const btns = card.querySelectorAll('button, a');
                const btnTexts = Array.from(btns).map(b => b.textContent.trim()).filter(t => t);
                // Get ALL data attributes
                const dataAttrs = {};
                for (const attr of card.attributes) {
                    if (attr.name.startsWith('data-')) {
                        dataAttrs[attr.name] = attr.value;
                    }
                }
                return {index: i, title: text, buttons: btnTexts, dataAttrs};
            });
        }''')

        log(f"\nFound {len(cards_raw)} community cards")
        for cd in cards_raw[:10]:
            log(f"  [{cd['index']}] title={cd['title'][:50]} btns={cd['buttons']} data={json.dumps(cd['dataAttrs'], ensure_ascii=False)[:150]}")

        # Try clicking install on first card
        for cd in cards_raw:
            if '安装' in (cd.get('buttons') or []):
                first_install_idx = cd['index']
                break
        else:
            first_install_idx = 0

        log(f"\n=== Clicking install on card {first_install_idx} ===")
        
        community_cards = page.locator('.community-card, [class*="community-card"]')
        target = community_cards.nth(first_install_idx)
        
        # Find install button
        install_btn = target.locator('button, a').first
        if await install_btn.count() > 0:
            await install_btn.click()
            await page.wait_for_timeout(5000)
            log("Clicked. Waiting for popup...")

        # Check for dialog/modal
        dialogs = await page.evaluate('''() => {
            const modals = document.querySelectorAll('[class*="modal"], [class*="dialog"], [class*="popup"], [class*="Popup"], [class*="drawer"]');
            return Array.from(modals).map(m => ({cls: m.className, text: m.textContent.trim().substring(0, 300), visible: m.offsetParent !== null}));
        }''')
        log(f"\nDialogs after click: {json.dumps(dialogs[:5], ensure_ascii=False)[:500]}")

        # Get page URL (check if redirected)
        log(f"\nCurrent URL: {page.url}")

        log(f"\n=== All API calls ({len(api_calls)}) ===")
        for ac in api_calls[-30:]:
            if ac['type'] == 'response':
                log(f"  RESP {ac['status']} {ac['url'][:120]}")
                log(f"    body[:300]: {ac['body'][:300]}")
            else:
                log(f"  REQ {ac['method']} {ac['url'][:120]}")
                if ac.get('post_data'):
                    log(f"    data: {ac['post_data'][:300]}")

        await browser.close()

    # Write log to file
    with open('click_install_log.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))
    print(f"\nLog saved to click_install_log.txt ({len(log_lines)} lines)")

if __name__ == '__main__':
    asyncio.run(main())
