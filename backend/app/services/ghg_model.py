"""Tier 3 GHG model -- N2O, CH4, NEE/NECB (spec 5).

Stateless. Input: annual aggregated data. Output: GHG budget.
"""

from dataclasses import dataclass

from app.services.units import N_TO_N2O

# GWP100 -- AR6 (spec 5.1)
GWP100_AR6 = {
    "N2O": 273,
    "CH4_non_fossil": 27,
    "CH4_fossil": 29.8,
}

# IPCC 2019 Refinement emission factors (spec 5.2)
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
    """Annual inputs for N2O calculation."""
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
    """N2O emissions -- IPCC 2019 Refinement full formula (spec 5.2)."""
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
    nee_co2_tCO2_ha_yr: float              # NEE in CO2 units


def compute_nee(inputs: NEEInputs) -> NEEResult:
    """Net Ecosystem Exchange (spec 5.3).

    NEE = -(NPP - Rh)  [negative = carbon sink, sign convention]
    NECB = NEE - C_harvest_exported + C_amendments_imported
    """
    # Convert NPP from gC/m2/yr to tC/ha/yr for consistency
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
    )


def compute_co2eq_net(
    nee_tCO2_ha_yr: float,
    n2o_tCO2eq_ha_yr: float,
    ch4_tCO2eq_ha_yr: float = 0.0,
) -> float:
    """Net CO2eq balance: sequestration plus GHG emissions.

    CO2eq_net = NEE(CO2) + N2O(CO2eq) + CH4(CO2eq)
    NEE is negative for sink; N2O/CH4 are positive emissions.
    Negative = net carbon sink to atmosphere.
    Positive = net source to atmosphere.
    """
    return nee_tCO2_ha_yr + n2o_tCO2eq_ha_yr + ch4_tCO2eq_ha_yr
