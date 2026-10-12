"""Unit tests for deterministic comparison helpers (rules.py)."""

from datetime import UTC, datetime

from app.services.rules import (
    area_to_sqm,
    areas_match_within,
    date_value,
    months_since,
    names_match,
    normalize_name,
)


class TestNames:
    def test_exact_after_normalization(self) -> None:
        assert names_match("Mr. Ravi  Kumar.", "ravi kumar")

    def test_initials_match_full(self) -> None:
        assert names_match("M. Ravi Kumar", "Mahesh Ravi Kumar")
        assert names_match("R. Kumar", "Ravi Kumar")

    def test_spelling_variant_4char_prefix(self) -> None:
        assert names_match("Ananya Deshpande", "Ananiya Deshpande")  # Anan| prefix ok
        assert names_match("Kumar Mahesh", "Kumaar Mahesh")

    def test_clear_mismatch(self) -> None:
        assert not names_match("Ravi Kumar", "Suresh Patel")
        assert not names_match("Ananya Deshpande", "Vikram Deshpande")

    def test_noise_words_ignored(self) -> None:
        assert names_match("Smt. Ananya Deshpande", "Ananya Deshpande")
        assert names_match("Ananya (Late)", "Ananya Deshpande") is False
        assert "late" not in normalize_name("Late Ananya")
        assert normalize_name("Shri. M. Ravi") == "m ravi"

    def test_empty_or_none(self) -> None:
        assert not names_match(None, "x")
        assert not names_match("", None)


class TestAreas:
    def test_unit_normalization(self) -> None:
        assert area_to_sqm({"value": 100, "unit": "sq m"}) == 100.0
        assert area_to_sqm({"value": 100, "unit": "sq ft"}) == pytest_approx(9.2903)
        assert area_to_sqm({"value": 1, "unit": "acre"}) == pytest_approx(4046.86)
        assert area_to_sqm({"value": 2, "unit": "hectare"}) == pytest_approx(20000.0)

    def test_unknown_unit_returns_none(self) -> None:
        assert area_to_sqm({"value": 5, "unit": "cubits"}) is None
        assert area_to_sqm(None) is None
        assert area_to_sqm({"value": "lots", "unit": "sq m"}) is None

    def test_tolerance_logic(self) -> None:
        a1 = {"value": 100.0, "unit": "sq m"}
        a2 = {"value": 101.5, "unit": "sq m"}
        a3 = {"value": 110.0, "unit": "sq m"}
        assert areas_match_within(a1, a2, tol_pct=2.0) is True
        assert areas_match_within(a1, a3, tol_pct=2.0) is False
        assert areas_match_within(a1, {"value": 3, "unit": "cubits"}, 2.0) is None


class TestDates:
    def test_parse_iso(self) -> None:
        d = date_value("2025-01-12")
        assert d is not None and d.year == 2025 and d.month == 1 and d.day == 12
        assert date_value("2025-01").month == 1

    def test_garbage_is_none(self) -> None:
        assert date_value("not a date") is None
        assert date_value(None) is None

    def test_months_since(self) -> None:
        d = datetime(2024, 1, 1, tzinfo=UTC)
        assert months_since(d, now=datetime(2025, 1, 1, tzinfo=UTC)) > 11.5
        assert months_since(None) is None


def pytest_approx(x: float) -> float:
    """Pointer to pytest.approx kept short; avoids repeated imports in tests."""
    import pytest

    return pytest.approx(x)
