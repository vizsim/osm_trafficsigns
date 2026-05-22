"""Port of ``lua/osm_import_traffic_sign.lua``.

This module contains the pure string-processing logic from the original Lua
config: parsing the ``traffic_sign`` tag into normalised sign lists, telling
main signs from additional signs, classifying zone vs. regular signs, and
converting ``direction`` values to degrees.

It contains NO spatial logic and NO I/O -- that lives in :mod:`tsp.osmread`
(the pyosmium handler) and the processing modules. Keeping it separate makes
it trivial to unit-test against the behaviour of the original Lua functions.
"""

from __future__ import annotations

import re

# --- configuration carried over verbatim from the Lua file --------------------

#: Default country code for traffic signs (Lua: ``default_country_code``).
DEFAULT_COUNTRY_CODE = "DE"

#: Human-readable traffic-sign aliases -> country-specific IDs.
#: (Lua: ``human_readable_values`` table.)
HUMAN_READABLE_VALUES: dict[str, str] = {
    "city_limit": "310",
    "city_limit_end": "311",
    "maxspeed": "274",
    "maxspeed_implicit": "278",
    "stop": "206",
    "give_way": "205",
    "overtaking_no": "276",
    "overtaking_yes": "280",
    "maxwidth": "264",
    "maxheight": "265",
    "maxweight": "262",
    "stop_ahead": "205,1004-32",
    "yield_ahead": "205,1004-30",
    "signal_ahead": "131",
    "hazard": "101",
}

#: Sign IDs that behave like zone signs (placed once at the zone entrance,
#: not repeated at every junction). Lua: ``zone_ids``.
#: NOTE: the same list is duplicated inside the original ``traffic_sign_way.sql``
#: and ``traffic_sign_zone.sql`` -- keep all copies in sync.
ZONE_IDS: list[str] = [
    "242", "250", "251", "253", "260", "270", "274.1", "290", "314", "325",
]

#: Cardinal direction strings -> degrees (Lua: ``cardinal_direction`` table).
#: NOTE: the Lua file has a known typo ``westnordost = 1337`` -- intentionally
#: NOT reproduced here; treat unknown cardinals as ``None`` instead.
_CARDINAL_DIRECTION: dict[str, int] = {
    "north": 0, "east": 90, "south": 180, "west": 270,
    "n": 0, "nne": 22, "ne": 45, "ene": 67, "e": 90, "ese": 112,
    "se": 135, "sse": 157, "s": 180, "ssw": 202, "sw": 225, "wsw": 247,
    "w": 270, "wnw": 292, "nw": 315, "nnw": 337,
    "northnortheast": 22, "northeast": 45, "eastnortheast": 67,
    "eastsoutheast": 112, "southeast": 135, "southsoutheast": 157,
    "southsouthwest": 202, "southwest": 225, "westsouthwest": 247,
    "westnorthwest": 292, "northwest": 315, "northnorthwest": 337,
    "north-north-east": 22, "north-east": 45, "east-north-east": 67,
    "east-south-east": 112, "south-east": 135, "south-south-east": 157,
    "south-south-west": 202, "south-west": 225, "west-south-west": 247,
    "west-north-west": 292, "north-west": 315, "north-north-west": 337,
}


# --- helpers (Lua: tolist / cardinaltodegree / directiontodegree) -------------

def tolist(value: str | None, separators: str = ";") -> list[str] | None:
    """Split *value* into a list, ``separators`` being a set of separator chars.

    Port of Lua ``tolist``. Empty parts are dropped. Returns ``None`` for
    ``None`` input.
    """
    if value is None:
        return None
    parts = re.split(f"[{re.escape(separators)}]", value)
    return [p for p in parts if p != ""]


def cardinal_to_degree(value: str) -> int | None:
    """Translate a cardinal direction string to degrees, or ``None``."""
    return _CARDINAL_DIRECTION.get(value.strip().lower())


def _mid_angle(a: float, b: float) -> int:
    """Mean of two angles on a 0..360 circle (Lua references ``mid_angle``)."""
    diff = ((b - a + 540) % 360) - 180
    return int(round((a + diff / 2) % 360))


def direction_to_degree(value: str | None) -> int | None:
    """Convert an OSM ``direction`` value to integer degrees, or ``None``.

    Port of Lua ``directiontodegree``. Handles: numeric degrees (incl. negative),
    cardinal strings, two opposite semicolon-separated values, and ``a-b`` ranges.
    The literal strings ``"forward"`` / ``"backward"`` are intentionally NOT
    resolved here -- they are passed through unchanged and handled later by the
    node-processing step, which needs the highway geometry to resolve them.
    """
    if value is None:
        return None

    value = value.strip()

    # plain numeric degrees
    try:
        num = float(value)
    except ValueError:
        num = None
    if num is not None:
        deg = int(num)
        return deg + 360 if deg < 0 else deg

    # cardinal strings / abbreviations
    card = cardinal_to_degree(value)
    if card is not None:
        return card

    # two opposite values, e.g. "255;75" or "E;W" -> take the first
    if ";" in value:
        parts = tolist(value, ";") or []
        if len(parts) == 2:
            try:
                n1, n2 = float(parts[0]), float(parts[1])
                if abs(n1 - n2) == 180:
                    return int(n1)
            except ValueError:
                pass
            c1, c2 = cardinal_to_degree(parts[0]), cardinal_to_degree(parts[1])
            if c1 is not None and c2 is not None and abs(c1 - c2) == 180:
                return c1
        return None

    # numeric range "a-b" -> mean value
    m = re.match(r"^(-?\d+)-(\d+)$", value)
    if m:
        return _mid_angle(int(m.group(1)), int(m.group(2)))

    return None


# --- sign classification (Lua: is_main_sign / get_nested_sign_list / ...) -----

def is_main_sign(sign_id: str | None) -> bool | None:
    """True if *sign_id* is a main sign (German rule: starts with exactly 3 digits).

    Port of Lua ``is_main_sign``. Adjust for non-German sign systems.
    """
    if sign_id is None:
        return None
    if re.match(r"\d{3}", sign_id[:3]):
        fourth = sign_id[3:4]
        if fourth == "" or not fourth.isdigit():
            return True
    return False


def get_nested_sign_list(sign_list: list[str] | None) -> list[list[str]] | None:
    """Group a flat sign list into ``[[main, sub, sub], [main], ...]``.

    Port of Lua ``get_nested_sign_list``. Each main sign starts a new group;
    additional signs attach to the preceding group (or start their own group
    if they appear stand-alone).
    """
    if sign_list is None:
        return None
    nested: list[list[str]] = []
    current: list[str] | None = None
    for sign_id in sign_list:
        if sign_id is None:
            continue
        if is_main_sign(sign_id):
            current = [sign_id]
            nested.append(current)
        else:
            if current is None:
                current = [sign_id]
                nested.append(current)
            else:
                current.append(sign_id)
    return nested or None


def get_main_signs(nested_list: list[list[str]]) -> str:
    """Concatenate the main sign of each group with ``;``.

    Port of Lua ``get_main_signs``. Sign-specific values in brackets
    (e.g. ``274[30]`` -> ``274``) are stripped.
    """
    result = []
    for sublist in nested_list:
        if sublist:
            result.append(re.sub(r"\[[^\]]*\]", "", sublist[0]))
    return ";".join(result)


def get_sign_list(nested_list: list[list[str]]) -> str:
    """Serialise a nested list back to OSM notation, e.g. ``"260,1020-30;325"``.

    Port of Lua ``get_sign_list``.
    """
    return ";".join(",".join(sublist) for sublist in nested_list)


def _is_zone_main_sign(main_sign: str) -> bool:
    """True if *main_sign* matches a zone ID (exact or as a prefix)."""
    return any(
        main_sign == zid or main_sign.startswith(zid) for zid in ZONE_IDS
    )


def get_zone_status(nested_list: list[list[str]] | None) -> str:
    """Return ``"no"`` / ``"yes"`` / ``"only"`` for the zone-sign content.

    Port of Lua ``get_zone_status``. ``"only"`` = all main signs are zone signs,
    ``"no"`` = none are, ``"yes"`` = mixed.
    """
    if nested_list is None:
        return "no"
    zone_count = total = 0
    for sublist in nested_list:
        if sublist:
            total += 1
            if _is_zone_main_sign(sublist[0]):
                zone_count += 1
    if total and zone_count == total:
        return "only"
    if zone_count == 0:
        return "no"
    return "yes"


def remove_zone_signs(nested_list: list[list[str]]) -> list[list[str]]:
    """Drop all groups whose main sign is a zone sign (Lua: ``remove_zone_signs``)."""
    return [s for s in nested_list if not (s and _is_zone_main_sign(s[0]))]


def remove_regular_signs(nested_list: list[list[str]]) -> list[list[str]]:
    """Keep only groups whose main sign is a zone sign (Lua: ``remove_regular_signs``)."""
    return [s for s in nested_list if s and _is_zone_main_sign(s[0])]


# --- the main tag parser (Lua: process_traffic_sign, parsing portion) ---------

def parse_traffic_sign(
    traffic_sign: str,
    tags: dict[str, str],
) -> dict | None:
    """Parse a raw ``traffic_sign`` tag value into normalised sign data.

    This is the country-code extraction + human-readable substitution +
    normalisation portion of Lua ``process_traffic_sign``. It does NOT do the
    table routing (node vs. way vs. zone) -- callers do that using
    :func:`get_zone_status` on the returned ``nested`` list.

    Returns ``None`` when there is no significant sign information, otherwise a
    dict with: ``country_code``, ``nested`` (nested sign list), ``main_signs``,
    ``sign_list``, ``zone_status``.
    """
    # strip filler values "none"/"no"/"yes"/"street_name_sign"
    value = traffic_sign
    for filler in ("none", "no", "yes", "street_name_sign"):
        value = re.sub(filler + r"[;,]?", "", value)

    # detect a leading country code ("XX:" but not a ":" inside brackets)
    cc_match = re.match(r"^([^:\[\],;]+):", value)
    country_code = cc_match.group(1) if cc_match else None

    rest = value[len(country_code) + 1:] if country_code else value
    sign_list = tolist(rest, ";,")

    # nothing meaningful left
    if not sign_list or not sign_list[0]:
        return None

    # normalise & clean up each sign
    for i, sign_id in enumerate(sign_list):
        # drop repeated country codes ("DE:274" inside the list)
        if country_code and sign_id.startswith(country_code + ":"):
            sign_list[i] = sign_id[len(country_code) + 1:]
            sign_id = sign_list[i]

        # replace human-readable aliases with sign IDs
        if sign_id in HUMAN_READABLE_VALUES:
            if sign_id == "city_limit" and tags.get("city_limit") == "end":
                sign_list[i] = HUMAN_READABLE_VALUES["city_limit_end"]
            elif sign_id == "maxspeed":
                ms = tags.get("maxspeed")
                if ms == "implicit":
                    sign_list[i] = HUMAN_READABLE_VALUES["maxspeed_implicit"]
                elif ms is not None and _is_number(ms):
                    sign_list[i] = HUMAN_READABLE_VALUES["maxspeed"] + "-" + ms
                else:
                    sign_list[i] = HUMAN_READABLE_VALUES["maxspeed"]
            elif sign_id == "overtaking":
                key = "overtaking_yes" if tags.get("overtaking") == "yes" else "overtaking_no"
                sign_list[i] = HUMAN_READABLE_VALUES[key]
            else:
                sign_list[i] = HUMAN_READABLE_VALUES[sign_id]
            if country_code is None:
                country_code = DEFAULT_COUNTRY_CODE

    nested = get_nested_sign_list(sign_list)
    if nested is None:
        return None

    return {
        "country_code": country_code,
        "nested": nested,
        "main_signs": get_main_signs(nested),
        "sign_list": get_sign_list(nested),
        "zone_status": get_zone_status(nested),
    }


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False
