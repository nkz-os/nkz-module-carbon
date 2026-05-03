# Carbon Sequestration Methodology — Nekazari Carbon Module

> **Version:** 0.1.0 | **License:** AGPL-3.0 | **Standards:** Verra VM0042, Gold Standard SOC Framework

## 1. Overview

The Nekazari Carbon Module quantifies carbon sequestration in agricultural parcels using a three-tier approach of increasing precision. Each tier adds data sources and model complexity, reducing uncertainty while maintaining full traceability.

| Tier | Model | Precision | Minimum Data Required |
|------|-------|-----------|----------------------|
| 1 | LUE (Light Use Efficiency) | ±35–40% | Satellite vegetation index + weather |
| 2 | LUE + RothC soil carbon | ±20–25% | Tier 1 + soil type + crop phenology + management |
| 3 | Full GHG budget (N₂O, CH₄, NEE) | ±10–15% | Tier 2 + soil sensors + plant sensors + fertilization log |

The tier is selected **automatically** based on available data — the user never chooses a tier. Each calculation result includes a confidence score derived from the actual uncertainty distribution, never assigned a priori.

---

## 2. Tier 1 — Light Use Efficiency (LUE) Model

### 2.1 Spectral Index Selection

The vegetation index used depends on crop morphological type:

| Crop Type | Index | Formula |
|-----------|-------|---------|
| Herbaceous (cereals, annuals) | NDVI | (NIR − RED) / (NIR + RED) |
| Woody (olive, vine, fruit trees) | OSAVI (L=0.16) | (NIR − RED) / (NIR + RED + 0.16) |
| Universal fallback | MSAVI2 | (2·NIR + 1 − √((2·NIR+1)² − 8·(NIR−RED))) / 2 |

**Rationale:** NDVI saturates at high biomass (LAI > 3), common in dense olive canopies and forests. OSAVI reduces soil background reflectance — critical for woody crops with open canopies where bare soil between trees inflates NDVI. MSAVI2 provides a self-adjusting alternative when the soil adjustment factor L cannot be determined.

**Source:** Myneni & Williams (1994), Pôças et al. (2014), Qi et al. (1994)

### 2.2 Cloud Masking

Sentinel-2 Scene Classification Layer (SCL) masks classes 3 (cloud shadow), 8 (cloud medium probability), 9 (cloud high probability), 10 (cirrus), and 11 (snow). Linear temporal interpolation fills gaps between valid observations. Monthly composites require a minimum of 2 valid observations.

### 2.3 Fraction of Absorbed Photosynthetically Active Radiation (fAPAR)

```
fAPAR = clamp(a · VI + b, 0, 0.95)
```

| Crop Type | a | b | VI | Source |
|-----------|---|---|----|--------|
| C3 herbaceous | 1.24 | −0.168 | NDVI | Myneni & Williams (1994) |
| Olive | 1.40 | −0.240 | OSAVI | Pôças et al. (2014) |
| C4 species | requires calibration | — | — | No default applied |

Parameters sourced from BioOrchestrator `PhenologyParams` where available. If a species has no parametrization, the calculation degrades explicitly — a generic default is never assumed.

### 2.4 Photosynthetically Active Radiation (PAR)

**Priority order:**
1. Weather-worker API (`GET /api/weather/par?lat=&lon=&date=`)
2. Clear-sky calculation (FAO-56, Allen et al. 1998):

```
Ra       = extraterrestrial_solar_radiation(lat, DOY)     [MJ/m²/day]
Rs_clear = 0.75 · Ra                                       [MJ/m²/day]
PAR      = 0.48 · Rs_clear                                 [MJ/m²/day]
```

When the clear-sky fallback is used, the result is flagged `data_quality=synthetic_par` for full traceability. No generic constant is ever used.

### 2.5 Light Use Efficiency (LUE)

LUE is sourced from BioOrchestrator by photosynthetic type. If the species is not found, the calculation fails explicitly — a generic fallback is never applied.

| Photosynthetic Type | LUE Range [gC/MJ] | Example Crops |
|--------------------|-------------------|---------------|
| C3 temperate | 0.9–1.2 | Wheat, barley, olive |
| C3 tropical | 1.2–1.5 | Rice |
| C4 | 1.5–1.8 | Corn, sorghum, sugarcane |
| Olive (specific) | 0.8–1.0 | Olea europaea (Villalobos et al. 2006) |

### 2.6 Gross and Net Primary Production

```
GPP           = PAR × fAPAR × LUE                           [gC/m²/day]
NPP_total     = GPP × CUE                                   [gC/m²/day], CUE = 0.5
NPP_aerea     = NPP_total × (1 − root_fraction)             [gC/m²/day]
NPP_radicular = NPP_total × root_fraction                   [gC/m²/day]
```

`root_fraction` from BioOrchestrator. Defaults: cereals 0.20–0.25, young olive 0.30, adult olive 0.20, pasture 0.50–0.65.

### 2.7 Above- and Below-Ground Biomass

```
AGB_dry = (NPP_aerea / 0.45) × 0.01                        [tDM/ha/day]
BGB_dry = (NPP_radicular / 0.45) × 0.01                    [tDM/ha/day]
```

Where 0.45 is the carbon fraction of dry matter (gC/gDM) and 0.01 converts g/m² to t/ha.

### 2.8 CO₂ Sequestration (Gross Photosynthetic Sink)

```
CO₂_sequestered = NPP_total × 3.664 × 10                   [kgCO₂/ha/day]
```

Where 3.664 = 44/12 converts gC to gCO₂. **Important:** Tier 1 measures the gross photosynthetic sink and does NOT subtract soil heterotrophic respiration (Rh). This is why Tier 1 carries ±35–40% uncertainty — it converges to true Net Ecosystem Exchange only at Tiers 2–3 where Rh from the RothC model is included.

---

## 3. Tier 2 — RothC Soil Carbon Model

### 3.1 Model Description

RothC (Rothamsted Carbon Model, Jenkinson 1990) simulates soil organic carbon turnover in five conceptual pools. It is the reference model for Verra VM0042 and the Gold Standard SOC Framework.

### 3.2 Carbon Pools

| Pool | Symbol | k [yr⁻¹] | Mean Residence Time |
|------|--------|----------|-------------------|
| Decomposable Plant Material | DPM | 10.0 | 0.1 years |
| Resistant Plant Material | RPM | 0.30 | 3.3 years |
| Microbial Biomass | BIO | 0.66 | 1.5 years |
| Humified Organic Matter | HUM | 0.02 | 50 years |
| Inert Organic Matter | IOM | 0.0 | infinite |

### 3.3 Rate Modifiers

**Temperature modifier** (Jenkinson 1990, canonical):

```
a_temp = 47.91 / (1 + exp(106.06 / (T_celsius + 18.27)))
```

Clamped at T ≤ −18°C to prevent numerical singularity. The Q₁₀ = 2.0 simplification is explicitly rejected — RothC's rate-temperature relationship is not a simple exponential.

**Moisture modifier — Topsoil Moisture Deficit (TSMD):**

TSMD is computed from a monthly water balance using precipitation and potential evapotranspiration, modulated by vegetation cover (ETP reduced by 25% when cover fraction > 0.5). The maximum TSMD depends on clay content:

```
TSMD_max = 20.0 + 1.3 · clay_pct − 0.01 · clay_pct²
```

The moisture rate modifier is:

```
b = 1.0                              if TSMD < 0.444 · TSMD_max
b = 0.2 + 0.8 · (TSMD_max − TSMD)    otherwise
          / (TSMD_max − 0.444 · TSMD_max)
```

**Critical:** TSMD measures soil moisture deficit — it is NOT interchangeable with CWSI (Crop Water Stress Index). CWSI measures plant water stress via canopy temperature and is used exclusively by the crop-health module, never as a RothC soil modifier input.

**Vegetation cover modifier:**

```
c_cover = 0.6  if vegetation is actively growing
c_cover = 1.0  if bare fallow
```

Vegetation cover reduces decomposition rates by ~40% compared to bare soil (RothC original formulation).

### 3.4 Pool Initialization — Weihermüller et al. (2013)

Pool initialization avoids the need for a multi-century equilibrium spin-up by directly partitioning total SOC into RothC pools using pedotransfer functions:

```
IOM = 0.049 · SOC_total^1.139
RPM = (0.1847 · SOC_total + 0.1555) · (clay_pct + 1.2750)^(−0.1158)
HUM = (0.7148 · SOC_total + 0.5069) · (clay_pct + 0.3421)^0.0184
BIO = (0.0140 · SOC_total + 0.0075) · (clay_pct + 8.8473)^0.0567
DPM = SOC_total − (RPM + HUM + BIO + IOM)
```

### 3.5 SOC Data Provenance

SOC_total at project start (t=0) is sourced by priority:

1. Farmer soil laboratory analysis (Walkley-Black or dry combustion) — **mandatory for olive**
2. LUCAS Soil 2018 — if parcel < 5 km from sampling point AND same land use
3. MITECO 2021 SOC map — Spain only
4. SoilGrids 2.0 (250 m, ISRIC) — global fallback

The data provenance is recorded on every calculation for auditability.

### 3.6 Carbon Inputs to Soil

Inputs are partitioned by source with differential humification:

| Source | Humification Coefficient | DPM:RPM Ratio | Reference |
|--------|------------------------|---------------|-----------|
| Above-ground residues | 1.0 | 1.44 (59:41) | Jenkinson (1990) |
| Roots | 2.3 | 1.0 | Rasse et al. (2005), Kätterer et al. (2011) |
| Root exudates | 2.3 | 2.0 | Pausch & Kuzyakov (2018) |
| Organic amendments (composted manure) | 1.7 | 49:49:2* | — |

*Manure split is fixed 49% DPM, 49% RPM, 2% HUM (bypasses source ratio).

Root-derived carbon is 2.3× more recalcitrant than shoot-derived carbon because root tissues contain more lignin and suberin, and root-derived C is physically protected within soil aggregates.

Exudate fraction is assumed at 7% of NPP (Pausch & Kuzyakov 2018).

### 3.7 Monthly Evolution

```
For each pool in [DPM, RPM, BIO, HUM]:
    decay = exp(−k × a_temp(T) × b(TSMD) × c_cover × 1/12)
    C_pool(t+1) = C_pool(t) × decay + C_input_pool
IOM: no decay
```

---

## 4. Tier 3 — Full GHG Budget

### 4.1 Global Warming Potentials — IPCC AR6

| Gas | GWP100 (AR6) | AR5 Value (not used) |
|-----|-------------|---------------------|
| N₂O | 273 | 298 |
| CH₄ (non-fossil) | 27 | 34 |
| CH₄ (fossil) | 29.8 | — |

AR6 values are used because they reflect the latest scientific consensus on radiative forcing.

### 4.2 Nitrous Oxide (N₂O) — IPCC 2019 Refinement

**Direct emissions:**

```
N₂O_direct = N_applied × EF1 × 44/28                [kgN₂O/ha/yr]
```

EF1 depends on water regime and fertilizer type:

| Water Regime | Synthetic EF1 | Organic EF1 |
|-------------|-------------|------------|
| Humid / Irrigated (precip > 1000 mm/yr) | 0.016 | 0.006 |
| Dry | 0.005 | 0.005 |

**Indirect emissions:**

```
N₂O_volatilization = N_applied × FracGASF × EF4 × 44/28
N₂O_leaching       = N_applied × FracLEACH × EF5 × 44/28

N₂O_total = N₂O_direct + N₂O_volatilization + N₂O_leaching
```

Where:
- `FracGASF` = 0.10 (synthetic), 0.20 (organic) — IPCC 2019 Table 11.3
- `EF4` = 0.014 — N volatilized and re-deposited
- `FracLEACH` = 0.30 when annual precipitation exceeds ETP
- `EF5` = 0.011 — N leached/runoff

### 4.3 Net Ecosystem Exchange (NEE)

```
Ra  = GPP − NPP_total                                   [autotrophic respiration]
Rh  = Σ(decay_pool for each active RothC pool)          [heterotrophic respiration]
NEE = −(NPP_total − Rh)                                 [negative = carbon sink]
```

### 4.4 Net Ecosystem Carbon Balance (NECB)

```
NECB = NEE − C_harvest_exported + C_amendments_imported
```

### 4.5 Net CO₂-equivalent Balance

```
CO₂eq_net = NEE(CO₂) + N₂O(CO₂eq) + CH₄(CO₂eq)
```

Negative values indicate a net sink (more sequestration than emissions).

---

## 5. Uncertainty Quantification

### 5.1 Tier 1 — Gaussian Analytical Propagation

For the product GPP = PAR × fAPAR × LUE, the relative variance is:

```
(σ_GPP / GPP)² = (σ_PAR / PAR)² + (σ_fAPAR / fAPAR)² + (σ_LUE / LUE)²
```

### 5.2 Tier 2 — Latin Hypercube Sampling

500 stratified samples from the joint distribution of input parameters (SOC_total, clay_pct, monthly temperature, precipitation, C input rates). The RothC model is run for each sample set, producing a distribution of SOC_delta values.

### 5.3 Tier 3 — Full Monte Carlo

5000 random samples (audit flag only). Identical parameter space to Tier 2, with larger sample size for Verra verification-grade uncertainty bounds.

### 5.4 Confidence Score

```
confidence = 1 − (CI95_width / mean_estimate)
```

Confidence is always derived from the actual uncertainty distribution, never assigned a priori.

---

## 6. Historical Baseline Reconstruction

For VM0042, a 10-year pre-project baseline is required. The reconstructor module assembles this from:

1. **SIGPAC** (Spain): Annual land use declarations per agricultural parcel (recinto)
2. **Sentinel-2** (ESA/Copernicus): NDVI/LAI timeseries at 10 m resolution since June 2015
3. **ERA5-Land** (ECMWF/Copernicus): Hourly climate reanalysis at 9 km, aggregated to monthly
4. **CORINE Land Cover**: Land use change detection (forest ↔ agricultural) pre-2015

Data from multiple sources is harmonized to a common monthly timestep via spatial reprojection (EPSG:25830 for peninsular Spain) and temporal alignment with gap interpolation.

A RothC spin-up runs from t=−10 to t=0 using reconstructed inputs to establish the project baseline SOC state.

---

## 7. MRV Standards Compliance

### 7.1 Verra VM0042 — Improved Agricultural Land Management

The module generates VM0042-compliant reports including:

- **§5.5:** Baseline scenario with management parameters, input hashing (SHA-256), and calculation run anchoring
- **§8:** Project scenario with net emission reductions, 20% buffer pool deduction, and verified credit calculation
- **Additionality:** Regulatory surplus demonstrated via baseline/project comparison
- **Permanence:** 20-year SOC projection with RothC

### 7.2 Gold Standard — Soil Organic Carbon Framework

Gold Standard reports include all VM0042 elements plus SOC baseline measurement requirements and sustainable development contribution documentation.

---

## 8. Validation

The model has been validated against:

1. **Rothamsted Long-Term Experiments** (Broadbalk, Hoosfield): SOC trends over 150+ years of continuous wheat with different treatments. Directional validation: FYM > NPK > Control.
2. **Cool Farm Tool cross-check**: 5 Mediterranean scenarios (cereal dryland/irrigated, olive traditional/intensive, vineyard). All scenarios produce physically reasonable NEE ranges.
3. **Mass conservation**: Σ(C_inputs) − Σ(C_outputs) − ΔSOC = 0 ± 0.1% verified for 1–20 year simulations.
4. **Monotonicity**: Increasing organic amendments monotonically increase final SOC.

---

## 9. Key Scientific References

| Reference | Application |
|-----------|------------|
| Allen et al. (1998). FAO-56. | Clear-sky PAR, ETo calculation |
| IPCC (2019). 2019 Refinement to the 2006 IPCC Guidelines. Vol 4, Ch 11. | N₂O emission factors |
| IPCC (2021). AR6 WG1. Ch 7. | GWP100 values |
| Jenkinson, D.S. (1990). Phil. Trans. R. Soc. B. 329:361-369. | RothC model |
| Kätterer et al. (2011). Plant Soil. 338:261-272. | Root humification coefficient |
| Myneni & Williams (1994). Remote Sens. Environ. 49:200-211. | fAPAR-NDVI relationship |
| Pausch & Kuzyakov (2018). Soil Biol. Biochem. 116:250-261. | Exudate fraction of NPP |
| Pôças et al. (2014). Agric. Water Manage. 142:15-27. | Olive fAPAR-OSAVI relationship |
| Rasse et al. (2005). Plant Soil. 269:341-356. | Root vs shoot decomposition |
| Villalobos et al. (2006). Eur. J. Agron. 24:282-291. | Olive LUE values |
| Weihermüller et al. (2013). Eur. J. Soil Sci. 64:570-585. | RothC pool initialization |

---

*Last updated: 2026-05-03*
