"""通过 OpenAPI 搜索获取 skillhub 全部技能列表，对比本地已安装。"""
import os, sys, json, requests

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

if __name__ == '__main__':
    from scripts.iwencai_openapi import get_openapi
    api = get_openapi()

    s = requests.Session()
    s.trust_env = False
    headers = {
        "Authorization": f"Bearer {api.api_key}",
        "Content-Type": "application/json",
    }

    # 用 OpenAPI 搜索获取技能列表
    all_slugs = []
    url = "https://www.iwencai.com/gateway/market/api/v1/skills/search"
    for keyword in ["", "a", "e", "i", "o", "u", "stock", "fund", "bond", "fx", "option", "futures", "index", "macro", "risk", "value", "quant", "trade"]:
        resp = s.get(url, params={"keyword": keyword, "current": 1, "size": 50}, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            records = data.get("data", {}).get("records", [])
            for r in records:
                slug = r.get("slug", "")
                if slug and slug not in all_slugs:
                    all_slugs.append(slug)

    # 对比本地
    skills_dir = os.path.join(project_root, "skills")
    local = set(os.listdir(skills_dir)) if os.path.isdir(skills_dir) else set()
    local.discard(".skills_store_lock.json")

    remote = set(all_slugs)
    missing = remote - local
    extra = local - remote

    print(f"远程技能: {len(remote)} 个")
    print(f"本地已安装: {len(local)} 个")
    print(f"交集: {len(remote & local)} 个")

    if missing:
        print(f"\n还缺 {len(missing)} 个: {sorted(missing)}")
    else:
        print("\n全部已安装，无遗漏！")

    if extra:
        print(f"\n本地多出 {len(extra)} 个(可能其他来源): {sorted(extra)}")

    # 保存供批量安装
    with open(os.path.join(project_root, "data", "skillhub_remote_slugs.json"), "w", encoding="utf-8") as f:
        json.dump({"remote": sorted(all_slugs), "missing": sorted(missing), "extra": sorted(extra)}, f, ensure_ascii=False, indent=2)
