from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from nxfon.audio import RenderedSegment
from nxfon.text import TextIntegrityError, normalize_fongbe


class QCPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_seconds: float = Field(default=1.0, gt=0)
    max_seconds: float = Field(default=15.0, gt=0)
    clipping_threshold: float = Field(default=0.999, gt=0, le=1)
    max_silence_ratio: float = Field(default=0.5, ge=0, lt=1)


class QCResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    segment_id: str
    status: Literal["accepted", "rejected"]
    reasons: tuple[str, ...]


def classify_segment(rendered: RenderedSegment, text: str, policy: QCPolicy) -> QCResult:
    """Classify a rendered segment using explicit, auditable observations."""

    reasons: list[str] = []
    if rendered.duration_seconds < policy.min_seconds:
        reasons.append("duration_below_min")
    if rendered.duration_seconds > policy.max_seconds:
        reasons.append("duration_above_max")
    if rendered.peak >= policy.clipping_threshold:
        reasons.append("clipping")
    if rendered.silence_ratio > policy.max_silence_ratio:
        reasons.append("excessive_silence")
    if rendered.music:
        reasons.append("music")
    if rendered.overlap:
        reasons.append("overlap")
    try:
        normalize_fongbe(text)
    except TextIntegrityError:
        reasons.append("invalid_text")

    status: Literal["accepted", "rejected"] = "rejected" if reasons else "accepted"
    return QCResult(segment_id=rendered.segment_id, status=status, reasons=tuple(reasons))
