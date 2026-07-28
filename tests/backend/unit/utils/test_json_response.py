"""Tests for the non-finite-float-safe JSON response class.

The bug these lock down: pandas represents SQL NULL as ``NaN``, most
payloads here are DataFrame-derived via ``to_dict(orient="records")``, and
Starlette's default ``JSONResponse`` dumps with ``allow_nan=False`` — so a
single ``NaN`` raised ``ValueError`` and 500'd the endpoint. A pending
refund saved without a note was enough to take down the whole refunds list
under pandas 3.
"""

import json
import math

import pytest

from backend.utils.json_response import SafeJSONResponse, sanitize_non_finite


class TestSanitizeNonFinite:
    """Tests for the recursive NaN/Infinity scrubber."""

    @pytest.mark.parametrize(
        "value", [float("nan"), float("inf"), float("-inf")]
    )
    def test_non_finite_scalars_become_none(self, value):
        """Verify NaN and both infinities collapse to None."""
        assert sanitize_non_finite(value) is None

    def test_finite_floats_are_untouched(self):
        """Verify ordinary numbers pass through unchanged."""
        assert sanitize_non_finite(3.5) == 3.5
        assert sanitize_non_finite(0.0) == 0.0
        assert sanitize_non_finite(-12.25) == -12.25

    def test_nested_structures_are_walked(self):
        """Verify NaN is scrubbed inside nested dicts and lists."""
        payload = {
            "rows": [
                {"notes": float("nan"), "amount": 7.0},
                {"notes": "ok", "amount": float("-inf")},
            ],
            "meta": {"ratio": float("inf"), "count": 2},
        }
        assert sanitize_non_finite(payload) == {
            "rows": [
                {"notes": None, "amount": 7.0},
                {"notes": "ok", "amount": None},
            ],
            "meta": {"ratio": None, "count": 2},
        }

    def test_non_float_types_pass_through(self):
        """Verify strings, ints, bools and None are left alone."""
        payload = {"a": "x", "b": 1, "c": True, "d": None}
        assert sanitize_non_finite(payload) == payload

    def test_tuples_become_lists(self):
        """Verify tuples are normalised to lists, as JSON requires anyway."""
        assert sanitize_non_finite(({"v": float("nan")},)) == [{"v": None}]


class TestSafeJSONResponse:
    """Tests for the response class wired in as the app default."""

    def test_renders_nan_as_null(self):
        """Verify a NaN field serialises to null rather than raising."""
        body = SafeJSONResponse({"notes": float("nan"), "amount": 7.0}).body
        assert json.loads(body) == {"notes": None, "amount": 7.0}

    def test_output_is_strict_json(self):
        """Verify the body never contains the invalid bare NaN/Infinity tokens.

        ``allow_nan=True`` would also avoid the exception, but emits tokens
        the browser's JSON.parse rejects — so assert strict parsing.
        """
        body = SafeJSONResponse([{"a": float("nan")}, {"b": float("inf")}]).body
        assert b"NaN" not in body and b"Infinity" not in body
        json.loads(
            body,
            parse_constant=lambda c: pytest.fail(f"non-strict JSON constant: {c}"),
        )

    def test_default_starlette_behaviour_would_have_raised(self):
        """Pin why this class exists: the stdlib default rejects NaN."""
        with pytest.raises(ValueError):
            json.dumps({"notes": float("nan")}, allow_nan=False)

    def test_ordinary_payloads_are_unaffected(self):
        """Verify a NaN-free payload round-trips identically."""
        payload = {"rows": [{"id": 1, "name": "x", "amount": -12.5}]}
        assert json.loads(SafeJSONResponse(payload).body) == payload

    def test_app_uses_it_as_the_default_response_class(self):
        """Verify the class is actually wired into the app, not just present.

        Without this, the unit tests above still pass while every
        DataFrame-backed endpoint 500s again — the class only helps if the
        FastAPI constructor keeps using it.
        """
        from backend.main import app

        default = app.router.default_response_class
        resolved = getattr(default, "value", default)
        assert resolved is SafeJSONResponse

    def test_math_isfinite_contract(self):
        """Sanity-pin the predicate the scrubber relies on."""
        assert math.isfinite(1.0)
        assert not math.isfinite(float("nan"))
