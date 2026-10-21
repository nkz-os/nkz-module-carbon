"""RothC soil carbon model, standard 1990 version (Jenkinson 1990; Coleman & Jenkinson).

Stateless and immutable. Mirrors the official Rothamsted Python code (RothC_Py,
Apache-2.0) step by step; tests/test_rothc_official.py checks it against the
published example.
"""

import math
from dataclasses import dataclass
from typing import Sequence


_K_OFFICIAL = {"dpm": 10.0, "rpm": 0.3, "bio": 0.66, "hum": 0.02}
_STEPS_PER_YEAR = 12


@dataclass(frozen=True)
class RothCPools:
    """Soil carbon pools, tC/ha."""
    dpm: float
    rpm: float
    bio: float
    hum: float
    iom: float

    @property
    def total(self) -> float:
        return self.dpm + self.rpm + self.bio + self.hum + self.iom

    def to_dict(self) -> dict[str, float]:
        return {"DPM": self.dpm, "RPM": self.rpm, "BIO": self.bio, "HUM": self.hum, "IOM": self.iom}

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> "RothCPools":
        return cls(float(d["DPM"]), float(d["RPM"]), float(d["BIO"]), float(d["HUM"]), float(d["IOM"]))


@dataclass(frozen=True)
class RothCState:
    """Pools plus the accumulated topsoil moisture deficit (mm, <= 0)."""
    pools: RothCPools
    swc_mm: float


@dataclass(frozen=True)
class RothCMonth:
    """One monthly time step, in the units of the official model."""
    temp_c: float
    rain_mm: float
    pan_evap_mm: float
    plant_cover: bool
    plant_c: float = 0.0    # plant C entering the soil this month, tC/ha
    dpm_rpm: float = 1.44   # DPM/RPM ratio of plant inputs (agricultural crops)
    fym_c: float = 0.0      # farmyard manure C, tC/ha


@dataclass(frozen=True)
class RothCRun:
    final: RothCState
    states: tuple[RothCState, ...]
    co2: tuple[float, ...]  # CO2-C released each month, tC/ha


def pan_evap_from_et0(et0_mm: float) -> float:
    """RothC runs on open-pan evaporation; potential ET is divided by 0.75."""
    return et0_mm / 0.75


def _rate_temp(temp_c: float) -> float:
    if temp_c < -5.0:
        return 0.0
    return 47.91 / (math.exp(106.06 / (temp_c + 18.27)) + 1.0)


def _moisture(swc: float, m: RothCMonth, clay: float, depth: float) -> tuple[float, float]:
    smd_max = -(20.0 + 1.3 * clay - 0.01 * clay * clay) * depth / 23.0
    smd_1bar = 0.444 * smd_max
    smd_bare = 0.556 * smd_max
    deficit = min(0.0, swc + m.rain_mm - 0.75 * m.pan_evap_mm)
    if m.plant_cover:
        swc = max(smd_max, deficit)
    else:
        swc = max(min(smd_bare, swc), deficit)
    if swc > smd_1bar:
        return swc, 1.0
    return swc, 0.2 + 0.8 * (smd_max - swc) / (smd_max - smd_1bar)


def step_month(state: RothCState, m: RothCMonth, clay_pct: float,
               depth_cm: float) -> tuple[RothCState, float]:
    """Advance one month. Returns the new state and the CO2-C released (tC/ha)."""
    swc, rm_moist = _moisture(state.swc_mm, m, clay_pct, depth_cm)
    rate = _rate_temp(m.temp_c) * rm_moist * (0.6 if m.plant_cover else 1.0)
    p = state.pools
    tstep = 1.0 / _STEPS_PER_YEAR
    kept = {name: getattr(p, name) * math.exp(-rate * k * tstep) for name, k in _K_OFFICIAL.items()}
    decomposed = sum(getattr(p, name) - kept[name] for name in _K_OFFICIAL)
    x = 1.67 * (1.85 + 1.60 * math.exp(-0.0786 * clay_pct))
    co2 = decomposed * (x / (x + 1.0))
    to_bio = decomposed * (0.46 / (x + 1.0))
    to_hum = decomposed * (0.54 / (x + 1.0))
    pools = RothCPools(
        dpm=kept["dpm"] + m.dpm_rpm / (m.dpm_rpm + 1.0) * m.plant_c + 0.49 * m.fym_c,
        rpm=kept["rpm"] + 1.0 / (m.dpm_rpm + 1.0) * m.plant_c + 0.49 * m.fym_c,
        bio=kept["bio"] + to_bio,
        hum=kept["hum"] + to_hum + 0.02 * m.fym_c,
        iom=p.iom,
    )
    return RothCState(pools, swc), co2


def run_months(state: RothCState, months: Sequence[RothCMonth], clay_pct: float,
               depth_cm: float) -> RothCRun:
    states: list[RothCState] = []
    co2s: list[float] = []
    for m in months:
        state, co2 = step_month(state, m, clay_pct, depth_cm)
        states.append(state)
        co2s.append(co2)
    return RothCRun(final=state, states=tuple(states), co2=tuple(co2s))


def equilibrium(year: Sequence[RothCMonth], clay_pct: float, depth_cm: float, iom: float,
                tol: float = 1e-6) -> RothCState:
    """Spin-up from empty pools, repeating one year until the annual change is <= tol."""
    state = RothCState(RothCPools(0.0, 0.0, 0.0, 0.0, iom), 0.0)
    toc = 0.0
    while True:
        for m in year:
            state, _ = step_month(state, m, clay_pct, depth_cm)
        toc_prev, toc = toc, state.pools.total - state.pools.iom
        if abs(toc - toc_prev) <= tol:
            return state


def weihermuller_pools(soc_tC_ha: float, clay_pct: float) -> RothCPools:
    """Pool partition of a measured SOC stock (Weihermüller et al. 2013).

    IOM after Falloon et al. (1998). DPM is the remainder. When the other pools
    already exceed the stock, DPM is 0 and RPM/BIO/HUM are scaled down so the pools
    add up to the measured SOC: the partition must never create carbon.
    """
    soc, clay = soc_tC_ha, clay_pct
    iom = min(0.049 * soc ** 1.139, soc)
    rpm = (0.1847 * soc + 0.1555) * (clay + 1.2750) ** -0.1158
    hum = (0.7148 * soc + 0.5069) * (clay + 0.3421) ** 0.0184
    bio = (0.0140 * soc + 0.0075) * (clay + 8.8473) ** 0.0567
    active, room = rpm + bio + hum, soc - iom
    if active <= room:
        return RothCPools(room - active, rpm, bio, hum, iom)
    k = room / active if active > 0 else 0.0
    return RothCPools(0.0, rpm * k, bio * k, hum * k, iom)
