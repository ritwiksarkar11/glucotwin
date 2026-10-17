"""Train the ward twin's models.

    python -m glucotwin.models.train

Fit on train admissions (10% of them held out for early stopping); calibrate
probabilities, interval widths and board thresholds on calibration admissions.
Test admissions are never used here.
"""
from __future__ import annotations

import time

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import precision_recall_curve

from ..config import MODEL_DIR, SETTINGS
from ..features.dataset import build
from ..features.ward_features import FEATURES_A, FEATURES_B, WIN_F, monotone
from .bundle import Bundle

BASE = dict(learning_rate=0.04, num_leaves=31, min_data_in_leaf=80, feature_fraction=0.8, bagging_fraction=0.8,
            bagging_freq=1, lambda_l2=3.0, verbose=-1, seed=SETTINGS.seed, num_threads=0,
            monotone_constraints_method="advanced")


def _es_split(df: pd.DataFrame):
    rng = np.random.default_rng(SETTINGS.seed)
    tr = sorted(df.loc[df.split == "train", "admission_id"].unique())
    es = set(rng.choice(tr, size=max(2, len(tr) // 10), replace=False))
    return df[(df.split == "train") & ~df.admission_id.isin(es)], df[df.admission_id.isin(es)], df[df.split == "cal"]


def _fit(params, X, y, Xv, yv, rounds=2000):
    d = lgb.Dataset(X, y); dv = lgb.Dataset(Xv, yv, reference=d)
    return lgb.train(params, d, rounds, valid_sets=[dv], callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(0)])


def _thresholds(p, y, target: str) -> tuple[float, float]:
    """Board thresholds on calibration patients.

    Lows are dangerous and rarer: amber = catch 80% of hours before a low, red = best F1.
    Severe highs are common and less urgent: amber = best F1, red only when precision >= 75%,
    so the board does not turn red all afternoon for every steroid patient."""
    pr, rc, th = precision_recall_curve(y, p)
    f1 = 2 * pr * rc / np.maximum(pr + rc, 1e-9)
    best = float(th[np.nanargmax(f1[:-1])])
    if target == "low":
        amber_i = np.where(rc[:-1] >= 0.80)[0]
        amber = float(th[amber_i[-1]]) if len(amber_i) else best / 2
        return min(amber, best), best
    red_i = np.where(pr[:-1] >= 0.75)[0]
    red = float(th[red_i[0]]) if len(red_i) else 0.9
    return min(best, red), max(best, red)


def train() -> Bundle:
    t0 = time.time()
    risk, traj = build()
    b = Bundle()
    meta = {"rows_risk": int(len(risk)), "rows_traj": int(len(traj)),
            "admissions": risk.groupby("split").admission_id.nunique().to_dict()}
    fit, es, cal = _es_split(risk)
    for target in ("low", "high"):
        y = f"y_{target}"
        for mode, feats in (("A", FEATURES_A), ("B", FEATURES_B)):
            tr, va, ca = fit[fit[y].notna()], es[es[y].notna()], cal[cal[y].notna()]
            p = {**BASE, "objective": "binary", "metric": "binary_logloss", "monotone_constraints": monotone(feats, target)}
            bst = _fit(p, tr[feats], tr[y], va[feats], va[y])
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(bst.predict(ca[feats]), ca[y])
            b.risk[(target, mode)] = bst; b.iso[(target, mode)] = iso
            amber, red = _thresholds(iso.predict(bst.predict(ca[feats])), ca[y], target)
            b.thresholds[f"{target}_{mode}"] = {"amber": round(amber, 3), "red": round(red, 3)}
            meta[f"rounds_{target}_{mode}"] = bst.best_iteration
            print(f"  risk {target}/{mode}: {bst.best_iteration} rounds, amber {amber:.2f} red {red:.2f}")
    tfit, tes, tcal = _es_split(traj)
    alpha = 1 - SETTINGS.interval
    for mode, feats in (("A", FEATURES_A), ("B", FEATURES_B)):
        f = feats + WIN_F
        tr, va, ca = tfit[tfit.y.notna()], tes[tes.y.notna()], tcal[tcal.y.notna()]
        mono = monotone(f, "glucose")
        b.traj[(mode, "mid")] = _fit({**BASE, "objective": "huber", "alpha": 30.0, "metric": "l1", "monotone_constraints": mono},
                                     tr[f], tr.y, va[f], va.y)
        # Interval = constrained central forecast + quantiles of its residual. The residual models see the
        # patient's state (not the scheduled doses), so a what-if dose change shifts the whole band in the
        # constrained direction while its width reflects how uncertain this patient's situation is.
        rtr = tr.y - b.traj[(mode, "mid")].predict(tr[f]); rva = va.y - b.traj[(mode, "mid")].predict(va[f])
        rf = feats + ["h", "target_tod_sin", "target_tod_cos"]
        for q, a in (("lo", alpha / 2), ("hi", 1 - alpha / 2)):
            b.traj[(mode, q)] = _fit({**BASE, "objective": "quantile", "alpha": a, "metric": "quantile"},
                                     tr[rf], rtr, va[rf], rva, rounds=1500)
        mid_c = b.traj[(mode, "mid")].predict(ca[f])
        lo = mid_c + b.traj[(mode, "lo")].predict(ca[rf]); hi = mid_c + b.traj[(mode, "hi")].predict(ca[rf])
        s = np.maximum(lo - ca.y.to_numpy(), ca.y.to_numpy() - hi)
        b.conformal[mode] = float(np.quantile(s, min(1, (1 - alpha) * (len(s) + 1) / len(s))))
        print(f"  trajectory {mode}: {b.traj[(mode, 'mid')].best_iteration} rounds, conformal {b.conformal[mode]:+.1f}")
    meta["train_seconds"] = round(time.time() - t0); meta["lightgbm"] = lgb.__version__
    b.meta = meta
    b.version = Bundle.make_version({k: v for k, v in meta.items() if k != "train_seconds"} | {"c": b.conformal, "t": b.thresholds})
    b.save(MODEL_DIR)
    print(f"saved {b.version} in {meta['train_seconds']}s")
    return b


if __name__ == "__main__":
    train()
