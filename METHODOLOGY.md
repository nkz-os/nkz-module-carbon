# Carbon Balance Methodology — Nekazari Carbon Module

> **Version:** 0.2.0 (engine 3.0.0) | **License:** AGPL-3.0 | **Report type:** monitoring estimate, not certified

## 1. Overview

The module computes, for each parcel and **campaign** (1 January – 31 December, labelled by the year), a carbon
balance from measured or modelled series only. A value that cannot be derived from real inputs is not defaulted:
it is listed in `missing` with the reason and what it blocks.

| Tier | What is computed | Needs |
|------|------------------|-------|
| 1 | Plant production (GPP, NPP) with a light-use-efficiency model | daily weather, NDVI, crop cycles, calibrated crop parameters |
| 2 | Soil organic carbon change with RothC | Tier 1 for every cycle day + soil SOC and clay + known exports |
| 3 | N₂O and the net CO₂-equivalent balance | Tier 2 + the N applied in the campaign |

The tier reported is the highest one actually computed. Sensors are not required by any formula.

### 1.1 Period and open campaigns

Accounting is by time: a campaign holds what happens between 1 January and `computedThrough`, the last day of
the last month whose daily weather is complete. The campaign in progress is recomputed every day. A crop cycle
that crosses the year contributes to each campaign the days that fall in it; its biomass returns to the soil in
the month the cycle ends, with everything it grew since sowing.

### 1.2 Inputs

| Input | Source |
|-------|--------|
| Crop cycles (start, end, role, provenance) | platform crop-cycle resolver |
| Daily min/max temperature, precipitation, ET0, global radiation | platform parcel daily weather (gaps filled from model analysis and reanalysis) |
| NDVI and OSAVI per acquisition | `EOProduct` entities (Sentinel-2) |
| Soil SOC and clay, 0–30 cm | `AgriSoilExtended` horizons, or laboratory values declared by the farmer |
| Harvest, fertilization, tillage, baling, irrigation | completed `AgriParcelOperation` entities |
| Export fractions, amendment carbon, lab soil; N and irrigation only without recorded operations | management form, only what the farmer entered |

Each value carries its provenance (`operation`, `declared`, or the source name), and every campaign stores an
inputs summary — weather days by source, vegetation scenes and longest gap, soil source, operations used — so the
result can be traced to its data. Tillage and cover crops are not declared: they come from field operations and
crop cycles. Weather always comes from the parcel daily series; sensor data belongs in that series.

## 2. Tier 1 — Light Use Efficiency

For each day inside a crop cycle:

```
PAR   = 0.48 · Rg                                   [MJ m⁻² d⁻¹]
fAPAR = clamp(a · NDVI + b, 0, 0.95)
GPP   = PAR · fAPAR · LUE                           [gC m⁻² d⁻¹]
NPP   = 0.5 · GPP
```

NDVI is interpolated linearly between acquisitions, never extrapolated, and not across gaps longer than 60 days.
A day without NDVI, without weather or for a crop without calibrated parameters is not computed; the share of
cycle days computed is reported as `tier1Coverage`. When two cycles overlap, the one started last produces.

Crop parameters come from BioOrchestrator when it returns LUE, fAPAR coefficients and root fraction together,
otherwise from the calibrated table below. Species not listed have no calibration and are reported as missing.

| Crop | LUE [gC/MJ] | fAPAR a, b | Index | Root fraction |
|------|-------------|------------|-------|---------------|
| Wheat / barley | 1.1 / 1.0 | 1.24, −0.168 | NDVI | 0.22 |
| Maize | 1.7 | 1.24, −0.168 | NDVI | 0.18 |
| Rice / sunflower / soybean / sugarcane | 1.3 / 1.3 / 1.2 / 1.8 | 1.24, −0.168 | NDVI | 0.15–0.20 |
| Olive, vineyard, almond, citrus | — | 1.40, −0.240 | OSAVI | 0.20–0.25 |

Woody crops are calibrated on OSAVI = (NIR − Red) / (NIR + Red + 0.16) (Rondeaux et al. 1996; Pôças et al. 2014),
published per acquisition next to NDVI. Each cycle uses the series of the index its fAPAR is calibrated on.

## 3. Carbon reaching the soil

NPP is split into shoot, root and exudates. Exudates are part of the below-ground share:

```
exudates = 0.07 · NPP                  enter the soil the month they are produced
roots    = (root_fraction − 0.07) · NPP   accumulated, enter the soil when the cycle ends
shoot    = (1 − root_fraction) · NPP      accumulated; at the end, shoot − exported enters the soil
```

Exported carbon at harvest (within 60 days of the cycle end):

```
exported = harvested_weight · (1 − moisture) · 0.45 / area      [tC/ha]
```

Without weight or moisture, the declared harvest-export fraction is used; without either, the export is
missing and Tier 2 is not computed. Baling removes the declared share of the remaining residue. A cover crop
without a harvest returns all its biomass. Perennial crops are reported without Tier 2: pruning and litter
inputs are not known.

Organic amendments: the carbon declared by the farmer (tC/ha/yr), placed in the months of the organic
fertilizations, or spread evenly when there are none. An organic fertilization without declared carbon blocks
Tier 2.

## 4. Tier 2 — RothC

The soil model is RothC, standard 1990 version (Jenkinson 1990; Coleman & Jenkinson), implemented step by step
as the official Rothamsted Python code (RothC_Py, Apache-2.0) and validated against its published example to a
relative tolerance of 10⁻⁶.

- Pools DPM, RPM, BIO, HUM (k = 10, 0.3, 0.66, 0.02 yr⁻¹) and inert IOM; monthly time step.
- Temperature modifier `47.91 / (1 + exp(106.06 / (T + 18.27)))`, zero below −5 °C.
- Topsoil moisture deficit with `rain − 0.75 · pan evaporation`, maximum deficit
  `−(20 + 1.3·clay − 0.01·clay²) · depth/23`, bare-soil limit 0.556 of it, rate modifier from 1 to 0.2.
  Pan evaporation is ET0 / 0.75, as the official model description prescribes for potential evapotranspiration.
- Cover modifier 0.6 when the month is covered (at least half of its days inside a cycle), 1.0 otherwise.
- Decomposed carbon splits into CO₂ and BIO + HUM with `x = 1.67 · (1.85 + 1.60 · exp(−0.0786 · clay))`;
  the retained part goes 46 % to BIO and 54 % to HUM.
- Plant inputs split DPM:RPM = 1.44; farmyard manure 49 % DPM, 49 % RPM, 2 % HUM.
- Soil depth: 30 cm (the layer of the SOC stock).

### 4.1 Initial state and chaining

The first campaign starts from the measured SOC partitioned with Weihermüller et al. (2013); when the partition
exceeds the stock, DPM is zero and the other active pools are scaled so the pools add up to the measured SOC.
The moisture deficit starts at zero on 1 January. Every later campaign starts from the pools stored at 31
December of the previous one. Computing an earlier campaign restarts the chain and recomputes the following ones.

SOC stock 0–30 cm from horizons:

```
SOC = Σ OC[%] · BD[g cm⁻³] · thickness[cm] · (1 − coarse fragments)        [tC/ha]
```

Horizons with bulk density outside 0.5–2.2 g cm⁻³ or without organic carbon make the stock missing.

## 5. Tier 3 — N₂O and net balance

N applied = fertilizer rate × N share of its N-P-K grade, per completed fertilization. Irrigation is taken from
recorded irrigation operations; the farmer's declaration applies only when none are recorded. N₂O follows the IPCC 2019
Refinement (Vol. 4, Ch. 11): EF1 for wet or dry climate — wet when precipitation exceeds ET0 over the computed
months, or when irrigated — plus volatilization (EF4) and leaching (EF5). GWP100 from IPCC AR6 (N₂O = 273).

```
NEE        = −(NPP − Rh) · 44/12                        [tCO₂/ha]
NECB       = NPP − Rh − exported C + imported C          [tC/ha]
CO₂eq net  = −NECB · 44/12 + N₂O                         [tCO₂eq/ha]
```

The net balance uses NECB, not NEE: exported harvest is respired off the farm and is not sequestration.
Negative values are a net sink.

## 6. Uncertainty

GPP uses analytical propagation with relative uncertainties of 10 % (PAR), 8 % (fAPAR) and 15 % (LUE). These are
model assumptions and are published with every result. The soil carbon change carries a 95 % interval from 500
Latin-hypercube samples of the plant-input multiplier. Soil-property uncertainty is not included.

## 7. Projection and monitoring report

- **Projection:** the last complete campaign with a soil balance is repeated year after year from its 31
  December pools. With a baseline scenario, its reference campaign is replayed under the same climate.
- **Report:** the stored campaigns of the chosen range, with the baseline (a computed reference campaign
  replayed under each campaign's own climate) when one is defined. It follows the structure of VM0042 or the
  Gold Standard SOC framework but is a **monitoring estimate, not a certification**: it lists what certification
  would still need (initial soil sampling, periodic re-sampling, independent verification, a defined baseline,
  Tier 3).

## 8. Validation

1. **Official RothC example:** monthly pools and SOC match the published results (relative error < 10⁻⁶).
2. **Mass conservation:** each RothC step and each campaign balance closes to 10⁻⁹ tC/ha.
3. **Rothamsted Hoosfield worked example** (official model description, published inputs): the unmanured plot declines
   from the pre-experiment equilibrium, annual FYM accumulates, FYM for 20 years ends in between.
4. **Monotonicity:** more organic amendment never lowers final SOC.

## 9. References

| Reference | Application |
|-----------|------------|
| Allen et al. (1998). FAO-56. | ET0 |
| Coleman, K. & Jenkinson, D.S. RothC — A model for the turnover of carbon in soil (model description). | RothC |
| IPCC (2019). 2019 Refinement, Vol. 4, Ch. 11. | N₂O |
| IPCC (2021). AR6 WG1, Ch. 7. | GWP100 |
| Jenkinson, D.S. (1990). Phil. Trans. R. Soc. B 329:361–369. | RothC |
| Myneni & Williams (1994). Remote Sens. Environ. 49:200–211. | fAPAR–NDVI |
| Pausch & Kuzyakov (2018). Soil Biol. Biochem. 116:250–261. | Root exudation |
| Pôças et al. (2014). Agric. Water Manage. 142:15–27. | Olive fAPAR–OSAVI |
| Rondeaux, Steven & Baret (1996). Remote Sens. Environ. 55:95–107. | OSAVI |
| Rothamsted Research, RothC_Py (2024), Apache-2.0. | Reference implementation |
| Villalobos et al. (2006). Eur. J. Agron. 24:282–291. | Olive LUE |
| Weihermüller et al. (2013). Eur. J. Soil Sci. 64:570–585. | Pool initialization |

---

*Last updated: 2026-10-10*
