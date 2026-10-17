"""Generate the synthetic ward cohort.

    python -m glucotwin.sim.generate --admissions 800 --days 60

Writes
  data/synthetic/fhir/*.ndjson.gz     Stream A: hospital record as a FHIR R4 Bulk Data export
  data/synthetic/cgm.csv.gz           Stream B: CGM readings (about half of admissions)
  data/synthetic/_hidden/             simulator ground truth (true glucose, injected process
                                      failures, physiology) — used only by evaluation to
                                      score process-failure detection and discharge findings;
                                      never read by features or models
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from ..config import SETTINGS, SYNTH_DIR
from .fhir_export import export
from .ward_sim import make_admissions, simulate


def main(n: int = 800, days: int = 60, seed: int = SETTINGS.seed) -> None:
    rng = np.random.default_rng(seed)
    adms = make_admissions(rng, n, days)
    d = simulate(adms, seed + 1)
    counts = export(d, SYNTH_DIR / "fhir")
    d["cgm"].to_csv(SYNTH_DIR / "cgm.csv.gz", index=False)
    h = SYNTH_DIR / "_hidden"; h.mkdir(parents=True, exist_ok=True)
    d["_truth"].to_csv(h / "truth_5min.csv.gz", index=False)
    d["_errors"].to_csv(h / "process_failures.csv", index=False)
    d["_hidden"].to_csv(h / "physiology.csv", index=False)
    poc = d["poc"].glucose_mgdl
    enc = d["encounters"]
    stats = {"admissions": n, "days": days, "cgm_admissions": int(enc.cgm.sum()), "fhir_resources": counts,
             "poc_readings": int(len(poc)), "poc_mean": round(float(poc.mean()), 1),
             "poc_in_140_180": round(float(poc.between(140, 180).mean()), 3),
             "admissions_with_poc_low": round(float(d["poc"][poc < 70].admission_id.nunique() / n), 3),
             "process_failures": d["_errors"].error.value_counts().to_dict()}
    (SYNTH_DIR / "cohort_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--admissions", type=int, default=800)
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--seed", type=int, default=SETTINGS.seed)
    a = ap.parse_args()
    main(a.admissions, a.days, a.seed)
