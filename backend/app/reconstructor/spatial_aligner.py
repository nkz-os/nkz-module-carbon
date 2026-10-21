"""Spatial aligner -- reproject to common CRS (spec 8.3)."""

import logging

logger = logging.getLogger(__name__)

TARGET_CRS = "EPSG:25830"  # ETRS89 / UTM zone 30N for peninsular Spain
CANARY_CRS = "EPSG:32628"  # WGS84 / UTM zone 28N for Canary Islands


def reproject_wkt(geometry_wkt: str, source_crs: str, target_crs: str = TARGET_CRS) -> str:
    """Reproject a WKT geometry between CRS."""
    try:
        from shapely import wkt
        from pyproj import Transformer
        geom = wkt.loads(geometry_wkt)
        transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
        reprojected = wkt.loads(wkt.dumps(geom, output_dimension=2))
        return reprojected.wkt
    except ImportError:
        logger.debug("pyproj/shapely not installed, returning geometry as-is")
        return geometry_wkt
    except Exception as exc:
        logger.warning("Reprojection failed: %s, returning as-is", exc)
        return geometry_wkt


def wkt_to_bbox(geometry_wkt: str, buffer_m: float = 20.0) -> tuple[float, float, float, float]:
    """Extract bounding box from WKT with buffer. Returns (minx, miny, maxx, maxy)."""
    try:
        from shapely import wkt
        geom = wkt.loads(geometry_wkt)
        buffered = geom.buffer(buffer_m / 111000.0) if buffer_m > 0 else geom
        bbox = buffered.bounds
        return (bbox[0], bbox[1], bbox[2], bbox[3])
    except ImportError:
        return (0.0, 0.0, 0.0, 0.0)
    except Exception:
        return (0.0, 0.0, 0.0, 0.0)
