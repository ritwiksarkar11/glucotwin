# Product brief — GlucoTwin Ward

*Written from the perspective of a product manager at a large Indian multi-specialty hospital network. This is a research
prototype on synthetic patients; no hospital has endorsed or deployed it.*

## 1. The problem

Roughly one in four inpatients has diabetes or high glucose, and glucose is managed on general wards with fingersticks four
times a day, paper sliding scales and a daily consultant round. The failure modes are well documented:

* **Lows happen between checks and harm patients.** In a 10-year study of 54,502 admissions of people with diabetes, 18% had
  a moderate and 2.8% a severe low; both were associated with longer stays, higher charges, readmission and 90-day mortality.
  The risk factors (insulin, fasting, tube feeds, kidney injury, heart failure) are already in the record.
* **Insulin errors are routine.** A 27-hospital bedside audit found insulin errors in up to 39% of insulin-treated inpatients
  and a documented peri-operative diabetes plan for only 29% of surgical patients.
* **Steroid highs are missed by design.** A morning steroid pushes glucose up in the afternoon and evening; wards check
  fasting glucose, which is often normal.
* **New diabetes is missed at discharge.** About a quarter of hyperglycaemic admissions in a 2026 Delhi study had undiagnosed
  diabetes; HbA1c is often not ordered.

Research has not reached the bedside: recent hospital hypoglycaemia models are retrospective, single-centre and predict
once at admission. Real-time CGM to the nursing station cut serious lows in a randomised trial, but CGM is not yet approved
for hospital use even in the US and needs staff and training. The one mature insulin-dosing system (Glytec) is US-only.

## 2. Users and the job to be done

| User | Moment | Job |
|---|---|---|
| Ward nurse in charge | Start of shift, evening round, before each insulin dose | "Show me who could go low tonight and why, and stop me giving a dose that no longer makes sense." |
| Treating doctor / resident | Round, night calls | "Let me see what tonight's basal is likely to do before I change it." |
| Diabetes educator / endocrinology | Daily | "Tell me who needs my team." |
| Discharging doctor | Discharge | "Don't let a new diagnosis or a low-risk regimen leave without a plan." |

## 3. The product: four features, one screen each

| # | Feature | What the user sees | Why it is new |
|---|---|---|---|
| 1 | **Ward risk board** | Every patient with diabetes or high glucose, sorted by risk of a low or a severe high in the next 12 h, each with one or two plain-language reasons from their own record. Red is reserved for lows. | Updates every hour from the data the ward already records, and uses orders already written (tonight's basal, tomorrow's fasting, the steroid course). Published models score once at admission. |
| 2 | **Before you give insulin** | For each dose due in the next 8 h: bedside checks (fasting, poor intake, steroid stopped, kidney injury, low recent glucose) and the chance of a low if given as ordered, reduced or held. Doctors can try a dose and see the projected 12-hour range. | Never proposes a dose. Dose what-ifs use a pharmacology layer validated against counterfactual simulations, because record-trained models cannot learn insulin effects (confounding by indication). |
| 3 | **Smart monitoring** | When the twin rates a patient high-risk, it suggests an extra fingerstick at the riskiest hour and, for the highest-risk patients, a CGM. | Routine fingersticks miss most lows; the twin targets extra checks and sensors to the few patients where lows cluster. |
| 4 | **Discharge handover** | One page: glucose during the stay, lows, steroid course, kidney changes, probable new diabetes from HbA1c (or a prompt to order it), and a follow-up to book. | Closes the loop the ward currently drops; also brings follow-up visits back to the hospital's own diabetes clinic. |

**Deliberately left out of version 1:** a chatbot, a patient app for inpatients, automatic dosing, live CGM dashboards,
and anything that writes to the hospital record without a human.

## 4. Success metrics (pilot)

| Metric | Why | Source |
|---|---|---|
| Lows (<70, <54) per 100 patient-days | The harm we exist to reduce | POC + CGM where available |
| Share of "good diabetes days" (no low, appropriate monitoring, ≤1 reading outside range) | Balanced quality measure used in inpatient audits | Ward data |
| Insulin doses given against a high-level flag | Process safety | Decision log |
| Nurse time per shift on glucose tasks | Adoption depends on saving time, not adding it | Time-motion sample |
| Undiagnosed diabetes identified / HbA1c ordered before discharge | Hand-over quality | Discharge pages |
| Diabetes clinic follow-ups booked and attended | Patient outcome and hospital value | Booking system |
| Alert precision and nuisance rate | Trust | Twin logs |

## 5. Pilot plan

1. **Integration (4-6 weeks):** FHIR export from the hospital information system (patients, encounters, fingersticks, MAR,
   diet/NPO orders, labs) into the twin; connected glucometers if available.
2. **Shadow mode (3 months), one ward** (e.g. cardiac step-down or general medicine): predictions recorded, not shown.
   Measures real accuracy, calibrates thresholds on local data, tests the counterfactual pharmacology layer against
   observed dose changes.
3. **Live (3 months):** board and checks shown to staff; compare with the shadow period and a matched ward.
4. **Decision gate:** expand, change, or stop, on the metrics above.

## 6. Regulation, privacy and safety

* Under CDSCO's Guidance Document on Medical Device Software (July 2026), software that predicts or monitors for a medical
  purpose is medical device software, whatever it is called; AI software must describe its training data (real or
  synthetic), robustness across Indian sub-populations, change control for retraining and post-market drift monitoring.
  Positioning: clinician decision support with mandatory human review and no dose recommendation.
* DPDP Act and Rules (2025): purpose limitation, data minimisation, consent and security; the pilot runs inside the
  hospital's environment.
* Safety design already built: red reserved for lows; no dose proposals; every flag, what-if, decision and booking is
  written to an audit log with the model version.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Alert fatigue | Red only for lows; highs shown as "watch"; thresholds calibrated on local data in shadow mode |
| Data gaps (late MAR entry, missing intake) | Data-quality messages on every patient; fingerstick-only mode by default |
| Staff see it as extra work | Built into existing moments (shift start, before a dose, discharge); one screen each |
| Over-trust in what-ifs | Labelled as estimates; validated against counterfactuals; doses always decided by the doctor |

Evidence from the synthetic evaluation: [`evaluation/model_report.md`](../evaluation/model_report.md).
