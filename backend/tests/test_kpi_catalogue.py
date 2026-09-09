from app.routers.kpi import get_kpis_for_sectors, get_generic_kpis


def test_agro_sector_kpis_are_distinct_and_not_duplicated():
    items = get_kpis_for_sectors(["agro"])
    ids = [item.id for item in items]
    assert ids  # non-empty
    assert len(ids) == len(set(ids))  # no duplicates
    assert "soil_moisture" in ids


def test_multiple_sector_kpis_are_appended():
    agro = get_kpis_for_sectors(["agro"])
    environment = get_kpis_for_sectors(["environment"])
    combined = get_kpis_for_sectors(["agro", "environment"])
    # Each sector contributes its KPIs to the combined list.
    assert len(combined) == len(agro) + len(environment)


def test_removed_home_sector_falls_back_to_generic():
    # "home" is no longer a GeoVision sector; it must not resolve to a dedicated
    # KPI set. Unknown sectors fall back to the generic KPIs.
    items = get_kpis_for_sectors(["home"])
    assert [i.id for i in items] == [i.id for i in get_generic_kpis()]
