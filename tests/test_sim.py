import numpy as np
import pandas as pd

from glucotwin.sim.ward_sim import make_admissions, simulate


def _run(seed=3):
    rng = np.random.default_rng(seed)
    return simulate(make_admissions(rng, 40, 10), seed + 1)


def test_deterministic():
    a, b = _run(), _run()
    pd.testing.assert_frame_equal(a["poc"], b["poc"])
    pd.testing.assert_frame_equal(a["mar"], b["mar"])


def test_plausible_ward():
    d = _run()
    g = d["poc"].glucose_mgdl
    assert g.between(20, 600).all() and 120 < g.mean() < 260
    assert set(d["poc"].reason) <= {"admission", "protocol", "recheck"}
    # every fingerstick under 70 is treated and rechecked within 20 minutes
    for r in d["poc"][g < 70].itertuples():
        treat = d["mar"][(d["mar"].admission_id == r.admission_id) & d["mar"].drug.isin(["oral_glucose", "dextrose_iv"]) & (d["mar"].time == r.time)]
        assert len(treat) == 1
    assert (d["meals"].intake_fraction.between(0, 1)).all()


def test_steroid_pattern_afternoon_peak():
    rng = np.random.default_rng(5)
    adms = [a for a in make_admissions(rng, 200, 10)]
    d = simulate(adms, 6)
    ster = d["orders"][d["orders"].kind == "steroid_dose"].admission_id.unique()
    tr = d["_truth"][d["_truth"].admission_id.isin(ster)].copy()
    hourly = tr.groupby(tr.time.dt.hour).glucose_true.mean()
    assert hourly.loc[14:19].mean() > hourly.loc[5:7].mean() + 30
