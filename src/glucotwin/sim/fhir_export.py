"""Export simulated ward data as an HL7 FHIR R4 Bulk Data export (NDJSON, one file per resource type).

This mirrors how a hospital information system would hand data to the twin
(FHIR Bulk Data Access "$export"). The twin's ingestion reads these files;
it never touches the simulator's tables directly.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pandas as pd

LOINC = {"poc": ("41653-7", "Glucose [Mass/volume] in Capillary blood by Glucometer", "mg/dL"),
         "hba1c": ("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood", "%"),
         "creatinine": ("2160-0", "Creatinine [Mass/volume] in Serum or Plasma", "mg/dL"),
         "weight": ("29463-7", "Body weight", "kg"), "height": ("8302-2", "Body height", "cm"),
         "intake": ("9108-2", "Fluid intake total 24 hour", "{fraction}")}
DRUG = {"rapid_prandial": ("insulin aspart", "A10AB05", "mealtime"), "rapid_correction": ("insulin aspart", "A10AB05", "correction"),
        "basal_glargine": ("insulin glargine", "A10AE04", "basal"), "glimepiride": ("glimepiride", "A10BB12", "oral"),
        "prednisolone": ("prednisolone", "H02AB06", "steroid"), "dexamethasone": ("dexamethasone", "H02AB02", "steroid"),
        "oral_glucose": ("glucose 15 g oral", "V06DC01", "hypoglycaemia treatment"),
        "dextrose_iv": ("dextrose 25% IV", "B05BA03", "hypoglycaemia treatment"),
        "dextrose_5pct_infusion": ("dextrose 5% infusion", "B05BA03", "infusion")}
REASON_SNOMED = {"infection": ("233604007", "Pneumonia / sepsis"), "cardiac_surgery": ("232717009", "Coronary artery bypass grafting"),
                 "respiratory": ("195951007", "Acute exacerbation of COPD / asthma"), "heart_failure": ("84114007", "Heart failure"),
                 "ortho_surgery": ("179344006", "Orthopaedic procedure")}


def _iso(t) -> str | None:
    return None if pd.isna(t) else pd.Timestamp(t).isoformat() + "+05:30"


def export(d: dict[str, pd.DataFrame], out: Path) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    res: dict[str, list] = {k: [] for k in ("Patient", "Encounter", "Condition", "Observation", "MedicationRequest",
                                            "MedicationAdministration", "NutritionOrder", "NutritionIntake", "Procedure")}
    enc = d["encounters"]
    for r in enc.itertuples():
        pid, eid = r.patient_id, r.admission_id
        res["Patient"].append({"resourceType": "Patient", "id": pid, "meta": {"tag": [{"system": "urn:glucotwin", "code": "synthetic"}]},
                               "name": [{"text": r.name}], "gender": r.sex,
                               "birthDate": f"{2026 - r.age}-01-01", "extension": [{"url": "urn:glucotwin:age", "valueInteger": int(r.age)}]})
        code, disp = REASON_SNOMED[r.admission_type]
        res["Encounter"].append({"resourceType": "Encounter", "id": eid, "status": "finished", "class": {"code": "IMP"},
                                 "subject": {"reference": f"Patient/{pid}"}, "period": {"start": _iso(r.admit_time), "end": _iso(r.discharge_time)},
                                 "reasonCode": [{"coding": [{"system": "http://snomed.info/sct", "code": code, "display": disp}], "text": r.admission_reason}],
                                 "extension": [{"url": "urn:glucotwin:admission-type", "valueCode": r.admission_type},
                                               {"url": "urn:glucotwin:cgm", "valueBoolean": bool(r.cgm)}]})
        conds = []
        if r.known_diabetes:
            conds.append(("44054006", "Type 2 diabetes mellitus"))
        if r.ckd:
            conds.append(("709044004", "Chronic kidney disease"))
        if r.heart_failure:
            conds.append(("84114007", "Heart failure"))
        for j, (c, dsp) in enumerate(conds):
            res["Condition"].append({"resourceType": "Condition", "id": f"{eid}-c{j}", "subject": {"reference": f"Patient/{pid}"},
                                     "encounter": {"reference": f"Encounter/{eid}"}, "code": {"coding": [{"system": "http://snomed.info/sct", "code": c, "display": dsp}]},
                                     "clinicalStatus": {"coding": [{"code": "active"}]}})
        for j, (key, val) in enumerate((("weight", r.weight_kg), ("height", r.height_cm))):
            cd = LOINC[key]
            res["Observation"].append(_obs(f"{eid}-{key}", pid, eid, cd, val, r.admit_time, "vital-signs"))
        home = []
        if r.home_insulin:
            home.append(("basal_glargine", "home insulin"))
        if r.home_sulfonylurea:
            home.append(("glimepiride", "home medication"))
        for j, (dk, note) in enumerate(home):
            nm, atc, _ = DRUG[dk]
            res["MedicationRequest"].append({"resourceType": "MedicationRequest", "id": f"{eid}-home{j}", "status": "active",
                                             "intent": "plan", "category": [{"text": "home medication"}],
                                             "subject": {"reference": f"Patient/{pid}"}, "encounter": {"reference": f"Encounter/{eid}"},
                                             "medicationCodeableConcept": {"coding": [{"system": "http://www.whocc.no/atc", "code": atc}], "text": nm},
                                             "authoredOn": _iso(r.admit_time), "note": [{"text": note}]})
        if pd.notna(r.surgery_time):
            res["Procedure"].append({"resourceType": "Procedure", "id": f"{eid}-surg", "status": "completed",
                                     "subject": {"reference": f"Patient/{pid}"}, "encounter": {"reference": f"Encounter/{eid}"},
                                     "code": {"text": r.admission_reason}, "performedDateTime": _iso(r.surgery_time)})
    pid_of = enc.set_index("admission_id")["patient_id"].to_dict()
    for j, r in enumerate(d["poc"].itertuples()):
        res["Observation"].append(_obs(f"{r.admission_id}-poc{j}", pid_of[r.admission_id], r.admission_id, LOINC["poc"],
                                       r.glucose_mgdl, r.time, "laboratory", method="point-of-care", note=r.reason))
    for j, r in enumerate(d["labs"].itertuples()):
        res["Observation"].append(_obs(f"{r.admission_id}-lab{j}", pid_of[r.admission_id], r.admission_id, LOINC[r.test],
                                       r.value, r.time, "laboratory"))
    for j, r in enumerate(d["orders"].itertuples()):
        base = {"id": f"{r.admission_id}-o{j}", "subject": {"reference": f"Patient/{pid_of[r.admission_id]}"},
                "encounter": {"reference": f"Encounter/{r.admission_id}"}, "authoredOn": _iso(r.time)}
        ext = [{"url": "urn:glucotwin:order-kind", "valueCode": r.kind},
               {"url": "urn:glucotwin:order-value", "valueString": str(r.value)},
               {"url": "urn:glucotwin:effective-start", "valueDateTime": _iso(r.start)}]
        if pd.notna(r.end):
            ext.append({"url": "urn:glucotwin:effective-end", "valueDateTime": _iso(r.end)})
        if r.kind in ("diet", "npo"):
            res["NutritionOrder"].append({"resourceType": "NutritionOrder", **base, "status": "active", "intent": "order",
                                          "patient": base.pop("subject"), "dateTime": base.pop("authoredOn"),
                                          "oralDiet": {"type": [{"text": "Nil by mouth" if r.kind == "npo" else "Diabetic diet"}]},
                                          "note": [{"text": r.note or str(r.value)}], "extension": ext})
        else:
            res["MedicationRequest"].append({"resourceType": "MedicationRequest", **base, "status": "active", "intent": "order",
                                             "medicationCodeableConcept": {"text": r.kind}, "note": [{"text": r.note}], "extension": ext})
    for j, r in enumerate(d["mar"].itertuples()):
        nm, atc, role = DRUG.get(r.drug, (r.drug, "", ""))
        res["MedicationAdministration"].append({
            "resourceType": "MedicationAdministration", "id": f"{r.admission_id}-a{j}",
            "status": "completed" if r.status == "given" else "not-done",
            "subject": {"reference": f"Patient/{pid_of[r.admission_id]}"}, "context": {"reference": f"Encounter/{r.admission_id}"},
            "medicationCodeableConcept": {"coding": [{"system": "http://www.whocc.no/atc", "code": atc}], "text": nm},
            "effectiveDateTime": _iso(r.time), "category": {"text": r.drug},
            "dosage": {"route": {"text": r.route}, "dose": {"value": r.dose, "unit": "U" if "insulin" in nm else "mg" if r.route == "PO" and "glucose" not in nm else "g"}},
            "note": [{"text": r.note}] if r.note else []})
    for j, r in enumerate(d["meals"].itertuples()):
        res["NutritionIntake"].append({"resourceType": "NutritionIntake", "id": f"{r.admission_id}-m{j}", "status": "completed",
                                       "subject": {"reference": f"Patient/{pid_of[r.admission_id]}"},
                                       "encounter": {"reference": f"Encounter/{r.admission_id}"}, "occurrenceDateTime": _iso(r.time),
                                       "consumedItem": [{"type": {"text": r.meal}, "nutritionProduct": {"text": "hospital diabetic diet"},
                                                         "amount": {"value": r.carbs_served_g, "unit": "g carbohydrate served"},
                                                         "rate": {"value": r.intake_fraction, "unit": "fraction eaten"}}]})
    counts = {}
    for rt, rows in res.items():
        with gzip.open(out / f"{rt}.ndjson.gz", "wt") as f:
            for x in rows:
                f.write(json.dumps(x, separators=(",", ":")) + "\n")
        counts[rt] = len(rows)
    return counts


def _obs(rid, pid, eid, code, value, t, cat, method=None, note=None):
    c, disp, unit = code
    o = {"resourceType": "Observation", "id": rid, "status": "final", "category": [{"coding": [{"code": cat}]}],
         "code": {"coding": [{"system": "http://loinc.org", "code": c, "display": disp}]},
         "subject": {"reference": f"Patient/{pid}"}, "encounter": {"reference": f"Encounter/{eid}"},
         "effectiveDateTime": _iso(t), "valueQuantity": {"value": float(value), "unit": unit}}
    if method:
        o["method"] = {"text": method}
    if note:
        o["note"] = [{"text": note}]
    return o
