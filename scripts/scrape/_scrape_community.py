"""用 Playwright 抓取 SkillHub 页面上的 @ClawHub 社区技能名称和slug"""
import asyncio, json, io, sys
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://www.iwencai.com/skillhub', wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(3000)

        # Close any popups
        try:
            close_btns = page.locator('[class*="close"], [class*="Close"], .modal-close, .dialog-close')
            count = await close_btns.count()
            if count > 0:
                await close_btns.first.click()
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        # Get full page text
        text = await page.evaluate('() => document.body.innerText')
        print("=== PAGE TEXT (6000-15000) ===")
        print(text[6000:15000])
        print("\n=== PAGE TEXT (15000-20000) ===")
        print(text[15000:])

        # Try to find community/clawhub section
        print("\n=== Looking for ClawHub/community section ===")
        # Get all text elements that might be skill cards
        cards = await page.evaluate('''() => {
            const result = [];
            document.querySelectorAll('[class*="card"], [class*="Card"], [class*="skill"], [class*="Skill"], [class*="item"], [class*="Item"]').forEach(el => {
                const text = el.textContent.trim();
                if (text.length > 5 && text.length < 300) {
                    result.push({text: text.substring(0, 150), tag: el.tagName, cls: el.className?.substring(0, 60)});
                }
            });
            return result;
        }''')

        for card in cards:
            if any(kw in card['text'].lower() for kw in ['clawhub', '社区', 'community', '波动', 'factor', 'momentum', '量化', '机器学习', '策略', '指标']):
                print(card)

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
