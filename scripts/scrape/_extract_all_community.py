"""从HTML中提取所有@ClawHub社区技能的名称和描述"""
import re, json, os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    html_path = os.path.join(BASE_DIR, 'data', 'skills', 'skillhub_full.html')
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        html = f.read()

    # Pattern for community cards
    pattern = r'<div[^>]*class="sc-name"[^>]*>([^<]+)</div>.*?<p[^>]*class="sc-desc"[^>]*>([^<]+)</p>.*?<div[^>]*class="card-author"[^>]*>@ClawHub</div>'
    matches = re.findall(pattern, html, re.DOTALL)
    print(f"Found {len(matches)} @ClawHub community skills")

    # Alternative: find all community cards and extract name+desc
    card_pattern = r'skill-card community-card.*?sc-name">([^<]+)</div>.*?sc-desc">([^<]+)</p>'
    matches2 = re.findall(card_pattern, html, re.DOTALL)
    print(f"Found {len(matches2)} community cards\n")

    # Deduplicate
    seen = set()
    skills = []
    for name, desc in matches2:
        name = name.strip()
        desc = desc.strip()
        if name not in seen:
            seen.add(name)
            skills.append({'name': name, 'description': desc})

    print(f"Unique skills: {len(skills)}")
    for i, sk in enumerate(skills):
        print(f"{i:3d}. {sk['name']}")
        print(f"     {sk['description'][:100]}")

    # Save for later use
    output_path = os.path.join(BASE_DIR, 'data', 'skills', 'community_skills_list.json')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(skills, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(skills)} skills to {output_path}")


if __name__ == '__main__':
    main()
