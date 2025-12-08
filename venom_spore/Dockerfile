# Dockerfile for Venom Spore
FROM python:3.11-slim

LABEL maintainer="Venom Project"
LABEL description="Venom Spore - Lightweight distributed node"

WORKDIR /app

# Copy tylko niezbędne pliki
COPY venom_spore/ /app/venom_spore/
COPY venom_core/nodes/ /app/venom_core/nodes/
COPY venom_core/__init__.py /app/venom_core/__init__.py

# Utwórz __init__.py dla venom_core jeśli nie istnieje
RUN touch /app/venom_core/__init__.py

# Instaluj minimalną listę zależności
RUN pip install --no-cache-dir \
    websockets \
    psutil \
    pydantic \
    pydantic-settings

# Utwórz katalog workspace
RUN mkdir -p /app/workspace

# Ustaw PYTHONPATH
ENV PYTHONPATH=/app

# Expose nie jest potrzebny - Spore tylko wychodzi na zewnątrz

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import psutil; psutil.cpu_percent()" || exit 1

# Uruchom Venom Spore
CMD ["python", "-u", "/app/venom_spore/main.py"]
