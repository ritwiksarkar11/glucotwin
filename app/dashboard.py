"""GlucoTwin Ward — Streamlit app.

    streamlit run app/dashboard.py

Four screens: Ward board · Patient (before-you-give check, what-if, next check) ·
Discharge handover · Evidence. A demo clock replays the synthetic ward.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from glucotwin.config import EVAL_DIR, SETTINGS
from glucotwin.twin.engine import WardTwin

st.set_page_config(page_title="GlucoTwin Ward", page_icon="🩺", layout="wide")
T = SETTINGS.thr
INK, MUTED, LINE = "#0f172a", "#64748b", "#e2e8f0"
TEAL, AMBER, RED, BLUE, VIOLET = "#0f766e", "#d97706", "#dc2626", "#2563eb", "#7c3aed"
DISCLAIMER = ("Research prototype on synthetic patients. Not a medical device. The twin flags and forecasts for "
              "clinician review; it never recommends a dose.")

st.markdown("""
<style>
.block-container {padding-top: 2.6rem; max-width: 1450px;}
.gw-top {display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap; gap:.6rem;
         border-bottom:1px solid #e2e8f0; padding-bottom:.55rem; margin-bottom:.7rem;}
.gw-title {font-size:1.5rem; font-weight:700; color:#0f172a; line-height:1.15;}
.gw-sub {color:#64748b; font-size:.88rem;}
.chip {display:inline-block; padding:.12rem .6rem; border-radius:999px; font-size:.8rem; font-weight:600; margin:.1rem .3rem .1rem 0;
       border:1px solid transparent; white-space:nowrap;}
.red {background:#fef2f2; color:#b91c1c; border-color:#fecaca;} .amber {background:#fffbeb; color:#b45309; border-color:#fde68a;}
.green {background:#ecfdf5; color:#047857; border-color:#a7f3d0;} .grey {background:#f1f5f9; color:#475569; border-color:#e2e8f0;}
.blue {background:#eff6ff; color:#1d4ed8; border-color:#bfdbfe;} .violet {background:#f5f3ff; color:#6d28d9; border-color:#ddd6fe;}
.card {border:1px solid #e2e8f0; border-radius:12px; padding:.8rem 1rem; background:#fff; margin-bottom:.7rem;}
.card h4 {margin:.0rem 0 .35rem 0; font-size:1rem; color:#0f172a;}
.k {color:#64748b; font-size:.75rem; text-transform:uppercase; letter-spacing:.04em; font-weight:600;}
.v {color:#0f172a; font-size:1.45rem; font-weight:700; line-height:1.15;}
.s {color:#64748b; font-size:.82rem;}
.banner {border-radius:12px; padding:.7rem 1rem; margin:.2rem 0 .8rem 0; font-size:.95rem;}
.b-red {background:#fef2f2; border:1px solid #fecaca; color:#7f1d1d;} .b-amber {background:#fffbeb; border:1px solid #fde68a; color:#78350f;}
.b-green {background:#ecfdf5; border:1px solid #a7f3d0; color:#064e3b;}
.flag {border-left:0; padding:.45rem .6rem; border-radius:8px; margin:.3rem 0; font-size:.88rem;}
.f-high {background:#fef2f2; color:#7f1d1d;} .f-medium {background:#fffbeb; color:#78350f;}
.foot {color:#94a3b8; font-size:.75rem; margin-top:1.2rem;}
</style>""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Loading the ward…")
def twin() -> WardTwin:
    return WardTwin()


tw = twin()
_mp = EVAL_DIR / "metrics.json"
_ad = json.loads(_mp.read_text()).get("adaptive_sensing", {}) if _mp.exists() else {}
if "now" not in st.session_state:
    st.session_state.now = tw.clock_or_default() if hasattr(tw, "clock_or_default") else tw.default_now()
    st.session_state.view = "Ward board"
    st.session_state.aid = None
qp = st.query_params
_key = f"{qp.get('aid', '')}|{qp.get('t', '')}|{qp.get('view', '')}"
if qp.get("aid") and st.session_state.get("_qp") != _key:
    st.session_state._qp = _key
    st.session_state.aid = qp["aid"]; st.session_state.nav = qp.get("view", "Patient")
    if qp.get("t"):
        st.session_state.now = pd.Timestamp(qp["t"])
st.session_state.setdefault("nav", "Ward board")
now: pd.Timestamp = st.session_state.now


@st.cache_data(show_spinner="Updating every patient's twin…", max_entries=64)
def board_at(now_iso: str) -> pd.DataFrame:
    return tw.board(pd.Timestamp(now_iso), record=True)


def patient_at(aid: str, now_iso: str):
    key = ("p", aid, now_iso)
    if key not in st.session_state:
        st.session_state[key] = tw.patient(aid, pd.Timestamp(now_iso))
    return st.session_state[key]


def ago(mins) -> str:
    if mins is None or pd.isna(mins):
        return "—"
    return f"{mins:.0f} min ago" if mins < 90 else f"{mins / 60:.1f} h ago"


def pct(p) -> str:
    return "<1%" if p < 0.01 else ">97%" if p > 0.97 else f"{p:.0%}"


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### 🩺 GlucoTwin Ward")
    st.caption("A live glucose twin for every inpatient with diabetes")
    role = st.radio("I am the", ["Nurse", "Doctor"], horizontal=True)
    user = st.text_input("Name", value="Sr. Anjali" if role == "Nurse" else "Dr. Mehta")
    st.divider()
    st.markdown(f"**Ward time** · {now:%a %d %b, %H:%M}")
    c1, c2, c3 = st.columns(3)
    step = None
    if c1.button("+1 h", width="stretch"): step = pd.Timedelta("1h")
    if c2.button("+4 h", width="stretch"): step = pd.Timedelta("4h")
    if c3.button("Shift", width="stretch", help="Jump to the next 08:00 or 20:00 handover"):
        nxt = [d for d in (now.normalize() + pd.Timedelta("8h"), now.normalize() + pd.Timedelta("20h"), now.normalize() + pd.Timedelta("32h")) if d > now][0]
        step = nxt - now
    if step is not None:
        st.session_state.now = now + step
        tw.store.audit(tw.ward, None, st.session_state.now, user, "clock_advanced", {"by": str(step)})
        st.rerun()
    if st.button("Back to demo moment", width="stretch"):
        st.session_state.now = tw.default_now(); st.rerun()
    st.divider()
    st.caption(DISCLAIMER)

# ------------------------------------------------------------------ navigation
views = ["Ward board", "Patient", "Discharge", "Evidence"]
st.session_state.view = st.segmented_control("View", views, label_visibility="collapsed", key="nav") or "Ward board"
board = board_at(now.isoformat())


# ================================================================== WARD BOARD
if st.session_state.view == "Ward board":
    n_red, n_amber = int((board.status == "red").sum()), int((board.status == "amber").sum())
    n_extra = int((board.next_check_reason.str.startswith("twin")).sum())
    n_flag = int((board.dose_flags > 0).sum()); n_cgm = int(board.suggest_cgm.sum())
    st.markdown(f"""<div class="gw-top"><div><div class="gw-title">{tw.ward}</div>
      <div class="gw-sub">{now:%A %d %B %Y · %H:%M} · {len(board)} patients with diabetes or high glucose · risk over the next 12 hours</div></div>
      <div><span class="chip red">{n_red} need attention</span><span class="chip amber">{n_amber} watch</span>
      <span class="chip violet">{n_extra} extra check(s) suggested</span><span class="chip blue">{n_flag} insulin dose(s) to review</span><span class="chip grey">{n_cgm} CGM suggested</span></div></div>""",
                unsafe_allow_html=True)
    def bar(p, color):
        w = max(2, int(round(100 * p)))
        return (f"<div style='display:flex;align-items:center;gap:.4rem'><div style='flex:1;height:7px;background:#f1f5f9;border-radius:4px'>"
                f"<div style='width:{w}%;height:7px;background:{color};border-radius:4px'></div></div><span style='min-width:2.6rem;text-align:right'>{pct(p)}</span></div>")
    trs = []
    for r in board.itertuples():
        dot = {"red": RED, "amber": AMBER, "green": "#10b981"}[r.status]
        href = f"?view=Patient&aid={r.admission_id}&t={now.isoformat()}"
        sensor = "CGM" if r.mode == "B" else "fingerstick"
        last = (f"<b style='font-size:1rem'>{r.last_glucose:.0f}</b><div class='s' style='white-space:nowrap'>{ago(r.last_glucose_mins)} · {sensor}</div>"
                if pd.notna(r.last_glucose) else "—")
        nxt = f"{r.next_check:%H:%M}" if pd.notna(r.next_check) else "—"
        if r.next_check_reason.startswith("twin"):
            nxt = f"<span class='chip violet'>{nxt} extra</span>"
        alerts = ""
        if r.dose_flags:
            alerts += f"<span class='chip blue'>⚠ insulin review</span>"
        if r.suggest_cgm:
            alerts += "<span class='chip red'>suggest CGM</span>"
        why = r.why or "<span class='s'>No concerns found</span>"
        trs.append(f"""<tr><td><span style='display:inline-block;width:11px;height:11px;border-radius:50%;background:{dot}'></span></td>
          <td style='white-space:nowrap'><b>{r.bed}</b></td><td><a href='{href}' target='_self' style='color:#0f172a;font-weight:600;text-decoration:none'>{r.name}</a>
          <span class='s'>· {r.age}</span><div class='s'>{r.reason} · day {r.day}</div></td>
          <td style='white-space:nowrap'>{last}</td><td style='min-width:110px'>{bar(r.p_low, RED)}</td><td style='min-width:110px'>{bar(r.p_high, AMBER)}</td>
          <td style='font-size:.86rem'>{why}</td><td style='white-space:nowrap'>{nxt}</td><td>{alerts}</td></tr>""")
    st.markdown("""<style>.board{width:100%;border-collapse:collapse;font-size:.9rem}
      .board th{text-align:left;color:#64748b;font-weight:600;font-size:.75rem;text-transform:uppercase;letter-spacing:.03em;padding:.45rem .5rem;border-bottom:1px solid #e2e8f0}
      .board td{padding:.55rem .5rem;border-bottom:1px solid #f1f5f9;vertical-align:top}
      .board tr:hover td{background:#f8fafc}</style>""", unsafe_allow_html=True)
    st.markdown("<table class='board'><thead><tr><th></th><th>Bed</th><th>Patient</th><th>Last glucose</th><th>Low risk 12 h</th>"
                "<th>Severe high 12 h</th><th>Why</th><th>Next check</th><th>Action</th></tr></thead><tbody>" + "".join(trs) + "</tbody></table>",
                unsafe_allow_html=True)
    st.caption("Low = glucose under 70 mg/dL in the next 12 hours; severe high = 250 mg/dL or more. Red is reserved for lows. "
               "Click a name to open that patient's twin.")

# ================================================================== PATIENT
elif st.session_state.view == "Patient":
    ids = list(board.admission_id)
    labels = {a: f"{b} · {n}" for a, b, n in zip(board.admission_id, board.bed, board.name)}
    cur = st.session_state.aid if st.session_state.aid in ids else ids[0]
    aid = st.selectbox("Patient", ids, index=ids.index(cur), format_func=lambda a: labels[a])
    st.session_state.aid = aid
    s = patient_at(aid, now.isoformat())
    e = tw.w["encounters"].loc[aid]; r = s["row"]; brow = board[board.admission_id == aid].iloc[0]
    meds = ", ".join(x for x, f in (("home insulin", e.home_insulin), ("glimepiride at home", e.home_sulfonylurea)) if f) or "no glucose-lowering drugs at home"
    st.markdown(f"""<div class="gw-top"><div><div class="gw-title">{brow.bed} · {e['name']} <span style="color:#94a3b8;font-weight:500;font-size:1rem">{int(e.age)} y {e.sex}</span></div>
      <div class="gw-sub">{e.admission_reason} · day {int(r.days_since_admit) + 1} · {'known diabetes' if e.known_diabetes else 'no diabetes diagnosis'} ({meds})
      {' · HbA1c ' + format(r.hba1c, '.1f') + '%' if pd.notna(r.hba1c) else ' · HbA1c not measured'}</div></div>
      <div><span class="chip {'blue' if s['mode'] == 'B' else 'grey'}">{'CGM' if s['mode'] == 'B' else 'Fingersticks'}</span>
      <span class="chip grey">model {tw.b.version}</span></div></div>""", unsafe_allow_html=True)
    word = {"red": "Needs attention", "amber": "Watch", "green": "No concerns in the next 12 h"}[s["status"]]
    why = "".join(f"<li>{'⬇' if k == 'low' else '⬆'} {t}</li>" for k, t in s["reasons"])
    st.markdown(f"""<div class="banner b-{s['status']}"><b>{word}.</b> Chance of a low (&lt;70) in 12 h: <b>{pct(s['p_low'])}</b> ·
      severe high (≥250): <b>{pct(s['p_high'])}</b><ul style="margin:.35rem 0 0 1rem;padding:0">{why}</ul></div>""", unsafe_allow_html=True)
    for q in s["quality"]:
        st.markdown(f"<div class='s'>⚠ {q}</div>", unsafe_allow_html=True)

    left, right = st.columns([1.55, 1])
    # ---------------- timeline + forecast
    with left:
        tb = tw.tabs(aid); start = now - pd.Timedelta("36h")
        poc = tb["poc"][(tb["poc"].time > start) & (tb["poc"].time <= now)]
        cgm = tb["cgm"][(tb["cgm"].time > start) & (tb["cgm"].time <= now)]
        mar = tb["mar"][(tb["mar"].time > start) & (tb["mar"].time <= now) & (tb["mar"].status == "given")]
        meals = tb["meals"][(tb["meals"].time > start) & (tb["meals"].time <= now)]
        traj = s["traj"]
        wi = st.session_state.get(("whatif", aid, now.isoformat()))
        fig = go.Figure()
        fig.add_hrect(y0=T.target_low, y1=T.target_high, fillcolor="#ecfdf5", opacity=0.7, line_width=0)
        fig.add_hline(y=T.hypo, line=dict(color=RED, width=1, dash="dot")); fig.add_hline(y=T.severe_high, line=dict(color=AMBER, width=1, dash="dot"))
        for (s0, e0) in s["view"].npo_windows(now):
            if e0 > start and s0 < now + pd.Timedelta("12h"):
                fig.add_vrect(x0=max(s0, start), x1=min(e0, now + pd.Timedelta("12h")), fillcolor="#f1f5f9", opacity=0.9, line_width=0,
                              annotation_text="nil by mouth", annotation_position="top left", annotation_font_size=10, annotation_font_color=MUTED)
        if len(cgm):
            fig.add_trace(go.Scatter(x=cgm.time, y=cgm.glucose_mgdl, mode="lines", name="CGM", line=dict(color="#94a3b8", width=1.5)))
        fig.add_trace(go.Scatter(x=poc.time, y=poc.glucose_mgdl, mode="markers+text", name="Fingerstick", text=poc.glucose_mgdl.round().astype(int),
                                 textposition="top center", textfont=dict(size=10, color=INK), marker=dict(size=9, color=INK)))
        xs = [now] + list(traj.time)
        g0 = r["cgm_now"] if s["mode"] == "B" and pd.notna(r.get("cgm_now")) else (traj.mid.iloc[0] if pd.isna(r["last_poc"]) else r["last_poc"])

        def band(tr, color, name, dash):
            fig.add_trace(go.Scatter(x=xs + xs[::-1], y=[g0] + list(tr.hi) + list(tr.lo)[::-1] + [g0], fill="toself", fillcolor=color,
                                     opacity=0.15, line=dict(width=0), name=f"{name} · 80% range", hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=xs, y=[g0] + list(tr.mid), mode="lines", name=name, line=dict(color=color, width=2.5, dash=dash)))
        band(traj, TEAL, "Twin forecast", "dash")
        if wi:
            band(wi["traj"], VIOLET, "What-if", "dot")
        for t, d, v in zip(mar.time, mar.drug, mar.dose):
            if d in ("basal_glargine", "rapid_prandial", "rapid_correction"):
                fig.add_annotation(x=t, y=48, text=f"{'B' if d == 'basal_glargine' else 'R'}{v:.0f}", showarrow=False,
                                   font=dict(size=10, color=BLUE), bgcolor="#eff6ff")
            elif d in ("prednisolone", "dexamethasone"):
                fig.add_annotation(x=t, y=48, text="steroid", showarrow=False, font=dict(size=10, color=AMBER), bgcolor="#fffbeb")
            elif d in ("oral_glucose", "dextrose_iv"):
                fig.add_annotation(x=t, y=60, text="glucose given", showarrow=False, font=dict(size=9, color=RED))
        for t, f in zip(meals.time, meals.intake_fraction):
            fig.add_annotation(x=t, y=34, text=f"🍽 {f:.0%}", showarrow=False, font=dict(size=9, color=MUTED))
        if s["plan"]["extra"]:
            x = s["plan"]["extra"]
            fig.add_vline(x=x["time"], line=dict(color=VIOLET, width=1.5, dash="dash"))
            fig.add_annotation(x=x["time"], y=0.97, yref="paper", text="extra check", showarrow=False, font=dict(color=VIOLET, size=11),
                               yanchor="top", xanchor="left", bgcolor="white")
        fig.add_vline(x=now, line=dict(color=MUTED, width=1))
        ymax = max(320, (poc.glucose_mgdl.max() if len(poc) else 0) + 30, traj.hi.max() + 20)
        fig.update_layout(height=430, margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="white", paper_bgcolor="white",
                          legend=dict(orientation="h", y=1.1, x=0, font=dict(size=11)), hovermode="x unified",
                          yaxis=dict(title="mg/dL", range=[25, ymax], gridcolor=LINE), xaxis=dict(gridcolor=LINE, range=[start, now + pd.Timedelta("12h")]))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.caption("Black dots: fingersticks. Teal: the twin's forecast for the next 12 h with its 80% range. B = basal, R = rapid insulin (units). 🍽 = share of meal eaten. Grey band = nil by mouth.")
        # next check (feature 3)
        pl = s["plan"]
        prot = ", ".join(f"{t:%H:%M}" for t in pl["protocol"]) or "none"
        if pl["extra"]:
            x = pl["extra"]
            st.markdown(f"""<div class="card"><h4>Next fingerstick</h4><span class="chip violet">Twin suggests an extra check at {x['time']:%H:%M}</span>
              <div class="s" style="margin-top:.3rem">{x['why']} ({pct(x['p'])} chance of being {'below 70' if x['kind'] == 'low' else 'above 250'} then).
              Protocol checks in the next 12 h: {prot}.</div></div>""", unsafe_allow_html=True)
            if st.button(f"Add {x['time']:%H:%M} check to the nursing list"):
                tw.store.add_check(aid, now, x["time"], x["why"], user); tw.store.audit(tw.ward, aid, now, user, "extra_check_added", {"time": x["time"]})
                st.toast("Check added to the nursing list.")
        if pl.get("suggest_cgm"):
            st.markdown(f"""<div class="card"><h4>Monitoring</h4><span class="chip red">Consider a CGM for this patient</span>
              <div class="s" style="margin-top:.3rem">The twin rates this patient at high risk of a low. On fingersticks alone, most lows happen
              between checks{(f"; in testing, a CGM started at the first red flag was on for {_ad['share_after_first_red_flag']:.0%} of all lows and was needed by {_ad['admissions_flagged']:.0%} of patients") if _ad else ""}.</div></div>""",
                        unsafe_allow_html=True)
        if not pl["extra"]:
            st.markdown(f"""<div class="card"><h4>Next fingerstick</h4><span class="chip green">Protocol timing is enough</span>
              <div class="s" style="margin-top:.3rem">Protocol checks in the next 12 h: {prot}. No hour between them carries a high chance of a low or a severe high.</div></div>""",
                        unsafe_allow_html=True)
    # ---------------- before you give insulin (feature 2)
    with right:
        st.markdown("#### Before you give insulin")
        if not s["doses"]:
            st.markdown("<div class='card s'>No insulin or sulfonylurea due in the next 8 hours.</div>", unsafe_allow_html=True)
        for i, d in enumerate(s["doses"]):
            name = {"basal": "Basal (glargine)", "mealtime": "Mealtime insulin (aspart)", "sulfonylurea": "Glimepiride"}[d["kind"]]
            unit = "mg" if d["kind"] == "sulfonylurea" else "U"
            flags = "".join(f"<div class='flag f-{f['level']}'>{'⛔' if f['level'] == 'high' else '⚠'} {f['text']}</div>" for f in d["flags"]) or \
                "<div class='s'>✓ No concerns found in the record.</div>"
            cmp_ = d["compare"]
            alt = " · ".join(f"{lab}: <b>{pct(v)}</b>" for lab, v in (("as ordered", cmp_["as_ordered"]), ("20% less", cmp_.get("reduced_20")), ("held", cmp_.get("held"))) if v is not None)
            st.markdown(f"""<div class="card"><h4>{name} · {d['units']:.0f} {unit} at {d['time']:%H:%M}</h4>{flags}
              <div class="s" style="margin-top:.4rem">Chance of a low in 12 h — {alt}</div></div>""", unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            k = f"{aid}{i}{now.isoformat()}"
            if c1.button("Give as ordered", key="g" + k):
                tw.store.decision(aid, now, d["kind"], d["time"], d["units"], "given_as_ordered", d["units"], user, "", d["flags"]); st.toast("Recorded.")
            if c2.button("Hold · ask doctor", key="h" + k):
                tw.store.decision(aid, now, d["kind"], d["time"], d["units"], "held_for_review", 0, user, "", d["flags"]); st.toast("Recorded; doctor notified.")
            if role == "Doctor" and d["kind"] != "sulfonylurea":
                new = c3.number_input("Try dose", 0, int(d["units"] * 2 + 10), int(d["units"]), key="n" + k, label_visibility="collapsed")
                if st.button(f"See what-if at {new} {unit}", key="w" + k):
                    ov = {"basal": "basal_tonight", "mealtime": "prandial_next"}[d["kind"]]
                    st.session_state[("whatif", aid, now.isoformat())] = tw.what_if(aid, now, {ov: new})
                    st.session_state[("whatif_i", aid, now.isoformat())] = i
                    tw.store.audit(tw.ward, aid, now, user, "what_if", {ov: new}); st.rerun()
                wi = st.session_state.get(("whatif", aid, now.isoformat()))
                if wi and st.session_state.get(("whatif_i", aid, now.isoformat())) == i:
                    dd = wi.get("delta")
                    eff = f" Expected change: {dd[5]:+.0f} mg/dL at 6 h, {dd[-1]:+.0f} at 12 h." if dd is not None else ""
                    st.markdown(f"<div class='s'>What-if: low {pct(wi['p_low'])} · high {pct(wi['p_high'])} (violet on the chart).{eff} "
                                "Uses standard insulin action profiles and this patient's insulin sensitivity; a model estimate, not a dosing recommendation.</div>",
                                unsafe_allow_html=True)
                    if st.button("Change the order to this dose", key="c" + k):
                        tw.store.decision(aid, now, d["kind"], d["time"], d["units"], "order_changed", new, user, "via what-if", d["flags"])
                        st.toast("Order change recorded (demo: the hospital record is not modified).")
        st.markdown("#### Recent fingersticks")
        rp = tb["poc"][tb["poc"].time <= now].tail(8).iloc[::-1]
        st.dataframe(pd.DataFrame({"Time": rp.time.dt.strftime("%d %b %H:%M"), "mg/dL": rp.glucose_mgdl.astype(int), "Type": rp.reason}),
                     hide_index=True, width="stretch")
        dec = tw.store.table("decisions", aid, 20)
        if len(dec):
            st.markdown("#### Decisions recorded")
            st.dataframe(dec[["created", "by", "dose_kind", "ordered_units", "decision", "units"]], hide_index=True, width="stretch")

# ================================================================== DISCHARGE
elif st.session_state.view == "Discharge":
    ids = list(board.admission_id); labels = {a: f"{b} · {n}" for a, b, n in zip(board.admission_id, board.bed, board.name)}
    cur = st.session_state.aid if st.session_state.aid in ids else ids[0]
    aid = st.selectbox("Patient going home", ids, index=ids.index(cur), format_func=lambda a: labels[a]); st.session_state.aid = aid
    d = tw.discharge(aid, now)
    m = d["metrics"]; ins = d["insulin_last_24h"]
    fl = "".join(f"<li>{x}</li>" for x in d["findings"]) or "<li>No glucose findings needing follow-up.</li>"
    ac = "".join(f"<li>{x}</li>" for x in d["actions"]) or "<li>Routine follow-up with the treating doctor.</li>"
    html = f"""<div class="card"><div class="k">Diabetes handover · generated by GlucoTwin Ward · {now:%d %b %Y %H:%M}</div>
      <div class="v" style="margin:.2rem 0">{d['name']} · {d['age']} y</div>
      <div class="s">{d['reason']} · admitted {d['admit']:%d %b} · {d['los_days']} days so far · {'known diabetes' if d['known_diabetes'] else 'no diabetes diagnosis on admission'}
      {' · HbA1c ' + format(d['hba1c'], '.1f') + '%' if d['hba1c'] else ' · HbA1c not measured'}</div>
      <h4 style="margin-top:.8rem">Glucose in hospital</h4>
      <div class="s">{m['fingersticks']} fingersticks · mean {m['mean']} mg/dL · {m['in_140_180']:.0%} in 140-180 · {m['in_70_180']:.0%} in 70-180 ·
      {m['lows']} below 70 · {m['highs_250']} at 250+</div>
      <h4 style="margin-top:.8rem">Findings</h4><ul>{fl}</ul>
      <h4>Suggested follow-up</h4><ul>{ac}</ul>
      <h4>Insulin given in the last 24 h (for reference)</h4>
      <div class="s">Basal {ins['basal_last_24h_units']:.0f} U · mealtime {ins['mealtime_last_24h_units']:.0f} U · correction {ins['correction_last_24h_units']:.0f} U.
      The discharge regimen is decided by the treating doctor.</div></div>"""
    st.markdown(html, unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    if c1.button("Book diabetes clinic follow-up", type="primary"):
        due = now + pd.Timedelta("14D" if any("2 weeks" in a for a in d["actions"]) else "35D")
        tw.store.followup(aid, now, "Diabetes clinic", due.date(), user); tw.store.audit(tw.ward, aid, now, user, "followup_booked", {"due": due})
        st.toast(f"Booked for {due:%d %b}.")
    c2.download_button("Download handover (HTML)", f"<html><head><meta charset='utf-8'><style>body{{font-family:sans-serif;max-width:720px;margin:2rem auto}}</style></head><body>{html}<p style='color:#888;font-size:12px'>{DISCLAIMER}</p></body></html>",
                       file_name=f"handover_{aid}.html", mime="text/html")

# ================================================================== EVIDENCE
else:
    p = EVAL_DIR / "metrics.json"
    if not p.exists():
        st.info("Run `make evaluate` to produce the evidence.")
    else:
        m = json.loads(p.read_text())
        st.markdown(f"#### Held-out evaluation · model `{m['model_version']}` · synthetic test patients")
        rows = []
        for tgt, lab in (("low", "Low <70 in 12 h"), ("high", "Severe high ≥250 in 12 h")):
            r = m["risk"][tgt]
            rows.append({"Outcome": lab, "Static admission model AUPRC": round(r["static_admission_model"]["auprc"], 2),
                         "Twin · fingersticks AUPRC": round(r["twin_A"]["auprc"], 2), "Twin · CGM AUPRC": round(r["twin_B"]["auprc"], 2),
                         "Prevalence": round(r["twin_A"]["prevalence"], 3)})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        figs = sorted((EVAL_DIR / "figures").glob("*.png"))
        cols = st.columns(2)
        for i, f in enumerate(figs):
            cols[i % 2].image(str(f), width="stretch")
        lim = Path(__file__).resolve().parents[1] / "docs" / "limitations.md"
        if lim.exists():
            st.markdown("#### Limitations"); st.markdown(lim.read_text())

st.markdown(f"<div class='foot'>{DISCLAIMER} · GlucoTwin Ward v0.2 · model {tw.b.version}</div>", unsafe_allow_html=True)
