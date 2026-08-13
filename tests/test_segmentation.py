from __future__ import annotations

import pytest
from pydantic import ValidationError

from nxfon.alignment import TimedToken
from nxfon.segmentation import SegmentationError, SegmentationPolicy, plan_segments

SAMPLE_RATE = 16_000


def token(start: float, end: float, text: str, boundary: str = "word") -> TimedToken:
    return TimedToken(
        start_sample=round(start * SAMPLE_RATE),
        end_sample=round(end * SAMPLE_RATE),
        text=text,
        confidence=0.99,
        boundary_kind=boundary,
    )


def test_planner_never_exceeds_fifteen_seconds() -> None:
    tokens = [
        token(i * 2.0, (i + 1) * 2.0, f"w{i}", "sentence" if i in {4, 7} else "word")
        for i in range(8)
    ]
    plans = plan_segments(tokens, SAMPLE_RATE, SegmentationPolicy(), "a" * 64)

    assert plans
    assert max(plan.duration_seconds for plan in plans) <= 15.0


def test_unsplittable_long_token_requires_review() -> None:
    plans = plan_segments(
        [token(0, 16, "longword")],
        SAMPLE_RATE,
        SegmentationPolicy(),
        "a" * 64,
    )

    assert plans[0].qc_status == "review"
    assert "no_safe_boundary" in plans[0].rejection_reasons


def test_segment_ids_are_stable_when_input_is_repeated() -> None:
    tokens = [token(0, 3, "é"), token(3, 6, "wá", "sentence")]

    first = plan_segments(tokens, SAMPLE_RATE, SegmentationPolicy(), "a" * 64)
    second = plan_segments(tokens, SAMPLE_RATE, SegmentationPolicy(), "a" * 64)

    assert [plan.segment_id for plan in first] == [plan.segment_id for plan in second]


def test_exact_fifteen_seconds_is_accepted() -> None:
    plan = plan_segments(
        [token(0, 15, "safe")],
        SAMPLE_RATE,
        SegmentationPolicy(),
        "b" * 64,
    )[0]

    assert plan.duration_seconds == 15.0
    assert plan.qc_status == "accepted"


def test_span_above_limit_is_split_at_word_boundary() -> None:
    plans = plan_segments(
        [token(0, 7.5, "one"), token(7.5, 15.001, "two")],
        SAMPLE_RATE,
        SegmentationPolicy(),
        "c" * 64,
    )

    assert len(plans) == 2
    assert max(plan.duration_seconds for plan in plans) <= 15.0


def test_overlapping_or_reordered_tokens_are_rejected() -> None:
    tokens = [token(2, 4, "later"), token(0, 2, "earlier")]

    with pytest.raises(SegmentationError, match="monotonic"):
        plan_segments(tokens, SAMPLE_RATE, SegmentationPolicy(), "d" * 64)


def test_segment_plan_rejects_non_digest_identifier() -> None:
    valid = plan_segments(
        [token(0, 3, "safe")],
        SAMPLE_RATE,
        SegmentationPolicy(),
        "e" * 64,
    )[0]
    payload = valid.model_dump(exclude_computed_fields=True)
    payload["segment_id"] = "../unsafe"

    with pytest.raises(ValidationError, match="segment_id"):
        type(valid).model_validate(payload)
