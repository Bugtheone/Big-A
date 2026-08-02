"""从 Vue 组件数据中提取社区技能 slug"""
import asyncio, json, os, re
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
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

        # Try to get Vue component data
        vue_data = await page.evaluate('''() => {
            const result = {};

            // Try __vue_app__
            const app = document.querySelector('#app');
            if (app && app.__vue_app__) {
                result.hasVueApp = true;
                const vueApp = app.__vue_app__;
                result.appVersion = vueApp.version;
                result.configKeys = Object.keys(vueApp.config || {});
            }

            // Try __NUXT__
            const nuxt = window.__NUXT__ || window.__nuxt__;
            if (nuxt) {
                result.hasNuxt = true;
                const keys = typeof nuxt === 'object' ? Object.keys(nuxt).slice(0, 20) : [];
                result.nuxtKeys = keys;
            }

            // Try __NEXT_DATA__
            const nextData = document.getElementById('__NEXT_DATA__');
            if (nextData) {
                result.hasNextData = true;
                try {
                    const data = JSON.parse(nextData.textContent);
                    result.nextDataKeys = Object.keys(data).slice(0, 20);
                } catch(e) {}
            }

            // Try to find any global store
            const storeKeys = [];
            for (let k in window) {
                if (k.includes('store') || k.includes('Store') || k.includes('state') || k.includes('State')) {
                    storeKeys.push(k);
                }
            }
            result.storeKeys = storeKeys.slice(0, 20);

            return result;
        }''')

        log = []
        log.append(f"Vue data: {json.dumps(vue_data, indent=2, ensure_ascii=False)}")

        # Get all community card data attributes including Vue binding data
        cards_data = await page.evaluate('''() => {
            const cards = document.querySelectorAll('.community-card, [class*="community-card"]');
            return Array.from(cards).slice(0, 10).map((card, i) => {
                // Get title
                const titleEl = card.querySelector('[class*="title"], h3, h4, [class*="name"], strong, .name');
                const title = titleEl?.textContent?.trim() || '';
                
                // Get ALL attributes
                const allAttrs = {};
                for (const attr of card.attributes) {
                    allAttrs[attr.name] = attr.value;
                }

                // Get inner HTML structure (first 500 chars)
                const inner = card.innerHTML.substring(0, 300);
                
                return {index: i, title, allAttrs, innerHTML: inner};
            });
        }''')

        for cd in cards_data:
            log.append(f"\n[{cd['index']}] {cd['title'][:60]}")
            log.append(f"  attrs: {json.dumps(cd['allAttrs'], ensure_ascii=False)[:300]}")
            log.append(f"  html: {cd['innerHTML'][:200]}")

        # Try to find Vue props for community cards
        card_vue_data = await page.evaluate('''() => {
            const cards = document.querySelectorAll('.community-card, [class*="community-card"]');
            const result = [];
            for (const card of Array.from(cards).slice(0, 5)) {
                const item = {};
                // Vue 2: __vue__
                if (card.__vue__) {
                    item.vue2_props = card.__vue__.props;
                    item.vue2_data = Object.keys(card.__vue__.$data || {});
                }
                // Vue 3: __vue_app__
                if (card._vnode) {
                    const vnode = card._vnode;
                    item.vue3_component = vnode.type?.name || vnode.type?.__name || '?';
                    if (vnode.component) {
                        item.vue3_props = vnode.component.props;
                    }
                }
                // React fiber
                const fiberKey = Object.keys(card).find(k => k.startsWith('__reactFiber'));
                if (fiberKey && card[fiberKey]) {
                    const fiber = card[fiberKey];
                    item.react_props = Object.keys(fiber.memoizedProps || {}).slice(0, 20);
                    item.react_type = fiber.type?.name || '?';
                }
                result.push(item);
            }
            return result;
        }''')
        
        log.append(f"\n\nCard Vue/React binding data:")
        for i, cd in enumerate(card_vue_data):
            log.append(f"  [{i}]: {json.dumps(cd, ensure_ascii=False)[:300]}")

        with open('card_vue_data.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(log))
        print(f"Done. Log saved.")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
