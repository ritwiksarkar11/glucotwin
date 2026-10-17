"""Synthetic hospital-ward simulator for inpatients with diabetes or hyperglycaemia.

Each admission is simulated at 5-minute resolution from admission to discharge.
Two layers interact inside the same loop:

1. Physiology (hidden): glucose responds to hospital meals (and how much of
   each meal the patient actually eats), rapid-acting and basal insulin,
   sulfonylureas, glucocorticoids (peak effect in the afternoon/evening after a
   morning dose), illness/post-operative stress that fades over days, acute
   kidney injury (insulin lasts longer and works harder), IV dextrose, and
   counter-regulation below 70 mg/dL.

2. The ward process (observable): fingerstick (POC) checks on a fixed protocol,
   sliding-scale correction insulin, basal-bolus orders, a daily consultant
   round that titrates insulin, fasting (NPO) orders before procedures,
   steroid courses, morning creatinine, hypoglycaemia treatment with 15-minute
   rechecks, and nurses recording meal intake. Realistic process failures are
   injected at stated probabilities (e.g. mealtime insulin given while fasting,
   basal not reduced before surgery, insulin not reduced after steroids stop).
   They are recorded in hidden ground truth only.

About half of admissions also wear a CGM (a "study" cohort, as in inpatient
CGM trials). CGM supplies outcome labels for training/evaluation and the
real-time input for the twin's CGM-assisted mode.

Everything is fictional and generated from the seed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import SETTINGS

STEP = 5
EPOCH = pd.Timestamp("2026-08-01 00:00:00")

FIRST_M = ["Arjun", "Rahul", "Vikram", "Suresh", "Anil", "Rakesh", "Imran", "Joseph", "Harpreet", "Karthik", "Manoj",
           "Prakash", "Sanjay", "Deepak", "Farhan", "Gaurav", "Naveen", "Ramesh", "Tarun", "Vinod", "Ashok", "Mohan"]
FIRST_F = ["Priya", "Anita", "Sunita", "Kavya", "Meena", "Fatima", "Lakshmi", "Neha", "Pooja", "Rekha", "Shalini",
           "Divya", "Geeta", "Ishita", "Mary", "Nandini", "Radha", "Sana", "Usha", "Zoya", "Kamla", "Savitri"]
LAST = ["Sharma", "Verma", "Iyer", "Reddy", "Nair", "Khan", "Gupta", "Patel", "Singh", "Das", "Menon", "Joshi", "Rao",
        "Kulkarni", "Banerjee", "Fernandes", "Chopra", "Mishra", "Pillai", "Ansari", "Yadav", "Saxena", "Tiwari"]

ADMISSION_TYPES = {
    #                    p,    LOS days, stress, AKI p, steroid p, surgery
    "infection":        (0.30, (4, 9), 0.35, 0.30, 0.15, False),
    "cardiac_surgery":  (0.18, (6, 10), 0.45, 0.25, 0.05, True),
    "respiratory":      (0.20, (4, 8), 0.20, 0.05, 0.95, False),
    "heart_failure":    (0.17, (5, 9), 0.20, 0.35, 0.03, False),
    "ortho_surgery":    (0.15, (3, 6), 0.25, 0.05, 0.03, True),
}
TYPE_LABEL = {"infection": "Pneumonia / sepsis", "cardiac_surgery": "Cardiac surgery (CABG)",
              "respiratory": "COPD / asthma exacerbation", "heart_failure": "Heart failure",
              "ortho_surgery": "Orthopaedic surgery"}
DM_STATUS = {"t2d_oral": 0.40, "t2d_insulin": 0.25, "undiagnosed": 0.15, "stress_only": 0.20}

# process-failure probabilities (documented in docs/data_card.md)
P_PRANDIAL_GIVEN_NPO = 0.20
P_BASAL_REDUCED_BEFORE_NPO = 0.50
P_REDUCE_AFTER_STEROID_STOP = 0.40
P_REDUCE_ON_AKI = 0.40
P_SU_CONTINUED = 0.30
P_SU_GIVEN_NPO = 0.50
P_STEROID_COVER = 0.35
P_TITRATE_AFTER_LOW = 0.85


@dataclass
class Admission:
    idx: int
    admission_id: str
    patient_id: str
    name: str
    sex: str
    age: int
    weight: float
    height: float
    adm_type: str
    dm_status: str
    hba1c: float
    hba1c_measured: bool
    creat_base: float
    ckd: bool
    heart_failure: bool
    home_su: bool
    home_insulin_tdd: float
    start_min: int
    los_steps: int
    cgm: bool
    surgery_min: int | None
    npo: list = field(default_factory=list)          # [(order_min, start_min, end_min, reason)]
    steroid: list = field(default_factory=list)      # [(day_abs, mg_pred_equiv, drug)]
    steroid_order_min: int | None = None
    aki: tuple | None = None                          # (onset_min, peak_rise, duration_min)
    # hidden physiology
    gb: float = 140.0
    k: float = 0.009
    meal_gain: float = 3.0
    isf: float = 45.0
    stress_amp: float = 0.3
    steroid_gain: float = 90.0
    tau_meal: float = 40.0


def _choice(rng, d: dict):
    keys = list(d); p = np.array([d[k] if not isinstance(d[k], tuple) else d[k][0] for k in keys], float)
    return keys[int(rng.choice(len(keys), p=p / p.sum()))]


def make_admissions(rng: np.random.Generator, n: int, window_days: int) -> list[Admission]:
    out = []
    for i in range(n):
        t = _choice(rng, ADMISSION_TYPES)
        p_t, los_rng, stress, p_aki, p_ster, surg = ADMISSION_TYPES[t]
        dm = _choice(rng, DM_STATUS)
        sex = "female" if rng.random() < 0.42 else "male"
        age = int(np.clip(rng.normal(62, 12), 28, 90))
        height = float(np.clip(rng.normal(163 if sex == "male" else 153, 7), 140, 190))
        weight = float(np.clip(rng.normal(70 if sex == "male" else 62, 12), 38, 130))
        hba1c = {"t2d_oral": rng.normal(8.0, 1.3), "t2d_insulin": rng.normal(8.9, 1.5),
                 "undiagnosed": rng.normal(7.4, 0.9), "stress_only": rng.normal(5.9, 0.3)}[dm]
        hba1c = float(np.clip(hba1c, 6.5 if dm == "undiagnosed" else 5.0, 6.4 if dm == "stress_only" else 13.5))
        ckd = rng.random() < 0.18 + 0.004 * (age - 60)
        creat = float(np.clip(rng.normal(1.9 if ckd else 0.95, 0.35 if ckd else 0.18), 0.5, 3.5))
        start_day = int(rng.integers(0, window_days))
        start_min = start_day * 1440 + int(rng.integers(8 * 12, 22 * 12)) * 5
        los = int(rng.integers(los_rng[0], los_rng[1] + 1))
        los_steps = los * 288 + int(rng.integers(-24, 36))
        a = Admission(
            idx=i, admission_id=f"ENC-{i + 1:04d}", patient_id=f"W-{i + 1:04d}",
            name=f"{rng.choice(FIRST_F if sex == 'female' else FIRST_M)} {rng.choice(LAST)}", sex=sex, age=age,
            weight=round(weight, 1), height=round(height, 1), adm_type=t, dm_status=dm, hba1c=round(hba1c, 1),
            hba1c_measured=bool(rng.random() < 0.65), creat_base=round(creat, 2), ckd=bool(ckd),
            heart_failure=(t == "heart_failure") or bool(rng.random() < 0.08),
            home_su=(dm == "t2d_oral") and bool(rng.random() < 0.40),
            home_insulin_tdd=float(np.clip(rng.normal(0.5, 0.15), 0.2, 1.0) * weight) if dm == "t2d_insulin" else 0.0,
            start_min=start_min, los_steps=los_steps, cgm=bool(rng.random() < 0.5), surgery_min=None)
        day0 = start_min // 1440
        # surgery & fasting windows (ordered at the previous day's round)
        if surg:
            sd = day0 + (1 if rng.random() < 0.7 else 2)
            a.surgery_min = sd * 1440 + 9 * 60
            end = sd * 1440 + (16 * 60 if t == "cardiac_surgery" else 13 * 60)
            a.npo.append((max(start_min, (sd - 1) * 1440 + 9 * 60), sd * 1440, end, "surgery"))
        if rng.random() < 0.18:  # endoscopy / imaging with contrast etc.
            pd_ = day0 + int(rng.integers(1, max(2, los - 1)))
            a.npo.append(((pd_ - 1) * 1440 + 9 * 60, pd_ * 1440, pd_ * 1440 + 11 * 60, "procedure"))
        # steroid course
        if rng.random() < p_ster:
            first = day0 if (start_min % 1440) < 8 * 60 else day0 + 1
            if t == "respiratory":
                days = int(rng.integers(5, 8)); dose = 40.0; drug = "prednisolone"
                course = [dose] * days
                if rng.random() < 0.3:
                    course += [20.0, 20.0]
            else:
                days = int(rng.integers(5, 8)); drug = "dexamethasone"
                course = [40.0] * days  # 6 mg dexamethasone ~ 40 mg prednisolone equivalent
            a.steroid = [(first + j, mg, drug) for j, mg in enumerate(course)]
            a.steroid_order_min = start_min
        if rng.random() < p_aki or (ckd and rng.random() < 0.15):
            onset = start_min + int(rng.uniform(0.5, 3.0) * 1440)
            a.aki = (onset, float(rng.uniform(0.4, 1.4)), int(rng.uniform(2.0, 5.0) * 1440))
        # hidden physiology
        eag = 28.7 * a.hba1c - 46.7
        a.gb = float(np.clip(eag * rng.normal(0.95, 0.08) if dm != "stress_only" else rng.normal(112, 10), 90, 300))
        a.k = float(np.clip(rng.normal(0.0085, 0.0018), 0.004, 0.015))
        a.meal_gain = float(np.clip(rng.lognormal(np.log(2.6 + 0.25 * (a.hba1c - 7)), 0.22), 1.2, 6.0))
        tdd_equiv = 0.5 * weight * (1 + 0.1 * (a.hba1c - 7))
        a.isf = float(np.clip(1500 / tdd_equiv * rng.lognormal(0, 0.25), 15, 110))
        a.stress_amp = float(np.clip(stress * rng.lognormal(0, 0.35), 0.03, 1.2))
        a.steroid_gain = float(np.clip(rng.normal(95 if dm != "stress_only" else 55, 25), 20, 180))
        a.tau_meal = float(np.clip(rng.normal(40, 8), 25, 65))
        out.append(a)
    return out


def _aki_level(a: Admission, t: int) -> float:
    if not a.aki:
        return 0.0
    onset, rise, dur = a.aki
    if t < onset:
        return 0.0
    x = (t - onset) / dur
    return float(rise * (np.sin(np.pi * min(x, 1.0)) if x < 1 else 0.0) + (rise * 0.2 if x >= 1 and x < 1.5 else 0.0))


def _in_npo(a: Admission, t: int) -> bool:
    return any(s <= t < e for (_, s, e, _) in a.npo)


def _npo_ordered_for(a: Admission, day_start: int, known_at: int) -> bool:
    return any(o <= known_at and s < day_start + 1440 and e > day_start for (o, s, e, _) in a.npo)


def _sliding_scale(g: float, bedtime: bool, sensitive: bool) -> float:
    if bedtime:
        u = 0 if g < 201 else 2 if g < 251 else 3 if g < 301 else 4 if g < 351 else 5
    else:
        u = 0 if g < 151 else 2 if g < 201 else 4 if g < 251 else 6 if g < 301 else 8 if g < 351 else 10
    return u * (0.5 if sensitive else 1.0)


def simulate(adms: list[Admission], seed: int, interventions: dict | None = None) -> dict[str, pd.DataFrame]:
    """interventions: {admission idx: [(abs_minute, "basal"|"prandial", factor)]} multiplies that dose.
    Every patient has independent random streams (keyed by seed and admission idx), so re-running one
    patient with an intervention reproduces the baseline exactly up to the intervention: a clean counterfactual."""
    rng = np.random.default_rng(seed)
    interventions = interventions or {}
    prng = [np.random.default_rng([seed, a.idx]) for a in adms]

    def iv(i, t, kind):
        return float(np.prod([f for (tt, k, f) in interventions.get(adms[i].idx, []) if tt == t and k == kind] or [1.0]))
    W = SETTINGS.ward
    P = len(adms)
    K = max(a.los_steps for a in adms)
    S = np.array([a.start_min for a in adms])
    los = np.array([a.los_steps for a in adms])

    # ---------------- per-patient parameters as arrays
    gb = np.array([a.gb for a in adms]); kk = np.array([a.k for a in adms])
    mg = np.array([a.meal_gain for a in adms]); isf = np.array([a.isf for a in adms])
    tau_m = np.array([a.tau_meal for a in adms]); s_gain = np.array([a.steroid_gain for a in adms])
    s_amp = np.array([a.stress_amp for a in adms])

    # ---------------- ward state (python, per patient)
    st = []
    for a in adms:
        on_ins = a.dm_status == "t2d_insulin"
        st.append(dict(
            basal=round(0.8 * 0.5 * a.home_insulin_tdd) if on_ins else 0.0,
            prandial=round(0.06 * a.weight) if on_ins else 0.0,
            correction=on_ins or a.dm_status == "t2d_oral",
            sensitive=a.age > 75 or a.ckd or a.weight < 50,
            su=a.home_su and prng[len(st)].random() < P_SU_CONTINUED,
            protocol_qid=on_ins or a.dm_status == "t2d_oral",
            poc_24h=[], last_poc=None, recheck_at=None, cover_steroid=1.0,
            reduced_for_steroid_stop=False, reduced_for_aki=False, aki_detected=False,
            basal_tonight_factor=1.0, dex_infusion=False))

    rec = {k: [] for k in ("poc", "mar", "orders", "meals", "labs", "errors")}

    def order(i, t, kind, value, start=None, end=None, note=""):
        rec["orders"].append((i, t, kind, value, t if start is None else start, end, note))

    for i, a in enumerate(adms):
        s = st[i]; t0 = a.start_min
        order(i, t0, "diet", "diabetic", note="admission")
        if s["basal"]:
            order(i, t0, "basal_units", s["basal"], note="home insulin continued at 80%")
        if s["prandial"]:
            order(i, t0, "prandial_units", s["prandial"], note="basal-bolus")
        order(i, t0, "correction_scale", "sensitive" if s["sensitive"] else "standard" if s["correction"] else "none")
        if a.home_su:
            order(i, t0, "sulfonylurea", "glimepiride 2 mg" if s["su"] else "held", note="home medication")
        for (o, s0, e0, why) in a.npo:
            order(i, o, "npo", why, start=s0, end=e0)
        if a.steroid:
            d0, mg0, drug = a.steroid[0]
            order(i, a.steroid_order_min, "steroid_course", f"{drug} {len(a.steroid)} days",
                  start=d0 * 1440 + int(W.steroid_h * 60), end=(a.steroid[-1][0] + 1) * 1440)
            for (d, mgv, drug) in a.steroid:
                order(i, a.steroid_order_min, "steroid_dose", mgv, start=d * 1440 + int(W.steroid_h * 60),
                      end=d * 1440 + int(W.steroid_h * 60) + 5, note=drug)
        if a.surgery_min:
            order(i, t0, "procedure", "surgery", start=a.surgery_min, end=a.surgery_min + 240)

    # ---------------- continuous state
    G = gb * (1 + s_amp) + np.array([prng[i].normal(0, 25) for i in range(P)])
    G = np.clip(G, 90, 420)
    q1 = np.zeros(P); q2 = np.zeros(P); f1 = np.zeros(P)
    r1 = np.zeros(P); r2 = np.zeros(P); b1 = np.zeros(P); b2 = np.zeros(P); u1 = np.zeros(P); u2 = np.zeros(P)
    s1 = np.zeros(P); s2 = np.zeros(P); w = np.zeros(P)
    # basal insulin already on board for home-insulin users
    for i, a in enumerate(adms):
        if st[i]["basal"]:
            b2[i] = st[i]["basal"] * 0.45; b1[i] = st[i]["basal"] * 0.25
    truth = np.full((P, K), np.nan, np.float32)
    cgm = np.full((P, K), np.nan, np.float32)
    cgm_on = np.array([a.cgm for a in adms])
    # per-patient physiological and sensor noise, drawn up front from per-patient streams
    nrng = [np.random.default_rng([seed, a.idx, 1]) for a in adms]
    W_N = np.stack([g.normal(0, 0.9, K) for g in nrng]); DR_N = np.stack([g.normal(0, 0.5, K) for g in nrng])
    OB_N = np.stack([g.normal(0, 1, K) for g in nrng]); DROP = np.stack([g.random(K) for g in nrng])
    drift = np.array([g.normal(0, 4) for g in nrng])

    minute = lambda h: int(round(h * 60))
    MEALS = {minute(W.breakfast_h): "breakfast", minute(W.lunch_h): "lunch", minute(W.dinner_h): "dinner"}
    BASAL_T = minute(W.basal_h); STER_T = minute(W.steroid_h); ROUND_T = minute(W.round_h); LAB_T = minute(W.lab_h)
    POC_Q = {minute(h) for h in W.poc_insulin}; POC_B = {minute(h) for h in W.poc_no_insulin}
    BEDTIME = minute(22.0)
    EVENT_MIN = np.array(sorted(set(MEALS) | {BASAL_T, STER_T, ROUND_T, LAB_T, 0, 660, 780, 960} | POC_Q | POC_B))
    recheck = np.full(P, np.iinfo(np.int64).max)
    dex_on = np.zeros(P, bool)
    # precomputed time-varying factors (per patient, per local step)
    aki_m = np.zeros((P, K), np.float32); surg_m = np.zeros((P, K), np.float32)
    steps = np.arange(K) * STEP
    for i, a in enumerate(adms):
        tt = a.start_min + steps
        if a.aki:
            onset, rise, dur = a.aki
            x = (tt - onset) / dur
            aki_m[i] = np.where(x < 0, 0, np.where(x < 1, rise * np.sin(np.pi * np.clip(x, 0, 1)), np.where(x < 1.5, rise * 0.2, 0)))
        if a.surgery_min:
            surg_m[i] = np.where(tt >= a.surgery_min, 0.5 * np.exp(-np.maximum(0, tt - a.surgery_min) / 2000), 0)

    def give(i, t, kind, dose, route="SC", status="given", note=""):
        rec["mar"].append((i, t, kind, float(dose), route, status, note))

    def poc_check(i, t, reason):
        a = adms[i]; s = st[i]
        val = float(np.clip(G[i] * (1 + prng[i].normal(0, 0.04)) + prng[i].normal(0, 3), 20, 600))
        val = round(val)
        rec["poc"].append((i, t, val, reason))
        s["last_poc"] = (t, val); s["poc_24h"].append((t, val))
        tod = t % 1440
        if val < SETTINGS.thr.hypo:
            if _in_npo(a, t):
                f1[i] += 20.0; give(i, t, "dextrose_iv", 20, route="IV", note="hypoglycaemia protocol (25% dextrose)")
            else:
                f1[i] += 15.0; give(i, t, "oral_glucose", 15, route="PO", note="hypoglycaemia protocol")
            s["recheck_at"] = t + 15; recheck[i] = t + 15
            return val
        if s["correction"] and reason == "protocol":
            u = _sliding_scale(val, bedtime=(tod == BEDTIME), sensitive=s["sensitive"])
            if u > 0:
                r1[i] += u; give(i, t, "rapid_correction", u, note="sliding scale")
        return val

    def round_titration(i, t):
        a = adms[i]; s = st[i]
        day = [v for (tt, v) in s["poc_24h"] if tt > t - 1440]
        s["poc_24h"] = [(tt, v) for (tt, v) in s["poc_24h"] if tt > t - 1440]
        if not day:
            return
        mn, mean = min(day), float(np.mean(day))
        d = t // 1440
        steroid_today = any(dd == d for (dd, _, _) in a.steroid)
        steroid_yday = any(dd == d - 1 for (dd, _, _) in a.steroid)
        on_insulin = s["basal"] > 0 or s["prandial"] > 0
        if mn < 70:
            if on_insulin and prng[i].random() < P_TITRATE_AFTER_LOW:
                s["basal"] = round(s["basal"] * 0.8); s["prandial"] = round(s["prandial"] * 0.8)
                order(i, t, "basal_units", s["basal"], note="reduced after hypoglycaemia")
                order(i, t, "prandial_units", s["prandial"], note="reduced after hypoglycaemia")
            if s["su"]:
                s["su"] = False; order(i, t, "sulfonylurea", "held", note="hypoglycaemia")
        elif mn < 100 and on_insulin and prng[i].random() < 0.6:
            s["basal"] = round(s["basal"] * 0.9); order(i, t, "basal_units", s["basal"], note="fasting glucose low-normal")
        elif mean > 180:
            if not on_insulin and sum(v > 180 for v in day) >= 2 and prng[i].random() < 0.6:
                s["basal"] = round(0.1 * a.weight * (1.3 if mean > 250 else 1.0))
                order(i, t, "basal_units", s["basal"], note="started: persistent hyperglycaemia")
                if prng[i].random() < 0.45:
                    s["prandial"] = round(0.05 * a.weight); order(i, t, "prandial_units", s["prandial"], note="started")
                s["correction"] = True; s["protocol_qid"] = True
                order(i, t, "correction_scale", "sensitive" if s["sensitive"] else "standard")
            elif on_insulin and prng[i].random() < (0.65 if mean > 200 else 0.45):
                f = 1.2 if mean > 220 else 1.1
                s["basal"] = round(s["basal"] * f) if s["basal"] else s["basal"]
                if s["prandial"]:
                    s["prandial"] = round(s["prandial"] * f)
                    order(i, t, "prandial_units", s["prandial"], note="up-titrated")
                if s["basal"]:
                    order(i, t, "basal_units", s["basal"], note="up-titrated")
            elif not s["correction"]:
                s["correction"] = True; s["protocol_qid"] = True
                order(i, t, "correction_scale", "sensitive" if s["sensitive"] else "standard", note="hyperglycaemia")
        # steroid started: some doctors add cover for the afternoon/evening rise
        if steroid_today and not steroid_yday and on_insulin and prng[i].random() < P_STEROID_COVER:
            s["prandial"] = round(max(s["prandial"], 0.05 * a.weight) * 1.4)
            order(i, t, "prandial_units", s["prandial"], note="steroid cover")
        if steroid_today and not s["correction"]:
            s["correction"] = True; s["protocol_qid"] = True
            order(i, t, "correction_scale", "standard", note="on steroids")
        # steroid stopped yesterday
        if steroid_yday and not steroid_today and a.steroid and on_insulin and not s["reduced_for_steroid_stop"]:
            s["reduced_for_steroid_stop"] = True
            if prng[i].random() < P_REDUCE_AFTER_STEROID_STOP:
                s["basal"] = round(s["basal"] * 0.75); s["prandial"] = round(s["prandial"] * 0.6)
                order(i, t, "basal_units", s["basal"], note="steroid stopped"); order(i, t, "prandial_units", s["prandial"], note="steroid stopped")
            else:
                rec["errors"].append((i, t, "insulin_not_reduced_after_steroid_stop"))
        # fasting tomorrow
        tomorrow = (d + 1) * 1440
        s["basal_tonight_factor"] = 1.0
        if _npo_ordered_for(a, tomorrow, t) and s["basal"]:
            if prng[i].random() < P_BASAL_REDUCED_BEFORE_NPO:
                s["basal_tonight_factor"] = 0.75
                order(i, t, "basal_tonight_units", round(s["basal"] * 0.75), start=d * 1440 + BASAL_T,
                      end=d * 1440 + BASAL_T + 5, note="fasting tomorrow")
            else:
                rec["errors"].append((i, t, "basal_not_reduced_before_fasting"))
        if s["aki_detected"] and on_insulin and not s["reduced_for_aki"]:
            s["reduced_for_aki"] = True
            if prng[i].random() < P_REDUCE_ON_AKI:
                s["basal"] = round(s["basal"] * 0.8); s["prandial"] = round(s["prandial"] * 0.8)
                order(i, t, "basal_units", s["basal"], note="kidney injury"); order(i, t, "prandial_units", s["prandial"], note="kidney injury")
            else:
                rec["errors"].append((i, t, "insulin_not_reduced_on_aki"))

    # appetite per admission-day (illness lowers intake early)
    appetite = {}

    for k in range(K):
        active = k < los
        if not active.any():
            break
        tabs = S + k * STEP
        tod = tabs % 1440
        days_in = (k * STEP) / 1440.0
        ev = active & (np.isin(tod, EVENT_MIN) | (recheck <= tabs) | (k == 0))
        idx_active = np.where(ev)[0]

        # ---------------- discrete ward events
        for i in idx_active:
            a = adms[i]; s = st[i]; t = int(tabs[i]); m = int(tod[i])
            if k == 0:
                poc_check(i, t, "admission")
                rec["labs"].append((i, t, "creatinine", round(float(a.creat_base + prng[i].normal(0, 0.05)), 2)))
                if a.hba1c_measured:
                    rec["labs"].append((i, t + 90, "hba1c", a.hba1c))
                continue
            if m == LAB_T:
                cr = a.creat_base + _aki_level(a, t) + prng[i].normal(0, 0.05)
                rec["labs"].append((i, t, "creatinine", round(float(cr), 2)))
                if (cr - a.creat_base) >= SETTINGS.rules.aki_creatinine_rise:
                    s["aki_detected"] = True
            if m == ROUND_T:
                round_titration(i, t)
            # steroid dose
            if m == STER_T:
                for (dd, mgv, drug) in a.steroid:
                    if dd == t // 1440:
                        s1[i] += mgv; give(i, t, drug, mgv if drug == "prednisolone" else round(mgv * 0.15, 1), route="PO",
                                           note="steroid course")
                if s["su"]:
                    if _in_npo(a, t + 60):
                        if prng[i].random() < P_SU_GIVEN_NPO:
                            u1[i] += 1.0; give(i, t, "glimepiride", 2, route="PO", note="")
                            rec["errors"].append((i, t, "sulfonylurea_given_while_fasting"))
                        else:
                            give(i, t, "glimepiride", 2, route="PO", status="held", note="fasting")
                    else:
                        u1[i] += 1.0; give(i, t, "glimepiride", 2, route="PO")
            # meals
            if m in MEALS:
                meal = MEALS[m]
                npo = _in_npo(a, t)
                key = (i, int(days_in))
                if key not in appetite:
                    base = 0.55 + 0.12 * days_in - (0.15 if a.adm_type in ("infection", "heart_failure") else 0)
                    appetite[key] = float(np.clip(base + prng[i].normal(0, 0.12), 0.15, 1.0))
                if npo:
                    frac = 0.0
                    if s["prandial"] > 0:
                        if prng[i].random() < P_PRANDIAL_GIVEN_NPO:
                            r1[i] += s["prandial"]; give(i, t - 10, "rapid_prandial", s["prandial"], note=meal)
                            rec["errors"].append((i, t, "prandial_given_while_fasting"))
                        else:
                            give(i, t - 10, "rapid_prandial", s["prandial"], status="held", note=f"{meal}: fasting")
                else:
                    frac = float(np.clip(appetite[key] + prng[i].normal(0, 0.18), 0, 1))
                    post_op = a.surgery_min is not None and 0 <= t - a.surgery_min < 1440
                    if post_op:
                        frac *= 0.4
                    if s["prandial"] > 0:
                        u = s["prandial"] * iv(i, t, "prandial")
                        r1[i] += u; give(i, t - 10, "rapid_prandial", u, note=meal)
                    carbs = float(np.clip(prng[i].normal(55, 6), 40, 70))
                    q1[i] += carbs * frac
                    rec["meals"].append((i, t, meal, round(carbs), round(frac * 4) / 4))
                if npo:
                    rec["meals"].append((i, t, meal, 0, 0.0))
            # basal insulin
            if m == BASAL_T and s["basal"] > 0:
                dose = round(s["basal"] * s["basal_tonight_factor"] * iv(i, t, "basal"))
                lp = s["last_poc"]
                if lp and lp[1] < 80 and t - lp[0] <= 30 and prng[i].random() < 0.7:
                    give(i, t + 5, "basal_glargine", dose, status="held", note="low bedtime glucose")
                else:
                    b1[i] += dose; give(i, t + 5, "basal_glargine", dose)
                s["basal_tonight_factor"] = 1.0
            # IV dextrose during long pre-operative fasts for insulin-treated patients
            if a.surgery_min and _in_npo(a, t) and s["basal"] > 0 and not s["dex_infusion"] and m == 0:
                if prng[i].random() < 0.5:
                    s["dex_infusion"] = True; dex_on[i] = True
                    give(i, t, "dextrose_5pct_infusion", 100, route="IV", note="ml/h while fasting")
            if s["dex_infusion"] and not _in_npo(a, t):
                s["dex_infusion"] = False; dex_on[i] = False
            # fingersticks
            sched = POC_Q if s["protocol_qid"] else POC_B
            if m in sched:
                poc_check(i, t, "protocol")
            if s["recheck_at"] is not None and t >= s["recheck_at"]:
                s["recheck_at"] = None; recheck[i] = np.iinfo(np.int64).max; poc_check(i, t, "recheck")

        # ---------------- continuous physiology (vectorised)
        aki_n = np.clip(aki_m[:, k], 0, 1.5)
        tau_r = 55 * (1 + 0.6 * aki_n); tau_b = 420 * (1 + 0.4 * aki_n); tau_u = 300.0; tau_s = 330.0
        ra = q2 / tau_m; q1n = q1 - STEP * q1 / tau_m; q2n = q2 + STEP * (q1 - q2) / tau_m
        rf = f1 * (1 - np.exp(-STEP / 12.0)) / STEP; f1 = f1 * np.exp(-STEP / 12.0)
        rr = r2 / tau_r; r1n = r1 - STEP * r1 / tau_r; r2n = r2 + STEP * (r1 - r2) / tau_r
        rb = b2 / tau_b; b1n = b1 - STEP * b1 / tau_b; b2n = b2 + STEP * (b1 - b2) / tau_b
        ru = u2 / tau_u; u1n = u1 - STEP * u1 / tau_u; u2n = u2 + STEP * (u1 - u2) / tau_u
        sl = s2 / tau_s; s1n = s1 - STEP * s1 / tau_s; s2n = s2 + STEP * (s1 - s2) / tau_s
        ster = sl / (40 / (tau_s * np.e))                                  # 1.0 = peak of a 40 mg dose
        stress = 1 + s_amp * np.exp(-days_in / 2.5) + surg_m[:, k]
        gb_eff = 85 + (gb - 85) * stress + s_gain * np.clip(ster, 0, 2)
        isf_eff = isf * (1 - 0.25 * np.clip(ster, 0, 1.5)) * (1 + 0.3 * aki_n) / np.sqrt(stress)
        dex = np.where(dex_on, 5.0 / 60, 0.0)  # g/min
        w = 0.93 * w + W_N[:, k]
        counter = np.where(G < 70, 0.05 * (70 - G), 0.0)
        dG = (-kk * (G - gb_eff) + mg * ra + 3.2 * rf + 2.5 * dex - isf_eff * (rr + rb + 3.0 * ru) + counter)
        G = np.clip(G + STEP * dG + w * 0.5, 32, 600)
        q1, q2, r1, r2, b1, b2, u1, u2, s1, s2 = q1n, q2n, r1n, r2n, b1n, b2n, u1n, u2n, s1n, s2n
        truth[active, k] = G[active]
        # CGM: ~10 min lag, drift, noise, occasional dropouts
        drift = 0.99 * drift + DR_N[:, k]
        obs = truth[:, max(k - 2, 0)] * (1 + drift / 100) + OB_N[:, k] * (2 + 0.02 * truth[:, max(k - 2, 0)])
        ok = active & cgm_on & (DROP[:, k] > 0.03)
        cgm[ok, k] = np.clip(obs[ok], 40, 400)

    # longer CGM gaps (signal loss, imaging)
    for i in np.where(cgm_on)[0]:
        g = nrng[i]
        for _ in range(int(g.poisson(1.2))):
            s0 = int(g.integers(0, max(1, los[i] - 30))); cgm[i, s0:s0 + int(g.integers(6, 36))] = np.nan

    return _to_frames(adms, rec, truth, cgm, S, los)


def _to_frames(adms, rec, truth, cgm, S, los):
    ts = lambda m: EPOCH + pd.to_timedelta(np.asarray(m), unit="m")
    aid = lambda i: adms[i].admission_id
    enc = pd.DataFrame([{
        "admission_id": a.admission_id, "patient_id": a.patient_id, "name": a.name, "sex": a.sex, "age": a.age,
        "weight_kg": a.weight, "height_cm": a.height, "admission_type": a.adm_type, "admission_reason": TYPE_LABEL[a.adm_type],
        "known_diabetes": a.dm_status in ("t2d_oral", "t2d_insulin"), "home_insulin": a.dm_status == "t2d_insulin",
        "home_sulfonylurea": a.home_su, "ckd": a.ckd, "heart_failure": a.heart_failure, "cgm": a.cgm,
        "admit_time": ts(a.start_min), "discharge_time": ts(a.start_min + a.los_steps * STEP),
        "surgery_time": ts(a.surgery_min) if a.surgery_min else pd.NaT} for a in adms])
    poc = pd.DataFrame(rec["poc"], columns=["i", "t", "glucose_mgdl", "reason"])
    mar = pd.DataFrame(rec["mar"], columns=["i", "t", "drug", "dose", "route", "status", "note"])
    orders = pd.DataFrame(rec["orders"], columns=["i", "t", "kind", "value", "start", "end", "note"])
    meals = pd.DataFrame(rec["meals"], columns=["i", "t", "meal", "carbs_served_g", "intake_fraction"])
    labs = pd.DataFrame(rec["labs"], columns=["i", "t", "test", "value"]).drop_duplicates(["i", "test", "t"])
    errors = pd.DataFrame(rec["errors"], columns=["i", "t", "error"])
    for df in (poc, mar, orders, meals, labs, errors):
        df.insert(0, "admission_id", df.pop("i").map(aid))
        df["time"] = ts(df.pop("t"))
    for c in ("start", "end"):
        orders[c] = ts(orders[c].astype(float))
    # dense 5-min frames
    rows_t, rows_c = [], []
    for i, a in enumerate(adms):
        n = int(los[i]); t = ts(a.start_min + np.arange(n) * STEP)
        rows_t.append(pd.DataFrame({"admission_id": a.admission_id, "time": t, "glucose_true": np.round(truth[i, :n], 1)}))
        if a.cgm:
            c = cgm[i, :n]; m = ~np.isnan(c)
            rows_c.append(pd.DataFrame({"admission_id": a.admission_id, "time": t[m], "glucose_mgdl": np.round(c[m])}))
    hidden = pd.DataFrame([{"admission_id": a.admission_id, "dm_status": a.dm_status, "hba1c_true": a.hba1c,
                            "hba1c_measured": a.hba1c_measured, "gb": a.gb, "k": a.k, "meal_gain": a.meal_gain,
                            "isf": a.isf, "stress_amp": a.stress_amp, "steroid_gain": a.steroid_gain,
                            "aki": a.aki is not None} for a in adms])
    return {"encounters": enc, "poc": poc, "mar": mar, "orders": orders, "meals": meals, "labs": labs,
            "cgm": pd.concat(rows_c, ignore_index=True) if rows_c else pd.DataFrame(columns=["admission_id", "time", "glucose_mgdl"]), "_truth": pd.concat(rows_t, ignore_index=True),
            "_errors": errors, "_hidden": hidden}
