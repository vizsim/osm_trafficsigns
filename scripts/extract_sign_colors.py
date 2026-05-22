"""Derive a per-sign {fill, stroke} pair from each SVG in ``viz/symbols/``.

Heuristic:
- Parse all ``fill:#xxxxxx`` and ``fill="#xxxxxx"`` colors in the SVG.
- Bucket near-white and near-black separately; keep the rest as "accent" hues.
- Group accent colors by hue (12 buckets) so anti-aliasing variants collapse.
- Pick the most-frequent accent hue as the sign's signature color.

Result mapping (driven by the accent's hue family + a few light/dark tweaks):
- Reds (prohibition rings, warning triangles)   -> fill #ffffff, stroke red
- Blues (mandatory / info signs)                -> fill blue,    stroke #ffffff
- Yellow / orange (directional, construction)   -> fill yellow,  stroke #1a1a1a
- Green (autobahn)                              -> fill green,   stroke #ffffff
- No saturated accent (supplementary plates)    -> fill #ffffff, stroke #1a1a1a

Output JSON shape::

    { "237": { "fill": "#154889", "stroke": "#ffffff" }, ... }
"""

from __future__ import annotations

import colorsys
import json
import re
from collections import Counter
from pathlib import Path

from tsp.signlist import collapse_shared_family, normalize_code

REPO_ROOT = Path(__file__).resolve().parent.parent
SVG_DIR = REPO_ROOT / "viz" / "symbols" / "DE"
OUT_PATH = REPO_ROOT / "viz" / "data" / "sign_colors.json"
README_PATH = REPO_ROOT / "viz" / "SIGN_CLASSIFICATION.md"
# Optional: also resolve every code that appears in these parquets via
# normalize + family-walk, so the JSON contains a direct entry for them.
# Just Berlin — it's the primary dataset, and Neukölln would double-count
# (it's a Berlin Bezirk, subset of the Berlin parquet). Bremen is the small
# test set; its unique codes are also covered by Berlin in practice.
PARQUETS = [
    REPO_ROOT / "output" / "berlin_signs.parquet",
]

# When a feature is tagged with a bare family code (e.g. "241") but multiple
# variants exist in the library (241-30, 241-31), my rule of "only set svg if
# a single variant exists" leaves the family without an icon. This override
# table lets you pick the canonical variant per family.
PREFERRED_FAMILY_VARIANT = {
    "241": "241-30",
    "244": "244.1",   # was the only 244-* before 244.3 was added; keep canonical
}

# Manual color entries for codes that DON'T have an SVG in the library but
# should still render as a coloured dot (not the grey "no-info" fallback).
# Used by the viz: the styleimagemissing handler picks these up and
# generates a circle bitmap in the given colours instead of the default grey.
# Add a code here when its visual identity is so iconic that a coloured dot
# is more useful than a grey badge with the code number.
MANUAL_COLOR_ENTRIES: dict[str, dict[str, str]] = {
    # Ortstafel ("city limit") — yellow with black border. Upstream SVG library
    # doesn't ship a 310 file; the yellow dot is recognisable enough on its own.
    "310": {"fill": "#fcd116", "stroke": "#1a1a1a"},
}

# Reference SVG size — square StVO signs ship at ~600×600. Wider/taller
# SVGs (e.g. directional Wegweiser like 439 = 2500×1750) get a per-code
# `scale` factor so they render at roughly the same on-screen footprint
# as the square signs.
SVG_REFERENCE_SIZE = 600.0

VIEWBOX_RE = re.compile(
    r'viewBox\s*=\s*"\s*([0-9.\-]+)\s+([0-9.\-]+)\s+([0-9.\-]+)\s+([0-9.\-]+)\s*"'
)

# Match #rrggbb (6-digit preferred, 3-digit fallback) in both `fill:#xxx` and
# `fill="#xxx"` forms — and the same for `stroke`. Many prohibition signs in
# the SupaplexOSM library use *stroke* for the red ring rather than fill, so
# we need both. The 6-digit branch comes first because Python regex picks the
# leftmost-matching alternative — putting {3} first truncates "154889" to "154".
COLOR_RE = re.compile(
    r'(?:fill|stroke)\s*[:=]\s*"?#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b'
)


def svg_scale(svg_text: str) -> float | None:
    """Return a scale factor that normalises this SVG's max dimension to
    ``SVG_REFERENCE_SIZE``. Returns None when no viewBox is found (caller
    should treat as 1.0 — i.e. no scaling)."""
    m = VIEWBOX_RE.search(svg_text)
    if not m:
        return None
    _, _, w, h = (float(x) for x in m.groups())
    longest = max(w, h)
    if longest <= 0:
        return None
    return SVG_REFERENCE_SIZE / longest

# Default colors per hue family (chosen to read well at small dot sizes).
RED = "#dc1414"
BLUE = "#1953a4"
YELLOW = "#fcd116"
GREEN = "#1a7f3c"
WHITE = "#ffffff"
DARK = "#1a1a1a"

DEFAULT = {"fill": WHITE, "stroke": DARK}


def parse_hex(token: str) -> tuple[int, int, int] | None:
    if len(token) == 3:
        token = "".join(c * 2 for c in token)
    if len(token) != 6:
        return None
    try:
        return int(token[0:2], 16), int(token[2:4], 16), int(token[4:6], 16)
    except ValueError:
        return None


def hsv(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (c / 255 for c in rgb)
    return colorsys.rgb_to_hsv(r, g, b)


def classify(svg_text: str) -> dict[str, str]:
    accents: Counter[str] = Counter()
    for match in COLOR_RE.finditer(svg_text):
        rgb = parse_hex(match.group(1))
        if rgb is None:
            continue
        h, s, v = hsv(rgb)
        # Drop near-black and near-white; they're pictogram/background filler.
        if v < 0.15 or (s < 0.15 and v > 0.85):
            continue
        # Bucket by 30°-wide hue ranges so AA edge fragments collapse together.
        key = f"{int(h * 12)}|{round(s, 1)}"
        accents[key] += 1

    if not accents:
        return dict(DEFAULT)

    # Pick the dominant accent and recover a representative RGB for it.
    top_key, _ = accents.most_common(1)[0]
    top_hue = int(top_key.split("|")[0])
    top_sat = float(top_key.split("|")[1])
    # Map hue bucket -> family color (constant fill, ignoring exact shade).
    if top_hue in (0, 11) and top_sat > 0.4:
        return {"fill": WHITE, "stroke": RED}      # red ring / triangle
    if 1 <= top_hue <= 2:                          # orange / amber
        return {"fill": YELLOW, "stroke": DARK}
    if top_hue == 2 and top_sat > 0.4:
        return {"fill": YELLOW, "stroke": DARK}
    if 1 <= top_hue <= 3 and top_sat > 0.5:
        return {"fill": YELLOW, "stroke": DARK}
    if 3 <= top_hue <= 5:                          # green
        return {"fill": GREEN, "stroke": WHITE}
    if 5 <= top_hue <= 8:                          # blue (the StVO "mandatory" blue is ~hue 0.55)
        return {"fill": BLUE, "stroke": WHITE}
    # Fallback for any unmapped accent: blue (matches most info signs).
    return {"fill": BLUE, "stroke": WHITE}


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out: dict[str, dict[str, str]] = {}
    # Origin tracking, for the human-readable README only — kept out of JSON.
    origin: dict[str, str] = {}
    family_votes: dict[str, Counter[tuple[str, str, str]]] = {}
    # Per-SVG scale: viewBox max-dim ratio, used by the viewer to keep
    # wide/tall icons from dwarfing the square ones. Only written to the
    # JSON when != 1.0 to keep the file lean.
    SCALE_THRESHOLD = 0.95
    for svg in sorted(SVG_DIR.glob("*.svg")):
        code = svg.stem
        svg_text = svg.read_text(encoding="utf-8")
        colors = classify(svg_text)
        entry: dict[str, object] = {**colors, "svg": code}
        scale = svg_scale(svg_text)
        if scale is not None and scale < SCALE_THRESHOLD:
            entry["scale"] = round(scale, 3)
        out[code] = entry
        origin[code] = "direct"
        base = re.split(r"[-.]", code, maxsplit=1)[0]
        if base != code:
            family_votes.setdefault(base, Counter())[
                (colors["fill"], colors["stroke"], code)
            ] += 1

    # Family bases: colors always; svg only when (a) the family has a single
    # variant OR (b) a manual preferred-variant override exists for this base.
    for base, votes in family_votes.items():
        if base in out:
            continue
        (fill, stroke, svg_name), _ = votes.most_common(1)[0]
        entry: dict[str, object] = {"fill": fill, "stroke": stroke}
        preferred = PREFERRED_FAMILY_VARIANT.get(base)
        if preferred and preferred in out:
            entry["svg"] = preferred
            # Inherit colors + scale from the preferred variant
            entry["fill"] = out[preferred]["fill"]
            entry["stroke"] = out[preferred]["stroke"]
            if "scale" in out[preferred]:
                entry["scale"] = out[preferred]["scale"]
            origin[base] = f"family-alias from {preferred} (manual override)"
        elif sum(votes.values()) == 1:
            entry["svg"] = svg_name
            if "scale" in out[svg_name]:
                entry["scale"] = out[svg_name]["scale"]
            origin[base] = f"family-alias from {svg_name}"
        else:
            origin[base] = (
                f"family-vote ({sum(votes.values())} variants) — colors only, no svg"
            )
        out[base] = entry

    # Bracket-notation aliases: OSM tags sometimes use "274[30]" as shorthand
    # for "274-30". Mirror every hyphenated code under both forms.
    bracketed = 0
    for code in list(out.keys()):
        m = re.match(r"^(\d+)-([\d.\-]+)$", code)
        if not m:
            continue
        bracket = f"{m.group(1)}[{m.group(2)}]"
        if bracket in out:
            continue
        out[bracket] = dict(out[code])
        origin[bracket] = f"bracket-notation -> {code}"
        bracketed += 1

    # Manual colour overrides — codes without an SVG that should still render
    # as a coloured dot rather than the grey "unknown" fallback.
    manual = 0
    for code, colors in MANUAL_COLOR_ENTRIES.items():
        if code in out:
            continue
        out[code] = dict(colors)   # explicitly no `svg` field — colour only
        origin[code] = "manual colour override (no SVG)"
        manual += 1

    # Parquet codes: try direct after normalisation; family-walk drops svg.
    aliased = 0
    parquet_codes = collect_parquet_codes()
    fallbacks: list[str] = []
    for raw in parquet_codes:
        if raw in out:
            continue
        resolved, source = resolve_via_family_with_origin(raw, out)
        if resolved is not None:
            out[raw] = resolved
            origin[raw] = source
            aliased += 1
        else:
            fallbacks.append(raw)

    OUT_PATH.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(
        f"wrote {OUT_PATH}  ({len(out)} signs incl. family + parquet aliases "
        f"[{aliased} parquet, {len(fallbacks)} parquet-only fallbacks])"
    )
    buckets = Counter((v["fill"], v["stroke"]) for v in out.values())
    for (fill, stroke), n in buckets.most_common():
        print(f"  {n:3d}  fill={fill} stroke={stroke}")

    write_readme(out, origin, parquet_codes, fallbacks)
    print(f"wrote {README_PATH}")


def collect_parquet_codes() -> Counter[str]:
    """Collect the normalized ``icon_code`` values that will appear in the
    PMTiles for every parquet in PARQUETS, **with feature counts**.

    Mirrors the derivation in ``build_pmtiles.py``: prefer ``sign_list`` (has
    variant info like ``274[30]`` -> ``274-30``), fall back to ``main_signs``,
    finally fall back to the raw ``main_signs`` string so free-text features
    like ``"Privatgrundstück"`` still appear here and get listed as parquet
    fallbacks in the README. The count drives sort order in the fallback
    table so you can prioritise which SVGs / overrides are worth adding.
    """
    counts: Counter[str] = Counter()
    try:
        import pandas as pd
    except ImportError:
        return counts
    for path in PARQUETS:
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=["sign_list", "main_signs"])
        for _, row in df.iterrows():
            normalized = normalize_code(row["sign_list"]) or normalize_code(row["main_signs"])
            if normalized:
                # Mirror build_pmtiles' shared-family collapse so the README
                # counts and the PMTiles agree on which codes exist.
                code, _ = collapse_shared_family(normalized)
                counts[code] += 1
            elif isinstance(row["main_signs"], str) and row["main_signs"]:
                counts[row["main_signs"]] += 1
    return counts


def resolve_via_family_with_origin(
    raw: str, table: dict[str, dict[str, str]]
) -> tuple[dict[str, str] | None, str]:
    """Like resolve_via_family but also returns a human-readable origin tag."""
    parts: list[str] = []
    candidate = re.split(r"[,;]", raw, maxsplit=1)[0].strip()
    if candidate != raw:
        parts.append("list-first")
    m = re.match(r"^([A-Z]{2})(.+)$", candidate)
    if m:
        candidate = m.group(2)
        parts.append("country-prefix-strip")
    m = re.match(r"^(\d+)\[([\d.\-]+)\]$", candidate)
    if m:
        candidate = f"{m.group(1)}-{m.group(2)}"
        parts.append("bracket-notation")
    if candidate in table:
        tag = ", ".join(parts) if parts else "identity"
        return dict(table[candidate]), f"{tag} -> {candidate}"
    while True:
        new = re.sub(r"[-.][^-.]*$", "", candidate)
        if new == candidate or not new:
            return None, ""
        candidate = new
        if candidate in table:
            entry = table[candidate]
            parts.append(f"family-walk -> {candidate} (colors only)")
            return {"fill": entry["fill"], "stroke": entry["stroke"]}, ", ".join(parts)


def resolve_via_family(raw: str, table: dict[str, dict[str, str]]) -> dict[str, str] | None:
    """Try to find a color entry for *raw* by progressively normalising it.

    Returns a fresh dict (not a reference into *table*). The crucial rule is
    that the `svg` field is only carried over when we're confident the raw
    code points to *exactly the same sign*:

    - Stripping a list separator (``1000-32;206`` -> ``1000-32``) keeps svg.
    - Stripping a country prefix (``DE242.1`` -> ``242.1``)        keeps svg.
    - Stripping a bracket variant (``274[30]`` -> ``274-30``)      keeps svg.
    - Walking up the family (``1000-33`` -> ``1000``)              drops svg,
      because the variant differs (e.g. 1000-33 is *not* 1000-10).
    """
    # 1) Take only the first sub-code if separated by ',' or ';'.
    candidate = re.split(r"[,;]", raw, maxsplit=1)[0].strip()
    # 2) Strip an ISO-style country prefix like "DE242.1".
    m = re.match(r"^([A-Z]{2})(.+)$", candidate)
    if m:
        candidate = m.group(2)
    # 3) Normalise OSM bracket notation: "274[30]" is shorthand for "274-30".
    m = re.match(r"^(\d+)\[([\d.\-]+)\]$", candidate)
    if m:
        candidate = f"{m.group(1)}-{m.group(2)}"
    # 4) Direct hit after the above strips? Same sign — copy the entry whole.
    if candidate in table:
        return dict(table[candidate])
    # 5) Walk up the family. svg is *not* inherited because the variant changes.
    while True:
        new = re.sub(r"[-.][^-.]*$", "", candidate)
        if new == candidate or not new:
            return None
        candidate = new
        if candidate in table:
            entry = table[candidate]
            return {"fill": entry["fill"], "stroke": entry["stroke"]}


def write_readme(
    out: dict[str, dict[str, str]],
    origin: dict[str, str],
    parquet_counts: Counter[str],
    fallbacks: list[str],
) -> None:
    """Emit viz/SIGN_CLASSIFICATION.md — a human-readable map of how every
    sign code is colored and which SVG (if any) it draws."""
    # Group entries by (fill, stroke) — that's our visual category.
    by_category: dict[tuple[str, str], list[str]] = {}
    for code, entry in out.items():
        key = (entry["fill"], entry["stroke"])
        by_category.setdefault(key, []).append(code)

    # Stable, opinionated ordering of categories.
    CATEGORY_LABELS = {
        ("#1953a4", "#ffffff"): "Blue — Vorschrift / Information",
        ("#ffffff", "#dc1414"): "Red ring / triangle — Verbots- / Warnzeichen",
        ("#fcd116", "#1a1a1a"): "Yellow — Wegweiser / Verkehrsführung",
        ("#1a7f3c", "#ffffff"): "Green — Autobahn / Schnellstraße",
        ("#ffffff", "#1a1a1a"): "White / black — Zusatzzeichen",
    }
    order = [
        ("#1953a4", "#ffffff"),
        ("#ffffff", "#dc1414"),
        ("#fcd116", "#1a1a1a"),
        ("#1a7f3c", "#ffffff"),
        ("#ffffff", "#1a1a1a"),
    ]

    def code_sort_key(code: str) -> tuple:
        # Sort numerically by prefix where possible so "237" < "1000-33".
        m = re.match(r"^(\d+)", code)
        return (0 if m else 1, int(m.group(1)) if m else 0, code)

    lines: list[str] = []
    lines.append("# Sign classification")
    lines.append("")
    lines.append(
        "Auto-generated by `scripts/extract_sign_colors.py`. **Do not edit by"
        " hand** — re-run the script to refresh."
    )
    lines.append("")
    lines.append("## How it works")
    lines.append("")
    lines.append(
        "Each sign code maps to a `{fill, stroke}` pair (used for the low-zoom"
        " dots in `viz/`) and optionally an `svg` basename (used for the"
        " high-zoom marker icon). Entries come from three sources:"
    )
    lines.append("")
    lines.append(
        "1. **direct** — there's a matching SVG file in `viz/symbols/DE/`; colors"
        " are derived by scanning its `fill:` and `stroke:` attributes,"
        " bucketed by hue."
    )
    lines.append(
        "2. **family alias** — e.g. `244` inherits from `244.1` because that's"
        " the only `244-*` file. Multi-variant families (`274`, `1000`) get"
        " colors but no `svg` — we don't know which specific variant to draw."
        " Exceptions are listed in `PREFERRED_FAMILY_VARIANT` at the top of"
        " the script (e.g. `241 → 241-30`)."
    )
    lines.append(
        "3. **parquet alias** — codes found in `output/*.parquet` are matched"
        " against the table after stripping list separators (`1000-32;206`),"
        " country prefixes (`DE:242.1`), and bracket / colon notation"
        " (`274[30]`, `274.1:30`, `274:30` → `274-30`). See"
        " `src/tsp/signlist.py` for the rules."
    )
    lines.append(
        "4. **manual override** — codes that don't have an SVG but should"
        " still render with a recognisable colour (e.g. `310` Ortstafel —"
        " yellow with black border). Listed in `MANUAL_COLOR_ENTRIES` at the"
        " top of the script. The viewer generates a coloured circle bitmap"
        " for these instead of the grey fallback."
    )
    lines.append("")
    lines.append(
        "Codes the table can't resolve at all (free-text annotations, signs"
        " without any SVG in the upstream library) render as **grey fallback"
        " dots with the raw code overlaid as a white-box label** in the viewer."
        " Grey is reserved for fallbacks; real yellow/amber signs like the"
        " city-limit *Ortstafel* keep their natural colour."
    )
    lines.append("")
    lines.append("## Categories")
    lines.append("")

    for key in order:
        codes = sorted(by_category.get(key, []), key=code_sort_key)
        if not codes:
            continue
        fill, stroke = key
        lines.append(f"### {CATEGORY_LABELS[key]}")
        lines.append("")
        lines.append(f"Fill `{fill}` · Stroke `{stroke}` · **{len(codes)} entries**")
        lines.append("")
        lines.append("| Code | Berlin | Icon (SVG) | Origin |")
        lines.append("| --- | ---: | --- | --- |")
        for code in codes:
            entry = out[code]
            svg = entry.get("svg", "_(no SVG — coloured dot only)_")
            if entry.get("svg"):
                svg = f"`{svg}.svg`"
            n = parquet_counts.get(code, 0)
            count_cell = f"{n}" if n else "—"
            lines.append(f"| `{code}` | {count_cell} | {svg} | {origin.get(code, '-')} |")
        lines.append("")

    # Parquet fallbacks: codes that appear in the data but have NO classification.
    if fallbacks:
        # Sort by feature count desc — most-frequent first so it's clear which
        # missing codes are worth drawing an SVG / adding a manual colour for.
        sorted_fallbacks = sorted(
            fallbacks,
            key=lambda c: (-parquet_counts.get(c, 0), code_sort_key(c)),
        )
        total = sum(parquet_counts.get(c, 0) for c in fallbacks)
        lines.append("## Parquet codes without any match (grey fallback)")
        lines.append("")
        lines.append(
            "These codes appear in the parquet but couldn't be resolved by the"
            " heuristics above — either no SVG file exists for them or they're"
            " free-text annotations. In the viewer they render as an enlarged"
            " grey dot with the raw code overlaid as a white-box label."
        )
        lines.append("")
        lines.append(
            f"Sorted by feature count in the Berlin parquet ({total} features"
            f" across {len(sorted_fallbacks)} unique codes) — the top of the"
            " list is where adding an SVG or a `MANUAL_COLOR_ENTRIES` entry"
            " has the biggest visual payoff."
        )
        lines.append("")
        lines.append("| Code | Berlin |")
        lines.append("| --- | ---: |")
        for code in sorted_fallbacks:
            n = parquet_counts.get(code, 0)
            lines.append(f"| `{code}` | {n} |")
        lines.append("")

    README_PATH.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
