"""用 OpenAPI Key 认证，拉取 skillhub 全部技能列表并批量安装。"""
import os, sys, json, subprocess

if __name__ == '__main__':
    # 1. 获取 API Key
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)
    from scripts.iwencai_openapi import get_openapi
    api = get_openapi()
    api_key = api.api_key
    if not api_key:
        print("API Key 未配置")
        sys.exit(1)

    import requests
    s = requests.Session()
    s.trust_env = False

    # 2. 带 Bearer 认证拉取技能列表
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = s.get(
        "https://www.iwencai.com/gateway/market/api/v1/skills/square",
        params={"current": 1, "size": 100},
        headers=headers,
        timeout=15,
    )
    print(f"HTTP {resp.status_code}")

    try:
        data = resp.json()
        records = data.get("data", {}).get("records", [])
        total = data.get("data", {}).get("total", len(records))
        print(f"市场共 {total} 个技能，当前页 {len(records)} 个:\n")

        slugs = []
        for r in records:
            slug = r.get("slug", "")
            name = r.get("name", "")
            desc = (r.get("description") or "")[:70]
            print(f"  [{slug}] {name}")
            if desc:
                print(f"         {desc}")
            slugs.append(slug)

        print(f"\n共需安装 {len(slugs)} 个技能")

        # 3. 保存列表供批量安装
        with open(os.path.join(project_root, "data", "skillhub_all_slugs.json"), "w", encoding="utf-8") as f:
            json.dump({"slugs": slugs, "total": len(slugs), "records": records}, f, ensure_ascii=False, indent=2)
        print(f"技能列表已保存到 data/skillhub_all_slugs.json")

    except Exception as e:
        print(f"解析失败: {e}")
        print(f"原始响应: {resp.text[:500]}")
