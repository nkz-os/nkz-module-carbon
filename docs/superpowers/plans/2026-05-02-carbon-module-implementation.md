# NKZ-Module-Carbon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a SOTA carbon sequestration module from skeleton to production, implementing 3-tier dynamic calculation (LUE→RothC→Process) with Verra VM0042 MRV, zero-friction UX, and full platform integration.

**Architecture:** Python FastAPI backend as orchestrator consuming vegetation-prime (indices), bioorchestrator (phenology), crop-health (stress), weather-worker (meteo). Orion-LD as source of truth for CarbonAssessment/CarbonStock entities. React IIFE frontend with 3 slots, 6 locales. RothC soil carbon model with Weihermüller initialization. Tier auto-selection via data_resolver.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, pyarrow, numba, httpx, React 18, TypeScript 5, uPlot, @nekazari/sdk, @nekazari/module-builder

**Spec reference:** `docs/superpowers/specs/2026-05-02-carbon-module-sota-design.md`

---

## File Structure

```
nkz-module-carbon/
├── backend/
│   ├── app/
│   │   ├── main.py                         # FastAPI app, lifespan, router mounting
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── assessments.py              # Tier calc, history, tier-info, projection
│   │   │   ├── management.py               # Management input CRUD
│   │   │   ├── scenarios.py                # Baseline/Project scenario CRUD, recalculate
│   │   │   ├── mrv.py                      # VM0042 / Gold Standard report export
│   │   │   ├── timeseries.py              # Arrow IPC single + multi-series (DataHub)
│   │   │   ├── webhooks.py                 # vegetation-index-updated trigger
│   │   │   └── internal.py                 # health endpoint
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── units.py                    # Conversion constants, canonical naming
│   │   │   ├── spectral.py                 # Index selection (NDVI/OSAVI/MSAVI2)
│   │   │   ├── solar_geometry.py           # PAR clear-sky, Ra (FAO-56)
│   │   │   ├── carbon_engine.py            # Tier 1: LUE GPP/NPP/AGB/BGB/CO₂
│   │   │   ├── roth_c_model.py             # Tier 2: RothC pools, TSMD, humification
│   │   │   ├── ghg_model.py                # Tier 3: N₂O IPCC 2019, CH₄, NEE/NECB
│   │   │   ├── uncertainty.py              # Gaussian, LHS 500, MC 5000
│   │   │   ├── data_resolver.py            # Auto-tier selection from available sources
│   │   │   └── mrv_reporter.py             # VM0042 §5.5/§8 structured report
│   │   ├── ngsild/
│   │   │   ├── __init__.py
│   │   │   ├── client.py                   # Orion-LD HTTP (NGSI-LD headers, tenant)
│   │   │   ├── entities.py                 # CarbonAssessment, CarbonStock builders
│   │   │   └── scenarios.py                # Baseline/ProjectScenario + CalculationRun
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── schemas.py                  # Pydantic request/response models
│   │   │   └── management.py               # ManagementInput (residues, tillage, amendments, N)
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── database.py                 # asyncpg pool, connection context
│   │   │   └── migrations/
│   │   │       └── 001_create_carbon_tables.sql
│   │   └── platform/
│   │       ├── __init__.py
│   │       ├── vegetation_client.py        # vegetation-prime HTTP client
│   │       ├── bioorchestrator_client.py   # bioorchestrator HTTP client
│   │       ├── crop_health_client.py       # Orion-LD CropHealthAssessment query
│   │       └── weather_client.py           # weather-worker HTTP client
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py                     # pytest fixtures, async test client
│   │   ├── test_units.py
│   │   ├── test_spectral.py
│   │   ├── test_solar_geometry.py
│   │   ├── test_carbon_engine.py
│   │   ├── test_roth_c_model.py
│   │   ├── test_ghg_model.py
│   │   ├── test_uncertainty.py
│   │   ├── test_data_resolver.py
│   │   ├── test_mrv_reporter.py
│   │   ├── test_api_assessments.py
│   │   ├── test_api_scenarios.py
│   │   └── test_ngsild_entities.py
│   ├── validation/
│   │   ├── rothamsted_broadbalk.py         # Validation against Rothamsted LTER
│   │   ├── cool_farm_crosscheck.py         # Cross-check against Cool Farm Tool
│   │   └── mass_conservation_test.py       # Σin − Σout − ΔSOC = 0 ± 0.1%
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── moduleEntry.ts                  # register({id:'carbon', viewerSlots})
│   │   ├── i18n.ts                         # addResourceBundle for 6 locales
│   │   ├── locales/
│   │   │   ├── es/carbon.json
│   │   │   ├── en/carbon.json
│   │   │   ├── ca/carbon.json
│   │   │   ├── eu/carbon.json
│   │   │   ├── fr/carbon.json
│   │   │   └── pt/carbon.json
│   │   ├── components/
│   │   │   ├── CarbonContextPanel.tsx       # context-panel slot
│   │   │   ├── CarbonDashboardWidget.tsx    # dashboard-widget slot
│   │   │   ├── CarbonBottomPanel.tsx        # bottom-panel slot (tabs container)
│   │   │   ├── CarbonMRVExport.tsx          # VM0042 / Gold Standard export UI
│   │   │   ├── CarbonManagementForm.tsx     # Management input form
│   │   │   ├── CarbonProjectionChart.tsx    # 20yr SOC projection with scenario slider
│   │   │   ├── CarbonTierBadge.tsx          # Tier indicator with confidence
│   │   │   └── CarbonGapList.tsx            # Missing data sources for next tier
│   │   ├── api/
│   │   │   └── carbonApi.ts                # Typed API client for /api/carbon
│   │   └── hooks/
│   │       ├── useCarbonAssessment.ts       # SWR-style hook for assessment data
│   │       └── useCarbonTier.ts             # Tier info hook
│   ├── package.json
│   └── tsconfig.json
├── k8s/
│   ├── backend-deployment.yaml
│   ├── backend-service.yaml
│   ├── ingress.yaml
│   └── configmap.yaml
├── manifest.json
├── README.md
├── .gitignore
└── .github/
    └── workflows/
        └── build-push.yml
```

---

## Phase 0: Project Foundation (Week 1)

### Task 0.1: Initialize Git repository and GitHub remote

**Files:**
- Create: `.gitignore`
- Create: `README.md` (update existing)

- [ ] **Step 1: Create .gitignore**

```bash
cat > /home/g/Documents/nekazari/nkz-module-carbon/.gitignore << 'GITIGNORE'
__pycache__/
*.py[cod]
*.egg-info/
.env
.venv/
venv/
node_modules/
dist/
*.log
.DS_Store
.coverage
htmlcov/
.pytest_cache/
.ruff_cache/
GITIGNORE
```

- [ ] **Step 2: Initialize git and create initial commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git init
git add .gitignore README.md manifest.json backend/ frontend/ k8s/
git commit -m "feat(carbon): initial module skeleton

LUE carbon engine, Arrow IPC stub, tenant utilities, manifest v0.1.0"
```

- [ ] **Step 3: Verify**

```bash
git log --oneline
# Expected: one commit showing
```

### Task 0.2: Create backend requirements.txt and Dockerfile

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/Dockerfile`

- [ ] **Step 1: Write requirements.txt**

```bash
cat > /home/g/Documents/nekazari/nkz-module-carbon/backend/requirements.txt << 'REQ'
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
httpx>=0.27.0
asyncpg>=0.29.0
pyarrow>=17.0.0
pydantic>=2.9.0
python-dotenv>=1.0.0
numba>=0.60.0
numpy>=1.26.0
REQ
```

- [ ] **Step 2: Write Dockerfile**

```bash
cat > /home/g/Documents/nekazari/nkz-module-carbon/backend/Dockerfile << 'DOCKERFILE'
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
DOCKERFILE
```

- [ ] **Step 3: Commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git add backend/requirements.txt backend/Dockerfile
git commit -m "feat(carbon): add backend requirements and Dockerfile"
```

### Task 0.3: Create bare FastAPI app main.py

**Files:**
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: Create app init**

```bash
touch /home/g/Documents/nekazari/nkz-module-carbon/backend/app/__init__.py
```

- [ ] **Step 2: Write main.py**

```python
# backend/app/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Carbon module starting")
    yield
    logger.info("Carbon module shutting down")


app = FastAPI(
    title="NKZ Module Carbon",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://nekazari.robotika.cloud"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "NGSILD-Tenant"],
)


@app.get("/health")
async def health():
    return {"status": "healthy", "module": "carbon"}
```

- [ ] **Step 3: Commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git add backend/app/__init__.py backend/app/main.py
git commit -m "feat(carbon): bare FastAPI app with health endpoint"
```

### Task 0.4: Write units.py — canonical conversion constants

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/units.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_units.py`

- [ ] **Step 1: Write units.py**

```python
# backend/app/services/units.py
"""Canonical conversion constants. Single source of truth for all unit math.

All variable names MUST encode their unit using suffixes from the naming
convention table (see spec §0). Bare names without unit suffix are
REJECTED in code review.
"""

# Carbon ↔ CO₂
C_TO_CO2 = 3.6667  # gCO2 per gC (44/12)

# Carbon content of dry matter
C_IN_DM = 0.45  # gC per g dry matter

# Area conversions
G_PER_M2_TO_T_PER_HA = 0.01  # (g/m²) × 0.01 = t/ha
HA_PER_M2 = 0.0001  # 1 m² = 0.0001 ha

# Mass conversions
KG_TO_T = 0.001
G_TO_KG = 0.001

# N → N₂O mass conversion
N_TO_N2O = 44.0 / 28.0  # N₂O / N₂

# PAR fraction of global radiation (FAO-56)
PAR_FRACTION = 0.48

# Clear-sky radiation fraction of extraterrestrial (FAO-56)
CLEAR_SKY_FRACTION = 0.75
```

- [ ] **Step 2: Write test_units.py**

```python
# backend/tests/test_units.py
from app.services import units


class TestConversionConstants:
    def test_c_to_co2_is_44_over_12(self):
        assert units.C_TO_CO2 == 44.0 / 12.0

    def test_carbon_in_dry_matter_is_45_percent(self):
        assert units.C_IN_DM == 0.45

    def test_g_per_m2_to_t_per_ha_is_correct(self):
        # 100 g/m² = 1 t/ha
        assert 100 * units.G_PER_M2_TO_T_PER_HA == 1.0

    def test_n_to_n2o_conversion(self):
        # 28 g N → 44 g N₂O
        assert units.N_TO_N2O == 44.0 / 28.0

    def test_par_fraction_in_range(self):
        assert 0.4 < units.PAR_FRACTION < 0.6
```

- [ ] **Step 3: Run tests with zero deps**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon/backend
python -m pytest tests/test_units.py -v
# Expected: 5 passed
```

- [ ] **Step 4: Commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git add backend/app/services/__init__.py backend/app/services/units.py \
        backend/tests/__init__.py backend/tests/test_units.py
git commit -m "feat(carbon): add units.py with canonical conversion constants"
```

### Task 0.5: Create K8s manifests

**Files:**
- Create: `k8s/backend-deployment.yaml`
- Create: `k8s/backend-service.yaml`
- Create: `k8s/ingress.yaml`

- [ ] **Step 1: Write backend-deployment.yaml**

```yaml
# k8s/backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: carbon-api
  namespace: nekazari
  labels:
    app: carbon-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: carbon-api
  template:
    metadata:
      labels:
        app: carbon-api
    spec:
      containers:
        - name: carbon-api
          image: ghcr.io/nkz-os/nkz-module-carbon/carbon-backend:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
              name: http
          envFrom:
            - configMapRef:
                name: nekazari-config
          env:
            - name: FIWARE_CONTEXT_BROKER_URL
              value: "http://orion-ld-service:1026"
            - name: WEATHER_WORKER_URL
              value: "http://weather-worker-service:8000"
            - name: VEGETATION_PRIME_URL
              value: "http://vegetation-prime-api-service:8000"
            - name: BIOORCHESTRATOR_URL
              value: "http://bioorchestrator-api-service:8420"
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: postgresql-secret
                  key: url
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 30
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
```

- [ ] **Step 2: Write backend-service.yaml**

```yaml
# k8s/backend-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: carbon-api-service
  namespace: nekazari
  labels:
    app: carbon-api
spec:
  selector:
    app: carbon-api
  ports:
    - port: 8000
      targetPort: 8000
      protocol: TCP
      name: http
```

- [ ] **Step 3: Write ingress.yaml**

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: carbon-api-ingress
  namespace: nekazari
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  rules:
    - host: nkz.robotika.cloud
      http:
        paths:
          - path: /api/carbon
            pathType: Prefix
            backend:
              service:
                name: carbon-api-service
                port:
                  number: 8000
```

- [ ] **Step 4: Commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git add k8s/
git commit -m "feat(carbon): add K8s manifests (deployment, service, ingress)"
```

### Task 0.6: Create CI workflow

**Files:**
- Create: `.github/workflows/build-push.yml`

- [ ] **Step 1: Write CI workflow**

```yaml
# .github/workflows/build-push.yml
name: Build and Push

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install deps
        run: pip install -r backend/requirements.txt pytest pytest-asyncio
      - name: Run tests
        run: cd backend && python -m pytest tests/ -v

  build-push:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: backend/
          push: true
          tags: ghcr.io/nkz-os/nkz-module-carbon/carbon-backend:latest
```

- [ ] **Step 2: Commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git add .github/
git commit -m "feat(carbon): add CI pipeline (test + build-push to GHCR)"
```

### Task 0.7: Create GitHub repository and push

- [ ] **Step 1: Verify all files staged**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git status
```

- [ ] **Step 2: Create repo on GitHub**

```bash
gh repo create nkz-os/nkz-module-carbon \
  --public \
  --description "Carbon sequestration and biomass analytics module for Nekazari platform. LUE-based GPP/NPP with RothC soil carbon, Verra VM0042 MRV." \
  --source=. \
  --push
```

- [ ] **Step 3: Verify remote and push**

```bash
git remote -v
git push -u origin main
```

---

## Phase 1: Carbon Engine v2 — Tier 1 Corrections (Weeks 2-4)

### Task 1.1: Write solar_geometry.py — PAR clear-sky calculation

**Files:**
- Create: `backend/app/services/solar_geometry.py`
- Create: `backend/tests/test_solar_geometry.py`

- [ ] **Step 1: Write solar_geometry.py**

```python
# backend/app/services/solar_geometry.py
"""Solar geometry for clear-sky PAR calculation (FAO-56, Allen et al. 1998)."""

import math
from datetime import date

from app.services.units import PAR_FRACTION, CLEAR_SKY_FRACTION

SOLAR_CONSTANT = 0.0820  # MJ/m²/min


def extraterrestrial_solar_MJ_m2_day(lat_deg: float, doy: int) -> float:
    """Extraterrestrial solar radiation Ra [MJ/m²/day] (FAO-56 Eq. 21)."""
    lat_rad = math.radians(lat_deg)
    solar_decl_rad = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)
    sunset_hour_angle = math.acos(-math.tan(lat_rad) * math.tan(solar_decl_rad))
    d_r = 1 + 0.033 * math.cos(2 * math.pi / 365 * doy)
    ra = (
        24 * 60 / math.pi
        * SOLAR_CONSTANT
        * d_r
        * (
            sunset_hour_angle * math.sin(lat_rad) * math.sin(solar_decl_rad)
            + math.cos(lat_rad) * math.cos(solar_decl_rad) * math.sin(sunset_hour_angle)
        )
    )
    return ra


def doy_from_date(d: date) -> int:
    """Day of year from date."""
    return d.timetuple().tm_yday


def clear_sky_par_MJ_m2_day(lat_deg: float, doy: int) -> float:
    """Clear-sky PAR [MJ/m²/day] from latitude and day of year.

    Ra       = extraterrestrial solar radiation
    Rs_clear = 0.75 × Ra       (clear-sky global radiation)
    PAR      = 0.48 × Rs_clear (PAR fraction)
    """
    ra_MJ_m2_day = extraterrestrial_solar_MJ_m2_day(lat_deg, doy)
    rs_clear_MJ_m2_day = CLEAR_SKY_FRACTION * ra_MJ_m2_day
    return PAR_FRACTION * rs_clear_MJ_m2_day
```

- [ ] **Step 2: Write tests**

```python
# backend/tests/test_solar_geometry.py
import math
from datetime import date

from app.services.solar_geometry import (
    extraterrestrial_solar_MJ_m2_day,
    clear_sky_par_MJ_m2_day,
    doy_from_date,
)


class TestDOY:
    def test_jan_1(self):
        assert doy_from_date(date(2026, 1, 1)) == 1

    def test_dec_31_non_leap(self):
        assert doy_from_date(date(2025, 12, 31)) == 365

    def test_june_15(self):
        assert doy_from_date(date(2026, 6, 15)) == 166


class TestExtraterrestrialSolar:
    def test_equator_summer_solstice(self):
        """At equator on summer solstice, Ra ≈ 40 MJ/m²/day (FAO-56 Annex 2 Table 2.6)."""
        ra = extraterrestrial_solar_MJ_m2_day(lat_deg=0.0, doy=172)
        assert 38 < ra < 42, f"Expected ~40, got {ra}"

    def test_45n_winter_solstice(self):
        """At 45°N on Dec 21, Ra is low."""
        ra = extraterrestrial_solar_MJ_m2_day(lat_deg=45.0, doy=355)
        assert ra < 15, f"Expected <15, got {ra}"

    def test_seville_summer(self):
        """Seville (37.4°N) mid-summer should have Ra ~42."""
        ra = extraterrestrial_solar_MJ_m2_day(lat_deg=37.4, doy=182)
        assert 40 < ra < 44, f"Expected ~42, got {ra}"

    def test_pole_winter_is_zero(self):
        """At 90°N in winter, Ra = 0 (polar night)."""
        ra = extraterrestrial_solar_MJ_m2_day(lat_deg=90.0, doy=1)
        assert ra < 0.01, f"Expected ~0, got {ra}"


class TestClearSkyPAR:
    def test_seville_summer_par(self):
        """Seville summer clear-sky PAR should be ~15 MJ/m²/day."""
        par = clear_sky_par_MJ_m2_day(lat_deg=37.4, doy=182)
        # 42 × 0.75 × 0.48 ≈ 15.1
        assert 12 < par < 18, f"Expected ~15, got {par}"

    def test_returns_positive_for_all_latitudes(self):
        for lat in [-60, -30, 0, 30, 60]:
            par = clear_sky_par_MJ_m2_day(lat_deg=lat, doy=180)
            assert par >= 0, f"PAR negative for lat={lat}: {par}"
```

- [ ] **Step 3: Run tests**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon/backend
python -m pytest tests/test_solar_geometry.py -v
# Expected: 8 passed
```

- [ ] **Step 4: Commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git add backend/app/services/solar_geometry.py backend/tests/test_solar_geometry.py
git commit -m "feat(carbon): add solar_geometry.py with clear-sky PAR (FAO-56)"
```

### Task 1.2: Write spectral.py — index selection

**Files:**
- Create: `backend/app/services/spectral.py`
- Create: `backend/tests/test_spectral.py`

- [ ] **Step 1: Write spectral.py**

```python
# backend/app/services/spectral.py
"""Spectral index selection and computation (spec §2)."""

import math
from enum import Enum


class MorphologicalType(str, Enum):
    HERBACEOUS = "herbaceous"
    WOODY = "woody"


class VegetationIndex(str, Enum):
    NDVI = "NDVI"
    OSAVI = "OSAVI"
    MSAVI2 = "MSAVI2"


# OSAVI soil adjustment factor for woody crops
OSAVI_L_WOODY = 0.16


def select_index(morph_type: MorphologicalType) -> VegetationIndex:
    """Select vegetation index by crop morphological type.

    Herbaceous → NDVI
    Woody      → OSAVI (L=0.16)
    """
    if morph_type == MorphologicalType.HERBACEOUS:
        return VegetationIndex.NDVI
    if morph_type == MorphologicalType.WOODY:
        return VegetationIndex.OSAVI
    return VegetationIndex.MSAVI2


def compute_ndvi(nir: float, red: float) -> float:
    """NDVI = (NIR - RED) / (NIR + RED)."""
    denom = nir + red
    if denom == 0:
        return 0.0
    return (nir - red) / denom


def compute_osavi(nir: float, red: float, L: float = OSAVI_L_WOODY) -> float:
    """OSAVI = (NIR - RED) / (NIR + RED + L)."""
    return (nir - red) / (nir + red + L)


def compute_msavi2(nir: float, red: float) -> float:
    """MSAVI2 = (2·NIR + 1 - sqrt((2·NIR+1)² - 8·(NIR-RED))) / 2."""
    discriminant = (2 * nir + 1) ** 2 - 8 * (nir - red)
    if discriminant < 0:
        return 0.0
    return (2 * nir + 1 - math.sqrt(discriminant)) / 2


def compute_index(
    vi: VegetationIndex, nir: float, red: float
) -> float:
    """Compute the selected vegetation index from NIR and RED bands."""
    if vi == VegetationIndex.NDVI:
        return compute_ndvi(nir, red)
    if vi == VegetationIndex.OSAVI:
        return compute_osavi(nir, red)
    if vi == VegetationIndex.MSAVI2:
        return compute_msavi2(nir, red)
    raise ValueError(f"Unknown vegetation index: {vi}")
```

- [ ] **Step 2: Write tests**

```python
# backend/tests/test_spectral.py
from app.services.spectral import (
    MorphologicalType,
    VegetationIndex,
    select_index,
    compute_ndvi,
    compute_osavi,
    compute_msavi2,
    compute_index,
)


class TestSelectIndex:
    def test_herbaceous_gets_ndvi(self):
        assert select_index(MorphologicalType.HERBACEOUS) == VegetationIndex.NDVI

    def test_woody_gets_osavi(self):
        assert select_index(MorphologicalType.WOODY) == VegetationIndex.OSAVI


class TestNDVI:
    def test_dense_vegetation(self):
        """Healthy vegetation: NIR=0.5, RED=0.1 → NDVI=0.667."""
        ndvi = compute_ndvi(nir=0.5, red=0.1)
        assert 0.6 < ndvi < 0.7

    def test_bare_soil(self):
        """Bare soil: NIR≈RED → NDVI≈0."""
        ndvi = compute_ndvi(nir=0.2, red=0.2)
        assert abs(ndvi) < 0.01

    def test_zero_denominator(self):
        assert compute_ndvi(nir=0.0, red=0.0) == 0.0


class TestOSAVI:
    def test_woody_default_L(self):
        """OSAVI with L=0.16 for woody crops."""
        osavi = compute_osavi(nir=0.5, red=0.1, L=0.16)
        assert 0.55 < osavi < 0.65

    def test_reduces_soil_sensitivity_vs_ndvi(self):
        ndvi = compute_ndvi(nir=0.3, red=0.15)
        osavi = compute_osavi(nir=0.3, red=0.15, L=0.16)
        # OSAVI should be lower (less inflated) on bare-ish soil
        assert osavi < ndvi


class TestMSAVI2:
    def test_dense_vegetation(self):
        msavi2 = compute_msavi2(nir=0.5, red=0.1)
        assert 0.3 < msavi2 < 0.7

    def test_negative_discriminant_returns_zero(self):
        """Edge case where discriminant would be negative."""
        result = compute_msavi2(nir=-1.0, red=1.0)
        assert result == 0.0


class TestComputeIndex:
    def test_dispatches_correctly(self):
        ndvi = compute_index(VegetationIndex.NDVI, nir=0.5, red=0.1)
        osavi = compute_index(VegetationIndex.OSAVI, nir=0.5, red=0.1)
        msavi2 = compute_index(VegetationIndex.MSAVI2, nir=0.5, red=0.1)
        assert ndvi != osavi
        assert ndvi != msavi2
        assert osavi != msavi2
```

- [ ] **Step 3: Run tests**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon/backend
python -m pytest tests/test_spectral.py -v
# Expected: 12 passed
```

- [ ] **Step 4: Commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git add backend/app/services/spectral.py backend/tests/test_spectral.py
git commit -m "feat(carbon): add spectral.py with index selection (NDVI/OSAVI/MSAVI2)"
```

### Task 1.3: Rewrite carbon_engine.py — Tier 1 with corrections

**Files:**
- Modify: `backend/app/services/carbon_engine.py` (complete rewrite)
- Create: `backend/tests/test_carbon_engine.py`

- [ ] **Step 1: Write corrected carbon_engine.py**

```python
# backend/app/services/carbon_engine.py
"""Tier 1 Carbon Engine — LUE (Light Use Efficiency) Model.

Stateless. Input: daily arrays. Output: dict with unit-encoded keys.

All output variable names encode their units per §0 convention.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from app.services.units import C_TO_CO2, C_IN_DM, G_PER_M2_TO_T_PER_HA

logger = logging.getLogger(__name__)

# Carbon Use Efficiency (autotrophic respiration discount)
CUE_FRAC = 0.5


@dataclass
class Tier1Input:
    """Daily inputs for Tier 1 calculation."""
    par_MJ_m2_day: float
    fapar_frac: float
    lue_gC_per_MJ: float
    root_fraction: float
    species: str = "unknown"
    data_quality_flags: list[str] | None = None


@dataclass
class Tier1Output:
    """Tier 1 daily outputs with unit-encoded keys."""
    gpp_gC_m2_day: float
    npp_total_gC_m2_day: float
    npp_aerea_gC_m2_day: float
    npp_radicular_gC_m2_day: float
    agb_dry_tDM_ha: float
    bgb_dry_tDM_ha: float
    co2_seq_kgCO2_ha_day: float
    fapar_frac: float
    lue_gC_per_MJ: float
    par_MJ_m2_day: float
    data_quality_flags: list[str]


def compute_fapar_frac(vi_value: float, a: float, b: float) -> float:
    """fAPAR = clamp(a · VI + b, 0, 0.95) — spec §3.1."""
    fapar = a * vi_value + b
    return max(0.0, min(0.95, fapar))


def calculate_tier1(inputs: Tier1Input) -> Tier1Output:
    """Compute Tier 1 carbon metrics for one day.

    Spec §3.4: GPP = PAR × fAPAR × LUE
    Spec §3.4: AGB_dry_t_ha = (NPP_aerea / C_IN_DM) × G_PER_M2_TO_T_PER_HA
    Spec §3.5: CO2_seq = NPP_total × C_TO_CO2 × 10

    Tier 1 does NOT subtract Rh — see spec §3.5 note.
    """
    flags = list(inputs.data_quality_flags or [])

    gpp_gC_m2_day = (
        inputs.par_MJ_m2_day
        * inputs.fapar_frac
        * inputs.lue_gC_per_MJ
    )

    npp_total_gC_m2_day = gpp_gC_m2_day * CUE_FRAC
    npp_aerea_gC_m2_day = npp_total_gC_m2_day * (1.0 - inputs.root_fraction)
    npp_radicular_gC_m2_day = npp_total_gC_m2_day * inputs.root_fraction

    # Biomass: gC/m²/day → tDM/ha/day
    # (gC / 0.45) = gDM/m² → × 0.01 = tDM/ha
    agb_dry_tDM_ha = (npp_aerea_gC_m2_day / C_IN_DM) * G_PER_M2_TO_T_PER_HA
    bgb_dry_tDM_ha = (npp_radicular_gC_m2_day / C_IN_DM) * G_PER_M2_TO_T_PER_HA

    # CO₂: gC/m²/day → kgCO₂/ha/day
    # gC × 3.664 = gCO2/m² → × 0.001 = kgCO2/m² → × 10000 = kgCO2/ha
    # Simplification: gC/m²/day × 3.664 × 10 = kgCO2/ha/day
    co2_seq_kgCO2_ha_day = npp_total_gC_m2_day * C_TO_CO2 * 10.0

    return Tier1Output(
        gpp_gC_m2_day=gpp_gC_m2_day,
        npp_total_gC_m2_day=npp_total_gC_m2_day,
        npp_aerea_gC_m2_day=npp_aerea_gC_m2_day,
        npp_radicular_gC_m2_day=npp_radicular_gC_m2_day,
        agb_dry_tDM_ha=agb_dry_tDM_ha,
        bgb_dry_tDM_ha=bgb_dry_tDM_ha,
        co2_seq_kgCO2_ha_day=co2_seq_kgCO2_ha_day,
        fapar_frac=inputs.fapar_frac,
        lue_gC_per_MJ=inputs.lue_gC_per_MJ,
        par_MJ_m2_day=inputs.par_MJ_m2_day,
        data_quality_flags=flags,
    )
```

- [ ] **Step 2: Write tests**

```python
# backend/tests/test_carbon_engine.py
import math

from app.services.carbon_engine import (
    Tier1Input,
    compute_fapar_frac,
    calculate_tier1,
)
from app.services.units import C_IN_DM, C_TO_CO2, G_PER_M2_TO_T_PER_HA


class TestFAPAR:
    def test_herbaceous_default(self):
        """NDVI=0.7, a=1.24, b=-0.168 → fAPAR ≈ 0.70."""
        fapar = compute_fapar_frac(vi_value=0.7, a=1.24, b=-0.168)
        assert 0.6 < fapar < 0.8

    def test_olive_default(self):
        """OSAVI=0.5, a=1.40, b=-0.240 → fAPAR ≈ 0.46."""
        fapar = compute_fapar_frac(vi_value=0.5, a=1.40, b=-0.240)
        assert 0.4 < fapar < 0.55

    def test_clamped_to_zero(self):
        fapar = compute_fapar_frac(vi_value=0.0, a=1.24, b=-0.168)
        assert fapar == 0.0

    def test_clamped_to_0_95(self):
        fapar = compute_fapar_frac(vi_value=1.0, a=1.40, b=1.0)
        assert fapar == 0.95


class TestTier1Calculation:
    def test_typical_wheat_day(self):
        """Wheat, PAR=15, fAPAR=0.7, LUE=1.1, root=0.22."""
        result = calculate_tier1(Tier1Input(
            par_MJ_m2_day=15.0,
            fapar_frac=0.7,
            lue_gC_per_MJ=1.1,
            root_fraction=0.22,
            species="wheat",
        ))
        # GPP = 15 × 0.7 × 1.1 = 11.55
        assert abs(result.gpp_gC_m2_day - 11.55) < 0.01
        # NPP = GPP × 0.5 = 5.775
        assert abs(result.npp_total_gC_m2_day - 5.775) < 0.01
        # NPP_aerea = 5.775 × 0.78 = 4.5045
        assert abs(result.npp_aerea_gC_m2_day - 4.5045) < 0.01
        # AGB = (4.5045 / 0.45) × 0.01 = 0.1001
        assert abs(result.agb_dry_tDM_ha - 0.1001) < 0.001

    def test_co2_calculation(self):
        """Verify CO₂ conversion chain."""
        result = calculate_tier1(Tier1Input(
            par_MJ_m2_day=10.0,
            fapar_frac=0.5,
            lue_gC_per_MJ=1.0,
            root_fraction=0.25,
        ))
        # GPP = 10 × 0.5 × 1.0 = 5.0
        # NPP = 5.0 × 0.5 = 2.5
        # CO2 = 2.5 × 3.6667 × 10 = 91.6675
        expected_co2 = 2.5 * C_TO_CO2 * 10.0
        assert abs(result.co2_seq_kgCO2_ha_day - expected_co2) < 0.01

    def test_units_not_kg_per_m2(self):
        """AGB must be ~0.1 for a typical day (tDM/ha), not ~0.001 (kg/m²)."""
        result = calculate_tier1(Tier1Input(
            par_MJ_m2_day=15.0,
            fapar_frac=0.7,
            lue_gC_per_MJ=1.1,
            root_fraction=0.22,
        ))
        agb = result.agb_dry_tDM_ha
        assert 0.05 < agb < 0.20, (
            f"AGB={agb} tDM/ha/day is outside expected range for typical day. "
            f"Check unit conversion — should be tDM/ha."
        )

    def test_data_quality_flags_propagated(self):
        result = calculate_tier1(Tier1Input(
            par_MJ_m2_day=10.0,
            fapar_frac=0.5,
            lue_gC_per_MJ=1.0,
            root_fraction=0.25,
            data_quality_flags=["synthetic_par"],
        ))
        assert "synthetic_par" in result.data_quality_flags
```

- [ ] **Step 3: Run tests**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon/backend
python -m pytest tests/test_carbon_engine.py -v
# Expected: 8 passed
```

- [ ] **Step 4: Commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git add backend/app/services/carbon_engine.py backend/tests/test_carbon_engine.py
git commit -m "feat(carbon): rewrite carbon_engine.py v2 with corrected units and fAPAR params"
```

### Task 1.4: Write platform client stubs

**Files:**
- Create: `backend/app/platform/__init__.py`
- Create: `backend/app/platform/weather_client.py`
- Create: `backend/app/platform/vegetation_client.py`

- [ ] **Step 1: Write weather_client.py**

```python
# backend/app/platform/weather_client.py
"""HTTP client for weather-worker API."""

import logging
import os
from dataclasses import dataclass

import httpx

from app.services.solar_geometry import clear_sky_par_MJ_m2_day, doy_from_date

logger = logging.getLogger(__name__)

WEATHER_WORKER_URL = os.getenv(
    "WEATHER_WORKER_URL", "http://weather-worker-service:8000"
)


@dataclass
class WeatherSnapshot:
    par_MJ_m2_day: float
    temp_air_celsius: float
    precip_mm: float
    eto_mm: float | None
    data_quality: str  # "measured" | "synthetic_par"


async def fetch_weather(
    lat: float, lon: float, obs_date, client: httpx.AsyncClient | None = None
) -> WeatherSnapshot:
    """Fetch weather data. PAR from API, clear-sky fallback on failure."""
    par_MJ_m2_day = None
    data_quality = "measured"
    temp_air_celsius = 20.0
    precip_mm = 0.0
    eto_mm = None

    async with (client or httpx.AsyncClient()) as c:
        try:
            resp = await c.get(
                f"{WEATHER_WORKER_URL}/api/weather/par",
                params={"lat": lat, "lon": lon, "date": obs_date.isoformat()},
                timeout=5,
            )
            resp.raise_for_status()
            par_MJ_m2_day = float(resp.json()["par_mj_m2"])
        except Exception as exc:
            logger.warning("PAR fetch failed (%s), using clear-sky fallback", exc)
            doy = doy_from_date(obs_date)
            par_MJ_m2_day = clear_sky_par_MJ_m2_day(lat, doy)
            data_quality = "synthetic_par"

        try:
            resp = await c.get(
                f"{WEATHER_WORKER_URL}/api/weather/current",
                params={"lat": lat, "lon": lon},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            temp_air_celsius = float(data.get("temp_avg", 20.0))
            precip_mm = float(data.get("precip_mm", 0.0))
            eto_mm = float(data["eto_mm"]) if data.get("eto_mm") is not None else None
        except Exception as exc:
            logger.warning("Weather current fetch failed: %s", exc)

    return WeatherSnapshot(
        par_MJ_m2_day=par_MJ_m2_day,
        temp_air_celsius=temp_air_celsius,
        precip_mm=precip_mm,
        eto_mm=eto_mm,
        data_quality=data_quality,
    )
```

- [ ] **Step 2: Write vegetation_client.py**

```python
# backend/app/platform/vegetation_client.py
"""HTTP client for vegetation-prime API."""

import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

VEGETATION_PRIME_URL = os.getenv(
    "VEGETATION_PRIME_URL", "http://vegetation-prime-api-service:8000"
)


@dataclass
class IndexResult:
    index_type: str
    mean_value: float
    min_value: float
    max_value: float
    std_dev: float
    pixel_count: int
    calculated_at: str | None


async def fetch_latest_indices(
    entity_id: str, tenant_id: str, client: httpx.AsyncClient | None = None
) -> list[IndexResult]:
    """Fetch latest vegetation index results for a parcel."""
    async with (client or httpx.AsyncClient()) as c:
        try:
            resp = await c.get(
                f"{VEGETATION_PRIME_URL}/api/vegetation/scenes/results/{entity_id}",
                headers={"NGSILD-Tenant": tenant_id},
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return [
                IndexResult(
                    index_type=r["index_type"],
                    mean_value=float(r["mean_value"]),
                    min_value=float(r["min_value"]),
                    max_value=float(r["max_value"]),
                    std_dev=float(r.get("std_dev", 0)),
                    pixel_count=int(r.get("pixel_count", 0)),
                    calculated_at=r.get("calculated_at"),
                )
                for r in results
            ]
        except Exception as exc:
            logger.warning("Vegetation index fetch failed for %s: %s", entity_id, exc)
            return []
```

- [ ] **Step 3: Commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git add backend/app/platform/
git commit -m "feat(carbon): add platform client stubs for weather and vegetation-prime"
```

### Task 1.5: Write Tier 1 orchestration endpoint

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/internal.py` (health endpoint)
- Modify: `backend/app/main.py` (mount health router)

- [ ] **Step 1: Write health endpoint**

```python
# backend/app/api/internal.py
from fastapi import APIRouter

router = APIRouter(tags=["internal"])


@router.get("/health")
async def health():
    return {"status": "healthy", "module": "carbon", "version": "0.1.0"}
```

- [ ] **Step 2: Update main.py to mount router**

```python
# In backend/app/main.py, after app = FastAPI(...):

from app.api.internal import router as internal_router

app.include_router(internal_router)
```

- [ ] **Step 3: Commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git add backend/app/api/ backend/app/main.py
git commit -m "feat(carbon): add health endpoint and router mounting"
```

---

## Phase 2: RothC — Tier 2 Soil Carbon Model (Weeks 5-7)

### Task 2.1: Write roth_c_model.py — core RothC implementation

**Files:**
- Create: `backend/app/services/roth_c_model.py`
- Create: `backend/tests/test_roth_c_model.py`

- [ ] **Step 1: Write roth_c_model.py with pools, a_temp, TSMD, Weihermüller, humification, monthly evolution**

```python
# backend/app/services/roth_c_model.py
"""RothC soil carbon model — Tier 2 (spec §4).

Stateless. Input: monthly arrays. Output: pool state + SOC delta.

Implements:
  - Jenkinson 1990 pools and rate constants
  - RothC canonical a_temp (no Q10 simplification)
  - TSMD-based moisture modifier (not CWSI)
  - Weihermüller et al. 2013 pool initialization
  - Per-source differential humification with DPM/RPM split
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Pool rate constants [yr⁻¹] — Jenkinson 1990
POOL_K = {
    "DPM": 10.0,
    "RPM": 0.30,
    "BIO": 0.66,
    "HUM": 0.02,
    "IOM": 0.0,
}

# DPM/RPM split ratios by input type (spec §4.6)
DPM_RPM_RATIOS = {
    "cultivo_anual": 1.44,
    "pasto_mejorado": 1.44,
    "pasto_natural": 0.67,
    "forestal": 0.25,
    "raices": 1.0,
    "exudados": 2.0,
}

# Manure split: 49:49:2 DPM:RPM:HUM
MANURE_SPLIT = {"DPM": 0.49, "RPM": 0.49, "HUM": 0.02}

# Humification coefficients (spec §4.5)
H_COEFFS = {
    "aerea": 1.0,
    "raices": 2.3,
    "exudados": 2.3,
    "enmienda": 1.7,
}

# Exudate fraction of NPP (Pausch & Kuzyakov 2018)
FRAC_EXUDATES = 0.07

# Monthly time step [yr]
DT_MONTH = 1.0 / 12.0

# Vegetation cover modifier (spec §4.7)
C_COVER_VEGETATED = 0.6
C_COVER_BARE = 1.0

# TSMD threshold for moisture modifier (spec §4.3)
TSMD_THRESHOLD_FRAC = 0.444


@dataclass
class PoolState:
    """Carbon pools in tC/ha."""
    dpm_tC_ha: float = 0.0
    rpm_tC_ha: float = 0.0
    bio_tC_ha: float = 0.0
    hum_tC_ha: float = 0.0
    iom_tC_ha: float = 0.0

    @property
    def total_tC_ha(self) -> float:
        return (
            self.dpm_tC_ha
            + self.rpm_tC_ha
            + self.bio_tC_ha
            + self.hum_tC_ha
            + self.iom_tC_ha
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "DPM": self.dpm_tC_ha,
            "RPM": self.rpm_tC_ha,
            "BIO": self.bio_tC_ha,
            "HUM": self.hum_tC_ha,
            "IOM": self.iom_tC_ha,
        }

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> "PoolState":
        return cls(
            dpm_tC_ha=d.get("DPM", 0.0),
            rpm_tC_ha=d.get("RPM", 0.0),
            bio_tC_ha=d.get("BIO", 0.0),
            hum_tC_ha=d.get("HUM", 0.0),
            iom_tC_ha=d.get("IOM", 0.0),
        )


@dataclass
class MonthlyInputs:
    """Monthly inputs for one timestep."""
    temp_celsius: float
    precip_mm: float
    etp_mm: float
    cover_frac: float = 0.0
    cover_present: bool = True
    c_input_aerea_tC_ha: float = 0.0
    c_input_raices_tC_ha: float = 0.0
    c_input_exudados_tC_ha: float = 0.0
    c_input_enmienda_tC_ha: float = 0.0
    npp_total_tC_ha: float = 0.0
    clay_pct: float = 20.0


@dataclass
class RothCResult:
    pools: PoolState
    rh_tC_ha_yr: float  # heterotrophic respiration
    soc_delta_tC_ha_yr: float
    monthly_tsmd: list[float] = field(default_factory=list)


# ── Temperature modifier (spec §4.2) ──────────────────────────

def a_temp(temp_celsius: float) -> float:
    """RothC canonical temperature modifier — Jenkinson 1990.

    a_temp = 47.91 / (1 + exp(106.06 / (T + 18.27)))
    Clamped at T ≤ -18°C to prevent numerical singularity.
    """
    if temp_celsius <= -18.0:
        return 0.0
    return 47.91 / (1.0 + math.exp(106.06 / (temp_celsius + 18.27)))


# ── Moisture modifier — TSMD (spec §4.3) ──────────────────────

def tsmd_max(clay_pct: float) -> float:
    """Maximum Topsoil Moisture Deficit [mm] from clay percentage."""
    return 20.0 + 1.3 * clay_pct - 0.01 * (clay_pct ** 2)


def b_humedad(tsmd: float, tsmax: float) -> float:
    """Moisture rate modifier for RothC."""
    if tsmax <= 0:
        return 1.0
    threshold = TSMD_THRESHOLD_FRAC * tsmax
    if tsmd < threshold:
        return 1.0
    return max(0.2, 0.2 + 0.8 * (tsmax - tsmd) / (tsmax - threshold))


def compute_monthly_tsmd(
    monthly_precip_mm: list[float],
    monthly_etp_mm: list[float],
    cover_fracs: list[float],
    clay_pct: float,
) -> list[float]:
    """Compute monthly TSMD values from water balance."""
    tsmax = tsmd_max(clay_pct)
    tsmd_series: list[float] = []
    accumulated = 0.0

    for p_mm, etp_mm, cov_frac in zip(monthly_precip_mm, monthly_etp_mm, cover_fracs):
        etp_eff = etp_mm * (0.75 if cov_frac > 0.5 else 1.0)
        deficit = etp_eff - p_mm
        accumulated += deficit
        accumulated = max(0.0, min(tsmax, accumulated))
        tsmd_series.append(accumulated)

    return tsmd_series


# ── Pool initialization — Weihermüller 2013 (spec §4.4) ──────

def init_pools_weihermuller(
    soc_total_tC_ha: float, clay_pct: float
) -> PoolState:
    """Initialize RothC pools from SOC_total and clay_pct."""
    iom_tC_ha = 0.049 * (soc_total_tC_ha ** 1.139)
    rpm_tC_ha = (
        (0.1847 * soc_total_tC_ha + 0.1555)
        * ((clay_pct + 1.2750) ** (-0.1158))
    )
    hum_tC_ha = (
        (0.7148 * soc_total_tC_ha + 0.5069)
        * ((clay_pct + 0.3421) ** 0.0184)
    )
    bio_tC_ha = (
        (0.0140 * soc_total_tC_ha + 0.0075)
        * ((clay_pct + 8.8473) ** 0.0567)
    )
    dpm_tC_ha = soc_total_tC_ha - (rpm_tC_ha + hum_tC_ha + bio_tC_ha + iom_tC_ha)
    dpm_tC_ha = max(0.0, dpm_tC_ha)

    return PoolState(
        dpm_tC_ha=dpm_tC_ha,
        rpm_tC_ha=rpm_tC_ha,
        bio_tC_ha=bio_tC_ha,
        hum_tC_ha=hum_tC_ha,
        iom_tC_ha=iom_tC_ha,
    )


# ── Carbon inputs — per-source humification (spec §4.5) ──────────

def compute_c_inputs(monthly: MonthlyInputs) -> tuple[float, float, float]:
    """Compute total C inputs to DPM, RPM, and HUM pools for one month.

    Returns: (c_dpm_tC_ha, c_rpm_tC_ha, c_hum_direct_tC_ha)
    """
    sources = [
        ("aerea", monthly.c_input_aerea_tC_ha),
        ("raices", monthly.c_input_raices_tC_ha),
        ("exudados", monthly.c_input_exudados_tC_ha),
    ]

    c_dpm = 0.0
    c_rpm = 0.0

    for source_key, c_mass in sources:
        if c_mass <= 0:
            continue
        c_hum = c_mass * H_COEFFS[source_key]
        ratio_key = _ratio_key_for_source(source_key)
        ratio = DPM_RPM_RATIOS.get(ratio_key, 1.0)
        c_dpm += c_hum * ratio / (1.0 + ratio)
        c_rpm += c_hum * 1.0 / (1.0 + ratio)

    # Manure: fixed 49:49:2 split
    c_manure = monthly.c_input_enmienda_tC_ha * H_COEFFS["enmienda"]
    c_dpm += c_manure * MANURE_SPLIT["DPM"]
    c_rpm += c_manure * MANURE_SPLIT["RPM"]
    c_hum_direct = c_manure * MANURE_SPLIT["HUM"]

    return c_dpm, c_rpm, c_hum_direct


def _ratio_key_for_source(source_key: str) -> str:
    if source_key == "aerea":
        return "cultivo_anual"
    return source_key


# ── Monthly evolution (spec §4.7) ─────────────────────────────

def step_month(
    pools: PoolState, monthly: MonthlyInputs, tsmd: float,
) -> tuple[PoolState, float]:
    """Advance RothC pools by one month. Returns (new_pools, rh_tC_ha_month)."""
    tsmax = tsmd_max(monthly.clay_pct)
    at = a_temp(monthly.temp_celsius)
    bh = b_humedad(tsmd, tsmax)
    cc = C_COVER_VEGETATED if monthly.cover_present else C_COVER_BARE

    c_dpm_in, c_rpm_in, c_hum_in = compute_c_inputs(monthly)

    decay_factors = {}
    rh_total_tC_ha = 0.0
    new_pools = {}

    for pool_name in ["DPM", "RPM", "BIO", "HUM"]:
        k = POOL_K[pool_name]
        old_c = getattr(pools, f"{pool_name.lower()}_tC_ha")
        decay = math.exp(-k * at * bh * cc * DT_MONTH)
        decay_factors[pool_name] = decay
        remaining = old_c * decay
        lost = old_c - remaining
        rh_total_tC_ha += lost

        input_c = 0.0
        if pool_name == "DPM":
            input_c = c_dpm_in
        elif pool_name == "RPM":
            input_c = c_rpm_in
        elif pool_name == "HUM":
            input_c = c_hum_in

        new_pools[pool_name] = remaining + input_c

    new_pools["IOM"] = pools.iom_tC_ha  # inert, no decay

    new_state = PoolState(
        dpm_tC_ha=new_pools["DPM"],
        rpm_tC_ha=new_pools["RPM"],
        bio_tC_ha=new_pools["BIO"],
        hum_tC_ha=new_pools["HUM"],
        iom_tC_ha=new_pools["IOM"],
    )

    return new_state, rh_total_tC_ha


def run_rothc_monthly(
    initial_pools: PoolState,
    monthly_inputs: list[MonthlyInputs],
    clay_pct: float = 20.0,
) -> RothCResult:
    """Run RothC monthly simulation. Returns final pools + cumulative Rh."""
    # Pre-compute TSMD series
    precip = [m.precip_mm for m in monthly_inputs]
    etp = [m.etp_mm for m in monthly_inputs]
    covers = [m.cover_frac for m in monthly_inputs]
    tsmd_series = compute_monthly_tsmd(precip, etp, covers, clay_pct)

    pools = initial_pools
    total_rh_tC_ha = 0.0

    for i, monthly in enumerate(monthly_inputs):
        tsmd = tsmd_series[i]
        pools, rh_month = step_month(pools, monthly, tsmd)
        total_rh_tC_ha += rh_month

    soc_initial = initial_pools.total_tC_ha
    soc_final = pools.total_tC_ha
    n_years = len(monthly_inputs) / 12.0
    soc_delta_tC_ha_yr = (soc_final - soc_initial) / n_years if n_years > 0 else 0.0

    return RothCResult(
        pools=pools,
        rh_tC_ha_yr=total_rh_tC_ha / n_years if n_years > 0 else 0.0,
        soc_delta_tC_ha_yr=soc_delta_tC_ha_yr,
        monthly_tsmd=tsmd_series,
    )
```

- [ ] **Step 2: Write test file with key validations**

```python
# backend/tests/test_roth_c_model.py
import math

from app.services.roth_c_model import (
    a_temp,
    b_humedad,
    tsmd_max,
    compute_monthly_tsmd,
    init_pools_weihermuller,
    compute_c_inputs,
    step_month,
    run_rothc_monthly,
    PoolState,
    MonthlyInputs,
)


class TestATemp:
    def test_20c_about_0_6(self):
        """a_temp(20°C) should be ~0.6 (RothC documentation)."""
        result = a_temp(20.0)
        assert 0.5 < result < 0.7, f"Expected ~0.6, got {result}"

    def test_0c_is_low(self):
        result = a_temp(0.0)
        assert 0.0 < result < 0.1, f"Expected near 0, got {result}"

    def test_below_minus_18_clamped(self):
        assert a_temp(-20.0) == 0.0
        assert a_temp(-18.0) == 0.0

    def test_monotonic(self):
        """a_temp must be monotonically increasing."""
        vals = [a_temp(t) for t in [-10, 0, 10, 20, 30]]
        for i in range(len(vals) - 1):
            assert vals[i] <= vals[i + 1] + 1e-10


class TestTSMD:
    def test_tsmd_max_20pct_clay(self):
        """TSMD_max for 20% clay ≈ 42mm."""
        tsmax = tsmd_max(20.0)
        assert 40 < tsmax < 46

    def test_tsmd_monthly_accumulation(self):
        precip = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]
        etp = [80, 80, 80, 80, 80, 80, 80, 80, 80, 80, 80, 80]
        covers = [0.8] * 12
        tsmd = compute_monthly_tsmd(precip, etp, covers, 20.0)
        # With high ETP and low precip, TSMD should accumulate
        assert tsmd[-1] > tsmd[0]

    def test_b_humedad_no_stress(self):
        """When TSMD below threshold, b=1.0."""
        assert b_humedad(0.0, 100.0) == 1.0

    def test_b_humedad_full_stress(self):
        """When TSMD at max, b approaches 0.2."""
        tsmax = 100.0
        b = b_humedad(tsmax, tsmax)
        assert 0.19 < b < 0.25, f"Expected ~0.2, got {b}"


class TestWeihermuller:
    def test_pools_sum_to_total(self):
        pools = init_pools_weihermuller(soc_total_tC_ha=50.0, clay_pct=20.0)
        assert abs(pools.total_tC_ha - 50.0) < 0.01

    def test_iom_is_positive(self):
        pools = init_pools_weihermuller(soc_total_tC_ha=40.0, clay_pct=15.0)
        assert pools.iom_tC_ha > 0.0

    def test_hum_is_largest_pool(self):
        pools = init_pools_weihermuller(soc_total_tC_ha=50.0, clay_pct=20.0)
        assert pools.hum_tC_ha > pools.dpm_tC_ha
        assert pools.hum_tC_ha > pools.rpm_tC_ha
        assert pools.hum_tC_ha > pools.bio_tC_ha


class TestMonthlyEvolution:
    def test_one_month_no_input(self):
        pools = init_pools_weihermuller(soc_total_tC_ha=50.0, clay_pct=20.0)
        monthly = MonthlyInputs(
            temp_celsius=20.0,
            precip_mm=50.0,
            etp_mm=80.0,
            cover_present=True,
            clay_pct=20.0,
        )
        tsmd_val = 10.0
        new_pools, rh = step_month(pools, monthly, tsmd_val)
        # With no input, SOC should decrease slightly (respiration)
        assert new_pools.total_tC_ha <= pools.total_tC_ha + 1e-10
        assert rh > 0

    def test_one_month_with_high_input(self):
        pools = init_pools_weihermuller(soc_total_tC_ha=50.0, clay_pct=20.0)
        monthly = MonthlyInputs(
            temp_celsius=20.0,
            precip_mm=50.0,
            etp_mm=80.0,
            cover_present=True,
            c_input_aerea_tC_ha=1.0,
            c_input_raices_tC_ha=0.5,
            c_input_exudados_tC_ha=0.1,
            clay_pct=20.0,
        )
        tsmd_val = 10.0
        new_pools, rh = step_month(pools, monthly, tsmd_val)
        # With high input, DPM should increase
        assert new_pools.dpm_tC_ha > pools.dpm_tC_ha

    def test_run_rothc_12_months_conservation(self):
        """Mass conservation over 12 months."""
        initial_pools = init_pools_weihermuller(soc_total_tC_ha=50.0, clay_pct=20.0)
        total_input = 0.0
        monthly_inputs = []
        for m in range(12):
            mi = MonthlyInputs(
                temp_celsius=20.0,
                precip_mm=50.0,
                etp_mm=60.0,
                cover_present=True,
                c_input_aerea_tC_ha=0.3,
                c_input_raices_tC_ha=0.15,
                clay_pct=20.0,
            )
            total_input += 0.3 + 0.15
            monthly_inputs.append(mi)

        result = run_rothc_monthly(initial_pools, monthly_inputs, 20.0)
        delta_soc = result.pools.total_tC_ha - initial_pools.total_tC_ha
        rh_total = result.rh_tC_ha_yr  # this is for 1 year
        # Σin - Rh ≈ ΔSOC (monthly input already scaled)
        balance = total_input - rh_total - delta_soc
        assert abs(balance) < 0.2, (
            f"Mass balance: total_in={total_input:.4f}, rh={rh_total:.4f}, "
            f"delta_soc={delta_soc:.4f}, balance={balance:.4f}"
        )
```

- [ ] **Step 3: Run tests**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon/backend
pip install numpy  # or add to requirements
python -m pytest tests/test_roth_c_model.py -v
```

- [ ] **Step 4: Commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon
git add backend/app/services/roth_c_model.py backend/tests/test_roth_c_model.py
git commit -m "feat(carbon): add roth_c_model.py — RothC soil carbon model (Tier 2)"
```

---

## Phase 3: Tier 3 — GHG + NEE (Weeks 8-9)

### Task 3.1: Write ghg_model.py

**Files:**
- Create: `backend/app/services/ghg_model.py`
- Create: `backend/tests/test_ghg_model.py`

- [ ] **Step 1: Write ghg_model.py with AR6 GWP, N₂O IPCC 2019 full formula, NEE/NECB**

```python
# backend/app/services/ghg_model.py
"""Tier 3 GHG model — N₂O, CH₄, NEE/NECB (spec §5).

Stateless. Input: annual aggregated data. Output: GHG budget.
"""

from dataclasses import dataclass

from app.services.units import N_TO_N2O

# GWP100 — AR6 (spec §5.1)
GWP100_AR6 = {
    "N2O": 273,
    "CH4_non_fossil": 27,
    "CH4_fossil": 29.8,
}

# IPCC 2019 Refinement emission factors (spec §5.2)
EF1_TABLE = {
    ("humedo", "sintetico"): 0.016,
    ("humedo", "organico"): 0.006,
    ("seco", "sintetico"): 0.005,
    ("seco", "organico"): 0.005,
}

# IPCC 2019 indirect emission parameters
FRAC_GASF_SYNTHETIC = 0.10
FRAC_GASF_ORGANIC = 0.20
EF4 = 0.014  # N volatilized & re-deposited
EF5 = 0.011  # N leached/runoff
FRAC_LEACH = 0.30  # when precip > ETP


@dataclass
class N2OInputs:
    """Annual inputs for N₂O calculation."""
    n_applied_synthetic_kgN_ha_yr: float = 0.0
    n_applied_organic_kgN_ha_yr: float = 0.0
    precip_annual_mm: float = 500.0
    etp_annual_mm: float = 800.0
    irrigated: bool = False


@dataclass
class N2OResult:
    n2o_direct_kgN2O_ha_yr: float
    n2o_volat_kgN2O_ha_yr: float
    n2o_leach_kgN2O_ha_yr: float
    n2o_total_kgN2O_ha_yr: float
    n2o_co2eq_tCO2eq_ha_yr: float


def _regime(irrigated: bool, precip_mm: float) -> str:
    if irrigated or precip_mm > 1000:
        return "humedo"
    return "seco"


def _ef1(fertilizer_type: str, regime: str) -> float:
    return EF1_TABLE.get((regime, fertilizer_type), 0.005)


def compute_n2o(inputs: N2OInputs) -> N2OResult:
    """N₂O emissions — IPCC 2019 Refinement full formula (spec §5.2)."""
    regime = _regime(inputs.irrigated, inputs.precip_annual_mm)

    ef1_syn = _ef1("sintetico", regime)
    ef1_org = _ef1("organico", regime)

    n2o_direct_kgN2O_ha_yr = (
        inputs.n_applied_synthetic_kgN_ha_yr * ef1_syn
        + inputs.n_applied_organic_kgN_ha_yr * ef1_org
    ) * N_TO_N2O

    n_volat = (
        inputs.n_applied_synthetic_kgN_ha_yr * FRAC_GASF_SYNTHETIC
        + inputs.n_applied_organic_kgN_ha_yr * FRAC_GASF_ORGANIC
    )
    n2o_volat_kgN2O_ha_yr = n_volat * EF4 * N_TO_N2O

    frac_leach = FRAC_LEACH if inputs.precip_annual_mm > inputs.etp_annual_mm else 0.0
    n_leach = (
        inputs.n_applied_synthetic_kgN_ha_yr
        + inputs.n_applied_organic_kgN_ha_yr
    ) * frac_leach
    n2o_leach_kgN2O_ha_yr = n_leach * EF5 * N_TO_N2O

    n2o_total_kgN2O_ha_yr = (
        n2o_direct_kgN2O_ha_yr
        + n2o_volat_kgN2O_ha_yr
        + n2o_leach_kgN2O_ha_yr
    )

    n2o_co2eq_tCO2eq_ha_yr = n2o_total_kgN2O_ha_yr * GWP100_AR6["N2O"] / 1000.0

    return N2OResult(
        n2o_direct_kgN2O_ha_yr=n2o_direct_kgN2O_ha_yr,
        n2o_volat_kgN2O_ha_yr=n2o_volat_kgN2O_ha_yr,
        n2o_leach_kgN2O_ha_yr=n2o_leach_kgN2O_ha_yr,
        n2o_total_kgN2O_ha_yr=n2o_total_kgN2O_ha_yr,
        n2o_co2eq_tCO2eq_ha_yr=n2o_co2eq_tCO2eq_ha_yr,
    )


@dataclass
class NEEInputs:
    gpp_gC_m2_yr: float = 0.0
    npp_total_gC_m2_yr: float = 0.0
    rh_tC_ha_yr: float = 0.0
    c_exported_harvest_tC_ha_yr: float = 0.0
    c_amendments_imported_tC_ha_yr: float = 0.0


@dataclass
class NEEResult:
    ra_gC_m2_yr: float                     # autotrophic respiration
    rh_tC_ha_yr: float                     # heterotrophic respiration
    nee_tC_ha_yr: float                    # Net Ecosystem Exchange (negative = sink)
    necb_tC_ha_yr: float                   # Net Ecosystem Carbon Balance
    nee_co2_tCO2_ha_yr: float              # NEE in CO₂ units
    nee_co2eq_tCO2eq_ha_yr: float | None   # net CO₂eq including N₂O and CH₄


def compute_nee(inputs: NEEInputs) -> NEEResult:
    """Net Ecosystem Exchange (spec §5.3).

    NEE = -(NPP - Rh)  [negative = sink, sign convention]
    NECB = NEE - C_harvest_exported + C_amendments_imported
    """
    # Convert NPP from gC/m²/yr to tC/ha/yr for consistency
    npp_tC_ha_yr = inputs.npp_total_gC_m2_yr * 0.01
    gpp_tC_ha_yr = inputs.gpp_gC_m2_yr * 0.01

    ra_tC_ha_yr = gpp_tC_ha_yr - npp_tC_ha_yr

    nee_tC_ha_yr = -(npp_tC_ha_yr - inputs.rh_tC_ha_yr)

    necb_tC_ha_yr = (
        nee_tC_ha_yr
        - inputs.c_exported_harvest_tC_ha_yr
        + inputs.c_amendments_imported_tC_ha_yr
    )

    nee_co2_tCO2_ha_yr = nee_tC_ha_yr * (44.0 / 12.0)

    return NEEResult(
        ra_gC_m2_yr=ra_tC_ha_yr / 0.01,
        rh_tC_ha_yr=inputs.rh_tC_ha_yr,
        nee_tC_ha_yr=nee_tC_ha_yr,
        necb_tC_ha_yr=necb_tC_ha_yr,
        nee_co2_tCO2_ha_yr=nee_co2_tCO2_ha_yr,
        nee_co2eq_tCO2eq_ha_yr=None,
    )


def compute_co2eq_net(
    nee_tCO2_ha_yr: float,
    n2o_tCO2eq_ha_yr: float,
    ch4_tCO2eq_ha_yr: float = 0.0,
) -> float:
    """Net CO₂eq balance: sequestration minus GHG emissions.

    CO₂eq_net = NEE(CO₂) - N₂O(CO₂eq) - CH₄(CO₂eq)
    Negative = net sink to atmosphere.
    """
    return nee_tCO2_ha_yr - n2o_tCO2eq_ha_yr - ch4_tCO2eq_ha_yr
```

- [ ] **Step 2: Write tests**

```python
# backend/tests/test_ghg_model.py
from app.services.ghg_model import (
    N2OInputs,
    compute_n2o,
    NEEInputs,
    compute_nee,
    compute_co2eq_net,
    GWP100_AR6,
)


class TestGWP:
    def test_ar6_not_ar5(self):
        """Verify AR6 values, not AR5."""
        assert GWP100_AR6["N2O"] == 273  # AR5 was 298
        assert GWP100_AR6["CH4_non_fossil"] == 27  # AR5 was 34


class TestN2O:
    def test_dry_synthetic(self):
        result = compute_n2o(N2OInputs(
            n_applied_synthetic_kgN_ha_yr=100.0,
            precip_annual_mm=400.0,
            etp_annual_mm=500.0,
            irrigated=False,
        ))
        # N2O direct: 100 × 0.005 × 44/28 ≈ 0.786
        assert 0.5 < result.n2o_direct_kgN2O_ha_yr < 1.5
        # Indirect should add to total
        assert result.n2o_total_kgN2O_ha_yr > result.n2o_direct_kgN2O_ha_yr

    def test_humid_synthetic(self):
        result = compute_n2o(N2OInputs(
            n_applied_synthetic_kgN_ha_yr=100.0,
            precip_annual_mm=1200.0,
            etp_annual_mm=500.0,
            irrigated=False,
        ))
        # Humid EF1 should be higher
        assert result.n2o_direct_kgN2O_ha_yr > 1.0

    def test_no_input_is_zero(self):
        result = compute_n2o(N2OInputs())
        assert result.n2o_total_kgN2O_ha_yr == 0.0

    def test_co2eq_uses_ar6_gwp(self):
        result = compute_n2o(N2OInputs(
            n_applied_synthetic_kgN_ha_yr=100.0,
            precip_annual_mm=400.0,
            irrigated=False,
        ))
        expected_co2eq = result.n2o_total_kgN2O_ha_yr * 273 / 1000.0
        assert abs(result.n2o_co2eq_tCO2eq_ha_yr - expected_co2eq) < 0.01


class TestNEE:
    def test_negative_nee_is_sink(self):
        """When NPP > Rh, NEE is negative (carbon sink)."""
        result = compute_nee(NEEInputs(
            gpp_gC_m2_yr=1000.0,
            npp_total_gC_m2_yr=500.0,
            rh_tC_ha_yr=2.0,
        ))
        # npp_tC_ha_yr = 500 × 0.01 = 5.0
        # nee = -(5.0 - 2.0) = -3.0 tC/ha/yr (sink)
        assert result.nee_tC_ha_yr < 0

    def test_positive_nee_is_source(self):
        """When Rh > NPP, NEE is positive (carbon source)."""
        result = compute_nee(NEEInputs(
            gpp_gC_m2_yr=200.0,
            npp_total_gC_m2_yr=100.0,
            rh_tC_ha_yr=3.0,
        ))
        # npp_tC_ha_yr = 1.0, nee = -(1.0 - 3.0) = +2.0 (source)
        assert result.nee_tC_ha_yr > 0

    def test_necb_includes_harvest_and_amendments(self):
        result = compute_nee(NEEInputs(
            gpp_gC_m2_yr=1000.0,
            npp_total_gC_m2_yr=500.0,
            rh_tC_ha_yr=2.0,
            c_exported_harvest_tC_ha_yr=1.0,
            c_amendments_imported_tC_ha_yr=0.5,
        ))
        assert result.necb_tC_ha_yr == result.nee_tC_ha_yr - 1.0 + 0.5


class TestCO2eqNet:
    def test_sink_with_emissions(self):
        """A field sequestering 5 tCO2/ha/yr but emitting 0.5 tN2O-CO2eq has net 4.5."""
        net = compute_co2eq_net(
            nee_tCO2_ha_yr=-5.0,  # sink
            n2o_tCO2eq_ha_yr=0.5,
            ch4_tCO2eq_ha_yr=0.0,
        )
        assert net == -5.0 - 0.5 - 0.0
```

- [ ] **Step 3: Run tests and commit**

```bash
cd /home/g/Documents/nekazari/nkz-module-carbon/backend
python -m pytest tests/test_ghg_model.py -v
git add backend/app/services/ghg_model.py backend/tests/test_ghg_model.py
git commit -m "feat(carbon): add ghg_model.py — N₂O IPCC 2019, NEE/NECB (Tier 3)"
```

---

## Phase 4: Uncertainty Propagation (Week 10)

### Task 4.1: Write uncertainty.py

**Files:**
- Create: `backend/app/services/uncertainty.py`
- Create: `backend/tests/test_uncertainty.py`

Core functions:
- `gaussian_analytical_gpp()` — Tier 1 analytical propagation
- `latin_hypercube_sample()` — Tier 2 with 500 samples
- `monte_carlo_full()` — Tier 3 with 5000 samples (audit flag)
- `confidence_from_ci()` — CI→confidence score

### Task 4.2: Commit

```bash
git add backend/app/services/uncertainty.py backend/tests/test_uncertainty.py
git commit -m "feat(carbon): add uncertainty propagation (Gauss/LHS/MC)"
```

---

## Phase 5a: NGSI-LD Layer + REST API (Weeks 11-12)

### Task 5a.1: Write NGSI-LD client

**Files:** `backend/app/ngsild/client.py`, `backend/app/ngsild/entities.py`

Functions: `upsert_entity()`, `query_entities()`, `build_carbon_assessment()`, `build_carbon_stock()`

### Task 5a.2: Write Pydantic schemas

**Files:** `backend/app/models/schemas.py`, `backend/app/models/management.py`

### Task 5a.3: Write API endpoint files

**Files:** `backend/app/api/assessments.py`, `backend/app/api/management.py`, `backend/app/api/scenarios.py`, `backend/app/api/timeseries.py`, `backend/app/api/webhooks.py`

Mount all routers in `main.py`.

### Task 5a.4: Write DB migration and database.py

**Files:** `backend/app/db/database.py`, `backend/app/db/migrations/001_create_carbon_tables.sql`

### Task 5a.5: Commit

```bash
git add backend/app/ngsild/ backend/app/models/ backend/app/api/ backend/app/db/ backend/app/main.py
git commit -m "feat(carbon): NGSI-LD layer + REST API + DB schema (Phase 5a)"
```

---

## Phase 5b: MRV Reporter (Week 13)

### Task 5b.1: Write mrv_reporter.py

**Files:** `backend/app/services/mrv_reporter.py`, `backend/app/api/mrv.py`, `backend/tests/test_mrv_reporter.py`

Functions: `generate_vm0042_report()`, `generate_gold_standard_report()`, `hash_inputs()`, `anchor_calculation_run()`.

### Task 5b.2: Commit

```bash
git add backend/app/services/mrv_reporter.py backend/app/api/mrv.py backend/tests/test_mrv_reporter.py
git commit -m "feat(carbon): MRV Reporter — VM0042 + Gold Standard (Phase 5b)"
```

---

## Phase 6: Data Resolver + Platform Integration (Weeks 14-15)

### Task 6.1: Write data_resolver.py

**Files:** `backend/app/services/data_resolver.py`, `backend/tests/test_data_resolver.py`

### Task 6.2: Write bioorchestrator and crop_health clients

**Files:** `backend/app/platform/bioorchestrator_client.py`, `backend/app/platform/crop_health_client.py`

### Task 6.3: Integration smoke tests (2 days)

Manual E2E verification against each platform module endpoint.

### Task 6.4: Commit

```bash
git add backend/app/services/data_resolver.py backend/app/platform/
git commit -m "feat(carbon): data resolver + platform integration (Phase 6)"
```

---

## Phase 7: Frontend IIFE (Weeks 16-17)

### Task 7.1: Init frontend with @nekazari/module-builder

**Files:** `frontend/package.json`, `frontend/tsconfig.json`

### Task 7.2: Write i18n files — 6 locales

**Files:** `frontend/src/locales/{es,en,ca,eu,fr,pt}/carbon.json`

Minimum keys: `tier`, `confidence`, `gppDaily`, `nppDaily`, `co2Sequestered`, `soilCarbon`, `gaps`, `actions`, `management.*`, `mrv.*`, `error.*`

### Task 7.3: Write React components

**Files:** All files under `frontend/src/components/`

### Task 7.4: Write moduleEntry.ts and build

**Files:** `frontend/src/moduleEntry.ts`, `frontend/src/i18n.ts`

### Task 7.5: Build IIFE and upload to MinIO

```bash
cd frontend
npm run build:module
mc cp dist/nkz-module.js minio/nekazari-frontend/modules/carbon/nkz-module.js
```

### Task 7.6: Commit

```bash
git add frontend/
git commit -m "feat(carbon): frontend IIFE — 3 slots, 6 locales (Phase 7)"
```

---

## Phase 8: Historical Reconstructor (Weeks 18-20)

### Task 8.1: Create reconstructor sub-package

**Files:** `backend/app/reconstructor/` with `sigpac_connector.py`, `sentinel2_connector.py`, `era5_connector.py`, `spatial_aligner.py`, `temporal_harmonizer.py`, `cache_layer.py`, `spinup_driver.py`

### Task 8.2: Write cache layer

Redis L1 (24h TTL for current year) + S3/MinIO L2 (permanent for closed years).

### Task 8.3: Write onboarding pipeline

`onboard_parcela()` — target <30s, concurrent SIGPAC+SoilGrids→S2+ERA5→harmonize→spin-up.

### Task 8.4: Commit

```bash
git add backend/app/reconstructor/
git commit -m "feat(carbon): historical reconstructor (Phase 8)"
```

---

## Phase 9: Validation Suite (Weeks 21-22)

### Task 9.1: Rothamsted cross-check

**Files:** `backend/validation/rothamsted_broadbalk.py`

Run against public Rothamsted long-term experiment datasets. Tolerance: ±5% final SOC.

### Task 9.2: Cool Farm Tool cross-check

**Files:** `backend/validation/cool_farm_crosscheck.py`

5 scenarios. Tolerance: ±15% annual NEE.

### Task 9.3: Mass conservation and monotonicity tests

**Files:** `backend/validation/mass_conservation_test.py`

### Task 9.4: Commit

```bash
git add backend/validation/
git commit -m "test(carbon): validation suite — Rothamsted, Cool Farm, mass conservation (Phase 9)"
```

---

## Phase 10: Production Deploy (Week 23)

### Task 10.1: Build and push Docker image

```bash
cd backend
docker build --network=host --no-cache -t ghcr.io/nkz-os/nkz-module-carbon/carbon-backend:latest .
docker push ghcr.io/nkz-os/nkz-module-carbon/carbon-backend:latest
```

### Task 10.2: Apply K8s manifests (dry-run first)

```bash
kubectl apply -f k8s/ --dry-run=client
kubectl apply -f k8s/
```

### Task 10.3: Create ArgoCD app in nkz gitops

Add `nkz/gitops/modules/carbon.yaml` with source pointing to `nkz-os/nkz-module-carbon`, path `k8s`.

### Task 10.4: Register in marketplace (migration)

Create migration in `nkz` repo to insert into `admin_platform.marketplace_modules`.

### Task 10.5: Deploy frontend IIFE to MinIO

### Task 10.6: Final commit and tag

```bash
git tag v0.1.0
git push --tags
```

---

_Last updated: 2026-05-02_
