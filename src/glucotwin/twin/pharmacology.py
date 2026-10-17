"""Pharmacology layer for insulin what-ifs (the 'hybrid' part of the twin).

Why: in hospital records, insulin is given *because* glucose is high, so a model
learned from records cannot separate a dose's effect from the reason it was
given (confounding by indication). Our learned forecast barely moves when a
dose changes. Dose what-ifs therefore use a transparent pharmacology layer on
top of the learned forecast:

    change in glucose at t+h = - c_kind x ISF x (change in units) x E_kind(h - offset)

* E_kind: glucose response to 1 unit, from a textbook insulin action profile
  (rapid analogue: peak ~1 h, lasting 4-5 h; glargine: near-flat release over
  24 h) passed through first-order glucose clearance. These are generic
  profiles, NOT the simulator's internal parameters.
* ISF: the patient's insulin sensitivity from the clinical "1700 rule"
  (1700 / total daily insulin dose), with simple adjustments for kidney injury
  and steroids.
* c_kind: one scale factor per insulin type, fitted on counterfactual
  simulations of *training* patients and validated on test patients
  (evaluation/metrics.json -> "what_if_validation").
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import pandas as pd

from ..config import MODEL_DIR

PROFILE = {"rapid": {"tau": 60.0}, "basal": {"release_min": 24 * 60}}
K_CLEAR = 0.008       # per minute, generic first-order return of glucose toward baseline
_GRID = np.arange(0, 13 * 60 + 1, 5)


@lru_cache(maxsize=4)
def response_curve(kind: str) -> np.ndarray:
    """Glucose change (mg/dL per unit of ISF*units) on a 5-min grid after a dose at t=0."""
    t = _GRID.astype(float)
    if kind == "rapid":
        tau = PROFILE["rapid"]["tau"]; rate = t / tau ** 2 * np.exp(-t / tau)           # action rate, integrates to 1
    else:
        L = PROFILE["basal"]["release_min"]; rate = np.where(t < L, 1.0 / L, 0.0)
    out = np.zeros_like(t); d = 0.0
    for i in range(1, len(t)):
        d += 5 * (-K_CLEAR * d - rate[i - 1]); out[i] = d
    return out          # negative numbers: glucose-lowering per (ISF * unit)


def isf_estimate(row: pd.Series) -> float:
    tdd = max(float(row.get("tdd_per_kg_24h", 0) or 0) * float(row["weight_kg"]), 0.3 * float(row["weight_kg"]))
    isf = 1700.0 / tdd
    if row.get("aki_flag"):
        isf *= 1.3
    if (row.get("steroid_today_mg") or 0) > 0:
        isf *= 0.8
    return float(np.clip(isf, 10, 120))


@lru_cache(maxsize=1)
def scale() -> dict:
    p = MODEL_DIR / "pharmacology.json"
    return json.loads(p.read_text()) if p.exists() else {"rapid": 1.0, "basal": 1.0}


def delta_curve(row: pd.Series, now: pd.Timestamp, changes: list[tuple[pd.Timestamp, str, float]], hours) -> np.ndarray:
    """Predicted glucose change at now+h for each h, given dose changes [(dose_time, kind, delta_units)]."""
    isf = isf_estimate(row); c = scale()
    out = np.zeros(len(hours))
    for (td, kind, du) in changes:
        curve = response_curve("rapid" if kind != "basal" else "basal")
        for j, h in enumerate(hours):
            m = (now + pd.Timedelta(hours=h) - td) / pd.Timedelta("1min")
            if m > 0:
                out[j] += c["rapid" if kind != "basal" else "basal"] * isf * du * curve[min(int(m // 5), len(curve) - 1)]
    return out
