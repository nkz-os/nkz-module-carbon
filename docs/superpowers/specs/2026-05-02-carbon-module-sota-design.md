# NKZ-Module-Carbon — SOTA Design v2.1

> Design document consolidating multi-agent review. Engine formulas, constants, and methods derived from IPCC AR6, Verra VM0042, RothC (Jenkinson 1990), Weihermüller et al. 2013, and peer-reviewed literature.

## 0. Unit Naming Convention

**Mandatory contract.** All variable names MUST encode their unit. Ambiguity caused the AGB `× 0.01` vs `÷ 1000` debate — the factor changes with unit but both were correct for their respective units. Explicit naming eliminates this class of bug.

### 0.1 Canonical units and suffixes

| Dimension | Unit | Suffix | Example |
|-----------|------|--------|---------|
| Carbon flux (area) | gC/m²/day | `_gC_m2_day` | `gpp_gC_m2_day` |
| Carbon flux (area) | tC/ha/yr | `_tC_ha_yr` | `soc_delta_tC_ha_yr` |
| Carbon stock | tC/ha | `_tC_ha` | `dpm_pool_tC_ha` |
| Carbon stock | kgC/m² | `_kgC_m2` | `agb_kgC_m2` |
| Biomass dry matter | tDM/ha | `_tDM_ha` | `agb_dry_tDM_ha` |
| Biomass dry matter | kgDM/m² | `_kgDM_m2` | `agb_dry_kgDM_m2` |
| CO₂ flux | kgCO₂/ha/day | `_kgCO2_ha_day` | `co2_seq_kgCO2_ha_day` |
| CO₂ cumulative | tCO₂/ha | `_tCO2_ha` | `co2_cum_tCO2_ha` |
| CO₂eq (GHG) | tCO₂eq/ha | `_tCO2eq_ha` | `co2eq_net_tCO2eq_ha` |
| N₂O flux | kgN₂O/ha/day | `_kgN2O_ha_day` | `n2o_flux_kgN2O_ha_day` |
| CH₄ flux | kgCH₄/ha/day | `_kgCH4_ha_day` | `ch4_flux_kgCH4_ha_day` |
| Energy (PAR) | MJ/m²/day | `_MJ_m2_day` | `par_MJ_m2_day` |
| Fraction | 0.0–1.0 | `_frac` | `fapar_frac`, `root_frac` |
| Percentage | 0–100 | `_pct` | `clay_pct`, `confidence_pct` |

### 0.2 Conversion factors (module-wide constants)

```python
# units.py — single source of truth for all conversions
C_TO_CO2    = 3.6667     # gCO2 per gC (44/12)
C_IN_DM     = 0.45       # gC per g dry matter
G_PER_M2_TO_T_PER_HA = 0.01  # (g/m²) × 0.01 = t/ha
KG_TO_T     = 0.001
HA_PER_M2   = 0.0001
G_TO_KG     = 0.001
N_TO_N2O    = 44.0 / 28.0  # N → N₂O mass conversion
```

### 0.3 Naming enforcement

Every function that returns a numeric value with physical units MUST either:
- Encode the unit in the variable name (e.g., `gpp_gC_m2_day`), OR
- Return a typed dataclass with unit-annotated fields

Linter rule: bare names like `gpp`, `npp`, `agb` without unit suffix are REJECTED in code review.

## 1. Architecture

### 1.1 Module as orchestrator — consumes platform, owns calculation

```
┌──────────────────────────────────────────────────────────────┐
│                   NKZ-MODULE-CARBON                           │
│                                                              │
│  Data Resolver ──▶ Carbon Engine ──▶ MRV Reporter            │
│       │                  │                  │                │
│       ▼                  ▼                  ▼                │
│  Orion-LD (reads VegetationIndex, CropHealthAssessment)      │
│  Orion-LD (writes CarbonAssessment, CarbonStock, Scenarios)  │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌──────────────┬──────────────┬──────────────┬───────────────┐
  │ veg-prime    │ bio-orch.    │ crop-health  │ weather-worker │
  │ NDVI,LAI,    │ pheno,kc,    │ CWSI,MDS,    │ PAR,ETo,T,     │
  │ OSAVI,fAPAR  │ LUE,root_fr  │ deficit      │ precip         │
  └──────────────┴──────────────┴──────────────┴───────────────┘
```

### 1.2 Module boundaries — what carbon OWNS vs CONSUMES

| Owns (implements) | Consumes (platform) |
|-------------------|---------------------|
| carbon_engine.py (LUE, RothC, GHG) | vegetation-prime: indices, rasters |
| data_resolver.py (tier selection) | bioorchestrator: phenology, crop params |
| mrv_reporter.py (VM0042, Gold Standard) | crop-health: water stress, vigor |
| roth_c_model.py (SOC pools) | weather-worker: PAR, ETo, T, precip |
| historical_reconstructor/ | datahub: timeseries visualization |
| CarbonAssessment, CarbonStock (Orion-LD) | timeseries-reader: historical data |
| carbon_calculations (PostgreSQL audit log) | telemetry-worker: Orion→Timescale persistence |
| React IIFE frontend (3 slots, 6 locales) | |

### 1.3 Engine — stateless, versioned

Input: arrays of management data (baseline, project)
Output: {baseline_NEE, project_NEE, delta_NEE, uncertainty}
No DB writes. No knowledge of "scenarios." Versioned via `engine_version` in audit log.

## 2. Spectral Index Selection (pre-Tier 1)

### 2.1 Index by crop morphological type

| Type | Index | Formula |
|------|-------|---------|
| Herbaceous (wheat, corn, sunflower, vegetables) | NDVI | `(NIR-RED)/(NIR+RED)` |
| Woody (olive, almond, vine, fruit trees) | OSAVI L=0.16 | `(NIR-RED)/(NIR+RED+0.16)` |
| Universal fallback | MSAVI2 | `(2·NIR+1 - sqrt((2·NIR+1)^2 - 8·(NIR-RED))) / 2` |

Morphological type sourced from bioorchestrator `PhenologyParams.morphological_type`.

### 2.2 Olive pixel unmixing (opt-in)

If SIGPAC planting frame available AND species is woody:
- 3 endmembers: canopy, soil, shadow
- Linear unmixing on Sentinel-2 bands
- OSAVI computed on canopy fraction only

If no planting frame: OSAVI on full pixel, flag `data_quality=pixel_unmixed_false`.

### 2.3 Cloud masking

SCL band classes masked: 3 (cloud shadow), 8 (cloud medium prob), 9 (cloud high prob), 10 (cirrus), 11 (snow).
Linear temporal interpolation between valid observations.
Minimum 2 valid observations/month for compositing.

## 3. Tier 1 — LUE + IPCC Tier 1

### 3.1 fAPAR — parametrizable by species

```
fAPAR = clamp(a · VI + b, 0, 0.95)
```

Parameters from bioorchestrator `fAPAR_a`, `fAPAR_b`, `fAPAR_VI_type`. Validated defaults:

| Crop type | a | b | VI | Source |
|-----------|---|---|----|--------|
| C3 herbaceous | 1.24 | -0.168 | NDVI | Myneni & Williams 1994 |
| Olive | 1.40 | -0.240 | OSAVI | Pôças et al. 2014 |
| C4 | requires calibration | — | — | No default; degrade if missing |

If species not in bioorchestrator → fail explicitly, do not assume generic.

### 3.2 LUE — by photosynthetic type

| Type | LUE range [gC/MJ] | Example crops |
|------|-------------------|---------------|
| C3 temperate | 0.9–1.2 | wheat, barley, olive |
| C3 tropical | 1.2–1.5 | rice |
| C4 | 1.5–1.8 | corn, sorghum, sugarcane |
| Olive (Villalobos 2006) | 0.8–1.0 | olive specific |

From bioorchestrator `LUE` field. If species unresolved → fail, do not assume.

### 3.3 PAR — clear-sky fallback (no generic constant)

Priority: 1) weather-worker API → 2) clear-sky calculation (FAO-56):

```
Ra       = extraterrestrial_solar(lat, DOY)      # MJ/m²/day
Rs_clear = 0.75 · Ra                              # clear-sky global radiation
PAR      = 0.48 · Rs_clear                        # PAR fraction
```

Mark result `data_quality=synthetic_par` for traceability.

### 3.4 GPP → NPP → Biomass

```
GPP           = PAR × fAPAR × LUE                         # gC/m²/day
NPP_total     = GPP × CUE                                 # CUE = 0.5, gC/m²/day
NPP_aerea     = NPP_total × (1 − root_fraction)           # gC/m²/day
NPP_radicular = NPP_total × root_fraction                 # gC/m²/day

AGB_dry_t_ha = (NPP_aerea / 0.45) × 0.01                 # tDM/ha/day
BGB_dry_t_ha = (NPP_radicular / 0.45) × 0.01             # tDM/ha/day
```

Unit: tDM/ha/day (standard in agronomy and VM0042 reporting).

`root_fraction` from bioorchestrator. Defaults:
- Cereals: 0.20–0.25
- Young olive: 0.30, adult olive: 0.20
- Pasture: 0.50–0.65

Seasonal accumulation via GDD-based aggregation.

### 3.5 CO₂ sequestration

```
CO2_seq_kgCO2_ha_day = NPP_total_gC_m2_day × 3.664 × 10    # kgCO2/ha/day
CO2_cum_tCO2_ha      = Σ(CO2_seq_kgCO2_ha_day) / 1000       # tCO2/ha cumulative
```

**Important:** Tier 1 CO₂ sequestration uses NPP only and does NOT subtract soil heterotrophic respiration (Rh). This is why Tier 1 carries ±35–40% uncertainty — it measures gross photosynthetic sink, not net ecosystem exchange. Tiers 2–3 include Rh from RothC, converging toward true NEE. Auditors should be made aware of this conceptual difference between tiers.

Precision: ±35–40%.

## 4. Tier 2 — LUE + RothC Soil Carbon

### 4.1 Pools and rate constants (Jenkinson 1990)

| Pool | k [yr⁻¹] | Label |
|------|----------|-------|
| DPM | 10.0 | Decomposable Plant Material |
| RPM | 0.30 | Resistant Plant Material |
| BIO | 0.66 | Microbial Biomass |
| HUM | 0.02 | Humified Organic Matter |
| IOM | 0.0 | Inert Organic Matter |

### 4.2 Temperature modifier (RothC canonical)

```
def a_temp(T_celsius):
    if T_celsius <= -18.0:
        return 0.0
    return 47.91 / (1 + math.exp(106.06 / (T_celsius + 18.27)))
```

Clamp at T ≤ -18°C prevents numerical singularity (denominator → ∞ near T = -18.27°C). Not relevant for Iberia but required for validation against Rothamsted (UK winter months).

Do NOT use Q10=2.0 simplification.

### 4.3 Moisture modifier — TSMD, not CWSI

Monthly Topsoil Moisture Deficit from water balance:

```
ETP_efectiva  = ETP_mm × (0.75 if cover_frac > 0.5 else 1.0)
deficit_month = ETP_efectiva − P_mm
TSMD          = clamp_accumulated(deficit_month, 0, TSMD_max(clay_pct))

b_humedad(TSMD, TSMD_max):
    if TSMD < 0.444 × TSMD_max: return 1.0
    else: return 0.2 + 0.8 × (TSMD_max − TSMD) / (TSMD_max − 0.444 × TSMD_max)
```

CWSI remains exclusive to crop-health (plant stress), never as soil modifier input.

### 4.4 Pool initialization — Weihermüller et al. 2013

No equilibrium spin-up required. Direct partitioning from SOC_total + clay_pct:

```
IOM = 0.049 × SOC_total^1.139
RPM = (0.1847 × SOC_total + 0.1555) × (clay_pct + 1.2750)^(−0.1158)
HUM = (0.7148 × SOC_total + 0.5069) × (clay_pct + 0.3421)^0.0184
BIO = (0.0140 × SOC_total + 0.0075) × (clay_pct + 8.8473)^0.0567
DPM = SOC_total − (RPM + HUM + BIO + IOM)
```

### 4.5 Carbon inputs — differential humification

Each input source has its own humification coefficient and DPM/RPM ratio. Inputs are processed **per source**, then summed:

```
C_total_humified = 0
C_DPM_total = 0
C_RPM_total = 0

for source_i in [aerea, raices, exudados, enmienda]:
    C_humified_i = C_input[source_i] × h[source_i]
    ratio_i      = DPM_RPM_RATIOS[source_i]
    C_DPM[source_i] = C_humified_i × ratio_i / (1 + ratio_i)
    C_RPM[source_i] = C_humified_i × 1.0   / (1 + ratio_i)

C_DPM_total = Σ C_DPM[source_i]
C_RPM_total = Σ C_RPM[source_i]
```

**Per-source C inputs:**
- `C_input[aerea]` = AGB_residues × frac_residues_not_removed
- `C_input[raices]` = BGB_annual
- `C_input[exudados]` = NPP_total × frac_exudates
- `C_input[enmienda]` = organic_amendments

**Humification coefficients (h):**
- `h_aerea` = 1.0 (reference)
- `h_root` = 2.3 (Rasse et al. 2005, Kätterer et al. 2011)
- `h_exudates` = 2.3 (assume ≈ roots)
- `h_amendment` = 1.7 (composted manure)
- `frac_exudates` = 0.07 (Pausch & Kuzyakov 2018)

**Manure special case:** manure split is fixed 49:49:2 (DPM:RPM:HUM), not via DPM_RPM_RATIOS. HUM fraction goes directly to HUM pool, bypassing the ratio.

### 4.6 DPM/RPM split by input type

| Input type | DPM:RPM ratio |
|------------|---------------|
| Annual crop | 1.44 (59:41) |
| Improved pasture | 1.44 |
| Natural pasture | 0.67 |
| Forestry | 0.25 |
| Roots | 1.0 |
| Exudates | 2.0 |

### 4.7 Monthly evolution

```
For each pool in [DPM, RPM, BIO, HUM]:
    decay = exp(−k × a_temp(T) × b_humedad(TSMD) × c_cover × dt)
    C[pool] = C[pool] × decay + C_input[pool]
IOM: no decay
```

`dt = 1/12` year.

`c_cover` — vegetation cover modifier (RothC original):

```
c_cover = 0.6 if vegetation_present_in_month else 1.0
```

Vegetation present = a crop is actively growing (from bioorchestrator phenological stage) OR permanent cover crop is declared. Bare fallow months use 1.0 (faster decomposition).

Precision: ±20–25%.

## 5. Tier 3 — Multi-sensor with daily dynamics

### 5.1 GWP — AR6 (not AR5)

| Gas | GWP100 |
|-----|--------|
| N₂O | 273 |
| CH₄ (non-fossil) | 27 |
| CH₄ (fossil) | 29.8 |

### 5.2 N₂O emissions — IPCC 2019 Refinement full formula

**Direct emissions:**

```
N2O_direct_kgN2O_ha_yr = N_applied_kgN_ha_yr × EF1
```

EF1 by water regime and fertilizer type:

| Regime | Synthetic EF1 | Organic EF1 |
|--------|-------------|------------|
| Humid/irrigated (precip > 1000 mm/yr) | 0.016 | 0.006 |
| Dry | 0.005 | 0.005 |

**Indirect emissions (mandatory for VM0042):**

```
N2O_volat_kgN2O_ha_yr  = N_applied_kgN_ha_yr × FracGASF × EF4
N2O_leach_kgN2O_ha_yr  = N_applied_kgN_ha_yr × FracLEACH × EF5

N2O_total_kgN2O_ha_yr  = (N2O_direct + N2O_volat + N2O_leach) × 44/28
```

Where:
- `FracGASF` = 0.10 (synthetic fertilizer), 0.20 (organic fertilizer) — IPCC 2019 Table 11.3
- `EF4` = 0.014 (N volatilized & re-deposited) — IPCC 2019 Table 11.3
- `FracLEACH` = 0.30 if precip > ETP in reporting period — IPCC 2019 §11.4.2
- `EF5` = 0.011 (N leached/runoff) — IPCC 2019 Table 11.3
- `44/28` = N → N₂O mass conversion

### 5.3 NEE explicit

```
Ra  = GPP − NPP_total                                # autotrophic respiration
Rh  = Σ(decay_pool for pool in [DPM,RPM,BIO,HUM])    # heterotrophic soil respiration
NEE = −(NPP_total − Rh)                              # negative = sink (convention)
NECB = NEE − C_exported_harvest + C_amendments_imported
```

Precision: ±10–15%.

## 6. Uncertainty Propagation

### 6.1 Method by tier

| Tier | Method | Samples | When |
|------|--------|---------|------|
| 1 | Gaussian analytical | — | Every calculation |
| 2 | Latin Hypercube | 500 | Every calculation (cached per parcel) |
| 3 | Monte Carlo full | 5000 | Audit flag only |

### 6.2 Tier 1 — analytical

```
σ²(GPP) = (σ_PAR × fAPAR × LUE)² + (PAR × σ_fAPAR × LUE)² + (PAR × fAPAR × σ_LUE)²
(σ_GPP / GPP)² ≈ (σ_PAR / PAR)² + (σ_fAPAR / fAPAR)² + (σ_LUE / LUE)²
```

### 6.3 Confidence from calculated uncertainty

```
confidence = 1 − (CI95_width / mean_estimate)
```

Never assign a priori (0.60/0.78/0.90). Derive from actual uncertainty distribution.

## 7. NGSI-LD Entity Model (source of truth)

### 7.1 CarbonAssessment

```
urn:ngsi-ld:CarbonAssessment:{tenant}:{parcel_id}-{YYYYMMDD}
```

| Attribute | Type | Unit |
|-----------|------|------|
| refAgriParcel | Relationship | — |
| refVegetationIndex | Relationship | — |
| assessmentDate | Property | ISO date |
| gppDaily, nppDaily | Property | gC/m²/day |
| co2SequesteredDaily | Property | kgCO2/ha/day |
| co2SequesteredCumulative | Property | tCO2/ha |
| agbDry, bgbDry | Property | tDM/ha |
| soilCarbonDelta | Property | tC/ha/yr |
| carbonStockTotal | Property | tC/ha |
| dataTier | Property | 1,2,3 |
| confidence | Property | 0.0–1.0 |
| confidenceIntervalPct | Property | ±% |
| methaneFlux, n2oFlux | Property | kg/ha/day |
| co2eqNetDaily | Property | kgCO2eq/ha/day |
| co2eqNetCumulative | Property | tCO2eq/ha |
| gwpStandard | Property | "AR6" |
| dataSources | Property | JSON array |
| methodology | Property | string |
| missingForNextTier | Property | JSON array |
| source | Property | "carbon" |

### 7.2 CarbonStock

```
urn:ngsi-ld:CarbonStock:{tenant}:{parcel_id}
```

| Attribute | Unit |
|-----------|------|
| refAgriParcel | Relationship |
| dpmPool, rpmPool, bioPool, humPool, iomPool | tC/ha |
| totalSOC | tC/ha |
| lastUpdated | ISO datetime |

### 7.3 BaselineScenario / ProjectScenario / CarbonCalculationRun

Mandatory for VM0042 §5.5 and §8 audit trail:

```
BaselineScenario {
    id, validFrom, validTo, inputsHash,
    managementParameters[], calculationRunId
}
ProjectScenario {
    id, validFrom, validTo, inputsHash,
    managementParameters[], calculationRunId,
    baselineRef → BaselineScenario.id
}
CarbonCalculationRun {
    id, timestamp, engineVersion, tier, confidence,
    inputsSnapshot, outputs, uncertaintyDistribution
}
```

## 8. SOC Initialization Protocol

Priority order for SOC_total at t=0:

1. Farmer soil lab analysis (Walkley-Black or dry combustion)
2. LUCAS Soil 2018 if parcel <5km from point AND same land use
3. MITECO 2021 SOC map (Spain only)
4. SoilGrids 2.0 (250m, ISRIC) — fallback
5. **Olive: mandatory t=0 sampling, no fallback acceptable**

   **Engine behavior when missing:**
   - **Tier 1**: allowed. Tier 1 does not use SOC data.
   - **Tier 2 and above**: BLOCKED. API returns HTTP 422 with error code `OLIVE_SOC_REQUIRED` and human-readable explanation (i18n key `carbon.error.olive_soc_required`). The `/tier-info` endpoint lists this as a blocking gap.
   - Rationale: olive is a high-value permanent crop for carbon markets (long crediting period, high SOC potential). Verra auditors will reject Tier 2+ estimates without baseline soil analysis. Unlike annual crops where SoilGrids can be defended for Tier 2, olive's permanence and market value demand measured SOC.

Mark `soc_data_provenance` on each parcel.

## 9. API Contract

```
/api/carbon
├── GET  /health
├── GET  /parcels/{entity_id}/assessment
├── GET  /parcels/{entity_id}/assessment/history
├── POST /parcels/{entity_id}/calculate
├── GET  /parcels/{entity_id}/tier-info
├── POST /parcels/{entity_id}/management
├── GET  /parcels/{entity_id}/mrv/report
├── GET  /parcels/{entity_id}/projection
│
├── POST /parcels/{entity_id}/scenarios/baseline
├── POST /parcels/{entity_id}/scenarios/project
├── GET  /parcels/{entity_id}/scenarios
├── GET  /parcels/{entity_id}/scenarios/{scenario_id}
├── GET  /parcels/{entity_id}/scenarios/{scenario_id}/calculation-runs
├── POST /parcels/{entity_id}/scenarios/{scenario_id}/recalculate
│
├── GET  /timeseries/entities/{entity_id}/data          (Arrow IPC)
├── POST /api/internal/timeseries/export-arrow           (DataHub multi-series)
└── POST /webhooks/vegetation-index-updated
```

## 10. Frontend IIFE

### 10.1 Slots

| Slot | Component | Content |
|------|-----------|---------|
| context-panel | CarbonContextPanel | Tier, confidence, key metrics, gaps |
| dashboard-widget | CarbonDashboardWidget | KPI cards, sparkline |
| bottom-panel | CarbonBottomPanel | uPlot charts, projection, MRV export, management form |

### 10.2 i18n — 6 mandatory locales

`es`, `en`, `ca`, `eu`, `fr`, `pt` under namespace `carbon`.

Using shared SDK i18n: `import { useTranslation } from '@nekazari/sdk'`.

### 10.3 UX principles

- User never chooses tier — sees result and what's missing for next tier
- Traffic-light indicators for data gaps
- Smart defaults from bioorchestrator to minimize manual input
- Interactive projection slider: "what if I switch to no-till?" → live SOC update

## 11. Historical Reconstructor (sub-module, Phase 8)

### 11.1 Architecture layers

```
SIGPAC Connector ──┐
S2 Connector ──────┤
ERA5 Connector ────┘
        │
   Spatial Aligner (EPSG:25830)
        │
   Temporal Harmonizer (monthly)
        │
   Cache Layer (Redis L1 + S3/MinIO L2)
        │
   RothC Spin-up Driver
```

### 11.2 Data sources

- **SIGPAC**: WMS/WFS nacional + APIs autonómicas (Andalucía, Navarra, Cataluña). Use autonómica first, nacional fallback.
- **Sentinel-2**: CDSE STAC + Sentinel Hub. Process on-demand with `sentinelhub-py`, avoid downloading full tiles.
- **ERA5-Land**: ARCO-ERA5 Zarr mirror on GCP (sub-2s latency for 10yr single-pixel queries).
- **Landsat**: Deferred to V2. S2 (2015+) covers 10-yr pre-project in 2026.
- **CORINE Land Cover** (CLC 1990, 2000, 2006, 2012, 2018): detect land use transitions (forest↔agricultural) pre-2015. Essential for additionality assessment when baseline period extends beyond Sentinel-2 coverage. If a parcel shows CLC transition (e.g., forest→olive grove between 2006-2012), flag for auditor review and elevate SOC initialization uncertainty. Access via Copernicus Land Monitoring Service WMS.

### 11.3 Spin-up protocol

1. SOC_total(t=-10) ≈ SOC_total(t=0) if no documented land use change
2. Pool partitioning: Weihermüller 2013
3. Run monthly RothC t=-10 to t=0 with reconstructed inputs
4. State at t=0 = project initial state
5. If soil analyses at t=-5 or t=0 exist, calibrate h_* coefficients via Bayesian residual minimization

## 12. Validation Tests

Before production, the engine MUST pass:

1. **Rothamsted Long-Term Experiments** (Broadbalk, Hoosfield) — SOC trend over 150 years. Tolerance: ±5% final SOC.
2. **Cool Farm Tool cross-check** — 5 typical scenarios (cereal dryland, cereal irrigated, traditional olive, super-intensive olive, vineyard). Tolerance: ±15% annual NEE.
3. **Mass conservation**: Σ(C_inputs) − Σ(C_outputs) − ΔSOC = 0 ± 0.1%.
4. **Monotonicity**: increasing organic amendments must monotonically increase final SOC.

## 13. Implementation Phases

| Phase | Weeks | Content |
|-------|-------|---------|
| 0 | 1 | Repo init (git, GitHub, CI), Dockerfile, K8s manifests, requirements.txt |
| 1 | 2–4 | Carbon Engine v2 — Tier 1 corrections (§2–3): OSAVI, fAPAR params, LUE, PAR clear-sky, AGB fix |
| 2 | 5–7 | RothC — Tier 2 (§4): pools, a_temp, TSMD, Weihermüller, differential humification |
| 3 | 8–9 | Tier 3 (§5): AR6, N₂O disaggregated, NEE/NECB |
| 4 | 10 | Uncertainty (§6): Gaussian, LHS 500, MC optional |
| 5a | 11–12 | NGSI-LD layer (§7) + REST API (§9, including scenario CRUD) |
| 5b | 13 | MRV Reporter — VM0042 structured report, input hashing, calculation run anchoring, Gold Standard template |
| 6 | 14–15 | Data Resolver + integration with vegetation-prime, bioorchestrator, crop-health, weather-worker |
| 6b | — | **Integration checkpoint:** smoke tests E2E against each platform module (2 days at end of phase 6) |
| 7 | 16–17 | Frontend IIFE (§10): 3 slots, 6 locales, zero-friction UX |
| 8 | 18–20 | Historical Reconstructor (§11): SIGPAC, S2 archive, ERA5-Land, spatial/temporal alignment, cache, spin-up |
| 9 | 21–22 | Validation (§12): Rothamsted, Cool Farm Tool, mass conservation, monotonicity |
| 10 | 23 | Production deploy: ArgoCD, marketplace registration, documentation |

## 14. Module Dependencies (manifest.json)

```json
{
  "dependencies": {
    "modules": ["vegetation-prime"],
    "platform_services": ["orion-ld", "postgresql", "weather-worker", "bioorchestrator", "crop-health"]
  }
}
```

## 15. Platform Changes Required

| Module | Change | Effort |
|--------|--------|--------|
| vegetation-prime | Add OSAVI to VegetationIndexProcessor | ~30 LOC |
| bioorchestrator | Add fAPAR_a, fAPAR_b, fAPAR_VI_type, LUE, root_fraction, photosynthetic_type, morphological_type to PhenologyParams | ~50 LOC + curated data |
| crop-health | None required | 0 |
| weather-worker | None required | 0 |

---

_Last updated: 2026-05-02_
