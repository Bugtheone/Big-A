"""调试腾讯行情 API 响应结构"""
import requests, json


def main():
    s = requests.Session()
    s.trust_env = False

    # 尝试两个不同的腾讯API
    urls = [
        "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,25,qfq",
        "http://web.ifzq.gtimg.cn/appstock/app/minute/query?_var=min_data&code=sh000001",
    ]

    for url in urls:
        try:
            r = s.get(url, timeout=12)
            print(f"\nURL: {url[:80]}...")
            print(f"Status: {r.status_code}")
            text = r.text[:500]
            print(f"Sample: {text}")
        except Exception as e:
            print(f"Error: {e}")

    # Also try the old format (non-data wrapper)
    url2 = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,25,qfq"
    try:
        r = s.get(url2, timeout=12)
        print(f"\nHTTPS URL Status: {r.status_code}")
        d = r.json()
        top_keys = list(d.keys())
        print(f"Top keys: {top_keys}")
        if 'data' in d:
            dd = d['data']
            if isinstance(dd, dict):
                inner_keys = list(dd.keys())[:5]
                print(f"data keys: {inner_keys}")
                for ik in inner_keys[:3]:
                    v = dd.get(ik)
                    if isinstance(v, dict):
                        print(f"  {ik} keys: {list(v.keys())}")
                        for subk in v:
                            sv = v[subk]
                            if isinstance(sv, list):
                                print(f"    {subk}: list len={len(sv)}, sample={sv[0] if sv else 'empty'}")
                            else:
                                print(f"    {subk}: {type(sv).__name__}")
            else:
                print(f"data is {type(dd).__name__}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == '__main__':
    main()
