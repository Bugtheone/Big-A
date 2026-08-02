"""在页面 JS 包中搜索社区技能的安装 prompt"""
import asyncio, json, os, re
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Capture ALL JS files
        js_contents = []

        async def on_response(response):
            url = response.url
            ct = response.headers.get('content-type', '')
            if 'javascript' in ct and ('10jqka' in url or 'thsi.cn' in url):
                try:
                    body = await response.text()
                    if '波动率' in body or 'volatility' in body.lower():
                        js_contents.append({'url': url, 'path': url.split('/')[-1], 'size': len(body)})
                except Exception:
                    pass

        page.on('response', on_response)

        await page.goto('https://www.iwencai.com/skillhub', wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(5000)

        # Scroll
        for _ in range(8):
            await page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(2000)

        log = [f"JS files containing community skill data: {len(js_contents)}"]
        for js in js_contents:
            log.append(f"  {js['path']} ({js['size']} bytes)")

        # Try to find where community skills are loaded from
        # Check for API calls that might return community skill data
        window_data = await page.evaluate('''() => {
            const result = {};
            // Check for any global data objects
            const checkKeys = ['skillList', 'skillsList', 'communitySkills', 'clawhubSkills', 'skills', 'plugins'];
            for (let k in window) {
                for (let ck of checkKeys) {
                    if (k.toLowerCase().includes(ck.toLowerCase())) {
                        result[k] = typeof window[k];
                    }
                }
            }
            // Try Pinia store
            try {
                const app = document.querySelector('#app');
                if (app && app.__vue_app__) {
                    const pinia = app.__vue_app__.config.globalProperties.$pinia;
                    if (pinia) {
                        result.pinia_stores = Object.keys(pinia.state?.value || {});
                    }
                }
            } catch(e) {
                result.error = e.message;
            }
            return result;
        }''')

        log.append(f"\nWindow skill data: {json.dumps(window_data, ensure_ascii=False)}")

        # Last resort: get ALL page HTML and search for download/install URLs
        html = await page.evaluate('() => document.documentElement.outerHTML')
        
        # Search for clawhub install patterns
        import re
        slug_patterns = re.findall(r'(?:clawhub|openclaw)\s+install\s+["\']?([\w-]+)', html)
        log.append(f"\nClawHub install commands in HTML: {slug_patterns}")

        # Search for npm/clawhub/skill patterns
        download_patterns = re.findall(r'https?://[^\s"<>]*?(?:clawhub|skill|install)[^\s"<>]*', html)
        log.append(f"\nDownload/install URLs: {download_patterns[:20]}")

        with open('js_analysis.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(log))
        print(f"Done. Log saved to js_analysis.txt")

        # Also save full HTML with community card sections
        with open('skillhub_full.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print("Full HTML saved to skillhub_full.html")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
