"""直接用 Python 调用 clawhub CLI 获取 JSON 技能列表"""
import subprocess, json, io, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def run_clawhub(cmd_args):
    """Run clawhub CLI and return JSON output"""
    result = subprocess.run(
        ['clawhub'] + cmd_args,
        capture_output=True,
        text=True,
        timeout=30,
        env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8'}
    )
    stdout = result.stdout
    stderr = result.stderr
    
    # Try to parse JSON from stdout
    if stdout.strip():
        try:
            return json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            # Try to find JSON in output
            import re
            match = re.search(r'\[.*\]', stdout, re.DOTALL)
            if match:
                return json.loads(match.group())
            match = re.search(r'\{.*\}', stdout, re.DOTALL)
            if match:
                return json.loads(match.group())
    
    if stderr.strip():
        print(f"STDERR: {stderr[:500]}")
    
    return None

if __name__ == '__main__':
    # Try explore
    print("=== EXPLORE ===")
    data = run_clawhub(['explore', '--limit', '200', '--sort', 'downloads', '--json'])
    if data and isinstance(data, list):
        print(f"Found {len(data)} skills")
        # Print all skill names and slugs
        for sk in data:
            if isinstance(sk, dict):
                name = sk.get('name', sk.get('slug', '?'))
                slug = sk.get('slug', sk.get('id', '?'))
                desc = (sk.get('description', '') or '')[:80]
                print(f"  {name} | slug={slug} | {desc}")
    elif data:
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
    else:
        print("No JSON data from explore")

    # Also try search
    print("\n=== SEARCH: stock ===")
    data = run_clawhub(['search', 'stock', '--json'])
    if data:
        if isinstance(data, list):
            print(f"Found {len(data)} skills")
            for sk in data[:10]:
                if isinstance(sk, dict):
                    name = sk.get('name', sk.get('slug', '?'))
                    slug = sk.get('slug', sk.get('id', '?'))
                    desc = (sk.get('description', '') or '')[:80]
                    print(f"  {name} | slug={slug} | {desc}")
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
    else:
        print("No JSON data from search")
