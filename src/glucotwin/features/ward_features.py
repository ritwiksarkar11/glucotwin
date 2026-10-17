"""Causal features for the ward twin.

At update time t the twin may use:
  * everything documented at or before t (fingersticks, CGM, medications given,
    meals and intake, labs, orders), and
  * orders already written at t that schedule the future: tonight's basal dose,
    mealtime insulin, fasting (NPO) windows for booked procedures, steroid courses.
    In a hospital these are known in advance; they are what the doctor changes in
    the "before you give insulin" what-if. They are never taken from what actually
    happened later.

`tests/test_features.py` checks that changing anything recorded after t leaves the
features at t unchanged, and that the streaming twin reproduces batch features.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import RISK_HORIZON_H, SETTINGS, TRAJ_HORIZONS_H

W = SETTINGS.ward
MEAL_H = (W.breakfast_h, W.lunch_h, W.dinner_h)
ADM_TYPES = ["infection", "cardiac_surgery", "respiratory", "heart_failure", "ortho_surgery"]
H = pd.Timedelta(hours=1)

POC_F = ["last_poc", "mins_since_poc", "poc_prev", "poc_delta", "poc_min_24h", "poc_max_24h", "poc_mean_24h",
         "n_poc_24h", "n_low_72h", "n_lt100_24h", "n_gt250_24h", "poc_max_afternoon_yday", "poc_same_time_yday"]
CGM_F = ["cgm_now", "cgm_slope30", "cgm_min_6h", "cgm_max_6h", "cgm_mean_6h", "cgm_std_6h", "cgm_cov_2h",
         "mins_since_cgm", "cgm_min_24h", "cgm_next12_yday_min", "cgm_next12_yday_max", "cgm_next12_yday_mean"]
INS_F = ["basal_given_24h", "rapid_given_6h", "rapid_iob", "basal_iob", "su_given_24h", "tdd_per_kg_24h",
         "basal_order_units", "basal_change_24h", "prandial_order_units", "correction_scale"]
FUT_F = ["basal_sched_12h", "prandial_sched_12h", "prandial_npo_12h", "su_sched_12h", "meals_sched_12h",
         "npo_now", "npo_hours_12h", "steroid_sched_12h", "hours_to_next_poc"]
NUT_F = ["last_intake", "mean_intake_24h", "carbs_eaten_6h", "hypo_treat_2h", "dextrose_infusion"]
STER_F = ["steroid_today_mg", "hours_since_steroid", "steroid_stopped_24h", "steroid_any_72h"]
REN_F = ["creat_last", "creat_delta_48h", "creat_vs_admit", "aki_flag"]
CLIN_F = ["age", "weight_kg", "bmi", "hba1c", "hba1c_known", "known_diabetes", "home_insulin", "home_sulfonylurea",
          "ckd", "heart_failure", "days_since_admit", "hours_since_surgery", "surgery_next_24h"] + [f"type_{a}" for a in ADM_TYPES]
TIME_F = ["tod_sin", "tod_cos"]

FEATURES_A = POC_F + INS_F + FUT_F + NUT_F + STER_F + REN_F + CLIN_F + TIME_F     # fingerstick ward (default)
FEATURES_B = FEATURES_A + CGM_F                                                 # CGM-assisted
STATIC_F = ["age", "weight_kg", "bmi", "hba1c", "hba1c_known", "known_diabetes", "home_insulin", "home_sulfonylurea",
            "ckd", "heart_failure", "admit_poc", "creat_admit"] + [f"type_{a}" for a in ADM_TYPES]
WIN_F = ["h", "basal_sched_h", "prandial_sched_h", "meals_sched_h", "npo_hours_h", "steroid_sched_h", "su_sched_h",
         "target_tod_sin", "target_tod_cos"]

# Monotone constraints: more scheduled insulin / fasting -> lower glucose & higher low-risk; more food / steroid -> higher.
_UP_LOW = {"basal_sched_12h", "prandial_sched_12h", "prandial_npo_12h", "su_sched_12h", "npo_hours_12h", "rapid_iob",
           "basal_sched_h", "prandial_sched_h", "npo_hours_h", "su_sched_h"}
_DOWN_LOW = {"meals_sched_12h", "steroid_sched_12h", "meals_sched_h", "steroid_sched_h"}


def monotone(features: list[str], target: str) -> list[int]:
    sgn = {"low": 1, "high": -1, "glucose": -1}[target]
    return [sgn if f in _UP_LOW else -sgn if f in _DOWN_LOW else 0 for f in features]


# ------------------------------------------------------------------ helpers
def _iob(dt_min: np.ndarray, tau: float) -> np.ndarray:
    x = np.clip(dt_min, 0, None) / tau
    return (1 + x) * np.exp(-x)


def _clock_times(t0: pd.Timestamp, t1: pd.Timestamp, hours: tuple) -> list[pd.Timestamp]:
    """All clock times (e.g. meal times) in (t0, t1]."""
    out = []
    d = t0.normalize()
    while d <= t1:
        for h in hours:
            x = d + pd.Timedelta(hours=h)
            if t0 < x <= t1:
                out.append(x)
        d += pd.Timedelta(days=1)
    return out


class AdmissionView:
    """Pre-indexed tables of one admission for fast feature computation at many times."""

    def __init__(self, tabs: dict, overrides: dict | None = None):
        self.e = tabs["encounter"]
        self.poc_t = tabs["poc"]["time"].to_numpy("datetime64[ns]"); self.poc_v = tabs["poc"]["glucose_mgdl"].to_numpy(float)
        c = tabs["cgm"]
        self.cgm = pd.Series(c["glucose_mgdl"].to_numpy(float), index=pd.DatetimeIndex(c["time"])).sort_index() if len(c) else pd.Series(dtype=float)
        m = tabs["mar"]; g = m[m.status == "given"]
        self.mar_t = g["time"].to_numpy("datetime64[ns]"); self.mar_d = g["drug"].to_numpy(); self.mar_v = g["dose"].to_numpy(float)
        o = tabs["orders"]
        self.orders = o
        self.basal = o[o.kind == "basal_units"][["time", "value"]].assign(value=lambda x: x.value.astype(float))
        self.prand = o[o.kind == "prandial_units"][["time", "value"]].assign(value=lambda x: x.value.astype(float))
        self.corr = o[o.kind == "correction_scale"][["time", "value"]]
        self.su = o[o.kind == "sulfonylurea"][["time", "value"]]
        self.tonight = o[o.kind == "basal_tonight_units"][["time", "start", "value"]].assign(value=lambda x: x.value.astype(float))
        self.npo = o[o.kind == "npo"][["time", "start", "end"]]
        self.ster = o[o.kind == "steroid_dose"][["time", "start", "value"]].assign(value=lambda x: x.value.astype(float))
        me = tabs["meals"]
        self.meal_t = me["time"].to_numpy("datetime64[ns]"); self.meal_f = me["intake_fraction"].to_numpy(float)
        self.meal_c = (me["carbs_served_g"] * me["intake_fraction"]).to_numpy(float)
        lb = tabs["labs"]
        cr = lb[lb.test == "creatinine"]; self.cr_t = cr["time"].to_numpy("datetime64[ns]"); self.cr_v = cr["value"].to_numpy(float)
        hb = lb[lb.test == "hba1c"]; self.hb_t = hb["time"].to_numpy("datetime64[ns]"); self.hb_v = hb["value"].to_numpy(float)
        self.ov = overrides or {}

    # -------------------------------------------------------------- order lookups (known at t)
    @staticmethod
    def _latest(df: pd.DataFrame, t, default):
        x = df[df.time <= t]
        return x["value"].iloc[-1] if len(x) else default

    def basal_units_at(self, t):
        return float(self._latest(self.basal, t, 0.0))

    def prandial_units_at(self, t):
        return float(self._latest(self.prand, t, 0.0))

    def npo_windows(self, t):
        x = self.npo[self.npo.time <= t]
        w = list(zip(x.start, x.end))
        if self.ov.get("fasting_until") is not None:
            w.append((t, self.ov["fasting_until"]))
        return w

    def _in_npo(self, x, wins):
        return any(s <= x < e for s, e in wins)

    def schedule_events(self, t: pd.Timestamp, hours: float = RISK_HORIZON_H) -> dict:
        """Everything scheduled in (t, t+hours] by orders known at t (plus what-if overrides).

        Returns event lists [(time, amount)] per kind and a 15-minute fasting grid."""
        t1 = t + hours * H
        wins = self.npo_windows(t)
        basal = self.basal_units_at(t); prand = self.prandial_units_at(t)
        ev = {"basal": [], "prandial": [], "prandial_npo": [], "meals": [], "steroid": [], "su": []}
        first_basal = _clock_times(t, t + 24 * H, (W.basal_h,))[0]
        for bt in _clock_times(t, t1, (W.basal_h,)):
            ton = self.tonight[(self.tonight.time <= t) & (self.tonight.start.dt.normalize() == bt.normalize())]
            u = float(ton["value"].iloc[-1]) if len(ton) else basal
            if "basal_tonight" in self.ov and bt == first_basal:
                u = float(self.ov["basal_tonight"])
            ev["basal"].append((bt, u))
        for n, mt in enumerate(_clock_times(t, t1, MEAL_H)):
            p = float(self.ov["prandial_next"]) if (n == 0 and "prandial_next" in self.ov) else prand
            if self._in_npo(mt, wins):
                ev["prandial_npo"].append((mt, p))
            else:
                ev["meals"].append((mt, 1.0)); ev["prandial"].append((mt, p))
        su_on = str(self._latest(self.su, t, "")).startswith("glimepiride") and not self.ov.get("su_hold", False)
        if su_on:
            ev["su"] = [(x, 2.0) for x in _clock_times(t, t1, (W.steroid_h,))]
        if "steroid_mg" in self.ov:
            ev["steroid"] = [(x, float(self.ov["steroid_mg"])) for x in _clock_times(t, t1, (W.steroid_h,))]
        else:
            s = self.ster[(self.ster.time <= t) & (self.ster.start > t) & (self.ster.start <= t1)]
            ev["steroid"] = list(zip(s.start, s.value))
        grid = pd.date_range(t, t1, freq="15min", inclusive="right")
        ev["npo_grid"] = (grid, np.array([self._in_npo(g, wins) for g in grid]) if wins else np.zeros(len(grid), bool))
        return ev

    @staticmethod
    def window_sums(ev: dict, t: pd.Timestamp, h: float) -> dict:
        lim = t + h * H
        out = {k: sum(a for (x, a) in ev[k] if x <= lim) for k in ("basal", "prandial", "prandial_npo", "steroid", "su")}
        out["meals"] = sum(1 for (x, _) in ev["meals"] if x <= lim)
        g, f = ev["npo_grid"]; out["npo_hours"] = float(f[g <= lim].sum()) * 0.25
        return out

    def scheduled(self, t: pd.Timestamp, t1: pd.Timestamp) -> dict:
        h = (t1 - t) / H
        return self.window_sums(self.schedule_events(t, h), t, h)

    # -------------------------------------------------------------- feature row(s)
    def features(self, times: pd.DatetimeIndex, horizons: tuple | None = None) -> pd.DataFrame:
        rows = []
        e = self.e
        admit = e["admit_time"]
        for t in times:
            tn = np.datetime64(t)
            r: dict = {"admission_id": e.name, "time": t}
            # ---- fingersticks
            i = np.searchsorted(self.poc_t, tn, "right")
            if i:
                r["last_poc"] = self.poc_v[i - 1]; r["mins_since_poc"] = (tn - self.poc_t[i - 1]) / np.timedelta64(1, "m")
                r["poc_prev"] = self.poc_v[i - 2] if i > 1 else np.nan
                r["poc_delta"] = r["last_poc"] - r["poc_prev"] if i > 1 else np.nan
            else:
                r.update(last_poc=np.nan, mins_since_poc=np.nan, poc_prev=np.nan, poc_delta=np.nan)
            j24 = np.searchsorted(self.poc_t, tn - np.timedelta64(24, "h"), "right"); w24 = self.poc_v[j24:i]
            j72 = np.searchsorted(self.poc_t, tn - np.timedelta64(72, "h"), "right")
            r["poc_min_24h"] = w24.min() if len(w24) else np.nan; r["poc_max_24h"] = w24.max() if len(w24) else np.nan
            r["poc_mean_24h"] = w24.mean() if len(w24) else np.nan; r["n_poc_24h"] = len(w24)
            r["n_low_72h"] = int((self.poc_v[j72:i] < 70).sum()); r["n_lt100_24h"] = int((w24 < 100).sum())
            r["n_gt250_24h"] = int((w24 >= 250).sum())
            y0 = np.datetime64(t.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=12)); y1 = y0 + np.timedelta64(11, "h")
            a, b = np.searchsorted(self.poc_t, y0), np.searchsorted(self.poc_t, min(y1, tn), "right")
            r["poc_max_afternoon_yday"] = self.poc_v[a:b].max() if b > a else np.nan
            s0, s1 = np.searchsorted(self.poc_t, tn - np.timedelta64(25, "h")), np.searchsorted(self.poc_t, tn - np.timedelta64(23, "h"), "right")
            r["poc_same_time_yday"] = self.poc_v[s0:s1].mean() if s1 > s0 else np.nan
            # ---- CGM
            if len(self.cgm):
                c = self.cgm.loc[:t]
                last = c.index[-1] if len(c) else None
                r["mins_since_cgm"] = (t - last) / pd.Timedelta("1min") if last is not None else np.nan
                r["cgm_now"] = c.iloc[-1] if last is not None and r["mins_since_cgm"] <= SETTINGS.rules.cgm_stale_min else np.nan
                c30 = c.loc[t - pd.Timedelta("30min"):]
                r["cgm_slope30"] = (c30.iloc[-1] - c30.iloc[0]) / max((c30.index[-1] - c30.index[0]) / pd.Timedelta("1min"), 1) if len(c30) > 2 else np.nan
                c6 = c.loc[t - 6 * H:]
                r["cgm_min_6h"], r["cgm_max_6h"] = (c6.min(), c6.max()) if len(c6) else (np.nan, np.nan)
                r["cgm_mean_6h"], r["cgm_std_6h"] = (c6.mean(), c6.std()) if len(c6) else (np.nan, np.nan)
                r["cgm_cov_2h"] = len(c.loc[t - 2 * H:]) / 24.0
                c24 = c.loc[t - 24 * H:]; r["cgm_min_24h"] = c24.min() if len(c24) else np.nan
                yd = c.loc[t - 24 * H: t - 12 * H]
                r["cgm_next12_yday_min"], r["cgm_next12_yday_max"], r["cgm_next12_yday_mean"] = (yd.min(), yd.max(), yd.mean()) if len(yd) else (np.nan,) * 3
            else:
                for f in CGM_F:
                    r[f] = np.nan
            # ---- insulin & drugs given
            k = np.searchsorted(self.mar_t, tn, "right")
            mt, md, mv = self.mar_t[:k], self.mar_d[:k], self.mar_v[:k]
            ago = (tn - mt) / np.timedelta64(1, "m")
            isr = np.isin(md, ["rapid_prandial", "rapid_correction"]); isb = md == "basal_glargine"
            r["basal_given_24h"] = mv[isb & (ago <= 1440)].sum(); r["rapid_given_6h"] = mv[isr & (ago <= 360)].sum()
            r["rapid_iob"] = (mv[isr] * _iob(ago[isr], 55)).sum(); r["basal_iob"] = (mv[isb] * _iob(ago[isb], 420)).sum()
            r["su_given_24h"] = mv[(md == "glimepiride") & (ago <= 1440)].sum()
            r["tdd_per_kg_24h"] = mv[(isr | isb) & (ago <= 1440)].sum() / e["weight_kg"]
            r["hypo_treat_2h"] = mv[np.isin(md, ["oral_glucose", "dextrose_iv"]) & (ago <= 120)].sum()
            dx = (md == "dextrose_5pct_infusion")
            r["dextrose_infusion"] = float(dx.any() and ago[dx].min() <= 12 * 60)
            r["basal_order_units"] = self.basal_units_at(t)
            r["basal_change_24h"] = r["basal_order_units"] - self.basal_units_at(t - 24 * H)
            r["prandial_order_units"] = self.prandial_units_at(t)
            cs = str(self._latest(self.corr, t, "none")); r["correction_scale"] = {"none": 0, "sensitive": 1, "standard": 2}.get(cs, 0)
            # ---- schedule (known orders)
            ev = self.schedule_events(t)
            sc = self.window_sums(ev, t, RISK_HORIZON_H)
            r["basal_sched_12h"], r["prandial_sched_12h"], r["prandial_npo_12h"] = sc["basal"], sc["prandial"], sc["prandial_npo"]
            r["su_sched_12h"], r["meals_sched_12h"], r["npo_hours_12h"], r["steroid_sched_12h"] = sc["su"], sc["meals"], sc["npo_hours"], sc["steroid"]
            r["npo_now"] = float(self._in_npo(t, self.npo_windows(t)))
            sched = W.poc_insulin if r["correction_scale"] or r["basal_order_units"] or r["prandial_order_units"] else W.poc_no_insulin
            nxt = _clock_times(t, t + 24 * H, sched)
            r["hours_to_next_poc"] = (nxt[0] - t) / H if nxt else np.nan
            # ---- nutrition
            q = np.searchsorted(self.meal_t, tn, "right")
            r["last_intake"] = self.meal_f[q - 1] if q else np.nan
            q24 = np.searchsorted(self.meal_t, tn - np.timedelta64(24, "h"), "right")
            r["mean_intake_24h"] = self.meal_f[q24:q].mean() if q > q24 else np.nan
            q6 = np.searchsorted(self.meal_t, tn - np.timedelta64(6, "h"), "right"); r["carbs_eaten_6h"] = self.meal_c[q6:q].sum()
            # ---- steroids
            sg = np.isin(md, ["prednisolone", "dexamethasone"])
            sm = np.where(md == "dexamethasone", mv / 0.15, mv)
            today = sg & (ago <= ((tn - np.datetime64(t.normalize())) / np.timedelta64(1, "m")))
            r["steroid_today_mg"] = sm[today].sum()
            r["hours_since_steroid"] = ago[sg].min() / 60 if sg.any() else np.nan
            r["steroid_any_72h"] = float((sg & (ago <= 4320)).any())
            r["steroid_stopped_24h"] = float(bool((sg & (ago <= 2880)).any()) and sc["steroid"] == 0 and r["steroid_today_mg"] == 0)
            # ---- renal
            u = np.searchsorted(self.cr_t, tn, "right")
            if u:
                r["creat_last"] = self.cr_v[u - 1]
                u48 = np.searchsorted(self.cr_t, tn - np.timedelta64(48, "h"))
                r["creat_delta_48h"] = self.cr_v[u - 1] - self.cr_v[u48:u].min()
                r["creat_vs_admit"] = self.cr_v[u - 1] - self.cr_v[0]
            else:
                r["creat_last"] = r["creat_delta_48h"] = r["creat_vs_admit"] = np.nan
            r["aki_flag"] = float((r["creat_delta_48h"] or 0) >= SETTINGS.rules.aki_creatinine_rise)
            # ---- clinical
            hb = np.searchsorted(self.hb_t, tn, "right")
            r["hba1c"] = self.hb_v[hb - 1] if hb else np.nan; r["hba1c_known"] = float(hb > 0)
            for f in ("age", "weight_kg", "bmi"):
                r[f] = float(e[f])
            for f in ("known_diabetes", "home_insulin", "home_sulfonylurea", "ckd", "heart_failure"):
                r[f] = float(bool(e[f]))
            r["days_since_admit"] = (t - admit) / pd.Timedelta("1D")
            st_ = e["surgery_time"]
            r["hours_since_surgery"] = (t - st_) / H if pd.notna(st_) and st_ <= t else np.nan
            r["surgery_next_24h"] = float(pd.notna(st_) and t < st_ <= t + 24 * H)
            for a in ADM_TYPES:
                r[f"type_{a}"] = float(e["admission_type"] == a)
            tod = (t.hour + t.minute / 60) / 24
            r["tod_sin"], r["tod_cos"] = np.sin(2 * np.pi * tod), np.cos(2 * np.pi * tod)
            r["admit_poc"] = self.poc_v[0] if len(self.poc_v) else np.nan
            r["creat_admit"] = self.cr_v[0] if len(self.cr_v) else np.nan
            if horizons:
                for h in horizons:
                    rh = dict(r); w = self.window_sums(ev, t, h)
                    tt = t + h * H; td = (tt.hour + tt.minute / 60) / 24
                    rh.update(h=h, basal_sched_h=w["basal"], prandial_sched_h=w["prandial"], meals_sched_h=w["meals"],
                              npo_hours_h=w["npo_hours"], steroid_sched_h=w["steroid"], su_sched_h=w["su"],
                              target_tod_sin=np.sin(2 * np.pi * td), target_tod_cos=np.cos(2 * np.pi * td))
                    rows.append(rh)
            else:
                rows.append(r)
        return pd.DataFrame(rows)


def targets(view: AdmissionView, times: pd.DatetimeIndex, horizons=TRAJ_HORIZONS_H) -> pd.DataFrame:
    """CGM-based outcomes (training/evaluation only; uses the future)."""
    c = view.cgm
    out = []
    for t in times:
        w = c.loc[t + pd.Timedelta("1min"): t + RISK_HORIZON_H * H]
        cov = len(w) / (RISK_HORIZON_H * 12)
        r = {"time": t, "cgm_cov_12h": cov,
             "y_low": float(w.min() < SETTINGS.thr.hypo) if cov >= 0.5 else np.nan,
             "y_high": float(w.max() >= SETTINGS.thr.severe_high) if cov >= 0.5 else np.nan,
             "y_min12": w.min() if cov >= 0.5 else np.nan, "y_max12": w.max() if cov >= 0.5 else np.nan}
        for h in horizons:
            x = c.loc[t + h * H - pd.Timedelta("10min"): t + h * H + pd.Timedelta("10min")]
            r[f"y_g{h}"] = x.mean() if len(x) else np.nan
        out.append(r)
    return pd.DataFrame(out)
