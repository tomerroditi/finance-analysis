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

from typing import Any

import pandas as pd
from pydantic import TypeAdapter

from backend.utils.json_response import (
    SafeJSONResponse,
    records_response,
    sanitize_non_finite,
)


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



class TestRecordsResponse:
    """The transactions list's frame-level encoder must say what the old path said.

    The old path was ``df.to_dict(orient="records")`` returned under a
    ``list[dict[str, Any]]`` annotation: FastAPI validated and serialised it
    through pydantic in JSON mode, then :class:`SafeJSONResponse` encoded it.
    """

    @staticmethod
    def _frame() -> pd.DataFrame:
        """A frame with NaN, timestamps, string dates and split rows."""
        return pd.DataFrame(
            {
                "unique_id": [1, "split_7", 3],
                "date": ["2024-01-05", "2024-01-06", "2024-01-07"],
                "amount": [-149.78, -218.62, 0.1 + 0.2],
                "category": ["Food", None, "Home"],
                "split_id": [float("nan"), 7.0, float("nan")],
                "parent_unique_id": [float("nan"), 2.0, float("nan")],
                "parent_amount": [float("nan"), -312.32, float("nan")],
                "created_at": pd.to_datetime(
                    [
                        "2026-10-09 22:37:15",
                        "2026-10-10 08:00:00",
                        "2026-10-09 22:37:15.250000",
                    ],
                    format="ISO8601",
                ),
                "count": [1, 2, 3],
                "flag": [True, False, True],
                "note": ["שלום", "", None],
            }
        )

    @staticmethod
    def _old_body(df: pd.DataFrame) -> bytes:
        """Encode ``df`` the way the route used to."""
        records = df.to_dict(orient="records")
        python = TypeAdapter(list[dict[str, Any]]).dump_python(records, mode="json")
        return SafeJSONResponse(python).body

    def test_matches_the_old_encoding(self):
        """Same keys, null for NaN, same numbers, ISO timestamps."""
        df = self._frame()

        new = json.loads(records_response(df).body)
        old = json.loads(self._old_body(df))

        assert new == old
        assert new[0]["split_id"] is None
        assert new[2]["created_at"] == "2026-10-09T22:37:15.250000"
        assert new[1]["parent_unique_id"] == 2.0
        assert new[2]["amount"] == 0.1 + 0.2

    def test_missing_timestamp_becomes_null(self):
        """NaT is missing like NaN — the old path could not encode it at all."""
        df = pd.DataFrame({"at": pd.to_datetime(["2024-01-01", None])})

        body = json.loads(records_response(df).body)

        assert body == [{"at": "2024-01-01T00:00:00"}, {"at": None}]

    def test_infinity_becomes_null(self):
        """A non-finite value can never produce invalid JSON."""
        df = pd.DataFrame({"amount": [float("inf"), 1.5]})

        body = json.loads(records_response(df).body)

        assert body == [{"amount": None}, {"amount": 1.5}]

    def test_an_empty_frame_is_an_empty_list(self):
        """No rows encode as ``[]``."""
        assert json.loads(records_response(pd.DataFrame()).body) == []


class TestSafeJSONResponseFastPath:
    """The encoder tries the C path first and walks only on a non-finite value."""

    def test_clean_payload_skips_the_walk(self, monkeypatch):
        """An all-finite payload never pays for the Python walk."""
        from backend.utils import json_response

        def fail(value):
            raise AssertionError("walked a clean payload")

        monkeypatch.setattr(json_response, "sanitize_non_finite", fail)
        payload = {"rows": [{"amount": 1.5, "name": "x"}]}

        assert json.loads(SafeJSONResponse(payload).body) == payload

    def test_dirty_payload_is_still_scrubbed(self):
        """A NaN deep inside still comes out as null."""
        payload = {"rows": [{"amount": float("nan"), "tags": (1, float("inf"))}]}

        assert json.loads(SafeJSONResponse(payload).body) == {
            "rows": [{"amount": None, "tags": [1, None]}]
        }
