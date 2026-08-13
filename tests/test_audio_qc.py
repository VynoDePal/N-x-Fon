from __future__ import annotations

import hashlib
import struct
import wave
from pathlib import Path

import pytest
from pydantic import ValidationError

from nxfon.audio import AudioRenderError, RenderedSegment, render_wav
from nxfon.qc import QCPolicy, classify_segment
from nxfon.segmentation import SegmentPlan

SAMPLE_RATE = 16_000


def write_wav(path: Path, samples: list[int]) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def plan(start: int, end: int, segment_id: str = "a" * 64) -> SegmentPlan:
    return SegmentPlan(
        segment_id=segment_id,
        source_sha256="b" * 64,
        start_sample=start,
        end_sample=end,
        sample_rate=SAMPLE_RATE,
        text="Wá dó.",
        token_start=0,
        token_end=0,
        qc_status="accepted",
    )


def test_render_wav_is_sample_exact_atomic_and_hashed(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    write_wav(source, [0] * SAMPLE_RATE + [8_000] * (2 * SAMPLE_RATE) + [0] * SAMPLE_RATE)
    output_root = tmp_path / "clips"

    rendered = render_wav(source, plan(SAMPLE_RATE, 3 * SAMPLE_RATE), output_root)

    assert rendered.duration_seconds == 2.0
    assert rendered.channels == 1
    assert rendered.sample_rate == SAMPLE_RATE
    assert rendered.path == output_root / f"{'a' * 64}.wav"
    assert rendered.sha256 == hashlib.sha256(rendered.path.read_bytes()).hexdigest()
    assert rendered.peak == pytest.approx(8_000 / 32_768)
    assert not list(output_root.glob("*.part"))
    with wave.open(str(rendered.path), "rb") as clip:
        assert clip.getnframes() == 2 * SAMPLE_RATE


def test_render_refuses_non_pcm16_or_out_of_bounds(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(1)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(b"\x80" * SAMPLE_RATE)

    with pytest.raises(AudioRenderError, match="PCM16"):
        render_wav(source, plan(0, SAMPLE_RATE), tmp_path / "clips")


def rendered_fixture(
    tmp_path: Path,
    *,
    duration: float = 2.0,
    peak: float = 0.2,
    silence_ratio: float = 0.1,
    music: bool = False,
    overlap: bool = False,
) -> RenderedSegment:
    path = tmp_path / "clip.wav"
    path.write_bytes(b"fixture")
    return RenderedSegment(
        segment_id="c" * 64,
        path=path,
        sha256=hashlib.sha256(b"fixture").hexdigest(),
        start_sample=0,
        end_sample=round(duration * SAMPLE_RATE),
        sample_rate=SAMPLE_RATE,
        channels=1,
        duration_seconds=duration,
        peak=peak,
        silence_ratio=silence_ratio,
        music=music,
        overlap=overlap,
    )


@pytest.mark.parametrize(
    ("rendered_kwargs", "text", "reason"),
    [
        ({"peak": 1.0}, "wá", "clipping"),
        ({"silence_ratio": 0.9}, "wá", "excessive_silence"),
        ({"music": True}, "wá", "music"),
        ({"overlap": True}, "wá", "overlap"),
        ({}, "...", "invalid_text"),
        ({"duration": 15.001}, "wá", "duration_above_max"),
    ],
)
def test_quality_failures_are_explicit(
    tmp_path: Path,
    rendered_kwargs: dict[str, float | bool],
    text: str,
    reason: str,
) -> None:
    result = classify_segment(
        rendered_fixture(tmp_path, **rendered_kwargs),
        text,
        QCPolicy(),
    )

    assert result.status == "rejected"
    assert reason in result.reasons


def test_clean_segment_is_accepted(tmp_path: Path) -> None:
    result = classify_segment(rendered_fixture(tmp_path), "É wá ɖò xwé mɛ̌.", QCPolicy())

    assert result.status == "accepted"
    assert result.reasons == ()


def test_rendered_segment_rejects_non_digest_identifier(tmp_path: Path) -> None:
    valid = rendered_fixture(tmp_path)
    payload = valid.model_dump()
    payload["segment_id"] = "../../unsafe"

    with pytest.raises(ValidationError, match="segment_id"):
        RenderedSegment.model_validate(payload)
