"""Trained model bundle: 12-hour low/high risk (fingerstick mode A, CGM mode B) and
1-12 hour glucose trajectories with conformalised 80% intervals."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from ..config import MODEL_DIR
from ..features.ward_features import FEATURES_A, FEATURES_B, WIN_F


@dataclass
class Bundle:
    version: str = "untrained"
    risk: dict = field(default_factory=dict)        # (target, mode) -> Booster
    iso: dict = field(default_factory=dict)         # (target, mode) -> IsotonicRegression
    traj: dict = field(default_factory=dict)        # (mode, q) -> Booster; q in {"lo","mid","hi"}
    conformal: dict = field(default_factory=dict)   # mode -> additive widening (mg/dL)
    thresholds: dict = field(default_factory=dict)  # board thresholds chosen on calibration patients
    meta: dict = field(default_factory=dict)

    @staticmethod
    def feats(mode: str) -> list[str]:
        return FEATURES_B if mode == "B" else FEATURES_A

    # ---------------------------------------------------------------- inference
    def risk_prob(self, X: pd.DataFrame, target: str, mode: str) -> np.ndarray:
        raw = self.risk[(target, mode)].predict(X[self.feats(mode)])
        # calibrated, but never shown as certain: 0.5%-98%
        return np.clip(self.iso[(target, mode)].predict(raw), 0.005, 0.98)

    def trajectory(self, Xh: pd.DataFrame, mode: str) -> pd.DataFrame:
        f = self.feats(mode) + WIN_F
        c = self.conformal[mode]
        rf = self.feats(mode) + ["h", "target_tod_sin", "target_tod_cos"]
        mid = self.traj[(mode, "mid")].predict(Xh[f])
        lo = np.minimum(mid + self.traj[(mode, "lo")].predict(Xh[rf]) - c, mid)
        hi = np.maximum(mid + self.traj[(mode, "hi")].predict(Xh[rf]) + c, mid)
        return pd.DataFrame({"h": Xh["h"].to_numpy(), "mid": np.clip(mid, 40, 500), "lo": np.clip(lo, 40, 500),
                             "hi": np.clip(hi, 40, 500)}, index=Xh.index)

    def contributions(self, X: pd.DataFrame, target: str, mode: str) -> pd.DataFrame:
        f = self.feats(mode)
        c = self.risk[(target, mode)].predict(X[f], pred_contrib=True)
        return pd.DataFrame(c[:, :-1], columns=f, index=X.index)

    # ---------------------------------------------------------------- persistence
    def save(self, d: Path = MODEL_DIR):
        d.mkdir(parents=True, exist_ok=True)
        files = {}
        for (t, m), b in self.risk.items():
            fn = f"risk_{t}_{m}.txt"; b.save_model(str(d / fn)); files[f"risk|{t}|{m}"] = fn
        for (m, q), b in self.traj.items():
            fn = f"traj_{m}_{q}.txt"; b.save_model(str(d / fn)); files[f"traj|{m}|{q}"] = fn
        joblib.dump({f"{t}|{m}": v for (t, m), v in self.iso.items()}, d / "calibrators.joblib")
        (d / "manifest.json").write_text(json.dumps({"version": self.version, "files": files, "conformal": self.conformal,
                                                     "thresholds": self.thresholds, "meta": self.meta}, indent=2, default=str))

    @classmethod
    def load(cls, d: Path = MODEL_DIR) -> "Bundle":
        m = json.loads((d / "manifest.json").read_text())
        b = cls(version=m["version"], conformal=m["conformal"], thresholds=m["thresholds"], meta=m["meta"])
        for k, fn in m["files"].items():
            kind, x, y = k.split("|")
            bst = lgb.Booster(model_file=str(d / fn))
            (b.risk if kind == "risk" else b.traj)[(x, y)] = bst
        b.iso = {tuple(k.split("|")): v for k, v in joblib.load(d / "calibrators.joblib").items()}
        return b

    @staticmethod
    def make_version(payload) -> str:
        return "gw-" + hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:10]


_B: Bundle | None = None


def get_bundle() -> Bundle:
    global _B
    if _B is None:
        _B = Bundle.load()
    return _B
