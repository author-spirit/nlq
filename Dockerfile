FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY nlq nlq
COPY static static
COPY hints.json ./
COPY hints hints
COPY recommendations recommendations
COPY fixtures fixtures
COPY data/csv data/csv
COPY data/datasets.json data/datasets.json

RUN python -m nlq.build_db

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Listen on all interfaces inside the container. Publish only 127.0.0.1 on the host
# via bin/start.sh (-p 127.0.0.1:8000:8000) so the app is not open on the LAN.
CMD ["uvicorn", "nlq.api:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
