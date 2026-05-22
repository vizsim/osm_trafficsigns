"""Generate a small synthetic .osm.pbf for testing the traffic-sign pipeline.

Builds a tiny but representative road network near Bremen (so the default
UTM 33N CRS is sensible) covering every code path:

  * a sign NODE sitting on a highway vertex (direction from line geometry)
  * a sign NODE next to a road (direction from nearest road, within 20 m)
  * a sign NODE with an explicit numeric direction (left untouched)
  * a road carrying a regular traffic_sign tag on its centerline, crossing
    another road (-> junction -> sign placed at the junction buffer edge)
  * a residential street tagged as a Tempo-30 zone (274.1) meeting a
    non-zone road (-> zone entrance)

Coordinates are hand-placed on a ~0.01 deg patch; at this latitude that is
roughly 700 x 1100 m, enough for the 8 m / 10 m / 20 m thresholds to behave.
"""

import osmium

# base point near Bremen
LAT0, LON0 = 53.075, 8.805


def dd(dlat=0.0, dlon=0.0):
    return (LON0 + dlon, LAT0 + dlat)


def main(path="osm/test_signs.osm.pbf"):
    writer = osmium.SimpleWriter(path)

    # --- nodes ---------------------------------------------------------------
    # main east-west road A: nodes 1..4
    coords = {
        1: dd(0.000, 0.000),
        2: dd(0.000, 0.004),
        3: dd(0.000, 0.008),   # junction with road B
        4: dd(0.000, 0.012),
        # north-south road B through node 3: nodes 5,3,6
        5: dd(0.004, 0.008),
        6: dd(-0.004, 0.008),
        # residential zone street C: nodes 7..9, meeting road A at node 2
        7: dd(0.000, 0.004),   # == node 2 location (shares the junction)
        8: dd(0.003, 0.004),
        9: dd(0.006, 0.004),
        # standalone sign nodes
        20: dd(0.0000, 0.0020),   # ON road A (between n1 and n2)
        21: dd(0.00015, 0.0060),  # ~16 m NEXT TO road A
        22: dd(-0.0010, 0.0100),  # standalone, explicit direction
    }

    def node(nid, tags):
        lon, lat = coords[nid]
        return osmium.osm.mutable.Node(
            id=nid, location=(lon, lat), tags=tags, version=1,
        )

    # plain network nodes (no tags)
    for nid in (1, 3, 4, 5, 6, 8, 9):
        writer.add_node(node(nid, {}))
    # node 2 doubles as a junction; node 7 is the same spot on street C
    writer.add_node(node(2, {}))
    writer.add_node(node(7, {}))

    # tagged sign nodes
    writer.add_node(node(20, {"traffic_sign": "DE:206"}))            # stop, on line
    writer.add_node(node(21, {"traffic_sign": "DE:274-30"}))         # 30 km/h, beside road
    writer.add_node(node(22, {"traffic_sign": "DE:101", "direction": "90"}))

    # --- ways ----------------------------------------------------------------
    def way(wid, nodes, tags):
        return osmium.osm.mutable.Way(id=wid, nodes=nodes, tags=tags, version=1)

    # road A: a residential road, carries a regular traffic_sign on its centerline
    writer.add_way(way(101, [1, 2, 3, 4], {
        "highway": "residential",
        "name": "Teststrasse A",
        "traffic_sign": "DE:274-50",   # 50 km/h, regular sign
    }))
    # road B: plain residential cross street
    writer.add_way(way(102, [5, 3, 6], {
        "highway": "residential",
        "name": "Teststrasse B",
    }))
    # street C: a Tempo-30 zone, branches off road A at node 2/7
    writer.add_way(way(103, [7, 8, 9], {
        "highway": "residential",
        "name": "Wohnstrasse C",
        "traffic_sign": "DE:274.1",    # zone sign (Tempo-30-Zone)
    }))

    writer.close()
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
