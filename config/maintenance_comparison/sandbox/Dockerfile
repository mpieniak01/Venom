FROM python@sha256:ccc7089399c8bb65dd1fb3ed6d55efa538a3f5e7fca3f5988ac3b5b87e593bf0
RUN apt-get update && apt-get install -y --no-install-recommends git ripgrep && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir pytest==9.2.0
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /workspace
