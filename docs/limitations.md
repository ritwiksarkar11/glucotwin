**GlucoTwin Ward is a research prototype on synthetic patients, not a medical device.** It has not been validated on real patients and must not be used for clinical decisions.

1. **Synthetic evidence only.** Every patient, dose and reading comes from our simulator. Results show the method works and is evaluated without leakage; they do not show accuracy on a real ward. Shadow-mode testing on real ward data is the necessary next step.
2. **The simulator shapes the results.** Physiology, ward routines and process-failure rates are simplified and set by us (documented in `docs/data_card.md`). Real wards will differ, especially in how often meals are missed, how doses are timed and how lows are treated.
3. **CGM-defined outcomes.** Lows and highs are labelled from CGM in about half of admissions. Real inpatient CGM has drug interferences and is not yet approved for hospital use in many countries.
4. **What-ifs are an estimate.** Learned models cannot separate a dose's effect from the reason it was given, so dose what-ifs use a pharmacology layer (standard action profiles plus the patient's estimated insulin sensitivity). It was validated against counterfactual simulations, which share the simulator's assumptions. It never recommends a dose.
5. **Smart monitoring has a low ceiling with fingersticks.** Routine checks catch about a fifth of CGM-recorded lows, and well-placed extra checks add only a few points. The larger gain comes from putting a CGM on the patients the twin flags.
6. **Not covered:** intensive care, intravenous insulin infusions, tube feeding, type 1 diabetes, diabetic ketoacidosis, children and pregnancy.
7. **Sulfonylurea what-ifs** fall back to the learned model, which has a weak dose signal; only the bedside rule is reliable for them.
8. **Single ward, single time zone, simulated documentation.** Real records arrive late, get corrected and have gaps that the simulator only partly reproduces.
