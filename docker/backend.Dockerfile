FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-ci-lite.txt /tmp/requirements-ci-lite.txt
RUN python -m pip install --upgrade pip \
    && pip install -r /tmp/requirements-ci-lite.txt

COPY venom_core /app/venom_core
COPY config /app/config
COPY scripts /app/scripts
COPY .env.example /app/.env.example

RUN mkdir -p /app/data/memory /app/workspace /app/logs

EXPOSE 8000

CMD ["uvicorn", "venom_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
