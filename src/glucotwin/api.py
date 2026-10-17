"""REST API: the same ward twin for other hospital systems (EMR side-panel, nurse station display).

    uvicorn glucotwin.api:app --port 8000     # docs at /docs
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import __version__
from .twin.engine import WardTwin

app = FastAPI(title="GlucoTwin Ward API", version=__version__,
              description="Research prototype on synthetic patients. Not a medical device. Never recommends a dose.")
_tw: WardTwin | None = None


def tw() -> WardTwin:
    global _tw
    if _tw is None:
        _tw = WardTwin()
    return _tw


def _t(t: Optional[str]) -> pd.Timestamp:
    return pd.Timestamp(t) if t else tw().default_now()


def _known(aid: str):
    if aid not in tw().w["encounters"].index:
        raise HTTPException(404, f"unknown admission {aid}")


class WhatIf(BaseModel):
    basal_tonight: Optional[float] = Field(None, ge=0, le=200, description="Units of glargine tonight")
    prandial_next: Optional[float] = Field(None, ge=0, le=100, description="Units of mealtime insulin at the next meal")


@app.get("/health")
def health():
    return {"status": "ok", "model_version": tw().b.version, "ward": tw().ward}


@app.get("/ward/board")
def board(t: Optional[str] = None):
    b = tw().board(_t(t))
    return b.drop(columns=[]).to_dict("records")


@app.get("/patients/{aid}/twin")
def patient(aid: str, t: Optional[str] = None):
    _known(aid)
    s = tw().patient(aid, _t(t))
    return {"admission_id": aid, "mode": s["mode"], "p_low_12h": s["p_low"], "p_high_12h": s["p_high"], "status": s["status"],
            "reasons": s["reasons"], "quality": s["quality"], "forecast": s["traj"][["time", "mid", "lo", "hi"]].to_dict("records"),
            "monitoring": {k: v for k, v in s["plan"].items() if k != "protocol"} | {"protocol": s["plan"]["protocol"]},
            "doses": [{k: v for k, v in d.items()} for d in s["doses"]], "model_version": tw().b.version}


@app.post("/patients/{aid}/what-if")
def what_if(aid: str, req: WhatIf, t: Optional[str] = None):
    _known(aid)
    ov = {k: v for k, v in req.model_dump().items() if v is not None}
    if not ov:
        raise HTTPException(400, "give basal_tonight and/or prandial_next")
    r = tw().what_if(aid, _t(t), ov)
    return {"p_low_12h": r["p_low"], "p_high_12h": r["p_high"], "forecast": r["traj"][["time", "mid", "lo", "hi"]].to_dict("records"),
            "label": "Model estimate under a hypothetical dose. Not a dosing recommendation."}


@app.get("/patients/{aid}/discharge")
def discharge(aid: str, t: Optional[str] = None):
    _known(aid)
    return tw().discharge(aid, pd.Timestamp(t) if t else None)
