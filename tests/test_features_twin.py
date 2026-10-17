import pandas as pd
import pytest

from glucotwin.twin.reasons import dose_checks
from tests.conftest import needs_artifacts

pytestmark = needs_artifacts


def test_board(twin):
    now = twin.default_now()
    b = twin.board(now)
    assert len(b) >= 8
    assert set(b.status) <= {"red", "amber", "green"}
    assert b.p_low.between(0, 1).all() and b.p_high.between(0, 1).all()
    assert list(b.columns[:3]) == ["admission_id", "bed", "name"]


def test_what_if_moves_in_safe_direction(twin):
    now = twin.default_now()
    for aid in twin.board(now).admission_id[:8]:
        p = twin.predict(aid, now)
        ev = p["view"].schedule_events(now)
        if not ev["basal"]:
            continue
        u = ev["basal"][0][1]
        more = twin.what_if(aid, now, {"basal_tonight": u * 2 + 10})
        none = twin.what_if(aid, now, {"basal_tonight": 0})
        assert more["p_low"] >= none["p_low"] - 1e-9
        assert (more["traj"].mid <= none["traj"].mid + 1e-6).all()
        return
    pytest.skip("no basal dose scheduled at demo time")


def _row(**kw):
    base = dict(mean_intake_24h=0.9, steroid_stopped_24h=0.0, basal_change_24h=0.0, creat_delta_48h=0.0, creat_vs_admit=0.0, last_poc=180.0, mins_since_poc=60.0)
    base.update(kw); return pd.Series(base)


def test_dose_rules():
    assert any(f["rule"] == "prandial_while_fasting" for f in dose_checks(_row(), {"kind": "mealtime", "fasting_at_dose": True}))
    assert any(f["rule"] == "basal_before_fasting" for f in dose_checks(_row(), {"kind": "basal", "fasting_tomorrow": True, "tonight_reduced": False}))
    assert not any(f["rule"] == "basal_before_fasting" for f in dose_checks(_row(), {"kind": "basal", "fasting_tomorrow": True, "tonight_reduced": True}))
    assert any(f["rule"] == "steroid_stopped" for f in dose_checks(_row(steroid_stopped_24h=1.0), {"kind": "basal"}))
    assert any(f["rule"] == "aki" for f in dose_checks(_row(creat_delta_48h=0.5), {"kind": "mealtime"}))
    assert any(f["rule"] == "aki" for f in dose_checks(_row(creat_vs_admit=0.4), {"kind": "basal"}))
    assert any(f["rule"] == "low_recent_glucose" and f["level"] == "high" for f in dose_checks(_row(last_poc=72.0), {"kind": "basal"}))
    assert dose_checks(_row(), {"kind": "basal"}) == []


def test_discharge_findings(twin):
    from glucotwin.twin.engine import WardTwin
    from glucotwin.twin.store import Store
    allw = WardTwin(store=Store(":memory:"), pool="all")
    enc = allw.w["encounters"]
    labs = allw.w["labs"]; hb = labs[labs.test == "hba1c"].groupby("admission_id").value.last()
    new = [a for a in hb[hb >= 6.5].index if not enc.at[a, "known_diabetes"]][:3]
    for a in new:
        s = allw.discharge(a)
        assert any("probable undiagnosed diabetes" in f for f in s["findings"])
        assert any("2 weeks" in x for x in s["actions"])
    s = allw.discharge(enc.index[0])
    assert "insulin" not in " ".join(s["actions"]).lower() or "teaching" in " ".join(s["actions"]).lower()
