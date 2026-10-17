"""Read a FHIR R4 Bulk Data export (NDJSON) + CGM stream into the twin's tables.

This is the only entry point for ward data. Swapping the synthetic export for a
real hospital export (same resource types) requires no change downstream.
"""
from __future__ import annotations

import gzip
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from ..config import SYNTH_DIR


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt") as f:
        return [json.loads(line) for line in f if line.strip()]


def _t(s):
    return pd.Timestamp(s[:19]) if s else pd.NaT


def _ext(r, url):
    for e in r.get("extension", []):
        if e["url"] == url:
            return next(v for k, v in e.items() if k.startswith("value"))
    return None


def _ref(r, key):
    v = r.get(key, {}).get("reference", "")
    return v.split("/", 1)[1] if "/" in v else None


@lru_cache(maxsize=2)
def load_ward(root: str = str(SYNTH_DIR)) -> dict[str, pd.DataFrame]:
    root = Path(root); f = root / "fhir"
    pats = {p["id"]: p for p in _read(f / "Patient.ndjson.gz")}
    enc_rows = []
    for e in _read(f / "Encounter.ndjson.gz"):
        p = pats[_ref(e, "subject")]
        enc_rows.append({"admission_id": e["id"], "patient_id": p["id"], "name": p["name"][0]["text"], "sex": p["gender"],
                         "age": _ext(p, "urn:glucotwin:age"), "admit_time": _t(e["period"]["start"]),
                         "discharge_time": _t(e["period"].get("end")), "admission_type": _ext(e, "urn:glucotwin:admission-type"),
                         "admission_reason": e["reasonCode"][0]["text"], "cgm": bool(_ext(e, "urn:glucotwin:cgm"))})
    enc = pd.DataFrame(enc_rows).set_index("admission_id")
    for c in ("known_diabetes", "ckd", "heart_failure", "home_insulin", "home_sulfonylurea"):
        enc[c] = False
    for c in _read(f / "Condition.ndjson.gz"):
        code = c["code"]["coding"][0]["code"]; eid = _ref(c, "encounter")
        col = {"44054006": "known_diabetes", "709044004": "ckd", "84114007": "heart_failure"}.get(code)
        if col:
            enc.loc[eid, col] = True
    obs_rows, lab_rows, poc_rows = [], [], []
    for o in _read(f / "Observation.ndjson.gz"):
        code = o["code"]["coding"][0]["code"]; eid = _ref(o, "encounter"); t = _t(o["effectiveDateTime"])
        v = o["valueQuantity"]["value"]
        if code == "41653-7":
            poc_rows.append((eid, t, v, (o.get("note") or [{}])[0].get("text", "")))
        elif code in ("4548-4", "2160-0"):
            lab_rows.append((eid, t, "hba1c" if code == "4548-4" else "creatinine", v))
        elif code == "29463-7":
            enc.loc[eid, "weight_kg"] = v
        elif code == "8302-2":
            enc.loc[eid, "height_cm"] = v
    poc = pd.DataFrame(poc_rows, columns=["admission_id", "time", "glucose_mgdl", "reason"]).sort_values(["admission_id", "time"])
    labs = pd.DataFrame(lab_rows, columns=["admission_id", "time", "test", "value"]).sort_values(["admission_id", "time"])
    ord_rows = []
    for r in _read(f / "MedicationRequest.ndjson.gz") + _read(f / "NutritionOrder.ndjson.gz"):
        eid = _ref(r, "encounter")
        if (r.get("category") or [{}])[0].get("text") == "home medication":
            col = "home_insulin" if "glargine" in r["medicationCodeableConcept"]["text"] else "home_sulfonylurea"
            enc.loc[eid, col] = True
            continue
        kind = _ext(r, "urn:glucotwin:order-kind")
        ord_rows.append((eid, _t(r.get("authoredOn") or r.get("dateTime")), kind, _ext(r, "urn:glucotwin:order-value"),
                         _t(_ext(r, "urn:glucotwin:effective-start")), _t(_ext(r, "urn:glucotwin:effective-end")),
                         (r.get("note") or [{}])[0].get("text", "")))
    orders = pd.DataFrame(ord_rows, columns=["admission_id", "time", "kind", "value", "start", "end", "note"]).sort_values(["admission_id", "time"])
    mar = pd.DataFrame([(_ref(m, "context"), _t(m["effectiveDateTime"]), m["category"]["text"], m["dosage"]["dose"]["value"],
                         m["dosage"]["route"]["text"], "given" if m["status"] == "completed" else "held",
                         (m.get("note") or [{}])[0].get("text", "")) for m in _read(f / "MedicationAdministration.ndjson.gz")],
                       columns=["admission_id", "time", "drug", "dose", "route", "status", "note"]).sort_values(["admission_id", "time"])
    meals = pd.DataFrame([(_ref(m, "encounter"), _t(m["occurrenceDateTime"]), m["consumedItem"][0]["type"]["text"],
                           m["consumedItem"][0]["amount"]["value"], m["consumedItem"][0]["rate"]["value"])
                          for m in _read(f / "NutritionIntake.ndjson.gz")],
                         columns=["admission_id", "time", "meal", "carbs_served_g", "intake_fraction"]).sort_values(["admission_id", "time"])
    proc = pd.DataFrame([(_ref(p, "encounter"), _t(p["performedDateTime"])) for p in _read(f / "Procedure.ndjson.gz")],
                        columns=["admission_id", "time"])
    enc["surgery_time"] = proc.set_index("admission_id")["time"].reindex(enc.index)
    cgm_path = root / "cgm.csv.gz"
    cgm = pd.read_csv(cgm_path, parse_dates=["time"]) if cgm_path.exists() else pd.DataFrame(columns=["admission_id", "time", "glucose_mgdl"])
    enc["bmi"] = enc["weight_kg"] / (enc["height_cm"] / 100) ** 2
    return {"encounters": enc, "poc": poc.reset_index(drop=True), "labs": labs.reset_index(drop=True),
            "orders": orders.reset_index(drop=True), "mar": mar.reset_index(drop=True), "meals": meals.reset_index(drop=True),
            "cgm": cgm}


def split(ward: dict, admission_id: str) -> dict:
    """Tables for one admission."""
    out = {k: v[v.admission_id == admission_id] for k, v in ward.items() if k != "encounters"}
    out["encounter"] = ward["encounters"].loc[admission_id]
    return out
