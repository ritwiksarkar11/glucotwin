"""Held-out evaluation of the four features (test admissions only).

    python -m glucotwin.evaluation.evaluate
"""
from __future__ import annotations

import json

import lightgbm as lgb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

from ..config import EVAL_DIR, SETTINGS, SYNTH_DIR
from ..features.dataset import build, patient_split
from ..features.ward_features import STATIC_F
from ..ingest.fhir_bulk import load_ward
from ..twin.engine import WardTwin
from ..twin.store import Store

FIG = EVAL_DIR / "figures"
T = SETTINGS.thr
INK, MUTED, GRID = "#1f2937", "#6b7280", "#e5e7eb"
C_A, C_B, C_S, C_R, C_T = "#d97706", "#0f766e", "#9ca3af", "#cbd5e1", "#2563eb"


def _style(ax, title):
    ax.spines[["top", "right"]].set_visible(False); ax.spines[["left", "bottom"]].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9); ax.grid(axis="y", color=GRID, lw=0.6); ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=11, color=INK, fontweight="bold")


def _cls(y, p):
    bins = np.clip((p * 10).astype(int), 0, 9)
    ece = sum(abs(p[bins == b].mean() - y[bins == b].mean()) * (bins == b).mean() for b in range(10) if (bins == b).any())
    return {"auroc": float(roc_auc_score(y, p)), "auprc": float(average_precision_score(y, p)), "prevalence": float(y.mean()),
            "brier": float(np.mean((p - y) ** 2)), "ece": float(ece), "n": int(len(y))}


def episodes(series: pd.Series, test, min_len: int) -> list[tuple]:
    """Contiguous CGM runs meeting `test` for at least min_len readings -> [(start, end)]."""
    m = test(series.to_numpy())
    out, s = [], None
    idx = series.index
    for i, v in enumerate(m):
        if v and s is None:
            s = i
        if (not v or i == len(m) - 1) and s is not None:
            e = i if v else i - 1
            if e - s + 1 >= min_len:
                out.append((idx[s], idx[e]))
            s = None
    return out


# ============================================================ feature 1 + trajectories
def eval_models(out: dict, risk: pd.DataFrame, traj: pd.DataFrame, tw: WardTwin):
    b = tw.b
    te, trn = risk[risk.split == "test"].copy(), risk[risk.split == "train"]
    res = {}
    curves = {}
    for target in ("low", "high"):
        y = f"y_{target}"; d = te[te[y].notna()]; yy = d[y].to_numpy()
        r = {}
        for m in ("A", "B"):
            p = b.risk_prob(d, target, m); r[f"twin_{m}"] = _cls(yy, p); curves[(target, m)] = (yy, p)
            te.loc[d.index, f"p_{target}_{m}"] = p
        s = trn[trn[y].notna()]
        st = lgb.train({"objective": "binary", "verbose": -1, "num_leaves": 15, "learning_rate": 0.05, "seed": 1},
                       lgb.Dataset(s[STATIC_F], s[y]), 250)
        ps = st.predict(d[STATIC_F]); r["static_admission_model"] = _cls(yy, ps); curves[(target, "S")] = (yy, ps)
        rule = ((d.last_poc < 100) | (d.n_low_72h > 0)).astype(float) if target == "low" else ((d.last_poc >= 200) | (d.poc_max_24h >= 250)).astype(float)
        r["simple_rule"] = {"recall": float(rule[yy == 1].mean()), "precision": float(yy[rule.to_numpy() == 1].mean()) if rule.sum() else None,
                            "flag_rate": float(rule.mean())}
        res[target] = r
    out["risk"] = res
    # episode-level board performance (CGM-defined episodes, hourly board updates)
    w = load_ward(); cg = w["cgm"]
    ep = {}
    for target, test_fn, minlen in (("low", lambda v: v < T.hypo, 3), ("high", lambda v: v >= T.severe_high, 6)):
        for m in ("A", "B"):
            th = b.thresholds[f"{target}_{m}"]
            caught = leads = 0; n_ep = 0; lead_list = []; red_hours = 0; red_false = 0; days = 0.0
            for aid, d in te.groupby("admission_id"):
                c = cg[cg.admission_id == aid].set_index("time").glucose_mgdl.sort_index()
                eps = episodes(c, test_fn, minlen)
                # ignore episodes already ongoing at first update
                eps = [e for e in eps if e[0] > d.time.min()]
                pr = d.set_index("time")[f"p_{target}_{m}"].dropna()
                red = pr[pr >= th["red"]]
                days += len(pr) / 24
                for (s0, _) in eps:
                    n_ep += 1
                    win = red[(red.index >= s0 - pd.Timedelta("12h")) & (red.index < s0)]
                    if len(win):
                        caught += 1; lead_list.append((s0 - win.index.min()) / pd.Timedelta("1h"))
                for t0 in red.index:
                    red_hours += 1
                    if not any(t0 < s0 <= t0 + pd.Timedelta("12h") or s0 <= t0 <= e0 for (s0, e0) in eps):
                        red_false += 1
            ep[f"{target}_{m}"] = {"episodes": n_ep, "flagged_before_onset": caught / max(n_ep, 1),
                                   "median_lead_h": float(np.median(lead_list)) if lead_list else None,
                                   "red_hours_per_patient_day": red_hours / max(days, 1e-9),
                                   "red_hours_not_followed_by_episode": red_false / max(red_hours, 1)}
    out["board_episodes"] = ep
    # adaptive sensing: start a CGM when the fingerstick twin first turns red for lows
    th = b.thresholds["low_A"]["red"]
    n_ep = after = 0; flagged_adm = 0; sensor_days = 0.0; all_days = 0.0; n_adm = 0
    for aid, d in te.groupby("admission_id"):
        c = cg[cg.admission_id == aid].set_index("time").glucose_mgdl.sort_index()
        eps = [e for e in episodes(c, lambda v: v < T.hypo, 3) if e[0] > d.time.min()]
        pr = d.set_index("time")["p_low_A"].dropna()
        first = pr[pr >= th].index.min() if (pr >= th).any() else None
        n_adm += 1; all_days += len(pr) / 24
        if first is not None:
            flagged_adm += 1; sensor_days += (pr.index.max() - first) / pd.Timedelta("1D")
        n_ep += len(eps); after += sum(1 for (s0, _) in eps if first is not None and s0 > first)
    out["adaptive_sensing"] = {"low_episodes": n_ep, "share_after_first_red_flag": after / max(n_ep, 1),
                               "admissions_flagged": flagged_adm / max(n_adm, 1), "sensor_days_share": sensor_days / max(all_days, 1e-9),
                               "note": "If a CGM were started at the twin's first red-for-low flag (fingerstick mode), these lows would occur while monitored."}
    # trajectories
    tt = traj[(traj.split == "test") & traj.y.notna()]
    tj = {}
    for m in ("A", "B"):
        pr = b.trajectory(tt, m)
        g = pd.DataFrame({"h": tt.h, "err": (pr.mid - tt.y).abs(), "cov": (tt.y >= pr.lo) & (tt.y <= pr.hi), "width": pr.hi - pr.lo,
                          "persistence": (tt.last_poc - tt.y).abs()}).groupby("h").mean()
        tj[m] = {int(h): {k: round(float(v), 3) for k, v in r.items()} for h, r in g.iterrows()}
    out["trajectory"] = tj
    return curves, te


# ============================================================ feature 3: smart check timing
def eval_check_timing(out: dict, tw: WardTwin, thresholds=(0.1, 0.2, 0.3, 0.4)):
    w = load_ward(); enc = w["encounters"]
    sp = patient_split(list(enc.index))
    ids = [a for a in enc.index if sp[a] == "test" and enc.at[a, "cgm"]]
    rng = np.random.default_rng(0)
    rows, ep_rows = [], []
    for aid in ids:
        tb = tw.tabs(aid)
        c = tb["cgm"].set_index("time").glucose_mgdl.sort_index()
        poc_t = list(tb["poc"].time)
        decision_times = list(tb["poc"][tb["poc"].reason.isin(["protocol", "admission"])].time)
        cands = []
        for t in decision_times:
            if t < enc.at[aid, "admit_time"] + pd.Timedelta("2h") or t > enc.at[aid, "discharge_time"] - pd.Timedelta("2h"):
                continue
            p = tw.predict(aid, t)
            if p["mode"] != "A":  # evaluate the fingerstick ward: force mode A
                pass
            pl = tw.check_plan(t, p["row"], p["traj"])
            nxt = pl["protocol"][0] if pl["protocol"] else t + pd.Timedelta("12h")
            tr = p["traj"].copy(); tr["p_out"] = tr[["p_low", "p_high"]].max(axis=1)
            far = [all(abs((x - pc) / pd.Timedelta("1h")) > 1.5 for pc in pl["protocol"]) and x < nxt for x in tr.time]
            cand = tr[far]
            if len(cand):
                best = cand.loc[cand.p_out.idxmax()]
                cands.append((t, best.time, float(best.p_out), [x for x in cand.time]))
        lows = episodes(c, lambda v: v < T.hypo, 3); highs = episodes(c, lambda v: v >= T.severe_high, 6)
        days = (enc.at[aid, "discharge_time"] - enc.at[aid, "admit_time"]) / pd.Timedelta("1D")
        rows.append({"admission_id": aid, "poc": poc_t, "cands": cands, "lows": lows, "highs": highs, "days": days,
                     "insulin": tb["mar"].drug.isin(["basal_glargine", "rapid_prandial"]).any()})
    def caught(eps, checks):
        return sum(any(s <= x <= e for x in checks) for (s, e) in eps)
    res = {}
    tot_low = sum(len(r["lows"]) for r in rows); tot_high = sum(len(r["highs"]) for r in rows)
    pdays = sum(r["days"] for r in rows)
    base_low = sum(caught(r["lows"], r["poc"]) for r in rows); base_high = sum(caught(r["highs"], r["poc"]) for r in rows)
    res["protocol_only"] = {"low_caught": base_low / tot_low, "high_caught": base_high / tot_high, "extra_checks_per_patient_day": 0.0}
    for thr in thresholds:
        cl = ch = n_extra = rl = rh = 0
        for r in rows:
            ex = [bt for (t, bt, p, _) in r["cands"] if p >= thr]
            rnd = [rng.choice(slots) for (t, bt, p, slots) in r["cands"] if p >= thr]
            n_extra += len(ex)
            cl += caught(r["lows"], r["poc"] + ex); ch += caught(r["highs"], r["poc"] + ex)
            rl += caught(r["lows"], r["poc"] + rnd); rh += caught(r["highs"], r["poc"] + rnd)
        # untargeted baseline: the same number of extra checks spread over random patients and random gap hours
        pool = [(i, slots) for i, r in enumerate(rows) for (t, bt, p, slots) in r["cands"]]
        pick = rng.choice(len(pool), size=min(n_extra, len(pool)), replace=False) if n_extra else []
        extra_by = {}
        for j in pick:
            i, slots = pool[j]; extra_by.setdefault(i, []).append(rng.choice(slots))
        ul = sum(caught(r["lows"], r["poc"] + extra_by.get(i, [])) for i, r in enumerate(rows))
        uh = sum(caught(r["highs"], r["poc"] + extra_by.get(i, [])) for i, r in enumerate(rows))
        res[f"twin_threshold_{thr}"] = {"low_caught": cl / tot_low, "high_caught": ch / tot_high, "extra_checks_per_patient_day": n_extra / pdays,
                                        "extra_checks": n_extra,
                                        "targeted_patients_random_hour_low_caught": rl / tot_low,
                                        "targeted_patients_random_hour_high_caught": rh / tot_high,
                                        "untargeted_same_number_low_caught": ul / tot_low, "untargeted_same_number_high_caught": uh / tot_high,
                                        "extra_lows_caught_per_100_checks": 100 * (cl - base_low) / max(n_extra, 1),
                                        "untargeted_extra_lows_per_100_checks": 100 * (ul - base_low) / max(n_extra, 1)}
    # common practice: a 03:00 check every night for insulin-treated patients
    cl = ch = n3 = 0
    for r in rows:
        if not r["insulin"]:
            cl += caught(r["lows"], r["poc"]); ch += caught(r["highs"], r["poc"]); continue
        d0 = min(r["poc"]).normalize(); d1 = max(r["poc"]).normalize()
        x3 = [d + pd.Timedelta("3h") for d in pd.date_range(d0, d1 + pd.Timedelta("1D"), freq="D") if min(r["poc"]) < d + pd.Timedelta("3h") < max(r["poc"])]
        n3 += len(x3); cl += caught(r["lows"], r["poc"] + x3); ch += caught(r["highs"], r["poc"] + x3)
    res["fixed_3am_check_on_insulin"] = {"low_caught": cl / tot_low, "high_caught": ch / tot_high, "extra_checks_per_patient_day": n3 / pdays,
                                         "extra_checks": n3, "extra_lows_caught_per_100_checks": 100 * (cl - base_low) / max(n3, 1)}
    res["episodes"] = {"low": tot_low, "high": tot_high, "admissions": len(rows), "patient_days": round(pdays, 1)}
    out["check_timing"] = res
    return res


# ============================================================ feature 2: before-you-give check
RULE_FOR = {"prandial_given_while_fasting": ("mealtime", "prandial_while_fasting"),
            "basal_not_reduced_before_fasting": ("basal", "basal_before_fasting"),
            "insulin_not_reduced_after_steroid_stop": (None, "steroid_stopped"),
            "insulin_not_reduced_on_aki": (None, "aki"),
            "sulfonylurea_given_while_fasting": ("sulfonylurea", "su_poor_intake")}


def eval_insulin_check(out: dict, tw: WardTwin):
    w = load_ward(); enc = w["encounters"]
    sp = patient_split(list(enc.index))
    test_ids = set(a for a in enc.index if sp[a] == "test")
    err = pd.read_csv(SYNTH_DIR / "_hidden" / "process_failures.csv", parse_dates=["time"])
    # the bedside checks are fixed rules (nothing trained), so they are scored on every admission
    out_n = len(err)
    found = {k: [0, 0] for k in RULE_FOR}
    for r in err.itertuples():
        kind, rule = RULE_FOR[r.error]
        t = r.time
        if r.error == "prandial_given_while_fasting":
            check_at = t - pd.Timedelta("40min")
        elif r.error == "basal_not_reduced_before_fasting":
            check_at = t.normalize() + pd.Timedelta("21h30min")
        elif r.error == "sulfonylurea_given_while_fasting":
            check_at = t - pd.Timedelta("30min")
        else:
            check_at = t + pd.Timedelta("3h")   # next dose after the round (lunch)
        if check_at >= enc.at[r.admission_id, "discharge_time"]:
            continue
        p = tw.predict(r.admission_id, check_at)
        ds = tw.doses(r.admission_id, check_at, p, window_h=12) if False else _doses_fast(tw, r.admission_id, check_at, p)
        hit = any(f["rule"] == rule for d in ds if (kind is None or d["kind"] == kind) for f in d["flags"])
        found[r.error][0] += int(hit); found[r.error][1] += 1
    res = {"injected_failures_flagged": {k: {"flagged": v[0], "total": v[1], "rate": v[0] / v[1] if v[1] else None} for k, v in found.items()}}
    tot = sum(v[1] for v in found.values()); hit = sum(v[0] for v in found.values())
    res["overall_flag_rate"] = hit / max(tot, 1)
    # burden: high-level flags at routine dose times on test admissions
    n_flags = n_dose = 0; pdays = 0.0
    for aid in sorted(test_ids)[:60]:
        e = enc.loc[aid]
        pdays += (e.discharge_time - e.admit_time) / pd.Timedelta("1D")
        for t in pd.date_range(e.admit_time.normalize() + pd.Timedelta("1D"), e.discharge_time, freq="D"):
            for hh in (7.5, 12.5, 19.5, 21.5):
                ct = t + pd.Timedelta(hours=hh)
                if not (e.admit_time + pd.Timedelta("1h") < ct < e.discharge_time):
                    continue
                p = tw.predict(aid, ct)
                for d in _doses_fast(tw, aid, ct, p, window_h=1.0):
                    n_dose += 1; n_flags += int(any(f["level"] == "high" for f in d["flags"]))
    res["routine_doses_checked"] = n_dose
    res["high_flags_per_dose"] = n_flags / max(n_dose, 1)
    res["patient_days_sampled"] = round(pdays, 1)
    out["insulin_check"] = res
    return res


def _doses_fast(tw, aid, now, p, window_h=12.0):
    """doses() without the what-if comparisons (rules only), for evaluation speed."""
    from ..twin.reasons import dose_checks
    v = p["view"]; row = p["row"]; ev = v.schedule_events(now, window_h); wins = v.npo_windows(now); out = []
    for kind, key in (("basal", "basal"), ("mealtime", "prandial"), ("mealtime", "prandial_npo"), ("sulfonylurea", "su")):
        for (t, u) in ev[key][:1]:
            if u <= 0:
                continue
            tomorrow = t.normalize() + pd.Timedelta("1D")
            d = {"kind": kind, "time": t, "units": u, "fasting_at_dose": key == "prandial_npo" or v._in_npo(t, wins),
                 "fasting_tomorrow": any(s < tomorrow + pd.Timedelta("1D") and e > tomorrow for s, e in wins),
                 "tonight_reduced": bool(len(v.tonight[(v.tonight.time <= now) & (v.tonight.start.dt.normalize() == t.normalize())]))}
            d["flags"] = dose_checks(row, d); out.append(d)
    return out


# ============================================================ feature 4: discharge
def eval_discharge(out: dict, tw_all: WardTwin):
    hid = pd.read_csv(SYNTH_DIR / "_hidden" / "physiology.csv").set_index("admission_id")
    und = hid[hid.dm_status == "undiagnosed"].index
    diag = prompt = 0
    for aid in und:
        s = tw_all.discharge(aid)
        txt = " ".join(s["findings"] + s["actions"])
        diag += "probable undiagnosed diabetes" in txt
        prompt += "Order HbA1c" in txt
    stress = hid[hid.dm_status == "stress_only"].index
    false_dx = sum("probable undiagnosed diabetes" in " ".join(tw_all.discharge(a)["findings"]) for a in stress)
    out["discharge"] = {"undiagnosed_diabetes_admissions": int(len(und)), "identified_as_probable_new_diagnosis": diag / len(und),
                        "prompted_to_order_hba1c": prompt / len(und), "identified_or_prompted": (diag + prompt) / len(und),
                        "false_new_diagnosis_in_stress_hyperglycaemia": false_dx / max(len(stress), 1),
                        "note": "Uses all 800 admissions (rule-based, no model). Without the prompt, undiagnosed cases are missed whenever HbA1c is not ordered."}


# ============================================================ figures
def figures(out, curves, tw):
    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans"})
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.3))
    for ax, target, title in ((axs[0], "low", "Low (<70) in next 12 h"), (axs[1], "high", "Severe high (≥250) in next 12 h")):
        for key, lab, col in (("S", "Static admission-time model", C_S), ("A", "Twin · fingersticks", C_A), ("B", "Twin · CGM", C_B)):
            y, p = curves[(target, key)]
            pr, rc, _ = precision_recall_curve(y, p)
            ap = average_precision_score(y, p)
            ax.plot(rc, pr, color=col, lw=2, label=f"{lab} (AUPRC {ap:.2f})")
        ax.axhline(y.mean(), color=C_R, ls="--", lw=1)
        ax.set_xlabel("Recall", color=MUTED); ax.set_ylabel("Precision", color=MUTED); _style(ax, title)
        ax.legend(frameon=False, fontsize=8.5)
    fig.tight_layout(); fig.savefig(FIG / "risk_pr_curves.png", dpi=160); plt.close(fig)

    ct = out["check_timing"]; k = "twin_threshold_0.2"; ad = out["adaptive_sensing"]
    labels = ["Fingerstick\nprotocol", "+ 3 am check,\neveryone on insulin", "+ extra checks,\nuntargeted", "+ extra checks,\ntwin-targeted",
              "+ CGM when twin\nflags red"]
    lows = [ct["protocol_only"]["low_caught"], ct["fixed_3am_check_on_insulin"]["low_caught"], ct[k]["untargeted_same_number_low_caught"],
            ct[k]["low_caught"], ad["share_after_first_red_flag"] + (1 - ad["share_after_first_red_flag"]) * ct["protocol_only"]["low_caught"]]
    sub = ["", f"{ct['fixed_3am_check_on_insulin']['extra_checks_per_patient_day']:.2f} checks/pt-day", f"{ct[k]['extra_checks_per_patient_day']:.2f} checks/pt-day",
           f"{ct[k]['extra_checks_per_patient_day']:.2f} checks/pt-day", f"sensor on {ad['admissions_flagged']:.0%} of patients"]
    fig, ax = plt.subplots(figsize=(10, 4.3)); x = np.arange(len(lows))
    bars = ax.bar(x, lows, 0.6, color=[C_S, C_R, C_R, C_A, C_B])
    for r_, v in zip(bars, lows):
        ax.text(r_.get_x() + r_.get_width() / 2, v + 0.015, f"{v:.0%}", ha="center", fontsize=10, color=INK, fontweight="bold")
    ax.set_xticks(x, [f"{l}\n{s_}" for l, s_ in zip(labels, sub)], fontsize=8.5)
    ax.set_ylim(0, 1); ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    _style(ax, "Share of CGM-recorded lows that the ward would detect")
    fig.tight_layout(); fig.savefig(FIG / "smart_monitoring.png", dpi=160); plt.close(fig)

    tj = out["trajectory"]
    fig, ax = plt.subplots(figsize=(7, 4)); hs = sorted(tj["A"])
    ax.plot(hs, [tj["A"][h]["persistence"] for h in hs], color=C_S, lw=2, marker="o", ms=3, label="Last fingerstick carried forward")
    ax.plot(hs, [tj["A"][h]["err"] for h in hs], color=C_A, lw=2, marker="o", ms=3, label="Twin · fingersticks")
    ax.plot(hs, [tj["B"][h]["err"] for h in hs], color=C_B, lw=2, marker="o", ms=3, label="Twin · CGM")
    ax.set_xlabel("Hours ahead", color=MUTED); ax.set_ylabel("Mean absolute error (mg/dL)", color=MUTED); ax.set_ylim(0, None)
    _style(ax, "Glucose forecast error, 1-12 hours ahead"); ax.legend(frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "trajectory_error.png", dpi=160); plt.close(fig)


def evaluate():
    risk, traj = build()
    tw = WardTwin(store=Store(":memory:"), pool="test")
    out = {"model_version": tw.b.version, "thresholds": tw.b.thresholds}
    curves, _ = eval_models(out, risk, traj, tw)
    print("models done"); eval_check_timing(out, tw); print("timing done")
    eval_insulin_check(out, WardTwin(store=Store(":memory:"), pool="all")); print("insulin check done")
    eval_discharge(out, WardTwin(store=Store(":memory:"), pool="all")); print("discharge done")
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    prev = EVAL_DIR / "metrics.json"
    if prev.exists():
        old = json.loads(prev.read_text())
        if "what_if_validation" in old:
            out["what_if_validation"] = old["what_if_validation"]
    (EVAL_DIR / "metrics.json").write_text(json.dumps(out, indent=2, default=float))
    figures(out, curves, tw)
    return out


if __name__ == "__main__":
    o = evaluate()
    print(json.dumps({k: o[k] for k in ("risk", "board_episodes", "check_timing", "insulin_check", "discharge")}, indent=1, default=float))
