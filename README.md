# NKZ Module Carbon — Carbon Intelligence

Carbon balance per parcel and campaign for the Nekazari platform.
**AGPL-3.0**

## What this module does

- **Campaign balance** — for each parcel and calendar-year campaign: plant production (LUE), soil organic
  carbon change (RothC, official 1990 version) and, with nitrogen data, N₂O and the net CO₂eq balance.
- **Real inputs only** — daily parcel weather, Sentinel-2 NDVI, crop cycles, soil horizons and field
  operations. Anything missing is reported with what it blocks; nothing is defaulted.
- **Tiers by what was computed** — 1: production; 2: + soil carbon; 3: + N₂O.
- **NGSI-LD native** — results are `CarbonAssessment` and `CarbonStock` entities, one per parcel and campaign.
- **Monitoring report** — VM0042 / Gold Standard structure, explicitly *not certified*, with the gaps to
  certification listed.

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
GET  /api/carbon/parcels/{entity_id}/campaigns
GET  /api/carbon/parcels/{entity_id}/campaigns/{year}
POST /api/carbon/parcels/{entity_id}/campaigns/{year}/calculate
GET  /api/carbon/parcels/{entity_id}/projection
GET  /api/carbon/parcels/{entity_id}/mrv/report?standard=VM0042&from_year=&to_year=
GET  /api/carbon/tenant/summary?year=
POST /api/carbon/parcels/{entity_id}/management
GET  /api/carbon/parcels/{entity_id}/scenarios
POST /api/carbon/parcels/{entity_id}/scenarios/baseline
POST /api/carbon/internal/campaigns/recalculate-open   (X-Internal-Service-Secret)
POST /api/carbon/internal/setup-parcel                 (X-Internal-Service-Secret)
```

## Architecture

```
nkz-module-carbon/
├── backend/
│   ├── app/
│   │   ├── api/          # REST endpoints
│   │   ├── services/     # roth_c_model, campaign_balance, campaign_runner, campaign_reports, ghg_model
│   │   ├── ngsild/       # Orion-LD client, entity builders
│   │   ├── platform/     # Clients: weather, vegetation, bioorchestrator, crop-health
│   │   ├── reconstructor/ # Historical baseline (SIGPAC, S2, ERA5)
│   │   ├── models/       # Pydantic schemas
│   │   └── db/           # asyncpg pool, audit log migrations
│   ├── tests/            # unit tests + official RothC reference data
│   ├── validation/       # Rothamsted, Cool Farm, mass conservation
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

See [METHODOLOGY.md](METHODOLOGY.md): periods, inputs, formulas, RothC validation, uncertainty and the report.

## Platform dependencies

| Service | Purpose |
|---------|---------|
| weather-api | Closed-day parcel weather (`/api/weather/parcel/{id}/daily`) |
| Orion-LD | `EOProduct` (NDVI), `AgriSoilExtended`, `AgriCrop` + `AgriParcelOperation` (crop cycles, resolved with the platform SDK), results |
| bioorchestrator | Crop parameters (LUE, fAPAR, root fraction), optional |
| PostgreSQL | Plan check and audit log |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FIWARE_CONTEXT_BROKER_URL` | `http://orion-ld-service:1026` | Orion-LD internal URL |
| `WEATHER_API_URL` | `http://weather-api-service:8000` | Parcel daily weather |
| `BIOORCHESTRATOR_URL` | `http://bioorchestrator-api-service:8420` | Crop parameters |
| `INTERNAL_SERVICE_SECRET` | — | Internal routes and calls |
| `DATABASE_URL` | — | PostgreSQL connection string |

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE).

---

Built for the [Nekazari](https://nekazari.robotika.cloud) platform by [robotika.cloud](https://robotika.cloud).
