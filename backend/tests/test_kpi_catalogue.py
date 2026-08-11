from app.routers.kpi import get_kpis_for_sectors


def test_home_kpis_are_distinct_and_not_duplicated():
    items = get_kpis_for_sectors(["home"])
    assert [item.id for item in items] == [
        "comfort_index",
        "air_quality",
        "energy_use",
        "security_events",
    ]
    assert not {"ndvi_avg", "water_stress", "yield_estimate"}.intersection(
        item.id for item in items
    )


def test_multiple_sector_kpis_are_appended_once():
    items = get_kpis_for_sectors(["agro", "home"])
    assert len(items) == 8
    assert len({item.id for item in items}) == 8
