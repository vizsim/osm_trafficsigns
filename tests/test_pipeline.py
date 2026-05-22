"""Integration tests for the spatial processing pipeline.

These build a tiny synthetic OSM network in-memory (via make_test_pbf) and run
each processing stage, checking the documented behaviour of the original SQL.
The fixture pbf is regenerated into a tmp dir so the tests are self-contained.
"""

import os
import sys

import pytest

# make_test_pbf lives in scripts/, not in the package
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
))


@pytest.fixture(scope="module")
def layers(tmp_path_factory):
    """Generate the synthetic pbf and return the four imported GeoDataFrames."""
    import make_test_pbf
    from tsp.osmread import read_osm

    pbf = tmp_path_factory.mktemp("osm") / "test_signs.osm.pbf"
    make_test_pbf.main(str(pbf))
    return read_osm(str(pbf))


def test_import_counts(layers):
    node_gdf, way_gdf, zone_gdf, highway_gdf = layers
    assert len(node_gdf) == 3       # 3 tagged sign nodes
    assert len(way_gdf) == 1        # 1 regular sign-way (274-50)
    assert len(zone_gdf) == 1       # 1 zone sign-way (274.1)
    assert len(highway_gdf) == 3    # 3 highways


def test_process_nodes_directions(layers):
    from tsp.nodes import process_nodes

    node_gdf, _, _, highway_gdf = layers
    result = process_nodes(node_gdf, highway_gdf)

    by_id = {r["osm_id"]: r for _, r in result.iterrows()}

    # node 22 has an explicit direction tag -> kept unchanged
    assert by_id[22]["direction"] == 90
    # nodes 20 (on road) and 21 (beside road) get a derived direction
    assert by_id[20]["direction"] is not None
    assert by_id[21]["direction"] is not None
    # all directions normalised into 0..360
    for r in by_id.values():
        d = r["direction"]
        if d is not None:
            assert 0 <= d < 360
    # node 21 sat next to road A -> highway adopted
    assert by_id[21]["highway"] == "residential"


def test_process_ways_places_nodes_at_junctions(layers):
    from tsp.ways import process_ways

    _, way_gdf, _, highway_gdf = layers
    result = process_ways(way_gdf, highway_gdf)

    # road A is split by 2 junction buffers into 3 segments -> 6 endpoints
    assert len(result) == 6
    assert set(result["sign_list"]) == {"274-50"}
    assert set(result["osm_id"]) == {101}   # osm_id adopted from highway


def test_process_zones_one_entrance(layers):
    from tsp.zones import process_zones

    _, _, zone_gdf, highway_gdf = layers
    result = process_zones(zone_gdf, highway_gdf)

    # street C is a zone branching off road A -> exactly one entrance node
    assert len(result) == 1
    assert result.iloc[0]["sign_list"] == "274.1"


def test_merge_combines_all_sources(layers):
    from tsp.merge import OUTPUT_COLUMNS, merge_signs
    from tsp.nodes import process_nodes
    from tsp.ways import process_ways
    from tsp.zones import process_zones

    node_gdf, way_gdf, zone_gdf, highway_gdf = layers
    merged = merge_signs(
        process_nodes(node_gdf, highway_gdf),
        process_ways(way_gdf, highway_gdf),
        process_zones(zone_gdf, highway_gdf),
    )

    # 3 node + 6 way + 1 zone, no dedup expected in this fixture
    assert len(merged) == 10
    assert list(merged.columns) == OUTPUT_COLUMNS
    assert set(merged["source"]) == {"node", "way", "zone"}
