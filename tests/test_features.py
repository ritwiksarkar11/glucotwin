import numpy as np
import pandas as pd
import pytest

from glucotwin.features.ward_features import FEATURES_B, AdmissionView
from glucotwin.ingest.fhir_bulk import split
from tests.conftest import needs_artifacts

pytestmark = needs_artifacts


def _cgm_admission(ward):
    enc = ward["encounters"]
    return enc[enc.cgm & enc.surgery_time.notna()].index[0]


def test_features_are_causal(ward):
    aid = _cgm_admission(ward); tabs = split(ward, aid)
    e = tabs["encounter"]; t = e.admit_time.ceil("h") + pd.Timedelta("30h")
    f1 = AdmissionView(tabs).features(pd.DatetimeIndex([t]))
    later = {k: v.copy() for k, v in tabs.items() if k != "encounter"}
    later["encounter"] = e
    later["poc"].loc[later["poc"].time > t, "glucose_mgdl"] = 40
    later["cgm"].loc[later["cgm"].time > t, "glucose_mgdl"] = 400
    later["mar"].loc[later["mar"].time > t, "dose"] = 99
    later["meals"].loc[later["meals"].time > t, "intake_fraction"] = 0.0
    later["labs"].loc[later["labs"].time > t, "value"] = 9.9
    # an order written after t must not change features at t
    extra = pd.DataFrame([{"admission_id": aid, "time": t + pd.Timedelta("1h"), "kind": "basal_units", "value": "77",
                           "start": t + pd.Timedelta("1h"), "end": pd.NaT, "note": ""}])
    later["orders"] = pd.concat([later["orders"], extra], ignore_index=True)
    f2 = AdmissionView(later).features(pd.DatetimeIndex([t]))
    pd.testing.assert_frame_equal(f1[FEATURES_B], f2[FEATURES_B])


def test_known_future_orders_are_used(ward):
    """Fasting booked for tomorrow appears in the schedule today (written at yesterday's round)."""
    aid = _cgm_admission(ward); tabs = split(ward, aid)
    npo = tabs["orders"][tabs["orders"].kind == "npo"].iloc[0]
    t = npo.time + pd.Timedelta("13h")   # evening before the fast
    row = AdmissionView(tabs).features(pd.DatetimeIndex([t])).iloc[0]
    assert row.npo_hours_12h > 0


def test_streaming_matches_batch(ward, twin):
    from glucotwin.features.dataset import build
    risk, _ = build()
    r = risk[risk.split == "test"].sample(25, random_state=1)
    for _, x in r.iterrows():
        p = twin.predict(x.admission_id, x.time)
        np.testing.assert_allclose(p["row"][FEATURES_B].astype(float).to_numpy(), x[FEATURES_B].astype(float).to_numpy(), rtol=1e-6, atol=1e-6)
