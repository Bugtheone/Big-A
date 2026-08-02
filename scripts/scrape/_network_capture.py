"""用 Playwright 拦截网络请求，捕获 ClawHub 社区技能的 slug 映射"""
import asyncio, json, io, sys, re
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def main():
    captured_urls = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Intercept network requests
        async def handle_request(request):
            url = request.url
            if any(kw in url.lower() for kw in ['skill', 'clawhub', 'community', 'page-data', 'store']):
                captured_urls.append(url)

        async def handle_response(response):
            url = response.url
            content_type = response.headers.get('content-type', '')
            if any(kw in url.lower() for kw in ['skill', 'clawhub', 'asg-component', 'page-data']):
                try:
                    body = await response.text()
                    if body and len(body) > 50 and len(body) < 100000:
                        print(f"\n=== RESPONSE: {response.status} {url} ===")
                        # Try to extract slugs from JSON response
                        try:
                            data = json.loads(body)
                            if isinstance(data, dict):
                                # Look for slug patterns
                                slugs = re.findall(r'{["\']name["\']\s*:\s*["\']([^"\']+)["\']', body)
                                if slugs:
                                    print(f"Slugs found: {slugs[:10]}")
                        except Exception:
                            pass
                        print(body[:1000])
                except Exception:
                    pass

        page.on('request', handle_request)
        page.on('response', handle_response)

        await page.goto('https://www.iwencai.com/skillhub', wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(5000)

        print("\n=== Captured URLs ===")
        for u in set(captured_urls):
            print(u)

        # Also try to extract from Vue.js data store
        vue_data = await page.evaluate('''() => {
            try {
                const app = document.querySelector('#app');
                if (app && app.__vue_app__) {
                    return 'Vue 3 app found';
                }
                return 'no Vue app ref';
            } catch(e) {
                return 'Error: ' + e.message;
            }
        }''')
        print(f"Vue data: {vue_data}")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
