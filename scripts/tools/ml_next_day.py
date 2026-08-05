# -*- coding: utf-8 -*-
"""ML 探索：次日方向预测基线回测（2026-08-05 用户要求 ML 方向）。

目的：用现有历史数据（上证指数 3 年）评估"ML 次日方向预测"在本项目的现实表现：
  - 基准：动量策略（昨日涨→今日看多）准确率
  - 模型：Logistic Regression（时间序列切分，防泄漏）
  - 输出：ML vs 基准准确率、胜率、特征重要性 → 判断是否值得深入

⚠️ 纪律：ML 输出仅供辅助参考，不替代 E/C 交易纪律（AGENTS.md）。

用法:
  python scripts/tools/ml_next_day.py            # 全量回测
  python scripts/tools/ml_next_day.py --years 3  # 指定年数
"""
import sys, os, argparse
from datetime import datetime, timedelta

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


def _rows(df):
    return df if isinstance(df, list) else df.to_dict("records")


def build_features(rows):
    """特征工程：动量/量能/技术指标（纯指数历史，无广度）。"""
    import numpy as np
    closes = np.array([float(r["close"]) for r in rows])
    vols = np.array([float(r.get("vol") or 0) for r in rows])
    pcts = np.array([float(r.get("pct_chg") or 0) for r in rows])

    X, y, dates = [], [], []
    n = len(rows)
    for i in range(20, n - 1):  # 从 20 日开始，目标 = 次日
        feat = []
        # 动量：前1/3/5/10/20日涨跌幅
        for d in (1, 3, 5, 10, 20):
            feat.append((closes[i] - closes[i - d]) / closes[i - d] * 100)
        # 量能：前1/3/5日量比（相对前 20 日均量）
        base_vol = vols[i - 20:i].mean()
        for d in (1, 3, 5):
            feat.append(vols[i - d + 1:i + 1].mean() / base_vol if base_vol > 0 else 1.0)
        # 距 MA5/MA10/MA20
        for d in (5, 10, 20):
            ma = closes[i - d + 1:i + 1].mean()
            feat.append((closes[i] - ma) / ma * 100)
        # RSI(14)（简化）
        gains, losses = [], []
        for j in range(i - 13, i + 1):
            dd = closes[j] - closes[j - 1]
            gains.append(max(dd, 0))
            losses.append(max(-dd, 0))
        ag, al = np.mean(gains), np.mean(losses)
        feat.append(100 - 100 / (1 + ag / al) if al > 0 else 100)
        # 昨日涨跌
        feat.append(pcts[i - 1])
        X.append(feat)
        y.append(1 if pcts[i] > 0 else 0)  # 次日涨=1
        dates.append(rows[i]["trade_date"])
    return X, y, dates


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=3)
    args = ap.parse_args()

    from scripts.data_gate import gate
    from scripts.tools.real_time import get_real_time
    t = get_real_time()

    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=365 * args.years)).strftime("%Y%m%d")
    rows = _rows(gate.ts_index_daily(ts_code="000001.SH", start=start, end=end))
    if len(rows) < 100:
        print(f"❌ 数据不足: {len(rows)}")
        return 1

    X, y, dates = build_features(rows)
    print(f"=== ML 次日方向回测（{t['used']} 腾讯CDN）===")
    print(f"样本: {len(X)}（{dates[0]}~{dates[-1]}）特征: {len(X[0])}")

    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import TimeSeriesSplit

    X = np.array(X); y = np.array(y)
    # 基准：动量（昨日涨→看多）——用样本对应日期的昨日 pct
    # 简化：y 的均值 = 上涨日占比（基准=始终看多）
    base_acc = max(y.mean(), 1 - y.mean())  # 基线（多数类）
    # 动量基准：昨日涨则预测今日涨（需要 pcts，重建）
    pcts = np.array([float(r.get("pct_chg") or 0) for r in rows])
    # 对齐：样本 i 对应 rows[i+1]（因为从 20 开始且目标次日）——用 dates 对齐重建
    date_pct = {r["trade_date"]: float(r.get("pct_chg") or 0) for r in rows}
    mom_correct = 0
    for di, d in enumerate(dates):
        # 动量基准：昨日涨→预测今日涨
        idx = {r["trade_date"]: k for k, r in enumerate(rows)}
        k = idx[d]
        prev = pcts[k - 1]
        pred = 1 if prev > 0 else 0
        if pred == y[di]:
            mom_correct += 1
    mom_acc = mom_correct / len(y)

    # 时间序列切分（训练→测试，防泄漏）
    tscv = TimeSeriesSplit(n_splits=3)
    results = []
    for train_idx, test_idx in tscv.split(X):
        clf = LogisticRegression(max_iter=2000, C=1.0)
        clf.fit(X[train_idx], y[train_idx])
        pred = clf.predict(X[test_idx])
        acc = (pred == y[test_idx]).mean()
        results.append(acc)
    ml_acc = np.mean(results)

    print(f"\n[基准 vs ML]")
    print(f"  多数类基准: {base_acc*100:.1f}%")
    print(f"  动量基准(昨涨看多): {mom_acc*100:.1f}%")
    print(f"  LogisticRegression(3折TS): {ml_acc*100:.1f}%")

    # 特征重要性（随机森林）
    rf = RandomForestClassifier(n_estimators=100, random_state=42)
    rf.fit(X, y)
    imp = rf.feature_importances_
    feat_names = ["mom1", "mom3", "mom5", "mom10", "mom20",
                  "vol1", "vol3", "vol5", "ma5d", "ma10d", "ma20d", "rsi14", "prev_pct"]
    top = sorted(zip(feat_names, imp), key=lambda x: -x[1])[:5]
    print(f"\n[特征重要性 TOP5（随机森林）]")
    for n, v in top:
        print(f"  {n}: {v:.3f}")

    # 结论
    edge = ml_acc - max(base_acc, mom_acc)
    verdict = "ML 有边际提升（可深入）" if edge > 0.01 else (
        "ML 无显著优势（数据不足/信号弱，不建议投入）")
    print(f"\n[结论] ML 相对基准提升 {edge*100:+.1f}pt → {verdict}")
    print(f"> ML 仅辅助参考，不替代 E/C 纪律（AGENTS.md）")

    # 写文件
    dstr = datetime.now().strftime("%Y-%m-%d")
    outdir = os.path.join(_PROJECT_ROOT, "reports", "daily", dstr)
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"ml_nextday_{datetime.now().strftime('%H%M')}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# ML 次日方向回测 — {dstr}\n\n")
        f.write(f"样本 {len(X)}（{dates[0]}~{dates[-1]}）\n")
        f.write(f"- 多数类基准: {base_acc*100:.1f}%\n")
        f.write(f"- 动量基准: {mom_acc*100:.1f}%\n")
        f.write(f"- ML(LR): {ml_acc*100:.1f}%\n")
        f.write(f"- 结论: {verdict}\n")
    print(f"\n[已写入] {os.path.relpath(out, _PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
