# Data card — GlucoTwin Ward synthetic cohort v2

**All data are synthetic.** No real patient data were used or needed.

## Summary

| | |
|---|---|
| Admissions | 800 fictional adults with diabetes or in-hospital hyperglycaemia, admitted over 60 days to medical and surgical wards |
| Admission reasons | pneumonia/sepsis 30%, cardiac surgery 18%, COPD/asthma exacerbation 20%, heart failure 17%, orthopaedic surgery 15% |
| Glycaemic status | known type 2 on oral drugs 40%, known type 2 on insulin 25%, undiagnosed diabetes 15%, stress hyperglycaemia without diabetes 20% |
| Length of stay | 3-10 days |
| CGM | about half of admissions (a "study cohort", as in inpatient CGM trials) |
| Format | HL7 FHIR R4 Bulk Data export (NDJSON) + CGM CSV; see `data/synthetic/cohort_stats.json` |
| Generator | `python -m glucotwin.sim.generate --admissions 800 --days 60` (deterministic, seed 11) |

## Stream A — the hospital record (FHIR R4)

| Resource | Content |
|---|---|
| Patient, Encounter | demographics; admission and discharge time; reason (SNOMED CT); CGM flag |
| Condition | type 2 diabetes, chronic kidney disease, heart failure |
| Observation | fingerstick glucose (LOINC 41653-7) with protocol/recheck note; HbA1c (4548-4, measured in ~65% of admissions); daily creatinine (2160-0); weight, height |
| MedicationRequest | home medicines; ward orders: basal units, mealtime units, correction scale, sulfonylurea continue/hold, steroid course and daily doses, "tonight's basal" adjustments |
| MedicationAdministration | every dose given or held (insulin aspart mealtime/correction, glargine, glimepiride, prednisolone, dexamethasone, oral glucose, IV dextrose) |
| NutritionOrder | diabetic diet; nil-by-mouth windows for surgery and procedures (written at the previous day's round) |
| NutritionIntake | each meal: carbohydrate served and share eaten (nurse-recorded, quarters) |
| Procedure | surgery time |

## Stream B — CGM

5-minute interstitial glucose with a 10-minute lag, slowly drifting calibration error, proportional noise, 3% random dropouts
and occasional longer gaps. About 700k readings.

## The simulator

**Physiology (hidden):** two-compartment meal absorption scaled by what the patient eats; rapid-acting and basal insulin
action; sulfonylurea effect; glucocorticoid effect peaking 4-8 hours after a morning dose; illness and post-operative
stress that fades over days; acute kidney injury that prolongs and strengthens insulin action; IV dextrose; counter-
regulation below 70 mg/dL; autocorrelated noise. Each patient has individual parameters (set point, clearance, meal
response, insulin sensitivity, steroid sensitivity) partly linked to HbA1c and weight and partly unobserved.

**Ward process (observable):** fingersticks at 07:30, 12:30, 19:30 and 22:00 on insulin (07:30 and 19:30 otherwise);
sliding-scale correction; basal-bolus orders; a 09:00 consultant round that titrates insulin from the last 24 hours;
hypoglycaemia protocol (15 g glucose or IV dextrose, recheck at 15 minutes); appetite that is poor early in illness and
after surgery; morning creatinine.

**Injected process failures** (recorded only in hidden ground truth):

| Failure | Probability |
|---|---|
| Mealtime insulin given although nil by mouth | 20% of fasting meals with insulin ordered |
| Basal not reduced the night before a fast | 50% |
| Insulin not reduced after the steroid course ends | 60% (reduced with probability 40%) |
| Insulin not reduced after kidney injury is detected | 60% (reduced with probability 40%) |
| Sulfonylurea given while fasting | 50% |
| Sulfonylurea continued in hospital | 30% of home users |

**Counterfactual design:** every admission has independent random streams, so re-simulating one admission with a single
dose changed reproduces the baseline exactly up to that dose. This is how the insulin what-ifs are validated.

## Resulting cohort (realism checks)

Mean fingerstick glucose ~177 mg/dL with ~29% of readings in 140-180; about 11% of admissions have a fingerstick low,
while CGM records lows in about a fifth of CGM-wearing admissions (CGM detects more lows than fingersticks, as in real
studies); steroid patients read about 156 mg/dL at 07:30 and peak around 215-225 mg/dL in mid-afternoon to evening.

## Hidden ground truth

`data/synthetic/_hidden/` holds true 5-minute glucose, injected failures and physiology. It is used only to score
process-failure detection and the discharge findings. Features and models never read it.
