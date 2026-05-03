"""Tests for uncertainty propagation module (Phase 4)."""

import math

import numpy as np

from app.services.uncertainty import (
    ParameterDist,
    UncertaintyResult,
    gaussian_product_uncertainty,
    confidence_from_ci,
    latin_hypercube_sample,
    monte_carlo_sample,
    compute_uncertainty_from_samples,
    tier1_gpp_uncertainty,
)


# ---------------------------------------------------------------------------
# 1. Gaussian product uncertainty
# ---------------------------------------------------------------------------

class TestGaussianProductUncertainty:
    def test_three_equal_rel_errors(self):
        """PAR=15+-1.5 (10%), fAPAR=0.7+-0.07 (10%), LUE=1.1+-0.11 (10%).

        sigma_rel_GPP ~ sqrt(0.01+0.01+0.01) = 0.1732
        GPP = 11.55, sigma_GPP ~ 2.0
        """
        gpp, sigma = gaussian_product_uncertainty(
            par=15.0, sigma_par=1.5,
            fapar=0.7, sigma_fapar=0.07,
            lue=1.1, sigma_lue=0.11,
        )
        assert abs(gpp - 11.55) < 1e-10
        expected_rel = math.sqrt(0.01 + 0.01 + 0.01)
        assert abs(sigma / gpp - expected_rel) < 1e-10
        assert abs(sigma - 2.000) < 0.01

    def test_zero_sigma(self):
        """All zero uncertainties -> sigma_GPP = 0."""
        gpp, sigma = gaussian_product_uncertainty(
            par=10.0, sigma_par=0.0,
            fapar=0.5, sigma_fapar=0.0,
            lue=2.0, sigma_lue=0.0,
        )
        assert abs(gpp - 10.0) < 1e-10
        assert sigma == 0.0

    def test_one_dominant_uncertainty(self):
        """Only PAR has uncertainty -> sigma_GPP = GPP * (sigma_PAR / PAR)."""
        gpp, sigma = gaussian_product_uncertainty(
            par=10.0, sigma_par=2.0,
            fapar=0.5, sigma_fapar=0.0,
            lue=2.0, sigma_lue=0.0,
        )
        # GPP = 10 * 0.5 * 2 = 10
        assert abs(gpp - 10.0) < 1e-10
        # sigma = GPP * (2/10) = 2.0
        assert abs(sigma - 2.0) < 1e-10

    def test_inverse_relation(self):
        """Doubling relative error doubles sigma_GPP."""
        _, sigma_a = gaussian_product_uncertainty(
            par=10.0, sigma_par=1.0,  # 10%
            fapar=0.5, sigma_fapar=0.05,  # 10%
            lue=2.0, sigma_lue=0.2,  # 10%
        )
        _, sigma_b = gaussian_product_uncertainty(
            par=10.0, sigma_par=2.0,  # 20%
            fapar=0.5, sigma_fapar=0.1,  # 20%
            lue=2.0, sigma_lue=0.4,  # 20%
        )
        # Doubling all rel errors doubles total sigma (since sqrt(4*k) = 2*sqrt(k))
        assert abs(sigma_b / sigma_a - 2.0) < 1e-10


# ---------------------------------------------------------------------------
# 2. Confidence from CI
# ---------------------------------------------------------------------------

class TestConfidenceFromCI:
    def test_confidence_0_6(self):
        """CI95 [80, 120] around estimate 100 -> width=40, conf=0.6."""
        conf = confidence_from_ci(80.0, 120.0, 100.0)
        assert abs(conf - 0.6) < 1e-10

    def test_zero_estimate(self):
        """Zero estimate returns 0 confidence."""
        conf = confidence_from_ci(0.0, 0.0, 0.0)
        assert conf == 0.0

    def test_narrow_ci(self):
        """CI95 [95, 105] around 100 -> conf=0.9."""
        conf = confidence_from_ci(95.0, 105.0, 100.0)
        assert abs(conf - 0.9) < 1e-10

    def test_clamp_below_zero(self):
        """CI wider than estimate -> clamp to 0."""
        conf = confidence_from_ci(0.0, 200.0, 100.0)
        assert conf == 0.0

    def test_clamp_above_one(self):
        """CI narrower than zero (should not happen) -> clamp to 1."""
        conf = confidence_from_ci(100.0, 100.0, 100.0)
        assert conf == 1.0

    def test_negative_estimate(self):
        """Negative estimate should work (abs is used)."""
        conf = confidence_from_ci(-120.0, -80.0, -100.0)
        assert abs(conf - 0.6) < 1e-10


# ---------------------------------------------------------------------------
# 3. Latin Hypercube Sampling
# ---------------------------------------------------------------------------

class TestLatinHypercubeSample:
    def test_sample_count(self):
        """Must return exactly n_samples elements."""
        dists = [
            ParameterDist("SOC", 50.0, 2.5),
            ParameterDist("clay", 20.0, 3.0),
        ]
        samples = latin_hypercube_sample(dists, n_samples=500, seed=42)
        assert len(samples) == 500

    def test_within_three_sigma(self):
        """All samples should be within ~3 sigma of the mean."""
        dists = [
            ParameterDist("SOC", 50.0, 2.5),
            ParameterDist("clay", 20.0, 3.0),
        ]
        samples = latin_hypercube_sample(dists, n_samples=500, seed=42)
        for s in samples:
            assert 50.0 - 4 * 2.5 <= s["SOC"] <= 50.0 + 4 * 2.5, (
                f"SOC={s['SOC']} outside 4 sigma range"
            )
            assert 20.0 - 4 * 3.0 <= s["clay"] <= 20.0 + 4 * 3.0, (
                f"clay={s['clay']} outside 4 sigma range"
            )

    def test_stratification_uniform_coverage(self):
        """Each stratum of [0,1) should be represented approx equally.

        Divide each parameter's CDF into 10 bins. With 500 samples and
        10 bins, each bin should have ~50 samples. Allow +/-50% tolerance.
        """
        dists = [ParameterDist("x", 0.0, 1.0)]
        samples = latin_hypercube_sample(dists, n_samples=500, seed=42)
        values = [s["x"] for s in samples]

        # CDF bins for N(0,1)
        bin_edges = [
            float("-inf"),
            -1.2816,  # 10th pct
            -0.8416,  # 20th
            -0.5244,  # 30th
            -0.2533,  # 40th
            0.0,       # 50th
            0.2533,   # 60th
            0.5244,   # 70th
            0.8416,   # 80th
            1.2816,   # 90th
            float("inf"),
        ]

        counts = []
        for i in range(len(bin_edges) - 1):
            lo = bin_edges[i]
            hi = bin_edges[i + 1]
            if i == 0:
                count = sum(1 for v in values if v <= hi)
            elif i == len(bin_edges) - 2:
                count = sum(1 for v in values if v > lo)
            else:
                count = sum(1 for v in values if lo < v <= hi)
            counts.append(count)

        # Each bin should have ~50 samples; allow +/-50%
        for idx, c in enumerate(counts):
            assert 20 <= c <= 80, (
                f"Bin {idx} has {c} samples (expected ~50, tol +-30)"
            )

    def test_deterministic_seed(self):
        """Same seed produces identical results."""
        dists = [ParameterDist("x", 10.0, 2.0)]
        a = latin_hypercube_sample(dists, 100, seed=42)
        b = latin_hypercube_sample(dists, 100, seed=42)
        for sa, sb in zip(a, b):
            assert sa["x"] == sb["x"]

    def test_different_seeds_different(self):
        """Different seeds produce different samples."""
        dists = [ParameterDist("x", 10.0, 2.0)]
        a = latin_hypercube_sample(dists, 100, seed=42)
        b = latin_hypercube_sample(dists, 100, seed=123)
        # At least some values should differ
        assert not all(sa["x"] == sb["x"] for sa, sb in zip(a, b))


# ---------------------------------------------------------------------------
# 4. Tier 1 GPP uncertainty end-to-end
# ---------------------------------------------------------------------------

class TestTier1GPPUncertainty:
    def test_typical_wheat_day_values(self):
        """End-to-end test with typical values."""
        result = tier1_gpp_uncertainty(
            par=15.0, sigma_par=1.5,
            fapar=0.7, sigma_fapar=0.07,
            lue=1.1, sigma_lue=0.11,
        )
        assert isinstance(result, UncertaintyResult)
        assert abs(result.mean - 11.55) < 1e-10
        assert abs(result.std - 2.0) < 0.01
        assert result.samples is None  # analytical
        # CI95 approx 11.55 +- 1.96 * 2.0 = [7.63, 15.47]
        assert abs(result.ci95_low - 7.63) < 0.02
        assert abs(result.ci95_high - 15.47) < 0.02
        # confidence = 1 - (15.47 - 7.63) / 11.55 = 1 - 0.679 = 0.321
        assert 0.30 < result.confidence < 0.35

    def test_exact_measurements(self):
        """With zero uncertainty, confidence should be 1.0."""
        result = tier1_gpp_uncertainty(
            par=10.0, sigma_par=0.0,
            fapar=0.5, sigma_fapar=0.0,
            lue=2.0, sigma_lue=0.0,
        )
        assert result.std == 0.0
        assert result.ci95_width == 0.0
        assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# 5. Monte Carlo sampling
# ---------------------------------------------------------------------------

class TestMonteCarlo:
    def test_sample_count(self):
        """MC with 5000 samples should return exactly 5000."""
        dists = [ParameterDist("x", 0.0, 1.0)]
        samples = monte_carlo_sample(dists, 5000, seed=42)
        assert len(samples) == 5000

    def test_deterministic(self):
        """Same seed produces identical results."""
        dists = [ParameterDist("x", 0.0, 1.0)]
        a = monte_carlo_sample(dists, 1000, seed=42)
        b = monte_carlo_sample(dists, 1000, seed=42)
        for sa, sb in zip(a, b):
            assert sa["x"] == sb["x"]


# ---------------------------------------------------------------------------
# 6. Compute uncertainty from samples
# ---------------------------------------------------------------------------

class TestComputeUncertaintyFromSamples:
    def test_normal_100_10(self):
        """Known normal distribution: N(100, 10) with 1000 samples.

        Mean should be ~100, std ~10.
        """
        rng = np.random.default_rng(123)
        raw = list(rng.normal(100.0, 10.0, size=1000))
        result = compute_uncertainty_from_samples(raw, estimate=100.0)

        assert abs(result.mean - 100.0) < 1.0
        assert abs(result.std - 10.0) < 1.0
        # CI95 should be ~ [80, 120] -> confidence ~ 0.6
        assert 0.55 < result.confidence < 0.70
        assert result.samples is not None
        assert len(result.samples) == 1000

    def test_confidence_from_ci_agrees(self):
        """The confidence in UncertaintyResult must match direct call."""
        rng = np.random.default_rng(456)
        raw = list(rng.normal(50.0, 5.0, size=200))
        result = compute_uncertainty_from_samples(raw, estimate=50.0)
        direct = confidence_from_ci(
            result.ci95_low, result.ci95_high, 50.0,
        )
        assert abs(result.confidence - direct) < 1e-10

    def test_insufficient_samples(self):
        """Fewer than 2 samples must raise ValueError."""
        try:
            compute_uncertainty_from_samples([10.0], estimate=10.0)
            assert False, "Expected ValueError"
        except ValueError:
            pass

    def test_exact_values(self):
        """Identical samples -> zero std -> CI95 single point -> confidence 1."""
        raw = [100.0] * 100
        result = compute_uncertainty_from_samples(raw, estimate=100.0)
        assert result.mean == 100.0
        assert result.std == 0.0
        assert result.ci95_width == 0.0
        assert result.confidence == 1.0
