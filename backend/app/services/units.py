"""Canonical conversion constants. Single source of truth for all unit math.

All variable names MUST encode their unit using suffixes from the naming
convention table (see spec §0). Bare names without unit suffix are
REJECTED in code review.
"""

# Carbon ↔ CO₂
C_TO_CO2 = 44.0 / 12.0  # gCO2 per gC (44/12)

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
