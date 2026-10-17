# GlucoTwin Ward — evaluation report

Model `gw-d83eeb94f9` · source of truth: [`metrics.json`](metrics.json) · regenerate with `make all`.

> All results are on **synthetic patients** from our own ward simulator. They show the method works and is evaluated
> without leakage; they do not establish accuracy on a real ward.

## Setup

| | |
|---|---|
| Cohort | 800 admissions over 60 days; about half wear a CGM, which supplies the outcome labels |
| Split | by patient: 70% train · 15% calibration (probabilities, thresholds, interval widths) · 15% test |
| Test set | 57 CGM-wearing admissions, 372 patient-days, 8,766 hourly twin updates; rule-based checks scored on all 800 admissions |
| Outcomes | **low**: CGM below 70 mg/dL in the next 12 h (5.1% of hours) · **severe high**: 250 mg/dL or more in the next 12 h (23%) |
| Leakage controls | features use only data recorded up to the update time plus orders already written (unit-tested); the streaming twin reproduces the batch features exactly (unit-tested) |

## Feature 1 — Ward risk board

| Predicting the next 12 hours | Low AUROC | Low AUPRC | High AUROC | High AUPRC |
|---|---:|---:|---:|---:|
| Static admission-time model (what published hospital models do) | 0.70 | 0.12 | 0.74 | 0.44 |
| **Twin, fingersticks only** | **0.88** | **0.47** | **0.90** | **0.75** |
| **Twin, with CGM** | **0.93** | **0.58** | **0.94** | **0.85** |

Calibration error (ECE) is 0.013 for lows on fingersticks. A simple rule ("last fingerstick under 100 or a low in 72 h")
catches 45% of hours before a low at 29% precision.

On the board (hourly updates, red = low risk above the threshold chosen on calibration patients):

| | Fingersticks | CGM |
|---|---:|---:|
| Low episodes flagged red in the 12 h before they started | 69% | 86% |
| Median warning | 11 h | 11 h |
| Red hours per patient-day | 0.64 | 0.68 |
| Red hours not followed by a low within 12 h | 40% | 30% |

Severe highs are common (23% of hours), so they show as amber ("watch"), never red.

**Forecasts (1-12 h):** mean absolute error 21-22 mg/dL on fingersticks (vs 36-38 for carrying the last fingerstick
forward) and 14-21 mg/dL with CGM; the 80% ranges contain the outcome 81-91% of the time.

## Feature 2 — Before you give insulin

**Bedside checks.** The simulator injects realistic process failures (recorded only in hidden ground truth). Run 30-60
minutes before the affected dose, the checks flagged:

| Failure | Flagged |
|---|---:|
| Mealtime insulin given while nil by mouth | 24 / 24 |
| Basal not reduced the night before a fast | 38 / 38 |
| Insulin not reduced after the steroid course ended | 26 / 31 |
| Insulin not reduced after kidney injury | 81 / 91 |
| Sulfonylurea given while fasting | 7 / 7 |
| **Total** | **176 / 191 (92%)** |

At routine dose times (598 doses sampled), 4.7% received a high-level flag.

**Dose what-if.** A model trained on hospital records cannot learn what an insulin dose does, because doses follow
glucose (confounding by indication): our learned forecast moved only 2 mg/dL when tonight's basal was held. The
what-if therefore uses a pharmacology layer (textbook action profiles × the patient's insulin sensitivity from the 1700
rule, one scale factor per insulin type fitted on training patients). It was tested on **counterfactual simulations**:
the same test patient re-simulated with one dose changed (×0, ×0.5, ×1.5), identical up to the dose, 60 dose events.

| | Basal (glargine) | Mealtime (aspart) |
|---|---:|---:|
| Error of the pharmacology layer (mg/dL, 1-12 h) | **6.1** | **5.4** |
| Error of the learned model's own what-if | 12.2 | 10.7 |
| Error if we assume no effect | 13.3 | 11.9 |
| Correlation with the true effect: pharmacology / learned | 0.84 / 0.41 | 0.88 / 0.59 |
| Effect at 6 h of holding the dose: true / pharmacology / learned | +25 / +23 / +2 | +15 / +23 / +3 |

The pharmacology layer overstates the effect of holding mealtime insulin at 6 hours; the overall error is still about
half that of the learned model.

## Feature 3 — Smart monitoring

Fingersticks at protocol times catch only **12%** of CGM-recorded low episodes (52% of severe highs). Lows are short
and fall between checks.

| Strategy | Lows caught | Extra checks per patient-day | Extra lows caught per 100 extra checks |
|---|---:|---:|---:|
| Protocol only | 12% | — | — |
| + a 3 am check for everyone on insulin (common practice) | 15% | 0.59 | 0.9 |
| + the same number of extra checks as the twin, untargeted | 12% | 0.29 | 0 |
| **+ twin-timed extra checks** | **20%** | 0.29 | **4.7** |
| **+ a CGM started at the twin's first red flag** | **82%**\* | sensor on 9% of patients (7% of patient-days) | — |

\*80% of all low episodes happened after the twin's first red flag, so a CGM started then would have been on for them;
the remaining lows are counted at the protocol catch rate.

Targeting matters more than timing: choosing the hour at random within the twin-selected patients does almost as well
(19%). The strongest version of this feature is therefore "who should get a CGM".

## Feature 4 — Discharge handover

Across all 800 admissions, 127 had undiagnosed diabetes. The handover identified **64%** as probable new diabetes from
HbA1c and prompted HbA1c testing for another **28%** where it had not been measured: **91% identified or prompted**,
with no false new diagnoses among the patients with stress hyperglycaemia only.

## Reproducibility

`make all` regenerates the cohort (byte-identical), features, models, what-if validation and this evaluation in about
15 minutes on 2 cores. 10 tests cover simulator determinism and realism, feature causality, known-future orders,
streaming = batch, the bedside rules, the what-if direction and discharge findings.

## Figures

`figures/risk_pr_curves.png` · `figures/trajectory_error.png` · `figures/smart_monitoring.png`
