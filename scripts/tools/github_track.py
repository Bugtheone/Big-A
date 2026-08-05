# -*- coding: utf-8 -*-
"""GitHub 跟踪（2026-08-05）：
  A. 本仓库动态：PR/Issue/commits/CI 状态（项目健康度）
  B. 上游 a-stock-data 更新：最新版本 vs 本地 V3.6.0（技能是否升级）

用法:
  python scripts/tools/github_track.py            # 全量（本仓库+上游）
  python scripts/tools/github_track.py --prs      # 仅 PR
  python scripts/tools/github_track.py --ci       # 仅 CI
  python scripts/tools/github_track.py --upstream # 仅上游
"""
import sys, os, argparse, subprocess
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

_REPO = "Bugtheone/Big-A"
_UPSTREAM = "simonlin1212/a-stock-data"
_LOCAL_VERSION = "3.6.0"  # 本地技能版本（V3.6.0）


def _token():
    """从 git credential 提取 GitHub token。"""
    try:
        r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                           capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1]
    except Exception:
        pass
    return None


def _api(path, token=None):
    import requests
    S = requests.Session(); S.trust_env = False
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    r = S.get(f"https://api.github.com{path}", headers=headers, timeout=10)
    if r.status_code == 200:
        return r.json()
    return None


def track_repo(token):
    """A. 本仓库动态。"""
    out = []
    # PR 开放
    prs = _api(f"/repos/{_REPO}/pulls?state=open&per_page=10", token) or []
    if prs:
        out.append(f"开放 PR（{len(prs)}）:")
        for p in prs[:5]:
            out.append(f"  #{p['number']} {p['title']} [{p['head']['ref']}→{p['base']['ref']}]")
    else:
        out.append("开放 PR: 无")
    # Issue 开放
    iss = _api(f"/repos/{_REPO}/issues?state=open&per_page=10", token) or []
    pr_numbers = {p["number"] for p in prs}
    real_issues = [i for i in iss if i["number"] not in pr_numbers]
    out.append(f"开放 Issue: {len(real_issues)}")
    # 最近 commits
    commits = _api(f"/repos/{_REPO}/commits?per_page=5", token) or []
    if commits:
        out.append("最近 commits:")
        for c in commits[:5]:
            msg = (c.get("commit", {}).get("message") or "").split("\n")[0]
            out.append(f"  {c.get('sha','')[:8]} {msg[:50]}")
    # 最近 CI
    runs = _api(f"/repos/{_REPO}/actions/runs?per_page=5", token) or []
    if runs.get("workflow_runs"):
        out.append("最近 CI:")
        for r in runs["workflow_runs"][:5]:
            out.append(f"  {r['name']}: {r['status']}/{r['conclusion']} ({r['created_at'][:16]})")
    return out


def track_upstream(token):
    """B. 上游 a-stock-data 更新。"""
    out = []
    # 最新 release
    rel = _api(f"/repos/{_UPSTREAM}/releases/latest", token)
    latest = rel.get("tag_name") if rel else None
    # 最新 tag
    if not latest:
        tags = _api(f"/repos/{_UPSTREAM}/tags?per_page=5", token) or []
        latest = tags[0]["name"] if tags else None
    out.append(f"上游最新: {latest or '未知'} | 本地: V{_LOCAL_VERSION}")
    if latest:
        lv = latest.lstrip("vV")
        if lv != _LOCAL_VERSION:
            out.append(f"⚠️ 上游版本 {lv} ≠ 本地 {_LOCAL_VERSION}——检查是否升级！")
            out.append(f"  release: {rel.get('html_url', '') if rel else '（仅 tag，无 release）'}")
        else:
            out.append("✅ 版本一致，无需升级")
    return out


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--prs", action="store_true")
    ap.add_argument("--ci", action="store_true")
    ap.add_argument("--upstream", action="store_true")
    args = ap.parse_args()

    token = _token()
    from scripts.tools.real_time import get_real_time
    t = get_real_time()
    print(f"=== GitHub 跟踪（{t['used']} 腾讯 CDN）===")

    if args.upstream:
        print("\n[上游 a-stock-data]")
        print("\n".join(track_upstream(token)))
        return 0

    if not args.prs and not args.ci and not args.upstream:
        print("\n[A. 本仓库动态]")
        print("\n".join(track_repo(token)))
        print("\n[B. 上游 a-stock-data]")
        print("\n".join(track_upstream(token)))
    else:
        if args.prs or args.ci:
            print("\n[A. 本仓库动态]")
            print("\n".join(track_repo(token)))
        if args.upstream:
            print("\n[B. 上游 a-stock-data]")
            print("\n".join(track_upstream(token)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
