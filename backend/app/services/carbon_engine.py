"""Tier 1 Carbon Engine -- LUE (Light Use Efficiency) Model.

Stateless. Input: daily parameters. Output: dict with unit-encoded keys.

All output variable names encode their units per 0 convention.
Tier 1 uses NPP only for CO2 -- does NOT subtract Rh.
See spec 3.5 for the conceptual difference vs Tier 2/3 NEE.
"""

import logging
from dataclasses import dataclass

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
    """fAPAR = clamp(a * VI + b, 0, 0.95) -- spec 3.1."""
    fapar = a * vi_value + b
    return max(0.0, min(0.95, fapar))


def calculate_tier1(inputs: Tier1Input) -> Tier1Output:
    """Compute Tier 1 carbon metrics for one day.

    Spec 3.4: GPP = PAR x fAPAR x LUE
    Spec 3.4: AGB_dry_t_ha = (NPP_aerea / C_IN_DM) x G_PER_M2_TO_T_PER_HA
    Spec 3.5: CO2_seq = NPP_total x C_TO_CO2 x 10

    Tier 1 does NOT subtract Rh -- see spec 3.5 note.
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

    # Biomass: gC/m2/day -> tDM/ha/day
    # (gC / 0.45) = gDM/m2 -> x 0.01 = tDM/ha
    agb_dry_tDM_ha = (npp_aerea_gC_m2_day / C_IN_DM) * G_PER_M2_TO_T_PER_HA
    bgb_dry_tDM_ha = (npp_radicular_gC_m2_day / C_IN_DM) * G_PER_M2_TO_T_PER_HA

    # CO2: gC/m2/day -> kgCO2/ha/day
    # gC x 3.664 = gCO2/m2 -> x 0.001 = kgCO2/m2 -> x 10000 = kgCO2/ha
    # Simplification: gC/m2/day x 3.6667 x 10 = kgCO2/ha/day
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
