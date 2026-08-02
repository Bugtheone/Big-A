"""拉取技能索引 JSON，检查结构。"""
import requests, json

if __name__ == '__main__':
    s = requests.Session()
    s.trust_env = False
    r = s.get("https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/skills.json", timeout=15)
    data = r.json()
    print(f"类型: {type(data).__name__}")
    if isinstance(data, dict):
        print(f"顶层 keys: {list(data.keys())}")
        for k, v in data.items():
            if isinstance(v, list):
                print(f"  {k}: 列表 {len(v)} 项")
                if v:
                    print(f"    首项: {json.dumps(v[0], ensure_ascii=False)[:300]}")
            elif isinstance(v, dict):
                print(f"  {k}: 字典 {len(v)} keys — {list(v.keys())[:5]}")
            else:
                print(f"  {k}: {str(v)[:100]}")
    elif isinstance(data, list):
        print(f"列表 {len(data)} 项")
        if data:
            print(f"首项: {json.dumps(data[0], ensure_ascii=False)[:300]}")
    else:
        print(f"内容: {str(data)[:500]}")
