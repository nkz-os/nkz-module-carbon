"""RothC soil carbon model -- Tier 2 (spec 4).

Stateless. Input: monthly arrays. Output: pool state + SOC delta.

Implements:
  - Jenkinson 1990 pools and rate constants
  - RothC canonical a_temp (no Q10 simplification)
  - TSMD-based moisture modifier (not CWSI)
  - Weihermuller et al. 2013 pool initialization
  - Per-source differential humification with DPM/RPM split
"""

import math
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Pool rate constants [yr-1] -- Jenkinson 1990
POOL_K = {
    "DPM": 10.0,
    "RPM": 0.30,
    "BIO": 0.66,
    "HUM": 0.02,
    "IOM": 0.0,
}

# DPM/RPM split ratios by input type (spec 4.6)
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

# Humification coefficients (spec 4.5)
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

# Vegetation cover modifier (spec 4.7)
C_COVER_VEGETATED = 0.6
C_COVER_BARE = 1.0

# TSMD threshold for moisture modifier (spec 4.3)
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
    cover_present: bool = True
    c_input_aerea_tC_ha: float = 0.0
    c_input_raices_tC_ha: float = 0.0
    c_input_exudados_tC_ha: float = 0.0
    c_input_enmienda_tC_ha: float = 0.0
    clay_pct: float = 20.0


@dataclass
class RothCResult:
    pools: PoolState
    rh_tC_ha_yr: float  # heterotrophic respiration
    soc_delta_tC_ha_yr: float
    monthly_tsmd: list[float] = field(default_factory=list)


# -- Temperature modifier (spec 4.2) --

def a_temp(temp_celsius: float) -> float:
    """RothC canonical temperature modifier -- Jenkinson 1990.

    a_temp = 47.91 / (1 + exp(106.06 / (T + 18.27)))
    Clamped at T <= -18C to prevent numerical singularity.
    """
    if temp_celsius <= -18.0:
        return 0.0
    return 47.91 / (1.0 + math.exp(106.06 / (temp_celsius + 18.27)))


# -- Moisture modifier -- TSMD (spec 4.3) --

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
    cover_fractions_0_1: list[float],
    clay_pct: float,
) -> list[float]:
    """Compute monthly TSMD values from water balance."""
    tsmax = tsmd_max(clay_pct)
    tsmd_series: list[float] = []
    accumulated = 0.0

    for p_mm, etp_mm, cov_frac in zip(
        monthly_precip_mm, monthly_etp_mm, cover_fractions_0_1
    ):
        etp_eff = etp_mm * (0.75 if cov_frac > 0.5 else 1.0)
        deficit = etp_eff - p_mm
        accumulated += deficit
        accumulated = max(0.0, min(tsmax, accumulated))
        tsmd_series.append(accumulated)

    return tsmd_series


# -- Pool initialization -- Weihermuller 2013 (spec 4.4) --

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


# -- Carbon inputs -- per-source humification (spec 4.5) --

def _ratio_key_for_source(source_key: str) -> str:
    """Map source key to DPM_RPM_RATIOS key."""
    if source_key == "aerea":
        return "cultivo_anual"
    return source_key


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


# -- Monthly evolution (spec 4.7) --

def step_month(
    pools: PoolState, monthly: MonthlyInputs, tsmd: float,
) -> tuple[PoolState, float]:
    """Advance RothC pools by one month. Returns (new_pools, rh_tC_ha_month)."""
    tsmax = tsmd_max(monthly.clay_pct)
    at = a_temp(monthly.temp_celsius)
    bh = b_humedad(tsmd, tsmax)
    cc = C_COVER_VEGETATED if monthly.cover_present else C_COVER_BARE

    c_dpm_in, c_rpm_in, c_hum_in = compute_c_inputs(monthly)

    rh_total_tC_ha = 0.0
    new_pools = {}

    for pool_name in ["DPM", "RPM", "BIO", "HUM"]:
        k = POOL_K[pool_name]
        old_c = getattr(pools, f"{pool_name.lower()}_tC_ha")
        decay = math.exp(-k * at * bh * cc * DT_MONTH)
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

    new_pools["IOM"] = pools.iom_tC_ha

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
    precip = [m.precip_mm for m in monthly_inputs]
    etp = [m.etp_mm for m in monthly_inputs]
    covers = [0.8 if m.cover_present else 0.0 for m in monthly_inputs]
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
