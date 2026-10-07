# ORBITGUARD AI Backend

FastAPI backend intelligence layer for the ORBITGUARD AI hackathon project.

## Current Phase

This repository currently includes the API skeleton and the MVP risk engine:

- `GET /`
- `GET /health`
- `POST /api/v1/analyze`
- `POST /api/v1/flood/analyze`
- `POST /api/v1/forest/analyze`
- `GET /api/v1/incidents/{incident_id}`

The impact-analysis layer also includes CRS-safe geometry utilities, a
population-provider interface, an OpenStreetMap/Overpass provider, and local
demo fallbacks for population and infrastructure exposure.

The AI analyst layer accepts structured incident evidence and returns a
structured summary, severity, priority areas, recommended actions, and
uncertainty. It never receives permission to calculate impact values, and
analyst prose containing numerical claims is rejected. When `DEMO_MODE=true`,
or when the configured provider is unavailable, a deterministic fallback is
returned.

The analysis endpoint accepts normalized FloodGuard or ForestGuard detector output
and returns a frontend-facing incident response. Impact values are clearly marked
as demo data until live population and infrastructure providers are enabled.
`DEMO_MODE=true` is the default, so the API does not call external services during
local development. Created incidents are held in a process-local MVP store and
can be retrieved with their returned incident ID.

The geospatial runtime uses Shapely and PyProj. The geometry helpers keep
public coordinates in WGS84 and project to a local UTM CRS for meter-based
buffers, lengths, and areas.

## MVP Risk Engine

`orbitguard.backend.services.risk_engine` calculates the explainable
**ORBITGUARD MVP Risk Score** from 0 to 100. Raw values are normalized before
they enter any weighted formula.

Flood weights:

- hazard severity: 30%
- population exposure: 30%
- infrastructure exposure: 20%
- model confidence: 20%

Deforestation weights:

- forest loss: 35%
- change magnitude: 25%
- population exposure: 20%
- infrastructure exposure: 10%
- model confidence: 10%

Risk levels are `LOW` (0-39), `MODERATE` (40-59), `HIGH` (60-79), and
`CRITICAL` (80-100). Weights and normalization thresholds are centralized in
`RiskEngineConfig` so they can be adjusted without changing the scoring
functions. This is an MVP heuristic and is not scientifically validated.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The optional live-mode settings are `OVERPASS_URL`, `HAZARD_BUFFER_METERS`,
and `OVERPASS_TIMEOUT_SECONDS`. Population data remains behind a provider
interface and uses the demo fallback until a real population provider is
connected. The analyst settings are `OPENAI_API_KEY`, `OPENAI_MODEL`,
`OPENAI_BASE_URL`, and `OPENAI_TIMEOUT_SECONDS`; keep the API key only in the
environment or a local `.env` file, never in source code.

## Run

```powershell
.venv\Scripts\python.exe -m uvicorn orbitguard.backend.main:app --reload
```

## Test

```powershell
.venv\Scripts\python.exe -m pytest
```

## Example Request

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/analyze `
  -ContentType 'application/json' `
  -Body '{
    "event_type": "flood",
    "latitude": 12.9716,
    "longitude": 77.5946,
    "affected_area_km2": 37.4,
    "confidence": 0.91,
    "mask_path": "outputs/flood_mask.png",
    "source": "Sentinel-1",
    "acquisition_date": "2026-10-07"
  }'
```
