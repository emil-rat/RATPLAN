import pytest

from ratplan_terrain.models.geometry import Position


def test_rounds_to_stable_hash_key():
    a = Position(lon=17.80488781, lat=59.23482161)
    b = Position(lon=17.8048878, lat=59.2348216)
    assert a == b
    assert hash(a) == hash(b)


def test_to_working_and_back_roundtrips():
    original = Position(lon=17.9, lat=59.3)
    x, y = original.to_working()
    roundtripped = Position.from_working(x, y)
    assert roundtripped.lon == pytest.approx(original.lon, abs=1e-5)
    assert roundtripped.lat == pytest.approx(original.lat, abs=1e-5)


def test_distance_m_between_known_points_is_physically_sane():
    a = Position(lon=17.9, lat=59.3)
    b = Position(lon=17.91, lat=59.3)
    # ~1 km/deg-lon at this latitude (cos(59.3deg) * 111.32 km/deg) times 0.01 deg
    assert a.distance_m(b) == pytest.approx(566.0, rel=0.1)
