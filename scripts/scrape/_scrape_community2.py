"""从 SkillHub 页面提取 @ClawHub 社区技能的确切安装 slug"""
import asyncio, json, io, sys
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://www.iwencai.com/skillhub', wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(3000)

        # Close popups
        try:
            btn = page.locator('button:has-text("关闭"), [class*="close"]').first
            if await btn.count() > 0:
                await btn.click()
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        # Scroll to load all community cards
        for _ in range(5):
            await page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(1500)

        # Get all community cards with their data
        skills_raw = await page.evaluate('''() => {
            const cards = document.querySelectorAll('.community-card, [class*="community-card"]');
            const result = [];
            cards.forEach(card => {
                const titleEl = card.querySelector('[class*="title"], h3, h4, [class*="name"]');
                const authorEl = card.querySelector('[class*="author"]');
                const installBtn = card.querySelector('[class*="install"], button, a[href*="install"]');
                const text = card.textContent.trim();
                const dataAttrs = {};
                for (const attr of card.attributes) {
                    dataAttrs[attr.name] = attr.value;
                }
                result.push({
                    text: text.substring(0, 200),
                    title: titleEl?.textContent?.trim() || '',
                    className: card.className,
                    dataAttrs: dataAttrs
                });
            });
            return result;
        }''')

        for i, sk in enumerate(skills_raw):
            print(f"[{i}] cls={sk['className'][:60]}")
            print(f"    text={sk['text'][:120]}")
            print(f"    attrs={json.dumps(sk['dataAttrs'], ensure_ascii=False)[:200]}")
            print()

        # Also look for install links anywhere on page
        print("\n=== All install-related links/buttons ===")
        links = await page.evaluate('''() => {
            const result = [];
            document.querySelectorAll('a, button').forEach(el => {
                const href = el.getAttribute('href') || '';
                const text = el.textContent.trim().substring(0, 80);
                const cls = el.className?.substring(0, 60) || '';
                if (href.includes('install') || href.includes('skill') || href.includes('clawhub') || text.includes('安装')) {
                    result.push({tag: el.tagName, text, href: href.substring(0, 150), cls});
                }
            });
            return result;
        }''')
        for l in links:
            print(json.dumps(l, ensure_ascii=False))

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
