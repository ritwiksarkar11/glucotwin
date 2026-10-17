# GlucoTwin Ward — video script (about 21 minutes)

Record the deck (`presentation/project_deck.pptx`) and the live app (`make app`, or the Streamlit link). The app opens on
Ward 7B, Monday 24 Aug, 21:00, before the bedtime insulin round.

## 0:00-3:00 · The problem (slides 1-3)
* Slide 1: "GlucoTwin Ward gives every inpatient with diabetes a live glucose twin."
* Slide 2: one in four inpatients has diabetes or high glucose. Lows between fingerstick checks (18% moderate, 2.8% severe
  in 54,502 admissions, linked to longer stays and mortality); insulin errors in up to 39% of insulin-treated patients;
  steroid highs missed because wards check fasting glucose; new diabetes missed at discharge.
* Slide 3: what research has not solved: models score once at admission; CGM in hospital works in trials but is not
  approved for hospital use in most places; the only dosing system is US-only. The gap: a live 12-hour picture per patient.

## 3:00-6:00 · Product (slides 4-5)
* Slide 4: four features, one screen each, built around moments the ward already has: shift start, before a dose, the
  night, discharge. What we left out: chatbot, patient app, automatic dosing.
* Slide 5: what makes it a twin: it synchronises every hour, uses orders already written (tonight's basal, tomorrow's
  fasting, the steroid course), predicts, simulates doses, and records every decision.

## 6:00-9:00 · Data and architecture (slides 6-7)
* Slide 6: the ward simulator: 800 admissions, physiology plus the ward process, process failures injected at stated rates,
  exported as FHIR R4 Bulk Data, the only thing the twin reads. Every patient has independent random streams, so any dose
  can be changed and the patient re-run: a true counterfactual.
* Slide 7: architecture, left to right.

## 9:00-14:00 · Live demo (slides 8-9, then the app)
1. **Board.** Two red patients, five amber. Read the reasons for 7B-15 ("4 readings under 100 in 24 h"). Point out that
   red is reserved for lows and severe highs show as amber. Chips: insulin doses to review, CGM suggested.
2. **Patient twin.** Click the red patient. Chart: fingersticks, insulin given (B/R), share of meals eaten, the 12-hour
   forecast with its range dipping toward 70 overnight.
3. **Before you give insulin.** Basal 14 U at 22:00: a 98% chance of a low if given as ordered.
4. **What-if.** Switch to Doctor, set the dose to 0, press *See what-if*: the violet line lifts about 38 mg/dL and the
   chance of a low falls. Say: "The twin never proposes a dose. The doctor decides, and the decision is recorded."
5. **Smart monitoring.** "Twin suggests an extra check at 01:00"; add it to the nursing list. "Consider a CGM for this
   patient."
6. **Another patient with an insulin flag**, e.g. the steroid patient: "Steroid course has ended; insulin dose not yet
   reduced."
7. **Clock.** Press *+4 h*: the board re-synchronises.
8. **Discharge.** Open the handover; book the follow-up; download the page.

## 14:00-18:00 · Evidence (slides 10-14)
* Slide 10: board: AUPRC 0.47 vs 0.12 for a static admission-time model; 69% of lows flagged red a median 11 h ahead.
* Slide 11: insulin check: 92% of injected unsafe situations flagged, a serious flag on under 5% of routine doses.
* Slide 12: what-if: learned models cannot learn insulin effects (confounding); the pharmacology layer matches the true
  counterfactual effect with half the error. Holding basal: true +25 mg/dL, twin +23, learned model +2.
* Slide 13: smart monitoring: fingersticks catch 12% of lows; targeted extra checks 20% (5x the yield of a 3 am check for
  everyone); a CGM on the twin's first red flag covers 80% of lows using sensors on 9% of patients.
* Slide 14: discharge: 91% of undiagnosed diabetes identified or prompted.

## 18:00-21:00 · Hospital adoption, limitations, close (slides 15-17)
* Slide 15: pilot: FHIR integration, 3 months shadow mode on one ward, 3 months live; metrics: lows per 100 patient-days,
  good diabetes days, flags overridden, nurse time, new diabetes captured, follow-ups booked. CDSCO medical device
  software guidance (July 2026): decision support, change control, drift monitoring. DPDP by design.
* Slide 16: limitations: synthetic evidence only; simulator assumptions; what-ifs share them; fingersticks have a low
  ceiling, which is why the CGM suggestion matters.
* Slide 17: close: "Every inpatient with diabetes gets a twin that warns, checks, targets and hands over." Show the repo.
