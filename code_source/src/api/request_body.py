"""Base of every request body: unknown fields refused, surrounding spaces stripped."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
