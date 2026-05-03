# NKZ Module Carbon — Carbon Intelligence

Carbon sequestration and biomass analytics module for the Nekazari platform.
**AGPL-3.0** | **v0.1.0** | **145 tests** | **Production**

> **Status:** Deployed. 3-tier engine (LUE → RothC → GHG), 22 API endpoints, IIFE frontend with 3 slots and 6 locales, Verra VM0042 + Gold Standard MRV reporting.

## What this module does

- **3-tier carbon calculation** — auto-selects precision level based on available data (zero user friction)
  - **Tier 1 (±35–40%)**: LUE model from satellite NDVI/OSAVI + weather — always available
  - **Tier 2 (±20–25%)**: RothC soil carbon model (5 pools) — requires soil type + management
  - **Tier 3 (±10–15%)**: Full GHG budget (N₂O IPCC 2019, CH₄, NEE/NECB) — requires sensors + N data
- **NGSI-LD native** — Orion-LD is the source of truth; all results published as `CarbonAssessment` and `CarbonStock` entities
- **DataHub integration** — Arrow IPC adapter for timeseries visualization
- **MRV reporting** — Verra VM0042 and Gold Standard SOC Framework compliant reports with SHA-256 input hashing and full audit trail
- **Historical reconstructor** — SIGPAC + Sentinel-2 + ERA5-Land → 10-year baseline for carbon projects
- **Uncertainty quantification** — Gaussian analytical (T1), Latin Hypercube 500 (T2), Monte Carlo 5000 (T3)

## Quick start

```bash
# Clone
git clone https://github.com/nkz-os/nkz-module-carbon.git
cd nkz-module-carbon

# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run build:module  # outputs dist/nkz-module.js
```

## API

```
GET  /health
GET  /api/carbon/parcels/{entity_id}/assessment
POST /api/carbon/parcels/{entity_id}/calculate
GET  /api/carbon/parcels/{entity_id}/tier-info
GET  /api/carbon/parcels/{entity_id}/assessment/history
POST /api/carbon/parcels/{entity_id}/management
GET  /api/carbon/parcels/{entity_id}/projection
GET  /api/carbon/parcels/{entity_id}/mrv/report?standard=VM0042
GET  /api/carbon/parcels/{entity_id}/scenarios
POST /api/carbon/parcels/{entity_id}/scenarios/baseline
POST /api/carbon/parcels/{entity_id}/scenarios/project
GET  /api/carbon/timeseries/entities/{entity_id}/data        (Arrow IPC)
POST /api/carbon/internal/timeseries/export-arrow             (DataHub)
POST /api/carbon/webhooks/vegetation-index-updated
```

## Architecture

```
nkz-module-carbon/
├── backend/
│   ├── app/
│   │   ├── api/          # 22 REST endpoints
│   │   ├── services/     # carbon_engine, roth_c_model, ghg_model, uncertainty, data_resolver, mrv_reporter
│   │   ├── ngsild/       # Orion-LD client, entity builders
│   │   ├── platform/     # Clients: weather, vegetation, bioorchestrator, crop-health
│   │   ├── reconstructor/ # Historical baseline (SIGPAC, S2, ERA5)
│   │   ├── models/       # Pydantic schemas
│   │   └── db/           # asyncpg pool, audit log migrations
│   ├── tests/            # 124 unit tests
│   ├── validation/       # Rothamsted, Cool Farm, mass conservation (21 tests)
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── components/   # 3 slot components
│       ├── locales/      # 6 languages (es, en, ca, eu, fr, pt)
│       └── api/          # Typed API client
├── k8s/                  # Deployment, Service, Ingress
├── METHODOLOGY.md        # Complete calculation methodology reference
├── manifest.json
└── LICENSE               # AGPL-3.0
```

## Methodology

See [METHODOLOGY.md](METHODOLOGY.md) for the complete technical reference covering all 3 tiers, formulas, data sources, uncertainty quantification, MRV standards compliance, and validation.

## Platform dependencies

| Service | Purpose |
|---------|---------|
| vegetation-prime | NDVI, LAI, OSAVI from Sentinel-2 |
| bioorchestrator | Crop phenology, LUE, fAPAR params, root fractions |
| crop-health | CWSI, water deficit, vigor (Tier 2–3) |
| weather-worker | PAR, ETo, temperature, precipitation |
| Orion-LD | NGSI-LD Context Broker (source of truth) |
| PostgreSQL/TimescaleDB | Audit log + telemetry (via telemetry-worker) |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FIWARE_CONTEXT_BROKER_URL` | `http://orion-ld-service:1026` | Orion-LD internal URL |
| `WEATHER_WORKER_URL` | `http://weather-worker-service:8000` | Weather data source |
| `VEGETATION_PRIME_URL` | `http://vegetation-prime-api-service:8000` | Vegetation indices |
| `BIOORCHESTRATOR_URL` | `http://bioorchestrator-api-service:8420` | Crop parameters |
| `DATABASE_URL` | — | PostgreSQL connection string |

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE).

---

Built for the [Nekazari](https://nekazari.robotika.cloud) platform by [robotika.cloud](https://robotika.cloud).
