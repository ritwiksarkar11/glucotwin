"""Counterfactual validation of insulin what-ifs.

For a sample of real dose events, the same patient is re-simulated with that one
dose changed (x0, x0.5, x1.5). Because every patient has independent random
streams, the two runs are identical up to the dose, so the difference in true
glucose afterwards is the dose's causal effect. We compare it with
  (a) the pharmacology layer and (b) the learned forecast's own what-if.

    python -m glucotwin.evaluation.counterfactual       # fits the scale on train, validates on test
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..config import EVAL_DIR, MODEL_DIR, SETTINGS
from ..features.dataset import patient_split
from ..features.ward_features import AdmissionView
from ..ingest.fhir_bulk import load_ward, split
from ..models.bundle import Bundle
from ..sim.ward_sim import EPOCH, make_admissions, simulate
from ..twin import pharmacology as ph

HOURS = list(range(1, 13))
FACTORS = (0.0, 0.5, 1.5)


def _admissions(n=800, days=60):
    return make_admissions(np.random.default_rng(SETTINGS.seed), n, days)


def _events(w, aid, max_per_kind=2):
    m = w["mar"][(w["mar"].admission_id == aid) & (w["mar"].status == "given")]
    e = w["encounters"].loc[aid]
    out = []
    b = m[m.drug == "basal_glargine"]
    b = b[(b.time > e.admit_time + pd.Timedelta("20h")) & (b.time < e.discharge_time - pd.Timedelta("13h"))]
    out += [("basal", t - pd.Timedelta("5min"), d) for t, d in zip(b.time[:max_per_kind], b.dose[:max_per_kind])]
    p = m[(m.drug == "rapid_prandial") & (m.note.isin(["lunch", "dinner"]))]
    p = p[(p.time > e.admit_time + pd.Timedelta("20h")) & (p.time < e.discharge_time - pd.Timedelta("13h"))]
    out += [("prandial", t + pd.Timedelta("10min"), d) for t, d in zip(p.time[:max_per_kind], p.dose[:max_per_kind])]
    return out


def run(split_name: str, n_adm: int, bundle: Bundle | None, seed=0) -> pd.DataFrame:
    w = load_ward(); enc = w["encounters"]
    sp = patient_split(list(enc.index))
    adms = _admissions(len(enc))
    by_id = {a.admission_id: a for a in adms}
    rng = np.random.default_rng(seed)
    ids = [a for a in enc.index if sp[a] == split_name]
    rng.shuffle(ids)
    rows = []
    for aid in ids:
        if len({r["admission_id"] for r in rows}) >= n_adm:
            break
        evs = _events(w, aid)
        if not evs:
            continue
        a = by_id[aid]
        base = simulate([a], SETTINGS.seed + 1)["_truth"].set_index("time").glucose_true
        view = AdmissionView(split(w, aid))
        for kind, t_ev, dose in evs:
            t_dec = t_ev - pd.Timedelta("30min")
            row = view.features(pd.DatetimeIndex([t_dec])).iloc[0]
            tmin = int((t_ev - EPOCH) / pd.Timedelta("1min"))
            for f in FACTORS:
                cf = simulate([a], SETTINGS.seed + 1, {a.idx: [(tmin, kind, f)]})["_truth"].set_index("time").glucose_true
                true_d = [float(cf.asof(t_dec + pd.Timedelta(hours=h)) - base.asof(t_dec + pd.Timedelta(hours=h))) for h in HOURS]
                pred1 = ph.delta_curve(row, t_dec, [(t_ev, kind, (f - 1) * dose)], HOURS) / ph.scale()["rapid" if kind != "basal" else "basal"]
                ml_d = [np.nan] * len(HOURS)
                if bundle is not None:
                    ov = {"basal": "basal_tonight", "prandial": "prandial_next"}[kind]
                    v0 = AdmissionView(split(w, aid)); v1 = AdmissionView(split(w, aid), {ov: f * dose})
                    X0 = v0.features(pd.DatetimeIndex([t_dec]), horizons=tuple(HOURS)); X1 = v1.features(pd.DatetimeIndex([t_dec]), horizons=tuple(HOURS))
                    ml_d = list(bundle.trajectory(X1, "A").mid.to_numpy() - bundle.trajectory(X0, "A").mid.to_numpy())
                for j, h in enumerate(HOURS):
                    rows.append({"admission_id": aid, "kind": kind, "factor": f, "dose": dose, "h": h, "true": true_d[j],
                                 "pharm_unscaled": pred1[j], "ml": ml_d[j], "isf": ph.isf_estimate(row)})
    return pd.DataFrame(rows)


def fit_and_validate(n_train=60, n_test=40) -> dict:
    tr = run("train", n_train, None, seed=1)
    c = {}
    for kind, key in (("basal", "basal"), ("prandial", "rapid")):
        d = tr[tr.kind == kind]
        c[key] = float((d.pharm_unscaled * d.true).sum() / max((d.pharm_unscaled ** 2).sum(), 1e-9))
    (MODEL_DIR / "pharmacology.json").write_text(json.dumps(c, indent=2))
    ph.scale.cache_clear()
    te = run("test", n_test, Bundle.load(), seed=2)
    te["pharm"] = te.pharm_unscaled * te.kind.map({"basal": c["basal"], "prandial": c["rapid"]})
    res = {"scale_fitted_on_train": c, "test_events": int(te.groupby(["admission_id", "kind"]).ngroups), "test_rows": int(len(te))}
    for kind in ("basal", "prandial"):
        d = te[(te.kind == kind) & (te.factor != 1.0)]
        res[kind] = {"mae_pharmacology": float((d.pharm - d.true).abs().mean()), "mae_learned_forecast": float((d.ml - d.true).abs().mean()),
                     "mae_assume_no_effect": float(d.true.abs().mean()),
                     "corr_pharmacology": float(np.corrcoef(d.pharm, d.true)[0, 1]),
                     "corr_learned_forecast": float(np.corrcoef(d.ml.fillna(0), d.true)[0, 1]),
                     "mean_true_effect_6h_when_held": float(d[(d.factor == 0) & (d.h == 6)].true.mean()),
                     "mean_pharm_effect_6h_when_held": float(d[(d.factor == 0) & (d.h == 6)].pharm.mean()),
                     "mean_learned_effect_6h_when_held": float(d[(d.factor == 0) & (d.h == 6)].ml.mean())}
    te.to_csv(EVAL_DIR / "what_if_counterfactuals.csv.gz", index=False)
    return res


if __name__ == "__main__":
    r = fit_and_validate()
    EVAL_DIR.mkdir(exist_ok=True)
    m = EVAL_DIR / "metrics.json"
    allm = json.loads(m.read_text()) if m.exists() else {}
    allm["what_if_validation"] = r
    m.write_text(json.dumps(allm, indent=2, default=float))
    print(json.dumps(r, indent=1))
