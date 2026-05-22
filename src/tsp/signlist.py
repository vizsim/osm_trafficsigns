"""Pick the canonical icon code from a raw OSM ``traffic_sign`` string.

The raw value can be a comma- or semicolon-separated list with country
prefixes, bracket notation, and free-text annotations. Examples:

    "DE:274[30],\"Altenheim\",\"Schule\""   -> "274-30"
    "DE242.1,[Ladeverkehr 7-18 h frei]"     -> "242.1"
    "1000-32;206"                            -> "1000-32"
    "\"Privatgrundstück\""                  -> None
    "Sinnbild \"Radverkehr\" ..."           -> None

The returned string is the canonical sign code (e.g. ``274-30``) that maps
1:1 to an SVG file in ``viz/symbols/<country>/`` when one exists.
"""

from __future__ import annotations

import re

_COUNTRY = re.compile(r"^[A-Z]{2}:?")
_BRACKET = re.compile(r"^(\d+)\[([\d.\-]+)\]$")
# Colon variant notation: `274:30` and `274.1:30` both render as `274-30`.
# The optional middle `.<digits>` is dropped — used in OSM where a mapper
# specifies the speed explicitly on a zone sign or as shorthand for the
# variant separator.
_DOT_COLON = re.compile(r"^(\d+)(?:\.\d+)?:([\d.\-]+)$")
_CODE = re.compile(r"^[0-9][0-9A-Za-z.\-]*$")
_TRAILING_PARAMS = re.compile(r"\[[^\]]*\]$")

# "Shared family base" SVGs: families whose variants all use the same SVG as
# the base, with the variant number rendered as a text overlay on top. Used
# for codes like `262-X` (Tonnage-Verbot) — visually they're the same red
# ring + white inside; the only difference is the printed number. The base
# SVG already prints one canonical variant, which we don't overlay again.
#
# Each entry: ``"baseline"`` = variant number already painted on the base SVG
# (in German `,` decimal form), ``"unit"`` = suffix appended to the overlay
# text so it reads as e.g. "3,5 t" instead of bare "3,5".
SHARED_FAMILY_BASES = {
    "262": {"baseline": "5,5", "unit": " t"},   # Tonnage-Verbot
}


def collapse_shared_family(code: object) -> tuple[str, str]:
    """If *code* is a variant of a SHARED_FAMILY_BASES entry, collapse it to
    the base code and return the variant text for overlay rendering.

    Returns ``(canonical_code, overlay_text)`` — ``overlay_text`` is empty for
    codes that don't need an overlay (either non-shared families, or the base
    variant that already matches the SVG's printed number). Includes the unit
    suffix when configured.

    Examples (with `SHARED_FAMILY_BASES["262"] = {"baseline": "5,5", "unit": " t"}`)::

        collapse_shared_family("262-3.5") -> ("262", "3,5 t")
        collapse_shared_family("262-12")  -> ("262", "12 t")
        collapse_shared_family("262-5.5") -> ("262", "")     # SVG already shows this
        collapse_shared_family("262")     -> ("262", "")
        collapse_shared_family("237")     -> ("237", "")     # not a shared family
    """
    if not isinstance(code, str) or not code:
        return code if isinstance(code, str) else "", ""
    for base, cfg in SHARED_FAMILY_BASES.items():
        baseline = cfg["baseline"]
        unit = cfg.get("unit", "")
        if code == base:
            return base, ""
        prefix = base + "-"
        if code.startswith(prefix):
            variant = code[len(prefix):]
            variant_de = variant.replace(".", ",")
            if variant_de == baseline:
                return base, ""
            return base, f"{variant_de}{unit}"
    return code, ""


def _normalize_item(part: str) -> str | None:
    """Normalize a single already-split item into a canonical code.

    Strips country prefix, converts ``274[30]`` -> ``274-30``, validates it's a
    sign code. Returns None for free text. Does *not* attempt to handle list
    separators — that's the caller's job.
    """
    if not part:
        return None
    part = _COUNTRY.sub("", part.strip())
    m = _BRACKET.match(part)
    if m:
        part = f"{m.group(1)}-{m.group(2)}"
    else:
        m = _DOT_COLON.match(part)
        if m:
            part = f"{m.group(1)}-{m.group(2)}"
    if not _CODE.match(part):
        return None
    return part


def parse_sign_list(raw: object) -> list[tuple[str, str]]:
    """Parse a full ``sign_list`` into an ordered list of ``(kind, value)`` items.

    ``kind`` is ``"code"`` (the value is a canonical sign code such as
    ``274-30`` or ``1022-10``) or ``"text"`` (the value is a free-text
    annotation such as ``"Altenheim"`` or ``"Lieferverkehr frei"``).

    Examples::

        parse_sign_list('DE:274[30],"Altenheim","Schule"')
        # -> [('code','274-30'), ('text','Altenheim'), ('text','Schule')]

        parse_sign_list('274[30],1012-50,1040-30[06:00-22:00]')
        # -> [('code','274-30'), ('code','1012-50'), ('code','1040-30')]
    """
    if not isinstance(raw, str):
        return []
    items: list[tuple[str, str]] = []
    for part in re.split(r"[,;]", raw):
        part = part.strip()
        if not part:
            continue
        # Quoted free-text: "Altenheim" / 'Altenheim'
        if (part[0] == '"' and part[-1] == '"') or (part[0] == "'" and part[-1] == "'"):
            inner = part[1:-1].strip()
            if inner:
                items.append(("text", inner))
            continue
        # Whole-bracket free-text: [Lieferverkehr frei]
        if part[0] == "[" and part[-1] == "]":
            inner = part[1:-1].strip()
            if inner:
                items.append(("text", inner))
            continue
        # Try as code (also handles 274[30] -> 274-30 inside _normalize_item).
        code = _normalize_item(part)
        if code:
            items.append(("code", code))
            continue
        # Try stripping a trailing [...] parameter block (e.g. time restrictions
        # like 1040-30[06:00-22:00]) and re-normalising the base.
        stripped = _TRAILING_PARAMS.sub("", part)
        if stripped != part:
            code = _normalize_item(stripped)
            if code:
                items.append(("code", code))
                continue
        # Fallback: treat as text.
        items.append(("text", part))
    return items


def normalize_code(raw: object) -> str | None:
    """Return the first canonical code in *raw*, or None if there isn't one.

    Wrapper around :func:`parse_sign_list` for the icon-code use case.
    """
    for kind, value in parse_sign_list(raw):
        if kind == "code":
            return value
    return None


if __name__ == "__main__":
    print("normalize_code:")
    cases_norm = [
        ('DE:274[30],"Altenheim","Schule"', "274-30"),
        ('274[30],"Lärmschutz"', "274-30"),
        ('DE242.1,[Ladeverkehr 7-18 h frei],1022-10', "242.1"),
        ('1000-32;206', "1000-32"),
        ('239;238', "239"),
        ('DE242.1', "242.1"),
        ('"Privatgrundstück"', None),
        ('Sinnbild "Radverkehr" auf der Fahrbahn', None),
        ('[Lieferverkehr frei]', None),
        ('274-30', "274-30"),
        # colon-variant notation: middle ".N" is dropped, ":N" becomes "-N"
        ('DE:274.1:30', "274-30"),
        ('DE:274:30', "274-30"),
        ('DE:262:20', "262-20"),
        (None, None),
        ('', None),
    ]
    for raw, expected in cases_norm:
        got = normalize_code(raw)
        ok = got == expected
        print(f"  {'OK' if ok else 'FAIL'}  {raw!r:55s}  -> {got!r:15s}  (expected {expected!r})")

    print()
    print("parse_sign_list:")
    cases_parse = [
        ('DE:274[30],"Altenheim","Schule"',
         [("code", "274-30"), ("text", "Altenheim"), ("text", "Schule")]),
        ('274[30],1012-50,1040-30[06:00-22:00]',
         [("code", "274-30"), ("code", "1012-50"), ("code", "1040-30")]),
        ('DE242.1,[Ladeverkehr 7-18 h frei],1022-10',
         [("code", "242.1"), ("text", "Ladeverkehr 7-18 h frei"), ("code", "1022-10")]),
        ('1000-32;206', [("code", "1000-32"), ("code", "206")]),
        ('"Privatgrundstück"', [("text", "Privatgrundstück")]),
    ]
    for raw, expected in cases_parse:
        got = parse_sign_list(raw)
        ok = got == expected
        print(f"  {'OK' if ok else 'FAIL'}  {raw!r}")
        if not ok:
            print(f"    got      {got}")
            print(f"    expected {expected}")

    print()
    print("collapse_shared_family:")
    cases_share = [
        ("262", ("262", "")),
        ("262-5.5", ("262", "")),       # baseline already on SVG
        ("262-3.5", ("262", "3,5 t")),
        ("262-12", ("262", "12 t")),
        ("262-26", ("262", "26 t")),
        ("237", ("237", "")),           # not a shared family
        ("274-30", ("274-30", "")),     # not a shared family
        ("", ("", "")),
    ]
    for code, expected in cases_share:
        got = collapse_shared_family(code)
        ok = got == expected
        print(f"  {'OK' if ok else 'FAIL'}  {code!r:12s} -> {got!r:18s}  (expected {expected!r})")
