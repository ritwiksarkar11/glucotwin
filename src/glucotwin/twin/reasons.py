"""Plain-language reasons and safety checks.

Reasons: the model's largest positive contributions are mapped to short ward
phrases. Each phrase is filled only from the patient's own documented data.

Checks ("before you give insulin"): deterministic rules a nurse or doctor can
verify at the bedside. They never propose a dose; they ask for a review.
"""
from __future__ import annotations

import math

import pandas as pd

from ..config import SETTINGS

R = SETTINGS.rules


def _pct(x):
    return f"{round(100 * x)}%"


def _ok(v):
    return v is not None and not (isinstance(v, float) and math.isnan(v))


# feature -> (group, template function(row) -> str | None)
LOW_REASONS = {
    "npo_hours_12h": ("fasting", lambda r: f"Fasting {r['npo_hours_12h']:.0f} h in the next 12 h with insulin scheduled"
                      if r["npo_hours_12h"] > 0 and (r["basal_sched_12h"] + r["prandial_sched_12h"] + r["prandial_npo_12h"]) > 0 else None),
    "prandial_npo_12h": ("fasting", lambda r: "Mealtime insulin ordered at a meal the patient will miss (fasting)" if r["prandial_npo_12h"] > 0 else None),
    "steroid_stopped_24h": ("steroid_stop", lambda r: "Steroid course has ended; insulin dose not yet reduced"
                            if r["steroid_stopped_24h"] and r["basal_change_24h"] >= 0 else None),
    "creat_delta_48h": ("kidney", lambda r: f"Creatinine up {r['creat_delta_48h']:.1f} mg/dL in 48 h: insulin lasts longer"
                        if _ok(r["creat_delta_48h"]) and r["creat_delta_48h"] >= R.aki_creatinine_rise else None),
    "aki_flag": ("kidney", lambda r: "Acute kidney injury on recent labs" if r["aki_flag"] else None),
    "mean_intake_24h": ("intake", lambda r: f"Eating about {_pct(r['mean_intake_24h'])} of meals" if _ok(r["mean_intake_24h"]) and r["mean_intake_24h"] < 0.6 else None),
    "last_intake": ("intake", lambda r: f"Ate {_pct(r['last_intake'])} of the last meal" if _ok(r["last_intake"]) and r["last_intake"] < 0.5 else None),
    "n_low_72h": ("prior_low", lambda r: f"{int(r['n_low_72h'])} low reading(s) in the last 72 h" if r["n_low_72h"] > 0 else None),
    "n_lt100_24h": ("prior_low", lambda r: f"{int(r['n_lt100_24h'])} reading(s) under 100 in 24 h" if r["n_lt100_24h"] > 0 else None),
    "last_poc": ("level", lambda r: f"Last fingerstick {r['last_poc']:.0f} mg/dL" if _ok(r["last_poc"]) and r["last_poc"] < 120 else None),
    "cgm_now": ("level", lambda r: f"CGM now {r['cgm_now']:.0f} mg/dL" if _ok(r.get("cgm_now")) and r["cgm_now"] < 120 else None),
    "cgm_next12_yday_min": ("pattern", lambda r: f"Went down to {r['cgm_next12_yday_min']:.0f} at this time yesterday (CGM)"
                            if _ok(r.get("cgm_next12_yday_min")) and r["cgm_next12_yday_min"] < 90 else None),
    "su_sched_12h": ("su", lambda r: "On glimepiride (sulfonylurea)" if r["su_sched_12h"] > 0 or r["su_given_24h"] > 0 else None),
    "basal_sched_12h": ("basal", lambda r: f"Basal {r['basal_sched_12h']:.0f} U due tonight" if r["basal_sched_12h"] > 0 else None),
    "basal_iob": ("basal", lambda r: "Basal insulin still active overnight" if r["basal_iob"] > 5 else None),
    "rapid_iob": ("rapid", lambda r: f"Rapid insulin on board ({r['rapid_iob']:.0f} U)" if r["rapid_iob"] >= 2 else None),
    "ckd": ("kidney", lambda r: "Chronic kidney disease" if r["ckd"] else None),
}
HIGH_REASONS = {
    "steroid_sched_12h": ("steroid", lambda r: f"Steroid {r['steroid_sched_12h']:.0f} mg (prednisolone-equivalent) due: glucose usually peaks 2-8 pm"
                          if r["steroid_sched_12h"] > 0 else None),
    "steroid_today_mg": ("steroid", lambda r: f"Steroid {r['steroid_today_mg']:.0f} mg given this morning: afternoon/evening peak expected"
                         if r["steroid_today_mg"] > 0 else None),
    "poc_max_afternoon_yday": ("pattern", lambda r: f"Reached {r['poc_max_afternoon_yday']:.0f} yesterday afternoon"
                               if _ok(r["poc_max_afternoon_yday"]) and r["poc_max_afternoon_yday"] >= 200 else None),
    "cgm_next12_yday_max": ("pattern", lambda r: f"Reached {r['cgm_next12_yday_max']:.0f} at this time yesterday (CGM)"
                            if _ok(r.get("cgm_next12_yday_max")) and r["cgm_next12_yday_max"] >= 220 else None),
    "n_gt250_24h": ("level", lambda r: f"{int(r['n_gt250_24h'])} reading(s) of 250+ in 24 h" if r["n_gt250_24h"] > 0 else None),
    "poc_max_24h": ("level", lambda r: f"Highest in 24 h: {r['poc_max_24h']:.0f} mg/dL" if _ok(r["poc_max_24h"]) and r["poc_max_24h"] >= 220 else None),
    "last_poc": ("level", lambda r: f"Last fingerstick {r['last_poc']:.0f} mg/dL" if _ok(r["last_poc"]) and r["last_poc"] >= 200 else None),
    "cgm_now": ("level", lambda r: f"CGM now {r['cgm_now']:.0f} mg/dL" if _ok(r.get("cgm_now")) and r["cgm_now"] >= 200 else None),
    "basal_order_units": ("regimen", lambda r: "No basal insulin: correction (sliding scale) only" if r["basal_order_units"] == 0 and r["correction_scale"] > 0 else None),
    "hba1c": ("control", lambda r: f"HbA1c {r['hba1c']:.1f}%" if _ok(r["hba1c"]) and r["hba1c"] >= 8.5 else None),
    "days_since_admit": ("stress", lambda r: "Early in an acute illness (stress hyperglycaemia)" if r["days_since_admit"] < 2 else None),
    "hours_since_surgery": ("stress", lambda r: "Within 24 h of surgery" if _ok(r["hours_since_surgery"]) and r["hours_since_surgery"] < 24 else None),
    "dextrose_infusion": ("dextrose", lambda r: "Dextrose infusion running" if r["dextrose_infusion"] else None),
    "meals_sched_12h": ("meals", lambda r: None),
}


def reasons(row: pd.Series, contrib: pd.Series, target: str, n: int = 2) -> list[str]:
    table = LOW_REASONS if target == "low" else HIGH_REASONS
    out, groups = [], set()
    for f in contrib.sort_values(ascending=False).index:
        if contrib[f] <= 0 or f not in table:
            continue
        g, fn = table[f]
        if g in groups:
            continue
        txt = fn(row)
        if txt:
            out.append(txt); groups.add(g)
        if len(out) >= n:
            break
    return out


# ------------------------------------------------------------------ insulin checks
def dose_checks(row: pd.Series, dose: dict) -> list[dict]:
    """Checks for one scheduled dose. dose = {kind, time, units, fasting_at_dose, fasting_tomorrow, tonight_reduced}."""
    flags = []

    def add(level, text, rule):
        flags.append({"level": level, "text": text, "rule": rule})
    k = dose["kind"]
    if k == "mealtime" and dose.get("fasting_at_dose"):
        add("high", "Patient is fasting at this meal (nil by mouth). Mealtime insulin is normally held: confirm with the doctor.", "prandial_while_fasting")
    if k == "mealtime" and _ok(row["mean_intake_24h"]) and row["mean_intake_24h"] < R.low_intake_fraction:
        add("medium", f"Eating about {_pct(row['mean_intake_24h'])} of meals. Check the hospital protocol for mealtime insulin with poor intake.", "low_intake")
    if k == "basal" and dose.get("fasting_tomorrow") and not dose.get("tonight_reduced"):
        add("high", "Fasting from midnight for a procedure, but tonight's basal is the usual dose. Review with the doctor.", "basal_before_fasting")
    if k in ("basal", "mealtime") and row["steroid_stopped_24h"] and row["basal_change_24h"] >= 0:
        add("high", "Steroid course has ended and insulin has not been reduced since. Review with the doctor.", "steroid_stopped")
    rise48 = row["creat_delta_48h"] if _ok(row["creat_delta_48h"]) else 0.0
    rise_adm = row["creat_vs_admit"] if _ok(row.get("creat_vs_admit")) else 0.0
    if k in ("basal", "mealtime", "sulfonylurea") and max(rise48, rise_adm) >= R.aki_creatinine_rise:
        when = "in 48 h" if rise48 >= R.aki_creatinine_rise else "since admission"
        add("medium", f"Creatinine up {max(rise48, rise_adm):.1f} mg/dL {when} (possible kidney injury): insulin and sulfonylureas last longer.", "aki")
    lp, ago = row["last_poc"], row["mins_since_poc"]
    if _ok(lp) and _ok(ago) and ago <= 240 and lp < 100:
        add("high" if lp < 80 else "medium", f"Last fingerstick {lp:.0f} mg/dL ({ago:.0f} min ago).", "low_recent_glucose")
    if k == "sulfonylurea" and (dose.get("fasting_at_dose") or (_ok(row["mean_intake_24h"]) and row["mean_intake_24h"] < R.low_intake_fraction)):
        add("high", "Glimepiride due while fasting or eating poorly: high risk of a low. Review with the doctor.", "su_poor_intake")
    return flags
