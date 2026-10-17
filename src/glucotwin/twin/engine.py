"""The ward twin: one live model per admitted patient, four features on top.

1. Ward risk board       board(now)
2. Before-you-give check doses(aid, now) / what_if(aid, now, overrides)
3. Smart check timing    check_plan(...)
4. Discharge handover    discharge(aid, now)

Every update uses only data documented up to `now` plus orders already written.
"""
from __future__ import annotations

import math
import zlib
from functools import lru_cache

import numpy as np
import pandas as pd

from ..config import DEMO_NOW, RISK_HORIZON_H, SETTINGS, TRAJ_HORIZONS_H
from ..features.dataset import patient_split
from ..features.ward_features import AdmissionView, _clock_times
from ..ingest.fhir_bulk import load_ward, split
from ..models.bundle import Bundle, get_bundle
from . import pharmacology as ph
from .reasons import dose_checks, reasons
from .store import Store

H = pd.Timedelta(hours=1)
T = SETTINGS.thr
WARD_NAME = "Ward 7B · Medicine & Cardiac Step-down"


def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _any(ps) -> float:
    """Chance of at least one hourly event, treating neighbouring hours as strongly correlated."""
    return float(np.clip(max(ps), 1e-4, 1 - 1e-4))


def _odds_shift(p_model: float, hourly_base, hourly_new) -> float:
    """Move the calibrated model probability by the odds ratio implied by the shifted trajectory."""
    pb, pn = _any(hourly_base), _any(hourly_new)
    o = (p_model / max(1 - p_model, 1e-6)) * (pn / (1 - pn)) / (pb / (1 - pb))
    return float(np.clip(o / (1 + o), 0, 1))


class WardTwin:
    def __init__(self, store: Store | None = None, bundle: Bundle | None = None, pool: str = "test", ward: str = WARD_NAME):
        self.w = load_ward()
        self.b = bundle or get_bundle()
        self.store = store or Store()
        self.ward = ward
        enc = self.w["encounters"]
        sp = patient_split(list(enc.index))
        self.enc = enc[[sp[a] == pool for a in enc.index]] if pool != "all" else enc
        self._tabs = {}

    # ------------------------------------------------------------------ basics
    def tabs(self, aid):
        if aid not in self._tabs:
            self._tabs[aid] = split(self.w, aid)
        return self._tabs[aid]

    def view(self, aid, overrides=None) -> AdmissionView:
        return AdmissionView(self.tabs(aid), overrides)

    def patients_at(self, now: pd.Timestamp) -> pd.DataFrame:
        e = self.enc[(self.enc.admit_time <= now) & (self.enc.discharge_time > now)].sort_values("admit_time").copy()
        e["bed"] = [f"7B-{(zlib.crc32(a.encode()) % 24) + 1:02d}" for a in e.index]   # stable across runs
        # make beds unique deterministically
        used, beds = set(), []
        for a, b in zip(e.index, e.bed):
            n = int(b[-2:])
            while f"7B-{n:02d}" in used:
                n = n % 24 + 1
            used.add(f"7B-{n:02d}"); beds.append(f"7B-{n:02d}")
        e["bed"] = beds
        return e

    def default_now(self) -> pd.Timestamp:
        """The demo moment (config.DEMO_NOW) if it falls in this ward's period, else the busiest 18:00."""
        d = pd.Timestamp(DEMO_NOW)
        if len(self.patients_at(d)) >= 8:
            return d
        days = pd.date_range(self.enc.admit_time.min().normalize() + pd.Timedelta("5D"),
                             self.enc.discharge_time.max().normalize() - pd.Timedelta("5D"), freq="D")
        best = max(days, key=lambda d: len(self.patients_at(d + pd.Timedelta("18h"))))
        return best + pd.Timedelta("18h")

    # ------------------------------------------------------------------ core state
    def mode_for(self, row) -> str:
        e = self.enc.loc[row["admission_id"]] if row["admission_id"] in self.enc.index else self.w["encounters"].loc[row["admission_id"]]
        return "B" if bool(e["cgm"]) and pd.notna(row.get("mins_since_cgm")) and row["mins_since_cgm"] <= SETTINGS.rules.cgm_stale_min else "A"

    def predict(self, aid: str, now: pd.Timestamp, overrides: dict | None = None) -> dict:
        v = self.view(aid, overrides)
        X = v.features(pd.DatetimeIndex([now]))
        row = X.iloc[0]
        mode = self.mode_for(row)
        p_low = float(self.b.risk_prob(X, "low", mode)[0]); p_high = float(self.b.risk_prob(X, "high", mode)[0])
        Xh = v.features(pd.DatetimeIndex([now]), horizons=TRAJ_HORIZONS_H)
        tr = self.b.trajectory(Xh, mode)
        tr["time"] = [now + h * H for h in tr.h]
        sd = (tr.hi - tr.lo) / (2 * 1.2816)
        tr["p_low"] = [_phi((T.hypo - m) / max(s, 5)) for m, s in zip(tr.mid, sd)]
        tr["p_high"] = [1 - _phi((T.severe_high - m) / max(s, 5)) for m, s in zip(tr.mid, sd)]
        return {"row": row, "X": X, "mode": mode, "p_low": p_low, "p_high": p_high, "traj": tr, "view": v}

    def status(self, p_low, p_high, mode) -> str:
        """Red is reserved for lows (dangerous, actionable now). Likely severe highs are common on a medical
        ward (about 1 in 5 patient-hours here), so they show as amber with their reason instead of paging staff."""
        th = self.b.thresholds
        lo, hi = th[f"low_{mode}"], th[f"high_{mode}"]
        if p_low >= lo["red"]:
            return "red"
        if p_low >= lo["amber"] or p_high >= hi["red"]:
            return "amber"
        return "green"

    def quality(self, row, mode) -> list[str]:
        out = []
        if pd.isna(row["last_poc"]):
            out.append("No fingerstick recorded yet.")
        elif row["mins_since_poc"] > SETTINGS.rules.poc_stale_h * 60 and mode == "A":
            out.append(f"Last fingerstick {row['mins_since_poc'] / 60:.0f} h ago: forecast is less certain.")
        e = self.w["encounters"].loc[row["admission_id"]]
        if bool(e["cgm"]) and mode == "A":
            out.append("CGM signal missing: using fingersticks only.")
        return out

    def patient(self, aid: str, now: pd.Timestamp) -> dict:
        p = self.predict(aid, now)
        row, mode = p["row"], p["mode"]
        cl = self.b.contributions(p["X"], "low", mode).iloc[0]
        ch = self.b.contributions(p["X"], "high", mode).iloc[0]
        st = self.status(p["p_low"], p["p_high"], mode)
        th = self.b.thresholds
        lo_flag = p["p_low"] >= th[f"low_{mode}"]["amber"]; hi_flag = p["p_high"] >= th[f"high_{mode}"]["amber"]
        why = []
        if lo_flag or not hi_flag:
            why += [("low", r) for r in reasons(row, cl, "low", 2 if lo_flag else 1)]
        if hi_flag:
            why += [("high", r) for r in reasons(row, ch, "high", 2)]
        plan = self.check_plan(now, row, p["traj"])
        e = self.w["encounters"].loc[aid]
        plan["suggest_cgm"] = bool(st == "red" and p["p_low"] >= self.b.thresholds[f"low_{mode}"]["red"] and not bool(e["cgm"]))
        doses = self.doses(aid, now, p)
        return {**p, "status": st, "reasons": why, "plan": plan, "doses": doses, "quality": self.quality(row, mode)}

    # ------------------------------------------------------------------ feature 1: ward board
    def board(self, now: pd.Timestamp, record: bool = False) -> pd.DataFrame:
        pts = self.patients_at(now)
        rows = []
        for aid, e in pts.iterrows():
            s = self.patient(aid, now)
            r = s["row"]
            last = r["cgm_now"] if s["mode"] == "B" and pd.notna(r.get("cgm_now")) else r["last_poc"]
            flags = sum(1 for d in s["doses"] for f in d["flags"] if f["level"] == "high")
            rows.append({"admission_id": aid, "bed": e["bed"], "name": e["name"], "age": int(e["age"]), "reason": e["admission_reason"],
                         "day": int(r["days_since_admit"]) + 1, "mode": s["mode"], "last_glucose": last,
                         "last_glucose_mins": r["mins_since_cgm"] if s["mode"] == "B" else r["mins_since_poc"],
                         "p_low": s["p_low"], "p_high": s["p_high"], "status": s["status"],
                         "why": " · ".join(t for _, t in s["reasons"][:2]),
                         "next_check": s["plan"]["next_check"], "next_check_reason": s["plan"]["next_reason"],
                         "suggest_cgm": s["plan"]["suggest_cgm"],
                         "dose_flags": flags})
        df = pd.DataFrame(rows)
        if len(df):
            th = self.b.thresholds
            df["_prio"] = [max(pl / th[f"low_{m}"]["red"], 0.6 * ph / th[f"high_{m}"]["red"]) for pl, ph, m in zip(df.p_low, df.p_high, df["mode"])]
            df = df.sort_values(["_prio"], ascending=False).drop(columns="_prio").reset_index(drop=True)
        if record:
            self.store.snapshot(self.ward, now, self.b.version, df.to_dict("records"))
        return df

    # ------------------------------------------------------------------ feature 3: smart check timing
    def check_plan(self, now, row, traj) -> dict:
        sched = SETTINGS.ward.poc_insulin if (row["correction_scale"] or row["basal_order_units"] or row["prandial_order_units"]) else SETTINGS.ward.poc_no_insulin
        protocol = _clock_times(now, now + RISK_HORIZON_H * H, sched)
        tr = traj.copy()
        tr["p_out"] = tr[["p_low", "p_high"]].max(axis=1)
        far = [all(abs((t - pc) / H) > 1.5 for pc in protocol) for t in tr.time]
        cand = tr[far]
        extra = None
        if len(cand) and cand.p_out.max() >= SETTINGS.rules.extra_check_threshold:
            c = cand.loc[cand.p_out.idxmax()]
            kind = "low" if c.p_low >= c.p_high else "high"
            extra = {"time": c.time, "kind": kind, "p": float(c.p_out),
                     "why": ("Forecast dips toward a low" if kind == "low" else "Forecast peaks above 250") + f" around {c.time:%H:%M}"}
        nxt = protocol[0] if protocol else None
        if extra and (nxt is None or extra["time"] < nxt):
            return {"protocol": protocol, "extra": extra, "next_check": extra["time"], "next_reason": "twin: " + extra["kind"]}
        return {"protocol": protocol, "extra": extra, "next_check": nxt, "next_reason": "protocol"}

    # ------------------------------------------------------------------ feature 2: before-you-give check
    def doses(self, aid: str, now: pd.Timestamp, p: dict, window_h: float = 12) -> list[dict]:
        v = p["view"]; row = p["row"]
        ev = v.schedule_events(now, window_h)
        wins = v.npo_windows(now)
        out = []
        firsts = {}
        for kind, key in (("basal", "basal"), ("mealtime", "prandial"), ("mealtime", "prandial_npo"), ("sulfonylurea", "su")):
            for (t, u) in ev[key]:
                if u <= 0 or kind in firsts:
                    continue
                firsts[kind] = True
                tomorrow = t.normalize() + pd.Timedelta("1D")
                d = {"kind": kind, "time": t, "units": float(u), "fasting_at_dose": key == "prandial_npo" or v._in_npo(t, wins),
                     "fasting_tomorrow": any(s < tomorrow + pd.Timedelta("1D") and e > tomorrow for s, e in wins),
                     "tonight_reduced": bool(len(v.tonight[(v.tonight.time <= now) & (v.tonight.start.dt.normalize() == t.normalize())]))}
                d["flags"] = dose_checks(row, d)
                d["compare"] = self._compare(aid, now, d, p)
                if d["compare"]["as_ordered"] >= self.b.thresholds[f"low_{p['mode']}"]["red"]:
                    d["flags"].append({"level": "high", "rule": "twin_low_risk",
                                       "text": f"Twin forecasts a {round(100 * d['compare']['as_ordered'])}% chance of a low in the next 12 h if given as ordered."})
                out.append(d)
        return sorted(out, key=lambda x: x["time"])

    def _ov_key(self, d):
        return {"basal": "basal_tonight", "mealtime": "prandial_next", "sulfonylurea": "su_hold"}[d["kind"]]

    def _compare(self, aid, now, d, p) -> dict:
        k = self._ov_key(d)
        alt = {}
        for lab, val in (("reduced_20", round(d["units"] * 0.8)), ("held", 0)):
            ov = {k: True} if d["kind"] == "sulfonylurea" else {k: val}
            if d["kind"] == "sulfonylurea" and lab == "reduced_20":
                continue
            alt[lab] = self.what_if(aid, now, ov, light=True)["p_low"]
        return {"as_ordered": p["p_low"], **alt}

    def what_if(self, aid: str, now: pd.Timestamp, overrides: dict, light: bool = False) -> dict:
        """Hybrid what-if. Insulin dose changes go through the pharmacology layer (validated against
        counterfactual simulations); the learned forecast supplies the baseline trajectory and risk."""
        base = self.predict(aid, now)
        ev = base["view"].schedule_events(now)
        changes = []
        if "basal_tonight" in overrides and ev["basal"]:
            t, u = ev["basal"][0]; changes.append((t, "basal", float(overrides["basal_tonight"]) - u))
        if "prandial_next" in overrides:
            meals = sorted(ev["prandial"] + ev["prandial_npo"])
            if meals:
                t, u = meals[0]; changes.append((t, "prandial", float(overrides["prandial_next"]) - u))
        if "su_hold" in overrides:      # no validated pharmacology for sulfonylureas: fall back to the learned model
            p = self.predict(aid, now, {"su_hold": True})
            return {"p_low": p["p_low"], "p_high": p["p_high"]} if light else p
        hours = list(base["traj"].h)
        d = ph.delta_curve(base["row"], now, changes, hours)
        tr = base["traj"].copy()
        tr["mid"] = np.clip(tr.mid + d, 40, 500); tr["lo"] = np.clip(tr.lo + d, 40, 500); tr["hi"] = np.clip(tr.hi + d, 40, 500)
        sd = (tr.hi - tr.lo) / (2 * 1.2816)
        tr["p_low"] = [_phi((T.hypo - m) / max(s_, 5)) for m, s_ in zip(tr.mid, sd)]
        tr["p_high"] = [1 - _phi((T.severe_high - m) / max(s_, 5)) for m, s_ in zip(tr.mid, sd)]
        p_low = _odds_shift(base["p_low"], base["traj"].p_low, tr.p_low)
        p_high = _odds_shift(base["p_high"], base["traj"].p_high, tr.p_high)
        out = {**base, "traj": tr, "p_low": p_low, "p_high": p_high, "delta": d, "changes": changes}
        return {"p_low": p_low, "p_high": p_high} if light else out

    # ------------------------------------------------------------------ feature 4: discharge handover
    def discharge(self, aid: str, now: pd.Timestamp | None = None) -> dict:
        tb = self.tabs(aid); e = self.w["encounters"].loc[aid]
        now = now or e["discharge_time"]
        poc = tb["poc"][tb["poc"].time <= now]; g = poc.glucose_mgdl
        labs = tb["labs"][tb["labs"].time <= now]
        hb = labs[labs.test == "hba1c"].value
        cr = labs[labs.test == "creatinine"].value
        mar = tb["mar"][(tb["mar"].time <= now) & (tb["mar"].status == "given")]
        last24 = mar[mar.time > now - 24 * H]
        ster = mar[mar.drug.isin(["prednisolone", "dexamethasone"])]
        findings, actions = [], []
        hba1c = float(hb.iloc[-1]) if len(hb) else None
        if hba1c is not None and hba1c >= 6.5 and not e["known_diabetes"]:
            findings.append(f"HbA1c {hba1c:.1f}% with no previous diabetes diagnosis: probable undiagnosed diabetes. Confirm and record the diagnosis.")
            actions.append("Diabetes clinic review within 2 weeks (new diagnosis)")
        elif hba1c is not None and 5.7 <= hba1c < 6.5 and not e["known_diabetes"]:
            findings.append(f"HbA1c {hba1c:.1f}%: prediabetes range. Hyperglycaemia in hospital may have been stress-related.")
            actions.append("Repeat HbA1c / glucose test in 3 months")
        elif hba1c is None and len(g) and (g > 180).sum() >= 2:
            findings.append("Glucose above 180 mg/dL more than once but HbA1c not measured this admission.")
            actions.append("Order HbA1c before discharge")
        n_low = int((g < T.hypo).sum()); n_l2 = int((g < T.hypo_l2).sum())
        if n_low:
            findings.append(f"{n_low} low reading(s) during the stay (lowest {g.min():.0f} mg/dL; {n_l2} below 54).")
            actions.append("Hypoglycaemia education before discharge")
        if len(ster):
            findings.append(f"Steroid course during the stay ({ster.drug.iloc[0]}, {ster.time.dt.date.nunique()} days). Glucose may fall when it stops.")
        if len(cr) and cr.max() - cr.iloc[0] >= SETTINGS.rules.aki_creatinine_rise:
            findings.append(f"Creatinine rose from {cr.iloc[0]:.1f} to {cr.max():.1f} mg/dL during the stay (latest {cr.iloc[-1]:.1f}).")
        started = (not e["home_insulin"]) and mar.drug.isin(["basal_glargine", "rapid_prandial"]).any()
        if started:
            findings.append("Insulin was started in hospital (patient was not on insulin before admission).")
            actions.append("Insulin and glucometer teaching if insulin continues at home")
        if (e["known_diabetes"] or started or (hba1c or 0) >= 6.5) and not any("Diabetes clinic" in a for a in actions):
            actions.append("Diabetes clinic follow-up within 4-6 weeks")
        metrics = {"fingersticks": int(len(g)), "mean": round(float(g.mean())) if len(g) else None,
                   "in_140_180": round(float(g.between(140, 180).mean()), 2) if len(g) else None,
                   "in_70_180": round(float(g.between(70, 180).mean()), 2) if len(g) else None,
                   "lows": n_low, "highs_250": int((g >= T.severe_high).sum())}
        reg = {"basal_last_24h_units": float(last24[last24.drug == "basal_glargine"].dose.sum()),
               "mealtime_last_24h_units": float(last24[last24.drug == "rapid_prandial"].dose.sum()),
               "correction_last_24h_units": float(last24[last24.drug == "rapid_correction"].dose.sum())}
        return {"admission_id": aid, "name": e["name"], "age": int(e["age"]), "sex": e["sex"], "reason": e["admission_reason"],
                "admit": e["admit_time"], "discharge": now, "los_days": round((now - e["admit_time"]) / pd.Timedelta("1D"), 1),
                "known_diabetes": bool(e["known_diabetes"]), "hba1c": hba1c, "metrics": metrics, "insulin_last_24h": reg,
                "findings": findings, "actions": actions}


@lru_cache(maxsize=1)
def default_twin() -> WardTwin:
    return WardTwin()
