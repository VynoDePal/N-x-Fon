from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BoundaryKind = Literal["sentence", "verse", "strong_punctuation", "word_silence", "word"]


class TimedToken(BaseModel):
    """A word-level alignment span expressed in exact source samples."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start_sample: int = Field(ge=0)
    end_sample: int = Field(gt=0)
    text: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    boundary_kind: BoundaryKind

    @model_validator(mode="after")
    def validate_span(self) -> TimedToken:
        if self.end_sample <= self.start_sample:
            raise ValueError("end_sample must be greater than start_sample")
        return self
