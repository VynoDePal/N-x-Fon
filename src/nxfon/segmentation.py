from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from nxfon.alignment import TimedToken


class SegmentationError(ValueError):
    """Raised when aligned input cannot be deterministically segmented."""


class SegmentationPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_seconds: float = Field(default=3.0, gt=0)
    target_seconds: float = Field(default=12.0, gt=0)
    max_seconds: float = Field(default=15.0, gt=0)


class SegmentPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    segment_id: str
    source_sha256: str
    start_sample: int
    end_sample: int
    sample_rate: int
    text: str
    token_start: int
    token_end: int
    qc_status: Literal["accepted", "review"]
    rejection_reasons: tuple[str, ...] = ()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_seconds(self) -> float:
        return (self.end_sample - self.start_sample) / self.sample_rate


_BOUNDARY_PRIORITY = {
    "sentence": 5,
    "verse": 4,
    "strong_punctuation": 3,
    "word_silence": 2,
    "word": 1,
}


def _validate_inputs(
    tokens: list[TimedToken],
    sample_rate: int,
    policy: SegmentationPolicy,
    source_sha256: str,
) -> None:
    if sample_rate <= 0:
        raise SegmentationError("sample_rate must be positive")
    if not (policy.min_seconds <= policy.target_seconds <= policy.max_seconds):
        raise SegmentationError("policy durations must be ordered")
    if len(source_sha256) != 64 or any(char not in "0123456789abcdef" for char in source_sha256):
        raise SegmentationError("source_sha256 must be lowercase SHA-256")
    previous_end = 0
    for token in tokens:
        if token.start_sample < previous_end:
            raise SegmentationError("token spans must be monotonic and non-overlapping")
        previous_end = token.end_sample


def _stable_id(
    source_sha256: str,
    start_sample: int,
    end_sample: int,
    sample_rate: int,
    text: str,
) -> str:
    canonical = json.dumps(
        {
            "end_sample": end_sample,
            "sample_rate": sample_rate,
            "source_sha256": source_sha256,
            "start_sample": start_sample,
            "text": text,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _make_plan(
    tokens: list[TimedToken],
    first: int,
    last: int,
    sample_rate: int,
    source_sha256: str,
    policy: SegmentationPolicy,
    *,
    unsplittable: bool = False,
) -> SegmentPlan:
    start_sample = tokens[first].start_sample
    end_sample = tokens[last].end_sample
    text = " ".join(token.text for token in tokens[first : last + 1])
    duration = (end_sample - start_sample) / sample_rate
    reasons: list[str] = []
    if unsplittable:
        reasons.append("no_safe_boundary")
    if duration < policy.min_seconds:
        reasons.append("below_min_duration")
    status: Literal["accepted", "review"] = "review" if reasons else "accepted"
    return SegmentPlan(
        segment_id=_stable_id(source_sha256, start_sample, end_sample, sample_rate, text),
        source_sha256=source_sha256,
        start_sample=start_sample,
        end_sample=end_sample,
        sample_rate=sample_rate,
        text=text,
        token_start=first,
        token_end=last,
        qc_status=status,
        rejection_reasons=tuple(reasons),
    )


def _best_cut(
    tokens: list[TimedToken],
    first: int,
    last: int,
    sample_rate: int,
    policy: SegmentationPolicy,
) -> int:
    eligible = [
        index
        for index in range(first, last + 1)
        if (tokens[index].end_sample - tokens[first].start_sample) / sample_rate
        >= policy.min_seconds
    ]
    candidates = eligible or list(range(first, last + 1))
    return max(
        candidates,
        key=lambda index: (
            _BOUNDARY_PRIORITY[tokens[index].boundary_kind],
            -abs(
                (tokens[index].end_sample - tokens[first].start_sample) / sample_rate
                - policy.target_seconds
            ),
            index,
        ),
    )


def plan_segments(
    tokens: list[TimedToken],
    sample_rate: int,
    policy: SegmentationPolicy,
    source_sha256: str,
) -> list[SegmentPlan]:
    """Plan stable sample-exact spans without ever truncating aligned words."""

    _validate_inputs(tokens, sample_rate, policy, source_sha256)
    plans: list[SegmentPlan] = []
    max_samples = round(policy.max_seconds * sample_rate)
    cursor = 0
    while cursor < len(tokens):
        current = tokens[cursor]
        if current.end_sample - current.start_sample > max_samples:
            plans.append(
                _make_plan(
                    tokens,
                    cursor,
                    cursor,
                    sample_rate,
                    source_sha256,
                    policy,
                    unsplittable=True,
                )
            )
            cursor += 1
            continue

        last = cursor
        while (
            last + 1 < len(tokens)
            and tokens[last + 1].end_sample - current.start_sample <= max_samples
        ):
            last += 1

        if last + 1 < len(tokens):
            last = _best_cut(tokens, cursor, last, sample_rate, policy)
        plans.append(_make_plan(tokens, cursor, last, sample_rate, source_sha256, policy))
        cursor = last + 1

    return plans
