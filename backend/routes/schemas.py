"""Shared Pydantic schemas for route requests and responses."""

from pydantic import BaseModel, ConfigDict


class ApiRequestModel(BaseModel):
    """Base for request bodies: rejects NaN/Infinity in every float field.

    Python's JSON parser accepts ``NaN``/``Infinity`` literals and bare
    ``float`` fields let them through, so a single poisoned money value would
    NaN-propagate through every pandas aggregation. Request models with
    numeric fields must inherit from this base instead of ``BaseModel``.
    """

    model_config = ConfigDict(allow_inf_nan=False)


class StatusResponse(BaseModel):
    """Generic ``{"status": ...}`` acknowledgement returned by write endpoints."""

    status: str
