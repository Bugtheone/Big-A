"""批量安装 SkillHub 社区技能

用法：python _batch_install_community.py
数据源：data/skills/community_skills_list.json
"""

import json, subprocess, sys, os

# ── 动态定位项目根目录和资源路径 ──
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data", "skills")
SKILLS_FILE = os.path.join(DATA_DIR, "community_skills_list.json")
RESULTS_FILE = os.path.join(DATA_DIR, "community_install_results.json")

# ── 自动探测 CLI 路径 ──
def find_cli():
    """查找 iwencai-skillhub-cli 安装位置"""
    candidates = [
        os.path.expanduser(r"~\.local\bin\iwencai-skillhub-cli.cmd"),
        os.path.expanduser(r"~\.local\bin\iwencai-skillhub-cli"),
        os.path.expanduser(r"~\.iwencai-skillhub\bin\iwencai-skillhub-cli.cmd"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # 尝试 PATH 查找
    for d in os.environ.get("PATH", "").split(os.pathsep):
        for name in ("iwencai-skillhub-cli.cmd", "iwencai-skillhub-cli.exe"):
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return None

def main():
    cli = find_cli()
    if not cli:
        print("找不到 iwencai-skillhub-cli，请先安装")
        sys.exit(1)
    print(f"CLI found: {cli}")

    with open(SKILLS_FILE, "r", encoding="utf-8") as f:
        skills = json.load(f)

    total = len(skills)
    success = []
    failed = []

    print(f"共 {total} 个社区技能待安装\n")

    for i, sk in enumerate(skills, 1):
        name = sk["name"]
        print(f"[{i}/{total}] {name} ... ", end="", flush=True)
        
        try:
            result = subprocess.run(
                [cli, "install", name],
                capture_output=True, text=True, timeout=60,
                encoding="utf-8", errors="replace"
            )
            if result.returncode == 0 and "Installed" in result.stdout:
                print("OK")
                success.append(name)
            else:
                msg = (result.stderr or result.stdout)[:100].strip().replace("\n", " ")
                print(f"FAIL ({msg})")
                failed.append((name, msg))
        except Exception as e:
            print(f"ERROR ({e})")
            failed.append((name, str(e)))

    print(f"\n{'='*50}")
    print(f"成功: {len(success)}/{total}")
    print(f"失败: {len(failed)}/{total}")

    if failed:
        print("\n失败列表:")
        for name, err in failed:
            print(f"  - {name}: {err}")

    # Save results
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"success": success, "failed": [n for n, _ in failed]}, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
