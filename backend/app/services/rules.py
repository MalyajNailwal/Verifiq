"""Shared deterministic comparison helpers for cross-check rules.

Deterministic code first (LLM only later for genuinely fuzzy cases).
No LLM calls here — these rules must be reproducible and fast.
"""

import re
from datetime import UTC, datetime

# Name variants commonly seen across Indian land/estate documents.
_NAME_NOISE = {
    "mr",
    "mrs",
    "ms",
    "shri",
    "smt",
    "dr",
    "late",
    "md",
    "mohd",
    "alias",
    "aka",
    "wio",
    "sio",
    "do",
    "s/o",
    "w/o",
    "d/o",
}
_INITIALS_RE = re.compile(r"\b([A-Z])\b\.?")
_MULTISPACE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, strip titles/SxO noise, collapse spaces. Keeps initials as letters."""
    text = name.lower()
    text = re.sub(r"[.,]", " ", text)
    tokens = [t for t in text.split() if t and t not in _NAME_NOISE]
    return " ".join(tokens)


def names_match(a: str | None, b: str | None) -> bool:
    """True if names plausibly refer to the same person.

    Handles: initials (M. Ravi Kumar == Mahesh Ravi Kumar), whitespace/punct
    noise, honorifics. Fuzzy (not exact) — a full token-level match is required.
    """
    if not a or not b:
        return False
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = na.split(), nb.split()
    if len(ta) != len(tb):
        # pad shorter with itself initials? no — different token counts: try initials-only compare
        return _initial_match(ta, tb)
    return all(_token_eq(x, y) for x, y in zip(ta, tb, strict=False))


def _token_eq(x: str, y: str) -> bool:
    if x == y:
        return True
    # one is an initial of the other ("m" vs "mahesh")
    if len(x) == 1 or len(y) == 1:
        return x[0] == y[0]
    # common prefix guard for spelling variants (kumar/kumaar): >=4 char prefix
    if len(x) >= 4 and len(y) >= 4 and x[:4] == y[:4]:
        return True
    return False


def _initial_match(ta: list[str], tb: list[str]) -> bool:
    """Different token counts: match if one is an initial-expansion of the other."""
    if len(ta) > len(tb):
        ta, tb = tb, ta
    # Case A: tb has exactly one extra single-letter initial ("m ravi kumar" == "ravi kumar")
    if len(tb) - len(ta) == 1:
        for i, w in enumerate(tb):
            if len(w) == 1 and tb[:i] + tb[i + 1 :] == ta:
                return True
    # Case B: ta is all initials expanding into tb in order ("m r k" == "mahesh ravi kumar")
    if len(ta) >= 2 and all(len(t) == 1 for t in ta):
        it = iter(tb)
        return all(any(_token_eq(t, w) for w in it) for t in ta)
    return False


def area_to_sqm(area: dict | None) -> float | None:
    """Normalize an area object {value, unit} to square metres. None if unknown."""
    if not isinstance(area, dict):
        return None
    value, unit = area.get("value"), str(area.get("unit", "")).strip().lower()
    if not isinstance(value, (int, float)):
        return None
    factors = {
        "sq m": 1.0,
        "sqm": 1.0,
        "sq mt": 1.0,
        "square meters": 1.0,
        "square feet": 0.092903,
        "sq ft": 0.092903,
        "sqft": 0.092903,
        "square yard": 9.0,
        "sq yd": 9.0,
        "sq yds": 9.0,
        "acre": 4046.86,
        "acres": 4046.86,
        "ac": 4046.86,
        "hectare": 10000.0,
        "hectares": 10000.0,
        "ha": 10000.0,
        "guntha": 101.17,
        "cents": 40.4686,
        "cent": 40.4686,
    }
    factor = factors.get(unit)
    return float(value) * factor if factor else None


def areas_match_within(a: dict | None, b: dict | None, tol_pct: float) -> bool | None:
    """True/False when both areas comparable; None when units unknown/disabled."""
    sa, sb = area_to_sqm(a), area_to_sqm(b)
    if sa is None or sb is None or sb == 0:
        return None
    return abs(sa - sb) / max(sb, sa) * 100.0 <= tol_pct


def date_value(raw: str | None) -> datetime | None:
    """Best-effort ISO date parse (YYYY-MM-DD or YYYY-MM -> first of month)."""
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(text[: 10 if fmt == "%Y-%m-%d" else 7], fmt).replace(
                tzinfo=UTC
            )
        except ValueError:
            continue
    return None


def months_since(d: datetime | None, now: datetime | None = None) -> float | None:
    if d is None:
        return None
    now = now or datetime.now(UTC)
    return (now - d).days / 30.44


def address_sigla(address: str | None) -> set[str]:
    """Cheap address signature: significant tokens (numbers + long words)."""
    if not address:
        return set()
    tokens = re.sub(r"[,./]", " ", address.lower()).split()
    stop = {
        "no",
        "plot",
        "survey",
        "village",
        "road",
        "street",
        "ward",
        "dist",
        "district",
        "taluk",
        "tehsil",
        "block",
        "post",
        "pin",
        "near",
        "opp",
        "behind",
        "and",
    }
    return {t for t in tokens if t not in stop and (t.isdigit() or len(t) >= 4)}
