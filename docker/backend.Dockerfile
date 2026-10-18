FROM python:3.12-slim-bookworm@sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d

ARG APP_VERSION=1.9.0
LABEL org.opencontainers.image.title="venom-backend" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venom-venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/locks/light-linux-py312.txt requirements/locks/light-linux-py312.json requirements/locks/build-linux-py312.txt requirements/locks/build-linux-py312.json /opt/venom-locks/
RUN python -m venv /opt/venom-venv \
    && /opt/venom-venv/bin/python -m pip install --require-hashes \
       -r /opt/venom-locks/build-linux-py312.txt \
    && /opt/venom-venv/bin/python -m pip install --require-hashes \
       -r /opt/venom-locks/light-linux-py312.txt \
    && /opt/venom-venv/bin/python -m pip check

COPY venom_core /app/venom_core
COPY config /app/config
COPY scripts /app/scripts
COPY .env.dev.example /app/.env.dev.example
COPY .env.preprod.example /app/.env.preprod.example

RUN mkdir -p /app/data/memory /app/workspace /app/logs

EXPOSE 8000

CMD ["uvicorn", "venom_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
