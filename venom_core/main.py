# venom/main.py
from fastapi import FastAPI

app = FastAPI(title="Venom Core", version="0.1.0")


@app.get("/healthz")
def healthz():
    """Prosty endpoint zdrowia – do sprawdzenia, czy Venom żyje."""
    return {"status": "ok", "component": "venom-core"}
