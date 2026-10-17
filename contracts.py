"""Shared wire format only; contains no agent or evaluation behavior."""

import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    text: str = Field(min_length=1)
    value: JsonValue
    evidence: list[str]

    @field_validator("evidence")
    @classmethod
    def valid_references(cls, values):
        for value in values:
            UUID(value)
        if len(values) != len(set(values)):
            raise ValueError("Duplicate evidence references")
        return values


class FinalAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    answer: JsonValue
    claims: list[Claim]

    @model_validator(mode="after")
    def finite_json(self):
        json.dumps(self.model_dump(), allow_nan=False)
        return self
