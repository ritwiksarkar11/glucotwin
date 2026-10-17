FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 make && rm -rf /var/lib/apt/lists/*
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install --no-cache-dir -e . \
 && python -m glucotwin.features.dataset
EXPOSE 8501 8000
# Dashboard by default; for the API: docker run -p 8000:8000 glucotwin uvicorn glucotwin.api:app --host 0.0.0.0
CMD ["streamlit", "run", "app/dashboard.py", "--server.address=0.0.0.0", "--server.port=8501"]
