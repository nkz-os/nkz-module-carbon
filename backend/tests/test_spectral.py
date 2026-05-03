from app.services.spectral import (
    MorphologicalType,
    VegetationIndex,
    select_index,
    compute_ndvi,
    compute_osavi,
    compute_msavi2,
    compute_index,
)


class TestSelectIndex:
    def test_herbaceous_gets_ndvi(self):
        assert select_index(MorphologicalType.HERBACEOUS) == VegetationIndex.NDVI

    def test_woody_gets_osavi(self):
        assert select_index(MorphologicalType.WOODY) == VegetationIndex.OSAVI


class TestNDVI:
    def test_dense_vegetation(self):
        """Healthy vegetation: NIR=0.5, RED=0.1 -> NDVI=0.667."""
        ndvi = compute_ndvi(nir=0.5, red=0.1)
        assert 0.6 < ndvi < 0.7

    def test_bare_soil(self):
        """Bare soil: NIR~RED -> NDVI~0."""
        ndvi = compute_ndvi(nir=0.2, red=0.2)
        assert abs(ndvi) < 0.01

    def test_zero_denominator(self):
        assert compute_ndvi(nir=0.0, red=0.0) == 0.0


class TestOSAVI:
    def test_woody_default_L(self):
        """OSAVI with L=0.16 for woody crops: 0.4/0.76 = 0.526."""
        osavi = compute_osavi(nir=0.5, red=0.1, L=0.16)
        assert 0.5 < osavi < 0.55

    def test_reduces_soil_sensitivity_vs_ndvi(self):
        ndvi = compute_ndvi(nir=0.3, red=0.15)
        osavi = compute_osavi(nir=0.3, red=0.15, L=0.16)
        # OSAVI should be lower (less inflated) on bare-ish soil
        assert osavi < ndvi


class TestMSAVI2:
    def test_dense_vegetation(self):
        msavi2 = compute_msavi2(nir=0.5, red=0.1)
        assert 0.3 < msavi2 < 0.7

    def test_negative_discriminant_returns_zero(self):
        """Edge case where discriminant would be negative (RED << 0)."""
        result = compute_msavi2(nir=0.5, red=-1.0)
        assert result == 0.0


class TestComputeIndex:
    def test_dispatches_correctly(self):
        ndvi = compute_index(VegetationIndex.NDVI, nir=0.5, red=0.1)
        osavi = compute_index(VegetationIndex.OSAVI, nir=0.5, red=0.1)
        msavi2 = compute_index(VegetationIndex.MSAVI2, nir=0.5, red=0.1)
        assert ndvi != osavi
        assert ndvi != msavi2
        assert osavi != msavi2
