"""Historical Reconstructor -- reconstruct 10-year parcel history for RothC spin-up.

All external connectors degrade gracefully (return empty/synthetic data).
Actual API credentials added at deploy time via env vars.
"""

from app.reconstructor.onboarding import onboard_parcela, OnboardingResult

__all__ = ["onboard_parcela", "OnboardingResult"]
