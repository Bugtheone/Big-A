"""检查 SkillHub API 所有页面，尤其是 THIRD_PARTY 技能"""
import requests, json, os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    s = requests.Session()
    s.trust_env = False
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.iwencai.com/skillhub'
    }
    url = 'https://www.iwencai.com/gateway/market/api/v1/skills/square'

    all_skills = []
    for page in range(1, 10):
        try:
            resp = s.get(url, params={'current': page, 'size': 100}, headers=headers, timeout=30)
            data = resp.json()
            records = data.get('data', {}).get('records', [])
            if not records:
                break
            all_skills.extend(records)
        except Exception as e:
            print(f"Page {page} failed: {e}")
            break

    output_path = os.path.join(BASE_DIR, 'data', 'skills', 'all_skills_check.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_skills, f, ensure_ascii=False, indent=2)

    # Classify
    from collections import Counter
    classify_counts = Counter(sk.get('classify', '?') for sk in all_skills)
    print(f"Total: {len(all_skills)} skills")
    print(f"Classify counts: {dict(classify_counts)}")

    print("\n=== OFFICIAL skills ===")
    for sk in all_skills:
        if sk.get('classify') == 'OFFICIAL':
            print(f"  slug={sk['name']} | {sk.get('cn_name', '')[:30] or (sk.get('description', '') or '')[:30]}")

    print("\n=== THIRD_PARTY skills ===")
    for sk in all_skills:
        if sk.get('classify') == 'THIRD_PARTY':
            need_third = sk.get('need_third_config', 0)
            third_desc = sk.get('third_config_desc', '') or ''
            print(f"  slug={sk['name']} | desc={third_desc[:60]} | need_config={need_third}")
            print(f"    full: {json.dumps(sk, ensure_ascii=False)[:500]}")

    print("\n=== Any other classify? ===")
    for sk in all_skills:
        if sk.get('classify') not in ('OFFICIAL', 'THIRD_PARTY'):
            print(f"  classify={sk.get('classify')} name={sk.get('name')}")


if __name__ == '__main__':
    main()
