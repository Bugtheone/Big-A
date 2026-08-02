"""分析 SkillHub API 返回数据的分类字段"""
import requests, json, io, sys, os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    s = requests.Session()
    s.trust_env = False
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://www.iwencai.com/skillhub'}
    url = 'https://ms.10jqka.com.cn/gateway/market/api/v1/skills/square'
    all_skills = []
    for page in range(1, 5):
        try:
            resp = s.get(url, params={'current': page, 'size': 100}, headers=headers, timeout=30)
            data = resp.json()
            records = data.get('data', {}).get('records', []) or []
            if not records:
                break
            all_skills.extend(records)
        except Exception as e:
            print(f"Page {page} failed: {e}")
            break

    print(f"Total: {len(all_skills)}")
    print()

    # All classify values
    classify_count = {}
    for sk in all_skills:
        c = sk.get('classify', 'N/A')
        classify_count[c] = classify_count.get(c, 0) + 1
    print("Classify values:", classify_count)

    # Sample keys
    if all_skills:
        print("\nSample keys:", list(all_skills[0].keys()))
    print()

    # Sample record
    print("=== Sample OFFICIAL ===")
    for sk in all_skills:
        if sk.get('classify') == 'OFFICIAL':
            print(json.dumps(sk, ensure_ascii=False, indent=2)[:500])
            print("---")
            break

    print("\n=== Sample NON-OFFICIAL ===")
    count = 0
    for sk in all_skills:
        if sk.get('classify') != 'OFFICIAL':
            count += 1
            if count <= 3:
                cn = sk.get('cn_name') or sk.get('name', '?')
                author = sk.get('author', '') or sk.get('publisher', '') or '?'
                slug = sk.get('name', '?')
                version = sk.get('version', '?')
                print(f"slug={slug} cn={cn} author={author} version={version} classify={sk.get('classify')}")

    # Check which have 'cn_name' (社区中文技能名)
    print(f"\nNon-OFFICIAL count: {count}")
    print("\n=== Non-OFFICIAL with cn_name (likely community) ===")
    for sk in all_skills:
        if sk.get('classify') != 'OFFICIAL' and sk.get('cn_name'):
            cn = sk['cn_name']
            slug = sk.get('name', '?')
            author = sk.get('author', '') or sk.get('publisher', '') or '?'
            print(f"slug={slug} cn_name={cn} author={author}")

    # Save all non-official to file for inspection
    non_official = [sk for sk in all_skills if sk.get('classify') != 'OFFICIAL']
    output_path = os.path.join(BASE_DIR, 'data', 'skills', 'all_non_official.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(non_official, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(non_official)} non-official skills to {output_path}")


if __name__ == '__main__':
    main()
