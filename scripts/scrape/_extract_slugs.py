"""从 SkillHub 页面 JS 数据中提取 ClawHub 社区技能 slug"""
import asyncio, json, io, sys, re
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Intercept all XHR/fetch responses containing skill data
        skill_data = []

        async def on_response(response):
            url = response.url
            ct = response.headers.get('content-type', '')
            if 'json' in ct and any(kw in url for kw in ['skill', 'page', 'community', 'clawhub']):
                try:
                    body = await response.text()
                    if body and len(body) > 100:
                        skill_data.append({'url': url, 'body': body[:5000]})
                except Exception:
                    pass

        page.on('response', on_response)

        await page.goto('https://www.iwencai.com/skillhub', wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(5000)

        # Scroll to load all
        for _ in range(8):
            await page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(2000)

        await page.wait_for_timeout(3000)

        print(f"Captured {len(skill_data)} skill-related responses\n")

        for sd in skill_data:
            print(f"=== URL: {sd['url']} ===")
            print(sd['body'][:1500])
            print()

        # Also try to get __NUXT__ or __INITIAL_STATE__ or window data
        window_data = await page.evaluate('''() => {
            const keys = [];
            for (let k in window) {
                if (k.includes('data') || k.includes('state') || k.includes('store') || k.includes('app') || k.includes('vue')) {
                    keys.push(k);
                }
            }
            return keys.slice(0, 30);
        }''')
        print(f"Window data keys: {window_data}")

        # Check Nuxt state
        nuxt = await page.evaluate('() => window.__NUXT__ || null')
        if nuxt:
            print("__NUXT__ found!")
            # Extract skill slugs
            s = json.dumps(nuxt)
            slugs = re.findall(r'"slug"\s*:\s*"([^"]+)"', s)
            names = re.findall(r'"name"\s*:\s*"([^"]+)"', s)
            print(f"Slugs: {slugs[:30]}")
            print(f"Names: {names[:30]}")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
