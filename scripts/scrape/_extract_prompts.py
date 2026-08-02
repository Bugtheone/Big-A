"""从 SkillHub 页面的社区技能弹窗中提取安装 Prompt 和 slug
用法：python _extract_prompts.py
输出：data/analysis/extracted_prompts.txt
"""

import asyncio, os, re
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "analysis", "extracted_prompts.txt")

async def main():
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto('https://www.iwencai.com/skillhub', wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(5000)

        # Close popup
        try:
            await page.click('button:has-text("关闭")', timeout=3000)
            await page.wait_for_timeout(1000)
        except Exception:
            pass

        # Get all community cards with their data
        cards = await page.evaluate('''() => {
            const cards = document.querySelectorAll('.community-card, [class*="community-card"]');
            return Array.from(cards).map((card, i) => {
                const titleEl = card.querySelector('[class*="title"], h3, h4, [class*="name"], strong');
                const fullText = card.textContent.trim().substring(0, 200);
                const title = titleEl?.textContent?.trim() || fullText.split('\\n')[0].trim();
                // Extract all data attributes
                const data = {};
                for (const attr of card.attributes) {
                    data[attr.name] = attr.value;
                }
                return {index: i, title, fullText, data};
            });
        }''')

        log_lines = [f"Total community cards: {len(cards)}"]

        # Click each card's install button and extract prompt from modal
        extracted = []
        for cd in cards[:20]:  # Process first 20
            try:
                # Use index to find card
                community_cards = page.locator('.community-card, [class*="community-card"]')
                if await community_cards.count() <= cd['index']:
                    continue

                card = community_cards.nth(cd['index'])
                
                # Find install button
                btn = card.locator('button, a, [role="button"]').first
                if await btn.count() == 0:
                    continue

                log_lines.append(f"\n[{cd['index']}] Clicking: {cd['title'][:50]}")
                await btn.click()
                await page.wait_for_timeout(2000)

                # Get modal content
                modal_text = await page.evaluate('''() => {
                    const modals = document.querySelectorAll(
                        '[class*="modal"], [class*="Modal"], [class*="dialog"], ' +
                        '[class*="Dialog"], [class*="drawer"], [class*="Drawer"], ' +
                        '[class*="popup"], [class*="Popup"], [class*="overlay"], ' +
                        '[role="dialog"]'
                    );
                    for (const m of modals) {
                        const text = m.textContent.trim();
                        if (text.length > 30 && m.offsetParent !== null) {
                            return {cls: m.className, text: text.substring(0, 2000)};
                        }
                    }
                    return null;
                }''')

                if modal_text:
                    log_lines.append(f"  Modal: {modal_text['cls'][:60]}")
                    log_lines.append(f"  Text: {modal_text['text'][:500]}")
                    
                    # Extract CLIXML commands from modal
                    import re
                    cmds = re.findall(r'(?:clawhub|openclaw|npm|iwencai)\s+\S+(?:\s+\S+){0,4}', modal_text['text'])
                    if cmds:
                        log_lines.append(f"  Commands: {cmds}")

                    extracted.append({
                        'index': cd['index'],
                        'title': cd['title'],
                        'text': modal_text['text']
                    })

                # Close modal
                try:
                    await page.click('button:has-text("关闭")', timeout=2000)
                except Exception:
                    try:
                        await page.click('[class*="close"]', timeout=2000)
                    except Exception:
                        try:
                            await page.keyboard.press('Escape')
                        except Exception:
                            pass
                await page.wait_for_timeout(1000)

            except Exception as e:
                log_lines.append(f"  Error: {e}")
                continue

        # Save results
        log_lines.append(f"\n\nExtracted {len(extracted)} skills")
        for ex in extracted:
            log_lines.append(f"\n=== [{ex['index']}] {ex['title']} ===")
            log_lines.append(ex['text'][:1000])

        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(log_lines))

        await browser.close()

    print(f"Done. {len(extracted)} skills extracted. See extracted_prompts.txt")

if __name__ == '__main__':
    asyncio.run(main())
