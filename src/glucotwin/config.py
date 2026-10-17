"""Central configuration for GlucoTwin Ward.

All clinically meaningful numbers live here, visible and configurable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(os.environ.get("GLUCOTWIN_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = ROOT / "data"
SYNTH_DIR = DATA_DIR / "synthetic"
MODEL_DIR = ROOT / "models"
EVAL_DIR = ROOT / "evaluation"
DB_PATH = Path(os.environ.get("GLUCOTWIN_DB", DATA_DIR / "ward.db"))

STEP_MIN = 5                     # simulation resolution (minutes)
RISK_HORIZON_H = 12              # risk window used on the ward board
TRAJ_HORIZONS_H = tuple(range(1, 13))
FORECAST_EVERY_MIN = 60          # cadence of twin updates in training/evaluation
DEMO_NOW = "2026-08-24 21:00"    # demo moment: before the bedtime insulin round (chosen for a variety of patient states)


@dataclass(frozen=True)
class Thresholds:
    """mg/dL. Inpatient target range 140-180 follows the ADA Standards of Care
    (Diabetes Care in the Hospital). Hypoglycaemia levels follow the International
    Hypoglycaemia Study Group: <70 level 1, <54 level 2. Severe hyperglycaemia
    for the ward board is >=250 (configurable)."""

    target_low: float = 140.0
    target_high: float = 180.0
    hypo: float = 70.0
    hypo_l2: float = 54.0
    severe_high: float = 250.0


@dataclass(frozen=True)
class Ward:
    breakfast_h: float = 8.0
    lunch_h: float = 13.0
    dinner_h: float = 20.0
    basal_h: float = 22.0
    steroid_h: float = 8.0
    round_h: float = 9.0                     # consultant round: insulin titration happens here
    poc_insulin: tuple = (7.5, 12.5, 19.5, 22.0)   # standard fingerstick protocol on insulin
    poc_no_insulin: tuple = (7.5, 19.5)            # patients not on insulin
    lab_h: float = 6.0                       # morning bloods (creatinine)


@dataclass(frozen=True)
class AlertRules:
    # Board red/amber thresholds are not set here: they are chosen on calibration patients at training time
    # and stored in models/manifest.json (see models/train.py::_thresholds).
    extra_check_threshold: float = 0.20      # smart monitoring: suggest an extra check when P(out of range) exceeds this (evaluated 0.1-0.4)
    poc_stale_h: float = 8.0                 # last fingerstick older than this -> wide-uncertainty warning
    cgm_stale_min: float = 20.0
    aki_creatinine_rise: float = 0.3         # KDIGO: >=0.3 mg/dL within 48 h
    low_intake_fraction: float = 0.5


@dataclass(frozen=True)
class Settings:
    thr: Thresholds = field(default_factory=Thresholds)
    ward: Ward = field(default_factory=Ward)
    rules: AlertRules = field(default_factory=AlertRules)
    interval: float = 0.80
    seed: int = 11


SETTINGS = Settings()
