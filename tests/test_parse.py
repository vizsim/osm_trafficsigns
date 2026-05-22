"""Tests for tsp.parse -- the fully-ported Lua tag-parsing logic.

These verify behaviour against the documented intent of the original Lua
functions. The spatial modules (nodes/ways/zones/merge) are still stubs and
have no tests yet.
"""

from tsp.parse import (
    direction_to_degree,
    get_nested_sign_list,
    get_zone_status,
    is_main_sign,
    parse_traffic_sign,
    tolist,
)


def test_tolist_basic():
    assert tolist("260,1020-30;325", ";,") == ["260", "1020-30", "325"]
    assert tolist(None) is None
    assert tolist("") == []


def test_is_main_sign():
    assert is_main_sign("260") is True          # 3 digits
    assert is_main_sign("274.1") is True         # 3 digits then non-digit
    assert is_main_sign("1020-30") is False      # 4 digits
    assert is_main_sign(None) is None


def test_direction_numeric_and_cardinal():
    assert direction_to_degree("90") == 90
    assert direction_to_degree("-90") == 270     # negative normalised
    assert direction_to_degree("N") == 0
    assert direction_to_degree("SW") == 225
    assert direction_to_degree("nonsense") is None
    # "forward"/"backward" are intentionally NOT resolved here
    assert direction_to_degree("forward") is None


def test_direction_opposite_pair_and_range():
    assert direction_to_degree("255;75") == 255  # opposite pair -> first
    assert direction_to_degree("E;W") == 90
    assert direction_to_degree("300-80") is not None  # range -> mean


def test_nested_sign_list_groups_main_and_sub():
    nested = get_nested_sign_list(["260", "1020-30", "325"])
    assert nested == [["260", "1020-30"], ["325"]]


def test_zone_status():
    assert get_zone_status(get_nested_sign_list(["260"])) == "only"
    assert get_zone_status(get_nested_sign_list(["274"])) == "no"
    assert get_zone_status(get_nested_sign_list(["260", "274"])) == "yes"


def test_parse_traffic_sign_country_code_and_humanreadable():
    parsed = parse_traffic_sign("DE:274-30", {})
    assert parsed is not None
    assert parsed["country_code"] == "DE"
    assert parsed["sign_list"] == "274-30"
    # Lua get_main_signs only strips bracketed values (274[30] -> 274);
    # dash variant suffixes are kept, so "274-30" stays "274-30".
    assert parsed["main_signs"] == "274-30"

    # bracketed sign-specific value IS stripped from main_signs
    parsed = parse_traffic_sign("DE:274[30]", {})
    assert parsed is not None
    assert parsed["main_signs"] == "274"

    # human-readable alias with maxspeed tag
    parsed = parse_traffic_sign("maxspeed", {"maxspeed": "30"})
    assert parsed is not None
    assert parsed["sign_list"] == "274-30"
    assert parsed["country_code"] == "DE"  # default applied


def test_parse_traffic_sign_filler_values_dropped():
    assert parse_traffic_sign("none", {}) is None
    assert parse_traffic_sign("street_name_sign", {}) is None
