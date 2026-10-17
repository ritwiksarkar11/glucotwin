"""Build the modelling datasets.

Outcomes come from CGM, so only CGM-wearing admissions (about half, a "study" cohort
as in inpatient CGM trials) are used for training and evaluation. Admissions are
split 70/15/15 by patient into train / calibration / test before anything else.

  risk.parquet  one row per admission-hour: features + 12-hour low/high outcomes
  traj.parquet  rows every 3 hours x horizons 1..12 h: features + glucose at t+h
"""
from __future__ import annotations

import os
from multiprocessing import Pool

import numpy as np
import pandas as pd

from ..config import SETTINGS, SYNTH_DIR, TRAJ_HORIZONS_H
from ..ingest.fhir_bulk import load_ward, split
from .ward_features import AdmissionView, targets

RISK_PATH = SYNTH_DIR / "_risk.parquet"
TRAJ_PATH = SYNTH_DIR / "_traj.parquet"


def patient_split(ids, seed: int = SETTINGS.seed) -> dict[str, str]:
    rng = np.random.default_rng(seed)
    ids = sorted(ids); rng.shuffle(ids)
    n = len(ids); a, b = int(0.70 * n), int(0.85 * n)
    return {**{x: "train" for x in ids[:a]}, **{x: "cal" for x in ids[a:b]}, **{x: "test" for x in ids[b:]}}


def update_times(e: pd.Series, every: str = "1h") -> pd.DatetimeIndex:
    return pd.date_range(e["admit_time"].ceil("h") + pd.Timedelta("2h"), e["discharge_time"] - pd.Timedelta("1h"), freq=every)


def _one(aid: str):
    w = load_ward()
    v = AdmissionView(split(w, aid))
    times = update_times(v.e)
    f = v.features(times)
    y = targets(v, times)
    risk = f.merge(y, on="time")
    tt = times[::3]
    traj = v.features(tt, horizons=TRAJ_HORIZONS_H)
    ty = y.set_index("time")
    traj["y"] = [ty.at[t, f"y_g{h}"] for t, h in zip(traj.time, traj.h)]
    return risk, traj


def build(force: bool = False):
    if RISK_PATH.exists() and TRAJ_PATH.exists() and not force:
        return pd.read_parquet(RISK_PATH), pd.read_parquet(TRAJ_PATH)
    w = load_ward()
    enc = w["encounters"]
    sp = patient_split(list(enc.index))
    ids = list(enc[enc.cgm].index)
    with Pool(max(1, min(4, os.cpu_count() or 1))) as pool:
        parts = pool.map(_one, ids, chunksize=8)
    risk = pd.concat([p[0] for p in parts], ignore_index=True)
    traj = pd.concat([p[1] for p in parts], ignore_index=True)
    for d in (risk, traj):
        d["split"] = d.admission_id.map(sp)
    risk.to_parquet(RISK_PATH); traj.to_parquet(TRAJ_PATH)
    return risk, traj


if __name__ == "__main__":
    import time
    t = time.time(); r, tr = build(force=True)
    print(r.shape, tr.shape, f"{time.time() - t:.0f}s")
    print(r.groupby("split").agg(adm=("admission_id", "nunique"), rows=("time", "size"), low=("y_low", "mean"), high=("y_high", "mean")).round(3))
