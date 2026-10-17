// Build presentation/project_deck.pptx  —  node presentation/build_deck.js
const pptxgen = require("pptxgenjs");
const path = require("path");
const fs = require("fs");
const { applyTheme } = require("/mnt/skills/public/pptx/scripts/apply_theme.js");

const A = (f) => path.join(__dirname, "assets", f);
const M = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "evaluation", "metrics.json"), "utf8"));
const THEME = {
  name: "GlucoTwin Ward", headFontFace: "Cambria", bodyFontFace: "Calibri",
  colors: { dk1: "0F172A", lt1: "FFFFFF", dk2: "134E4A", lt2: "F1F5F9", accent1: "0F766E", accent2: "D97706",
            accent3: "DC2626", accent4: "2563EB", accent5: "7C3AED", accent6: "059669", hlink: "0F766E", folHlink: "134E4A" },
};
const MUTED = "64748B";
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "GlucoTwin Ward"; pres.author = "GlucoTwin team";
const C = pres.SchemeColor;
const pc = (x) => `${Math.round(100 * x)}%`;

pres.defineSlideMaster({ title: "TITLE_DARK", background: { color: C.text2 }, objects: [
  { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.0, w: 11.7, h: 1.3, fontFace: THEME.headFontFace, fontSize: 58, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
  { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.45, w: 11.0, h: 1.3, fontSize: 22, color: "CCFBF1", valign: "top", margin: 0 }, text: "" } }] });
pres.defineSlideMaster({ title: "CONTENT", background: { color: C.background1 }, objects: [
  { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.85, fontFace: THEME.headFontFace, fontSize: 30, bold: true, color: C.text1, valign: "middle", margin: 0 }, text: "" } },
  { text: { text: "GlucoTwin Ward · research prototype on synthetic patients", options: { x: 0.6, y: 7.02, w: 8, h: 0.3, fontSize: 10, color: MUTED, margin: 0 } } }],
  slideNumber: { x: 12.2, y: 7.02, w: 0.5, h: 0.3, fontSize: 10, color: MUTED, align: "right" } });
pres.defineSlideMaster({ title: "CLOSING_DARK", background: { color: C.text1 }, objects: [
  { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 0.8, w: 11.7, h: 1.0, fontFace: THEME.headFontFace, fontSize: 34, bold: true, color: C.background1, align: "left", margin: 0 }, text: "" } }] });

const T = (s, text, o) => s.addText(text, { isTextBox: true, fontSize: 15, color: C.text1, valign: "top", margin: 0, ...o });
const card = (s, x, y, w, h, fill = C.background2, name = "card") => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { type: "none" }, objectName: name });
function badge(s, x, y, label, fill = C.accent1, d = 0.5) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" }, objectName: "badge-" + label });
  s.addText(String(label), { isTextBox: true, x, y, w: d, h: d, fontSize: 15, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0 });
}
function stat(s, x, y, w, big, small, color = C.accent1, size = 48) {
  T(s, big, { x, y, w, h: 0.9, fontSize: size, bold: true, color, fontFace: THEME.headFontFace, valign: "bottom" });
  T(s, small, { x, y: y + 0.95, w, h: 0.75, fontSize: 13.5, color: MUTED });
}
const content = (sec, title) => { const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: sec }); s.addText(title, { placeholder: "title" }); return s; };
const shot = (s, f, x, y, w, ratio, name) => s.addImage({ path: A(f), x, y, w, h: w * ratio, objectName: name, shadow: { type: "outer", blur: 6, offset: 2, angle: 90, color: "94A3B8", opacity: 0.35 } });
const chartText = { catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", dataLabelFontFace: "+mn-lt", legendFontFace: "+mn-lt", titleFontFace: "+mn-lt" };

// 1 ------------------------------------------------------------- title
pres.addSection({ title: "Problem" });
let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Problem" });
s.addText("GlucoTwin Ward", { placeholder: "title" });
s.addText("A live glucose twin for every inpatient with diabetes: it warns about lows before they happen, checks insulin before it is given, targets monitoring and hands over new diabetes at discharge", { placeholder: "body" });
T(s, "[Team name] · Indian Institute of Management Lucknow · Digital Twin in Healthcare PoC Challenge 2026", { x: 0.8, y: 5.6, w: 11.5, h: 0.4, fontSize: 15, color: "99F6E4" });
T(s, "Research prototype on synthetic patients · not a medical device · never recommends a dose", { x: 0.8, y: 6.05, w: 11.5, h: 0.4, fontSize: 13, color: "5EEAD4", italic: true });
s.addNotes("GlucoTwin Ward gives every inpatient with diabetes a live glucose twin that helps the ward prevent lows, catch unsafe insulin doses, monitor the right patients and hand over properly at discharge.");

// 2 ------------------------------------------------------------- problem
s = content("Problem", "Diabetes on the ward goes wrong in predictable ways");
stat(s, 0.6, 1.4, 4.0, "~1 in 4", "inpatients has diabetes or high glucose (27-hospital bedside audit)", C.accent1, 54);
const prob = [["Lows happen between checks", "18% moderate and 2.8% severe lows in 54,502 admissions, linked to longer stays, readmission and 90-day mortality."],
  ["Insulin errors are routine", "Up to 39% of insulin-treated inpatients had an insulin error; 29% of surgical patients had a peri-operative diabetes plan."],
  ["Steroid highs are missed by design", "Morning steroids push glucose up in the afternoon and evening; wards check fasting glucose."],
  ["New diabetes leaves undiagnosed", "About a quarter of hyperglycaemic admissions in a 2026 Delhi study had undiagnosed diabetes."]];
prob.forEach(([h, b], i) => { const y = 1.35 + i * 1.38; card(s, 5.0, y, 7.7, 1.2); badge(s, 5.25, y + 0.33, i + 1, C.accent3, 0.5);
  T(s, h, { x: 6.0, y: y + 0.15, w: 6.5, h: 0.4, fontSize: 18, bold: true }); T(s, b, { x: 6.0, y: y + 0.55, w: 6.5, h: 0.6, fontSize: 13.5, color: "334155" }); });
T(s, "Sources: SHM Converge 2025 · Med J Aust 2021 (QuIDS) · Medicine Today 2014 · J Assoc Physicians India 2026", { x: 0.6, y: 6.6, w: 12, h: 0.3, fontSize: 10, color: MUTED });
s.addNotes("On general wards glucose is managed with fingersticks four times a day, paper sliding scales and one round a day. Four failure modes recur: lows between checks, insulin errors, missed steroid highs and missed new diabetes.");

// 3 ------------------------------------------------------------- gap
s = content("Problem", "What research has not solved yet");
const gap = [["Hospital risk models", "Retrospective, single-centre, predict once at admission; not tested in real time (2025 studies).", C.accent2],
  ["Inpatient CGM", "Cut serious lows in an RCT (Diabetes Care 2020), but not approved for hospital use in most places; needs staff and training.", C.accent4],
  ["Insulin dosing software", "The one mature system is US-only. Indian wards run on paper sliding scales.", C.accent5]];
gap.forEach(([h, b, col], i) => { const x = 0.6 + i * 4.1; card(s, x, 1.5, 3.85, 2.6, C.background2, "gap" + i);
  s.addShape(pres.shapes.OVAL, { x: x + 0.3, y: 1.8, w: 0.3, h: 0.3, fill: { color: col }, line: { type: "none" }, objectName: "gd" + i });
  T(s, h, { x: x + 0.8, y: 1.72, w: 2.9, h: 0.5, fontSize: 18, bold: true }); T(s, b, { x: x + 0.3, y: 2.4, w: 3.3, h: 1.6, fontSize: 14, color: "334155" }); });
card(s, 0.6, 4.5, 12.1, 2.1, "CCFBF1", "gapbox");
T(s, "The gap", { x: 0.95, y: 4.7, w: 11, h: 0.4, fontSize: 15, bold: true, color: C.accent1 });
T(s, "A live, patient-level picture of the next 12 hours, built from what the ward already records, that works on fingersticks today and uses a CGM when one is worn.", { x: 0.95, y: 5.15, w: 11.4, h: 1.2, fontSize: 22, fontFace: THEME.headFontFace, color: C.text2 });
s.addNotes("Research models score once at admission. CGM works in trials but is not yet a hospital standard. Dosing software is US-only. Nobody gives an Indian ward a live 12-hour picture per patient.");

// 4 ------------------------------------------------------------- product
pres.addSection({ title: "Product" });
s = content("Product", "Four features, one screen each, at moments the ward already has");
const feats = [["Ward risk board", "Shift start", "Every patient sorted by chance of a low or severe high in the next 12 h, with reasons from their own record. Red only for lows."],
  ["Before you give insulin", "Before each dose", "Bedside checks plus the chance of a low if given, reduced or held. Doctors can try a dose. Never proposes one."],
  ["Smart monitoring", "Overnight", "An extra fingerstick at the riskiest hour for high-risk patients; a CGM for the highest-risk ones."],
  ["Discharge handover", "Going home", "Glucose during the stay, lows, steroids, kidney changes, probable new diabetes, a follow-up to book."]];
feats.forEach(([h, when, b], i) => { const x = 0.6 + (i % 2) * 6.15, y = 1.45 + Math.floor(i / 2) * 2.55; card(s, x, y, 5.95, 2.35, C.background2, "f" + i);
  badge(s, x + 0.3, y + 0.3, i + 1, C.accent1, 0.55); T(s, h, { x: x + 1.05, y: y + 0.28, w: 4.7, h: 0.45, fontSize: 20, bold: true, fontFace: THEME.headFontFace });
  T(s, when, { x: x + 1.05, y: y + 0.75, w: 4.7, h: 0.35, fontSize: 13, color: C.accent1, bold: true }); T(s, b, { x: x + 0.3, y: y + 1.2, w: 5.4, h: 1.05, fontSize: 14, color: "334155" }); });
T(s, "Left out on purpose: chatbot · patient app for inpatients · automatic dosing", { x: 0.6, y: 6.6, w: 12, h: 0.35, fontSize: 12.5, italic: true, color: MUTED });
s.addNotes("The PM rule: no feature without a moment in the ward's existing day. Four screens, each used at a moment that already exists.");

// 5 ------------------------------------------------------------- twin
s = content("Product", "What makes it a twin");
const loop = ["Synchronise hourly", "Use orders already written", "Predict 12 h", "Simulate a dose", "Check before giving", "Record decisions"];
loop.forEach((l, i) => { const x = 0.6 + i * 2.05; card(s, x, 1.5, 1.85, 1.35, i === 3 ? "EDE9FE" : C.background2, "l" + i);
  badge(s, x + 0.67, 1.62, i + 1, i === 3 ? C.accent5 : C.accent1, 0.48); T(s, l, { x: x + 0.1, y: 2.17, w: 1.65, h: 0.65, fontSize: 13, bold: true, align: "center" }); });
const tw = [["Known future", "Tonight's basal, tomorrow's fasting order and the steroid course are written in advance. The twin uses them; published models cannot."],
  ["Honest uncertainty", "Every forecast has an 80% range that contains the outcome 81-91% of the time on test patients."],
  ["Hybrid what-if", "Insulin effects come from a pharmacology layer, validated against counterfactual simulations, because record-trained models cannot learn them."],
  ["Every decision recorded", "Flags, what-ifs, given/held decisions, extra checks and bookings go to an audit log with the model version."]];
tw.forEach(([h, b], i) => { const x = 0.6 + (i % 2) * 6.15, y = 3.25 + Math.floor(i / 2) * 1.75; card(s, x, y, 5.95, 1.55, C.background2, "t" + i);
  T(s, h, { x: x + 0.3, y: y + 0.18, w: 5.4, h: 0.4, fontSize: 17, bold: true, color: C.accent1 }); T(s, b, { x: x + 0.3, y: y + 0.6, w: 5.4, h: 0.9, fontSize: 13.5, color: "334155" }); });
s.addNotes("A dashboard shows the past. This twin keeps each patient's state, uses orders already written, predicts, simulates and records.");

// 6 ------------------------------------------------------------- data
pres.addSection({ title: "How it works" });
s = content("How it works", "Synthetic ward, real hospital formats");
stat(s, 0.6, 1.3, 3.0, "800", "admissions over 60 days: sepsis, cardiac surgery, COPD/asthma, heart failure, orthopaedics", C.accent1, 44);
stat(s, 3.75, 1.3, 3.0, "73k", "FHIR R4 resources (Bulk Data NDJSON): the only thing the twin reads", C.accent4, 44);
stat(s, 6.9, 1.3, 2.7, "~50%", "of admissions wear a CGM, which supplies outcome labels", C.accent6, 44);
stat(s, 9.75, 1.3, 3.0, "5", "process failures injected at stated rates (hidden ground truth)", C.accent3, 44);
const dd = [["Physiology", "Meals and how much is eaten, rapid and basal insulin, sulfonylureas, steroids peaking in the afternoon, stress, kidney injury, counter-regulation."],
  ["Ward process", "Fingerstick protocol, sliding scale, 09:00 titration round, fasting orders for procedures, hypoglycaemia protocol with rechecks."],
  ["Counterfactual-ready", "Each patient has independent random streams: change one dose and re-run, and everything before the dose is identical."]];
dd.forEach(([h, b], i) => { const x = 0.6 + i * 4.1; card(s, x, 3.6, 3.85, 2.9, C.background2, "d" + i); T(s, h, { x: x + 0.3, y: 3.8, w: 3.3, h: 0.45, fontSize: 18, bold: true });
  T(s, b, { x: x + 0.3, y: 4.35, w: 3.3, h: 2.0, fontSize: 14, color: "334155" }); });
s.addNotes("The simulator is realistic where it matters: steroid patients read about 156 at 07:30 and peak around 220 by evening; fingersticks find lows in 9% of admissions while CGM finds them in about a fifth.");

// 7 ------------------------------------------------------------- architecture
s = content("How it works", "Architecture");
s.addImage({ path: A("architecture.png"), x: 0.6, y: 1.45, w: 12.1, h: 12.1 * 1056 / 3607, objectName: "arch" });
const ar = [["Data in", "FHIR R4 Bulk export from the hospital system + CGM. Swap synthetic for real without touching the models."],
  ["Models", "LightGBM 12-h risk (fingerstick and CGM modes), 1-12 h forecasts with conformal ranges, pharmacology layer."],
  ["Out", "Streamlit ward app and REST API; SQLite store with snapshots, decisions and audit."]];
ar.forEach(([h, b], i) => { const x = 0.6 + i * 4.1; card(s, x, 5.2, 3.85, 1.55, C.background2, "a" + i); T(s, h, { x: x + 0.3, y: 5.35, w: 3.3, h: 0.4, fontSize: 16, bold: true, color: C.accent1 });
  T(s, b, { x: x + 0.3, y: 5.75, w: 3.3, h: 0.95, fontSize: 13, color: "334155" }); });

// 8 ------------------------------------------------------------- demo screens
pres.addSection({ title: "Demo" });
s = content("Demo", "The ward board at 21:00, before the bedtime insulin round");
shot(s, "ward_board.png", 0.6, 1.3, 7.2, 1680 / 2140, "board");
const bd = [["Sorted by risk", "Two red patients (risk of a low), five amber (likely severe high)."], ["Reasons in ward language", "From each patient's own record: readings under 100, steroid given this morning, fasting tomorrow."],
  ["Actions", "Insulin doses to review; CGM suggested; extra check times."]];
bd.forEach(([h, b], i) => { const y = 1.45 + i * 1.6; badge(s, 8.3, y, i + 1, C.accent1, 0.45); T(s, h, { x: 8.95, y: y - 0.02, w: 3.75, h: 0.4, fontSize: 16, bold: true });
  T(s, b, { x: 8.95, y: y + 0.4, w: 3.75, h: 1.1, fontSize: 13.5, color: "334155" }); });

s = content("Demo", "One patient's twin: check, simulate, monitor");
shot(s, "patient_twin.png", 0.6, 1.3, 6.2, 1910 / 2140, "pt");
const pd = [["Before you give insulin", "Basal 14 U due at 22:00: 98% chance of a low in 12 h if given as ordered."], ["Doctor what-if", "Hold the dose: forecast rises ~38 mg/dL (violet), chance of a low falls. The doctor decides; the decision is recorded."],
  ["Smart monitoring", "Extra check suggested at 01:00 and a CGM for this patient."]];
pd.forEach(([h, b], i) => { const y = 1.4 + i * 1.75; badge(s, 7.5, y, i + 1, i === 1 ? C.accent5 : C.accent1, 0.45); T(s, h, { x: 8.15, y: y - 0.02, w: 4.55, h: 0.4, fontSize: 16, bold: true });
  T(s, b, { x: 8.15, y: y + 0.4, w: 4.55, h: 1.25, fontSize: 13.5, color: "334155" }); });

// 9 ------------------------------------------------------------- evidence: board
pres.addSection({ title: "Evidence" });
const r = M.risk, be = M.board_episodes;
s = content("Evidence", "The live twin beats an admission-time model by a wide margin");
s.addChart(pres.charts.BAR, [
  { name: "Static admission model", labels: ["Low in 12 h", "Severe high in 12 h"], values: [r.low.static_admission_model.auprc, r.high.static_admission_model.auprc] },
  { name: "Twin · fingersticks", labels: ["Low in 12 h", "Severe high in 12 h"], values: [r.low.twin_A.auprc, r.high.twin_A.auprc] },
  { name: "Twin · CGM", labels: ["Low in 12 h", "Severe high in 12 h"], values: [r.low.twin_B.auprc, r.high.twin_B.auprc] }],
  { x: 0.6, y: 1.35, w: 7.4, h: 5.3, barDir: "col", barGapWidthPct: 55, chartColors: ["CBD5E1", "D97706", "0F766E"], showValue: true, dataLabelPosition: "outEnd",
    dataLabelFormatCode: "0.00", dataLabelFontSize: 12, dataLabelColor: "334155", showLegend: true, legendPos: "b", legendFontSize: 12,
    valAxisMinVal: 0, valAxisMaxVal: 1, valGridLine: { color: "E2E8F0", size: 0.5 }, catGridLine: { style: "none" }, catAxisLabelColor: "334155",
    valAxisLabelColor: MUTED, catAxisLabelFontSize: 13, valAxisLabelFontSize: 11, showTitle: true, title: "AUPRC on held-out patients (higher is better)",
    titleFontSize: 14, titleColor: "334155", ...chartText });
stat(s, 8.5, 1.4, 4.2, pc(be.low_A.flagged_before_onset), `of lows flagged red before they started (fingersticks), median ${Math.round(be.low_A.median_lead_h)} h ahead`, C.accent3, 48);
stat(s, 8.5, 3.2, 4.2, be.low_A.red_hours_per_patient_day.toFixed(2), "red hours per patient-day: a light alert load", C.accent1, 48);
stat(s, 8.5, 5.0, 4.2, "81-91%", "of outcomes fall inside the twin's 80% forecast range", C.accent4, 40);

// 10 ------------------------------------------------------------ evidence: insulin check
const ic = M.insulin_check, f = ic.injected_failures_flagged;
s = content("Evidence", "The insulin check catches unsafe doses before they are given");
const rowsIC = [["Mealtime insulin while nil by mouth", f.prandial_given_while_fasting], ["Basal not reduced the night before a fast", f.basal_not_reduced_before_fasting],
  ["Insulin not reduced after the steroid course ended", f.insulin_not_reduced_after_steroid_stop], ["Insulin not reduced after kidney injury", f.insulin_not_reduced_on_aki],
  ["Sulfonylurea given while fasting", f.sulfonylurea_given_while_fasting]];
const tbl = [[{ text: "Injected process failure", options: { bold: true, color: MUTED } }, { text: "Flagged before the dose", options: { bold: true, color: MUTED, align: "right" } }]];
rowsIC.forEach(([lab, v]) => tbl.push([lab, { text: `${v.flagged} / ${v.total}`, options: { align: "right", bold: true } }]));
s.addTable(tbl, { x: 0.6, y: 1.45, w: 7.4, colW: [5.4, 2.0], fontSize: 15, fontFace: "Calibri", color: "334155", border: { type: "solid", color: "E2E8F0", pt: 0.75 }, rowH: 0.62 });
stat(s, 8.6, 1.45, 4.1, pc(ic.overall_flag_rate), "of all injected unsafe situations flagged (bedside rules, all 800 admissions)", C.accent1, 54);
stat(s, 8.6, 3.5, 4.1, `${(100 * ic.high_flags_per_dose).toFixed(1)}%`, "of routine doses get a high-level flag: low noise for nurses", C.accent4, 44);
T(s, "Rules a nurse can verify at the bedside: fasting, poor intake, steroid stopped, kidney injury, low recent glucose. The twin never proposes a dose.", { x: 0.6, y: 5.5, w: 12, h: 0.8, fontSize: 14, italic: true, color: MUTED });

// 11 ------------------------------------------------------------ evidence: what-if
const wv = M.what_if_validation;
s = content("Evidence", "Dose what-ifs: pharmacology beats learning from records");
s.addChart(pres.charts.BAR, [{ name: "Error vs true effect (mg/dL)", labels: ["Assume no effect", "Learned model", "Pharmacology layer"],
  values: [wv.basal.mae_assume_no_effect, wv.basal.mae_learned_forecast, wv.basal.mae_pharmacology] }],
  { x: 0.6, y: 1.35, w: 6.2, h: 4.4, barDir: "bar", chartColors: ["CBD5E1", "D97706", "7C3AED"], invertedColors: ["CBD5E1", "D97706", "7C3AED"], showValue: true, dataLabelPosition: "outEnd",
    dataLabelFormatCode: "0.0", dataLabelFontSize: 13, dataLabelColor: "334155", showLegend: false, valAxisMinVal: 0, valGridLine: { color: "E2E8F0", size: 0.5 },
    catGridLine: { style: "none" }, catAxisLabelColor: "334155", catAxisLabelFontSize: 13, valAxisLabelColor: MUTED, showTitle: true,
    title: "Basal what-if: mean error vs counterfactual simulation", titleFontSize: 14, titleColor: "334155", ...chartText });
card(s, 7.2, 1.4, 5.5, 2.3, "F5F3FF", "wi1");
T(s, "Holding tonight's basal: glucose at 6 h", { x: 7.5, y: 1.6, w: 5, h: 0.4, fontSize: 15, bold: true, color: C.accent5 });
T(s, [{ text: `True +${Math.round(wv.basal.mean_true_effect_6h_when_held)}`, options: { bold: true } }, { text: `   ·   twin +${Math.round(wv.basal.mean_pharm_effect_6h_when_held)}   ·   learned model +${Math.round(wv.basal.mean_learned_effect_6h_when_held)} mg/dL` }],
  { x: 7.5, y: 2.15, w: 5, h: 1.2, fontSize: 20, fontFace: THEME.headFontFace });
card(s, 7.2, 3.95, 5.5, 2.75, C.background2, "wi2");
T(s, "Why", { x: 7.5, y: 4.15, w: 5, h: 0.4, fontSize: 15, bold: true, color: C.accent1 });
T(s, "Doctors give more insulin to patients who run high, so a model trained on records cannot separate a dose's effect from its reason (confounding by indication). The twin uses textbook insulin action profiles × the patient's insulin sensitivity, scaled on training patients and tested on counterfactual re-runs of test patients.",
  { x: 7.5, y: 4.6, w: 5, h: 2.0, fontSize: 13, color: "334155" });
T(s, `Mealtime insulin: error ${wv.prandial.mae_pharmacology.toFixed(1)} vs ${wv.prandial.mae_learned_forecast.toFixed(1)} mg/dL · ${wv.test_events} test dose events`, { x: 0.6, y: 6.0, w: 6.2, h: 0.4, fontSize: 12.5, color: MUTED });

// 12 ------------------------------------------------------------ evidence: smart monitoring
const ct = M.check_timing, ad = M.adaptive_sensing, k = "twin_threshold_0.2";
s = content("Evidence", "Fingersticks miss most lows: target the patients who need more");
s.addImage({ path: path.join(__dirname, "..", "evaluation", "figures", "smart_monitoring.png"), x: 0.6, y: 1.35, w: 7.8, h: 7.8 * 4.3 / 10, objectName: "sm" });
stat(s, 8.8, 1.35, 3.9, pc(ct.protocol_only.low_caught), "of CGM-recorded lows are caught by routine fingersticks", C.accent3, 44);
stat(s, 8.8, 3.0, 3.9, `${ct[k].extra_lows_caught_per_100_checks.toFixed(1)} vs ${ct.fixed_3am_check_on_insulin.extra_lows_caught_per_100_checks.toFixed(1)}`, "extra lows caught per 100 extra checks: twin-targeted vs a 3 am check for everyone", C.accent2, 40);
stat(s, 8.8, 4.65, 3.9, pc(ad.share_after_first_red_flag), `of lows happen after the twin's first red flag: a CGM then needs a sensor on only ${pc(ad.admissions_flagged)} of patients`, C.accent1, 44);

// 13 ------------------------------------------------------------ evidence: discharge
const dc = M.discharge;
s = content("Evidence", "Discharge handover closes the loop the ward drops");
shot(s, "discharge.png", 0.6, 1.35, 7.4, 1100 / 2140, "dc");
stat(s, 8.5, 1.4, 4.2, pc(dc.identified_or_prompted), `of ${dc.undiagnosed_diabetes_admissions} patients with undiagnosed diabetes identified (${pc(dc.identified_as_probable_new_diagnosis)}) or prompted for HbA1c (${pc(dc.prompted_to_order_hba1c)})`, C.accent1, 54);
stat(s, 8.5, 3.6, 4.2, "0", "false new diagnoses among patients with stress hyperglycaemia only", C.accent6, 54);
T(s, "Also on the page: lows during the stay, steroid course, kidney changes, insulin started in hospital, a follow-up to book. It brings follow-up visits back to the hospital's own diabetes clinic.", { x: 0.6, y: 5.4, w: 7.4, h: 1.2, fontSize: 13.5, color: "334155" });

// 14 ------------------------------------------------------------ adoption
pres.addSection({ title: "Adoption" });
s = content("Adoption", "From prototype to one real ward");
const steps = [["Integrate", "4-6 weeks", "FHIR export from the hospital system: encounters, fingersticks, MAR, diet/NPO orders, labs. Connected glucometers if available."],
  ["Shadow mode", "3 months", "One ward. Predictions recorded, not shown. Measure real accuracy; recalibrate thresholds; test the what-if on real dose changes."],
  ["Live", "3 months", "Board and checks shown to staff; compare with shadow period and a matched ward."],
  ["Decide", "Gate", "Expand, change or stop on lows per 100 patient-days, good diabetes days, flags overridden, nurse time, new diabetes captured, follow-ups."]];
steps.forEach(([h, d, b], i) => { const x = 0.6 + i * 3.08; card(s, x, 1.5, 2.88, 3.3, C.background2, "st" + i); badge(s, x + 0.25, 1.7, i + 1, C.accent1, 0.48);
  T(s, h, { x: x + 0.85, y: 1.72, w: 1.95, h: 0.45, fontSize: 18, bold: true }); T(s, d, { x: x + 0.25, y: 2.35, w: 2.4, h: 0.35, fontSize: 13, bold: true, color: C.accent1 });
  T(s, b, { x: x + 0.25, y: 2.75, w: 2.45, h: 2.0, fontSize: 13, color: "334155" }); });
card(s, 0.6, 5.1, 12.1, 1.55, "FFFBEB", "reg");
T(s, "Regulation and privacy", { x: 0.9, y: 5.25, w: 11.5, h: 0.4, fontSize: 15, bold: true, color: "B45309" });
T(s, "CDSCO medical device software guidance (July 2026): prediction/monitoring software is medical device software; AI must disclose training data (real or synthetic), Indian sub-population robustness, change control and drift monitoring. Positioned as decision support with human review and no dose recommendation. DPDP by design.",
  { x: 0.9, y: 5.65, w: 11.6, h: 1.0, fontSize: 12.5, color: "334155" });

// 15 ------------------------------------------------------------ limitations
s = content("Adoption", "Limitations, stated plainly");
const lim = ["All evidence is synthetic: the next step is shadow mode on real ward data.", "The simulator sets physiology, ward routines and failure rates; real wards will differ.",
  "Dose what-ifs are validated on counterfactuals that share the simulator's assumptions.", "Fingersticks have a low ceiling for catching lows; that is why the CGM suggestion matters.",
  "Not covered: ICU, insulin infusions, tube feeds, type 1 diabetes, DKA, children, pregnancy."];
lim.forEach((l, i) => { const y = 1.5 + i * 1.0; badge(s, 0.6, y, i + 1, C.accent2, 0.45); T(s, l, { x: 1.3, y: y + 0.05, w: 11.3, h: 0.6, fontSize: 17, color: "334155" }); });

// 16 ------------------------------------------------------------ close
pres.addSection({ title: "Close" });
s = pres.addSlide({ masterName: "CLOSING_DARK", sectionTitle: "Close" });
s.addText("Every inpatient with diabetes gets a twin", { placeholder: "title" });
T(s, "that warns, checks, targets and hands over.", { x: 0.8, y: 1.8, w: 11, h: 0.6, fontSize: 26, italic: true, color: "5EEAD4", fontFace: THEME.headFontFace });
const fin = [[`${r.low.twin_A.auprc.toFixed(2)} vs ${r.low.static_admission_model.auprc.toFixed(2)}`, "AUPRC for lows: twin vs admission model"], [pc(ic.overall_flag_rate), "unsafe doses flagged before giving"],
  [pc(ad.share_after_first_red_flag), "of lows covered by a CGM on 9% of patients"], [pc(dc.identified_or_prompted), "undiagnosed diabetes caught at discharge"]];
fin.forEach(([b, l], i) => { const x = 0.8 + i * 3.05; T(s, b, { x, y: 3.0, w: 2.9, h: 0.9, fontSize: 32, bold: true, color: "FFFFFF", fontFace: THEME.headFontFace, valign: "bottom" });
  T(s, l, { x, y: 3.95, w: 2.8, h: 0.8, fontSize: 14, color: "CBD5E1" }); });
T(s, "github.com/ritwiksarkar11/glucotwin  ·  make app", { x: 0.8, y: 5.6, w: 11.5, h: 0.5, fontSize: 18, color: "99F6E4", fontFace: "Courier New" });
T(s, "Research prototype on synthetic patients · Apache-2.0", { x: 0.8, y: 6.2, w: 11.5, h: 0.4, fontSize: 13, color: "94A3B8" });

(async () => { const out = path.join(__dirname, "project_deck.pptx"); await pres.writeFile({ fileName: out }); await applyTheme(out, THEME); console.log("wrote", out); })();
