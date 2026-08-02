"""从 SkillHub API 提取 @ClawHub 社区技能列表"""
import requests
import json
import io, sys, os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    # 强制 UTF-8 输出
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.iwencai.com/skillhub",
    }

    # API endpoint we discovered earlier
    url = "https://ms.10jqka.com.cn/gateway/market/api/v1/skills/square"
    params = {"current": 1, "size": 300}

    s = requests.Session()
    s.trust_env = False

    try:
        resp = s.get(url, params=params, headers=headers, timeout=30)
        data = resp.json()
    except Exception as e:
        print(f"API request failed: {e}")
        return

    all_skills = data.get("data", {}).get("records", [])

    # Classify
    official = []
    community = []
    other = []

    for sk in all_skills:
        classify = sk.get("classify", "UNKNOWN")
        if classify == "OFFICIAL":
            official.append(sk)
        elif classify in ("THIRD_PARTY", "COMMUNITY", "CLAWHUB"):
            community.append(sk)
        else:
            other.append(sk)

    print(f"Total skills: {len(all_skills)}")
    print(f"OFFICIAL: {len(official)}")
    print(f"COMMUNITY (@ClawHub): {len(community)}")
    print(f"OTHER: {len(other)}")
    print()

    print("=== @ClawHub COMMUNITY SKILLS ===")
    for sk in community:
        name = sk.get("name", "?")
        cn_name = sk.get("cn_name", "") or name
        author = sk.get("author", "") or sk.get("publisher", "") or "?"
        desc = (sk.get("description") or "")[:80]
        print(f"slug={name}")
        print(f"  名称: {cn_name}")
        print(f"  作者: {author}")
        print(f"  描述: {desc}")
        print()

    # Save full list
    output_path = os.path.join(BASE_DIR, "data", "skills", "community_skills_raw.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(community, f, ensure_ascii=False, indent=2)

    # Print slugs only (for batch install)
    print("\n=== SLUGS (for batch install) ===")
    for sk in community:
        print(sk["name"])


if __name__ == '__main__':
    main()
