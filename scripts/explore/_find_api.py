"""查找加载 @ClawHub 社区技能的 API 端点"""
import asyncio, json, os
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    all_urls = set()
    skill_responses = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Capture ALL network requests
        async def on_request(request):
            url = request.url
            all_urls.add(url)

        async def on_response(response):
            url = response.url
            ct = response.headers.get('content-type', '')
            if 'json' in ct or 'javascript' in ct:
                if any(kw in url for kw in ['skill', 'community', 'clawhub', 'third', 'page', 'index']):
                    try:
                        body = await response.text()
                        skill_responses.append({'url': url, 'body': body})
                    except Exception:
                        pass

        page.on('request', on_request)
        page.on('response', on_response)

        await page.goto('https://www.iwencai.com/skillhub', wait_until='networkidle', timeout=60000)
        await page.wait_for_timeout(5000)

        # Scroll to load all
        for _ in range(8):
            await page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(2000)
        await page.wait_for_timeout(3000)

        log = []
        log.append(f"Total URLs: {len(all_urls)}")
        log.append(f"Skill-related JSON responses: {len(skill_responses)}\n")

        for sr in skill_responses:
            log.append(f"\n=== {sr['url']} ===")
            body = sr['body']
            # Try to extract skill slugs
            import re
            slugs = re.findall(r'"slug"\s*:\s*"([^"]*)"', body)
            names = re.findall(r'"name"\s*:\s*"([^"]*)"', body)
            log.append(f"  Length: {len(body)}")
            log.append(f"  Slugs: {slugs[:15]}")
            log.append(f"  Names: {names[:15]}")
            log.append(f"  Preview: {body[:500]}")

        # Print ALL URLs sorted
        log.append("\n\n=== ALL URLs ===")
        for u in sorted(all_urls):
            if 'skill' in u.lower() or 'clawhub' in u.lower() or 'community' in u.lower() or '10jqka' in u.lower():
                log.append(f"  {u}")

        with open('api_findings.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(log))
        print(f"Done. {len(skill_responses)} responses, {len(all_urls)} URLs")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
