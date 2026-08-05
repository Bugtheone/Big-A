# -*- coding: utf-8 -*-
"""ML 排序模型（2026-08-05，market_filter 增强——相对强弱比方向预测更有价值）。

原理：候选池历史样本 → 特征(动量/MA乖离/量能/估值分位) → 目标=次日涨幅 → LightGBM 回归
对当日候选预测次日涨幅并排序（相对强弱）。

⚠️ 纪律：ML 排序仅辅助（参考分），不替代 E/C 交易纪律与人工确认。

用法:
  python scripts/tools/ml_rank.py                    # 默认候选池（观察池+主线）排序
  python scripts/tools/ml_rank.py --codes 000977,603019 --days 250
"""
import sys, os, argparse, json
from datetime import datetime, timedelta

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

# 默认候选池（观察池 + 半导体链 + AI 应用）
_DEFAULT_CODES = [
    "000977", "603019", "603501", "688012", "688525", "688041", "688256",
    "002371", "603986", "688008", "688981", "002049", "603629", "002929",
    "601858", "600186", "000815", "300857", "002463", "002916",
]


def _rows(df):
    return df if isinstance(df, list) else df.to_dict("records")


def fetch_kline(S, code, days=260):
    """腾讯日K。返回 (dates, closes, vols)。"""
    pref = ("sh" if code.startswith(("6", "9")) else "sz") + code
    try:
        r = S.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                  params={"param": f"{pref},day,,,{days},qfq"}, timeout=8)
        d = r.json()["data"][pref]
        kl = d.get("qfqday") or d.get("day") or []
        if len(kl) < 60:
            return None
        return [x[0] for x in kl], [float(x[2]) for x in kl], [float(x[5]) if len(x) > 5 else 0 for x in kl]
    except Exception:
        return None


def build_pool_features(S, codes, days=260):
    """对候选池构建特征。返回 (X, y, meta)。"""
    import numpy as np
    X, y, meta = [], [], []
    for code in codes:
        k = fetch_kline(S, code, days)
        if not k:
            continue
        dates, closes, vols = k
        n = len(closes)
        if n < 60:
            continue
        c = np.array(closes)
        v = np.array(vols)
        pcts = np.array([(c[i] - c[i - 1]) / c[i - 1] * 100 if i > 0 else 0 for i in range(n)])
        for i in range(20, n - 1):
            feat = []
            for d in (1, 3, 5, 10, 20):
                feat.append((c[i] - c[i - d]) / c[i - d] * 100)
            bv = v[i - 20:i].mean()
            for d in (1, 3, 5):
                feat.append(v[i - d + 1:i + 1].mean() / bv if bv > 0 else 1.0)
            for d in (5, 10, 20):
                ma = c[i - d + 1:i + 1].mean()
                feat.append((c[i] - ma) / ma * 100)
            gains = [max(c[j] - c[j - 1], 0) for j in range(i - 13, i + 1)]
            losses = [max(c[j - 1] - c[j], 0) for j in range(i - 13, i + 1)]
            ag, al = np.mean(gains), np.mean(losses)
            feat.append(100 - 100 / (1 + ag / al) if al > 0 else 100)
            feat.append(pcts[i - 1])
            X.append(feat)
            y.append(pcts[i + 1])  # 次日涨幅（回归目标，非当日——防特征泄漏）
            meta.append((code, dates[i]))
    return np.array(X), np.array(y), meta


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", help="逗号分隔代码（默认观察池+主线）")
    ap.add_argument("--days", type=int, default=260)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    import requests
    S = requests.Session(); S.trust_env = False
    S.headers.update({"User-Agent": "Mozilla/5.0"})
    from scripts.tools.real_time import get_real_time
    t = get_real_time()

    codes = args.codes.split(",") if args.codes else _DEFAULT_CODES
    X, y, meta = build_pool_features(S, codes, args.days)
    if len(X) < 200:
        print(f"❌ 样本不足: {len(X)}（需≥200）")
        return 1

    import numpy as np
    import lightgbm as lgb

    # 按 code 分组切分（防泄漏：同一股票样本不能横跨 train/test）
    meta_codes = np.array([c for c, _ in meta])
    uniq = sorted(set(meta_codes.tolist()))
    n_train_codes = max(2, int(len(uniq) * 0.8))
    train_codes = set(uniq[:n_train_codes])
    train_mask = np.array([c in train_codes for c in meta_codes])
    test_mask = ~train_mask

    if train_mask.sum() < 200 or test_mask.sum() < 50:
        print(f"❌ 分组后样本不足: train={train_mask.sum()} test={test_mask.sum()}")
        return 1

    X_tr, y_tr, X_te, y_te = X[train_mask], y[train_mask], X[test_mask], y[test_mask]

    model = lgb.LGBMRegressor(n_estimators=200, learning_rate=0.05, num_leaves=31,
                              random_state=42, verbose=-1)
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)

    # 测试集排序能力（相对强弱）：预测 vs 实际的 Spearman 相关
    from scipy.stats import spearmanr
    rho, _ = spearmanr(pred, y_te)

    # 当日候选排序（最新一日特征）
    print(f"=== ML 排序（{t['used']} 腾讯CDN）===")
    print(f"样本 {len(X)}（{len(codes)}只 × 历史）· 特征 {X.shape[1]} · 测试集排序相关 ρ={rho:.3f}")

    # 各候选最新预测（用每个 code 最后样本的特征）
    latest_pred = {}
    for code in codes:
        idx = [i for i, (c, _) in enumerate(meta) if c == code]
        if not idx:
            continue
        last_i = idx[-1]
        latest_pred[code] = float(model.predict(X[last_i:last_i + 1])[0])

    ranked = sorted(latest_pred.items(), key=lambda x: -x[1])
    print("\n[候选次日涨幅预测（ML 排序）]")
    for code, p in ranked:
        tag = "🟢强" if p > 0.5 else ("🔴弱" if p < -0.5 else "中性")
        print(f"  {code}: 预测 {p:+.2f}% {tag}")

    # 特征重要性
    names = ["mom1", "mom3", "mom5", "mom10", "mom20", "vol1", "vol3", "vol5",
             "ma5", "ma10", "ma20", "rsi14", "prev_pct"]
    imp = sorted(zip(names, model.feature_importances_), key=lambda x: -x[1])[:5]
    print(f"\n[特征重要性 TOP5] " + ", ".join(f"{n}:{v}" for n, v in imp))

    result = {"ts": t["used"], "n": len(X), "rho_test": round(rho, 3), "ranking": ranked}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    dstr = datetime.now().strftime("%Y-%m-%d")
    outdir = os.path.join(_PROJECT_ROOT, "reports", "daily", dstr)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"ml_rank_{datetime.now().strftime('%H%M')}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# ML 候选排序 — {dstr}\n\n")
        f.write(f"测试集排序相关 ρ={rho:.3f}\n\n")
        for code, p in ranked:
            f.write(f"- {code}: 预测 {p:+.2f}%\n")
    print(f"\n[已写入] {os.path.relpath(out, _PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
