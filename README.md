# QUANT NEXUS

Standalone multi-market intelligence platform.

## Safety
- Simulation / paper-trading only.
- Live order execution is disabled by design.
- No exchange API secrets are required for the initial demo.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000.

## Initial scope
- Responsive web application foundation.
- Market overview and watchlist UI.
- Signal-analysis API with explicit demo status.
- Paper portfolio foundation; no live execution.
- Native Android client planned as a separate module.
