PY ?= python

.PHONY: all install data features train whatif evaluate test app api clean

all: install data features train whatif evaluate test   ## full reproducible pipeline (~15 min on 2 cores)

install:
	$(PY) -m pip install -r requirements.txt && $(PY) -m pip install -e .

data:        ## simulate the ward and export it as FHIR R4 Bulk Data + CGM
	$(PY) -m glucotwin.sim.generate --admissions 800 --days 60

features:    ## causal hourly features and CGM-labelled outcomes (patient-level split)
	$(PY) -m glucotwin.features.dataset

train:       ## 12-h risk models (fingerstick / CGM), 1-12 h forecasts, board thresholds
	$(PY) -m glucotwin.models.train

whatif:      ## fit + validate the insulin what-if pharmacology layer on counterfactual simulations
	$(PY) -m glucotwin.evaluation.counterfactual

evaluate:    ## held-out evaluation of the four features -> evaluation/metrics.json + figures
	$(PY) -m glucotwin.evaluation.evaluate

test:
	$(PY) -m pytest -q

app:
	streamlit run app/dashboard.py

clean:
	rm -rf data/synthetic/fhir data/synthetic/*.gz data/synthetic/_* data/ward.db* models/*
