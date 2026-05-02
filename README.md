# nekazari-module-carbon

Carbon sequestration and biomass analytics module for the Nekazari platform.

## Status: Skeleton — in active development

Extracted from `nekazari-module-vegetation-health` (2026-02-22).
Vegetation-health now handles spectral indices only; all carbon calculations live here.

## What this module does

- **LUE model** (Light Use Efficiency): GPP = PAR × fAPAR × LUE
- **PAR integration**: real values from weather-worker, fallback to 20 MJ/m²/day
- **DataHub adapter**: exposes carbon timeseries as Arrow IPC for the Data Canvas
- **NGSI-LD**: publishes `carbonFixationRateDaily`, `co2SequesteredCumulative` to AgriParcel

## Planned expansion

- Soil Organic Carbon (SOC) estimation from BSI + NDVI temporal series
- Net Ecosystem Exchange (NEE) = GPP − ecosystem respiration
- Methane estimation for flooded rice paddies
- Voluntary carbon market reporting (Verra VCS, Gold Standard)

## DataHub integration

Source name: `carbon` → env var `TIMESERIES_ADAPTER_CARBON_URL`

Attributes:
| Attribute | Unit | Description |
|-----------|------|-------------|
| `carbonFixationRateDaily` | gC/m²/day | Daily gross primary production |
| `gppDaily` | gC/m²/day | Alias for carbonFixationRateDaily |
| `nppDaily` | gC/m²/day | Net primary production (GPP × 0.5) |
| `co2SequesteredCumulative` | kgCO2 | Running total per parcel |

## Module structure

```
backend/
  app/
    api/internal.py      ← Arrow adapter for DataHub
    services/
      carbon_engine.py   ← LUE calculation logic (extracted from vegetation-health)
k8s/                     ← Kubernetes manifests (TBD)
frontend/                ← React IIFE module (TBD)
manifest.json
```

## i18n (frontend) — TODO for next developer

The `frontend/` part of this module is still TBD. When implementing UI, **do not hardcode user-facing strings**.

- **Use the shared SDK i18n instance**: `import { useTranslation, i18n } from '@nekazari/sdk'`
- **Register module resources** (recommended namespace: `carbon`):
  - Create `frontend/src/locales/en.json` and `frontend/src/locales/es.json`
  - Add `frontend/src/i18n.ts` that calls:
    - `i18n.addResourceBundle('en', 'carbon', en, true, true)`
    - `i18n.addResourceBundle('es', 'carbon', es, true, true)`
  - Ensure `frontend/src/moduleEntry.ts` (or `App.tsx`) imports `./i18n` once
- **Minimum**: keep `en` + `es` key sets identical. Use English as temporary fallback for other languages.

## Migration from vegetation-health

The following was removed from vegetation-health and lives here:
- `app/jobs/carbon_calculator.py` → `backend/app/services/carbon_engine.py`
- Carbon Celery task (`vegetation.carbon`) → to be ported as `carbon.calculate`
- `co2SequesteredTotal` / `dailyGPP` Orion-LD patches → now owned by this module

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FIWARE_CONTEXT_BROKER_URL` | `http://orion-ld-service:1026` | Orion-LD internal URL |
| `WEATHER_WORKER_URL` | `http://weather-worker-service:8000` | PAR data source |
| `DATABASE_URL` | — | PostgreSQL connection string |
