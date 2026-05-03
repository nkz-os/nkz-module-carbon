"""Uncertainty propagation for carbon calculations — Phase 4.

Tier 1:  Gaussian analytical propagation (closed-form, every calculation).
Tier 2:  Latin Hypercube Sampling (LHS, 500 samples, cached per parcel).
Tier 3:  Monte Carlo (5000 samples, audit flag only, expensive).

Confidence scores are DERIVED from actual uncertainty distributions,
never assigned a priori.
"""

import math
import statistics
from dataclasses import dataclass
from typing import Callable

import numpy as np


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class ParameterDist:
    """A parameter with a distribution for sampling."""

    name: str
    mean: float
    std: float


@dataclass
class UncertaintyResult:
    """Uncertainty metrics for a single estimate."""

    mean: float
    std: float
    ci95_low: float
    ci95_high: float
    ci95_width: float  # ci95_high - ci95_low
    confidence: float  # 1 - ci95_width / mean, clamped [0, 1]
    samples: list[float] | None  # raw samples for audit (None for analytical)


# ---------------------------------------------------------------------------
# Tier 1 — Analytical Gaussian propagation
# ---------------------------------------------------------------------------

def gaussian_product_uncertainty(
    par: float, sigma_par: float,
    fapar: float, sigma_fapar: float,
    lue: float, sigma_lue: float,
) -> tuple[float, float]:
    """Analytical sigma_GPP for product GPP = PAR x fAPAR x LUE.

    Returns (GPP, sigma_GPP).
    Uses the Gaussian variance-of-a-product formula:
      (sigma_GPP / GPP)^2 ~ (sigma_PAR / PAR)^2 + (sigma_fAPAR / fAPAR)^2
        + (sigma_LUE / LUE)^2
    """
    gpp = par * fapar * lue

    # Relative variance from first-order Taylor expansion
    rel_var = (
        (sigma_par / par) ** 2
        + (sigma_fapar / fapar) ** 2
        + (sigma_lue / lue) ** 2
    )
    sigma_gpp = gpp * math.sqrt(rel_var)
    return gpp, sigma_gpp


# ---------------------------------------------------------------------------
# Confidence from CI (spec 6.3)
# ---------------------------------------------------------------------------

def confidence_from_ci(
    ci95_low: float, ci95_high: float, estimate: float,
) -> float:
    """Derive confidence score from CI95 width.

    confidence = 1 - (CI95_width / mean_estimate)
    Clamped to [0, 1].
    """
    if estimate == 0.0:
        return 0.0
    width = ci95_high - ci95_low
    conf = 1.0 - width / abs(estimate)
    return max(0.0, min(1.0, conf))


# ---------------------------------------------------------------------------
# Tier 2 — Latin Hypercube Sampling (LHS)
# ---------------------------------------------------------------------------

def latin_hypercube_sample(
    param_dists: list[ParameterDist],
    n_samples: int,
    seed: int = 42,
) -> list[dict[str, float]]:
    """Generate N Latin Hypercube samples from parameter distributions.

    Each returned element is a dict mapping param name to sampled value.
    Uses NumPy for LHS stratification and NormalDist.inv_cdf for the
    inverse Normal CDF transform.
    """
    normal_dist = statistics.NormalDist()
    rng = np.random.default_rng(seed)
    n_params = len(param_dists)
    samples: list[dict[str, float]] = []

    # Generate LHS matrix: shape (n_samples, n_params)
    lhs_matrix = np.zeros((n_samples, n_params))
    for j in range(n_params):
        # Stratify [0, 1) into n_samples equal intervals
        strata = np.linspace(0.0, 1.0, n_samples + 1)
        # Pick a random point within each stratum
        u = rng.uniform(0.0, 1.0 / n_samples, size=n_samples)
        lhs_matrix[:, j] = strata[:-1] + u
        # Shuffle to decorrelate parameters
        rng.shuffle(lhs_matrix[:, j])

    # Transform from uniform [0,1) to each parameter's distribution
    for i in range(n_samples):
        sample: dict[str, float] = {}
        for j, dist in enumerate(param_dists):
            u_val = lhs_matrix[i, j]
            # Inverse CDF (Normal): ppf via NormalDist.inv_cdf
            z = normal_dist.inv_cdf(u_val)
            sample[dist.name] = dist.mean + dist.std * z
        samples.append(sample)

    return samples


def monte_carlo_sample(
    param_dists: list[ParameterDist],
    n_samples: int,
    seed: int = 42,
) -> list[dict[str, float]]:
    """Simple random Monte Carlo sampling from parameter distributions.

    Intended for audit use only (Tier 3).
    """
    rng = np.random.default_rng(seed)
    samples: list[dict[str, float]] = []

    for _ in range(n_samples):
        sample: dict[str, float] = {}
        for dist in param_dists:
            z = rng.normal(0.0, 1.0)
            sample[dist.name] = dist.mean + dist.std * z
        samples.append(sample)

    return samples


# ---------------------------------------------------------------------------
# Uncertainty metrics from samples
# ---------------------------------------------------------------------------

def compute_uncertainty_from_samples(
    samples: list[float],
    estimate: float,
) -> UncertaintyResult:
    """Compute uncertainty metrics from a list of output samples.

    Parameters
    ----------
    samples : list[float]
        Output values from repeated model runs.
    estimate : float
        The point estimate (e.g. the nominal model result).
    """
    n = len(samples)
    if n < 2:
        raise ValueError("Need at least 2 samples to compute uncertainty.")

    mean = statistics.mean(samples)
    std = statistics.stdev(samples)  # sample standard deviation (ddof=1)

    # Normal-approximation CI95
    ci95_low = mean - 1.96 * std
    ci95_high = mean + 1.96 * std
    ci95_width = ci95_high - ci95_low

    confidence = confidence_from_ci(ci95_low, ci95_high, estimate)

    return UncertaintyResult(
        mean=mean,
        std=std,
        ci95_low=ci95_low,
        ci95_high=ci95_high,
        ci95_width=ci95_width,
        confidence=confidence,
        samples=list(samples),
    )


# ---------------------------------------------------------------------------
# Tier-specific convenience functions
# ---------------------------------------------------------------------------

def tier1_gpp_uncertainty(
    par: float, sigma_par: float,
    fapar: float, sigma_fapar: float,
    lue: float, sigma_lue: float,
) -> UncertaintyResult:
    """Tier 1 analytical uncertainty for GPP. No sampling needed.

    Returns UncertaintyResult with samples=None (analytical).
    """
    gpp, sigma_gpp = gaussian_product_uncertainty(
        par, sigma_par, fapar, sigma_fapar, lue, sigma_lue,
    )
    ci95_low = gpp - 1.96 * sigma_gpp
    ci95_high = gpp + 1.96 * sigma_gpp
    return UncertaintyResult(
        mean=gpp,
        std=sigma_gpp,
        ci95_low=ci95_low,
        ci95_high=ci95_high,
        ci95_width=ci95_high - ci95_low,
        confidence=confidence_from_ci(ci95_low, ci95_high, gpp),
        samples=None,
    )
