from __future__ import annotations

import hashlib
import os
import sys
import uuid
import wave
from array import array
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from nxfon.schemas import Sha256Hex
from nxfon.segmentation import SegmentPlan


class AudioRenderError(ValueError):
    """Raised when a source cannot be rendered losslessly and safely."""


class RenderedSegment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    segment_id: Sha256Hex
    path: Path
    sha256: Sha256Hex
    start_sample: int = Field(ge=0)
    end_sample: int = Field(gt=0)
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)
    duration_seconds: float = Field(gt=0)
    peak: float = Field(ge=0.0, le=1.0)
    silence_ratio: float = Field(ge=0.0, le=1.0)
    music: bool = False
    overlap: bool = False


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _measure_pcm16(frames: bytes) -> tuple[float, float]:
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        raise AudioRenderError("rendered segment has no samples")
    peak = max(abs(sample) for sample in samples) / 32_768
    silence_threshold = round(32_767 * 0.01)
    silent = sum(abs(sample) <= silence_threshold for sample in samples)
    return peak, silent / len(samples)


def render_wav(
    source: Path,
    plan: SegmentPlan,
    output_root: Path,
    *,
    music: bool = False,
    overlap: bool = False,
) -> RenderedSegment:
    """Render a sample-exact PCM16 mono WAV using an atomic destination replace."""

    source_path = source.resolve()
    if not source_path.is_file():
        raise AudioRenderError("source WAV is unavailable")
    try:
        with wave.open(str(source_path), "rb") as input_wav:
            if (
                input_wav.getcomptype() != "NONE"
                or input_wav.getsampwidth() != 2
                or input_wav.getnchannels() != 1
            ):
                raise AudioRenderError("Alpha renderer requires mono PCM16 WAV")
            if input_wav.getframerate() != plan.sample_rate:
                raise AudioRenderError("source and plan sample rates differ")
            if plan.end_sample > input_wav.getnframes():
                raise AudioRenderError("segment boundaries exceed source frames")
            if plan.end_sample <= plan.start_sample:
                raise AudioRenderError("segment boundaries are empty")
            input_wav.setpos(plan.start_sample)
            frame_count = plan.end_sample - plan.start_sample
            frames = input_wav.readframes(frame_count)
    except (OSError, EOFError, wave.Error) as exc:
        raise AudioRenderError(f"unable to read source WAV: {exc}") from exc

    if len(frames) != frame_count * 2:
        raise AudioRenderError("source returned fewer frames than requested")
    peak, silence_ratio = _measure_pcm16(frames)
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / f"{plan.segment_id}.wav"
    temporary = output_root / f".{plan.segment_id}.{uuid.uuid4().hex}.part"
    try:
        with temporary.open("wb") as raw_output:
            with wave.open(raw_output, "wb") as output_wav:
                output_wav.setnchannels(1)
                output_wav.setsampwidth(2)
                output_wav.setframerate(plan.sample_rate)
                output_wav.writeframes(frames)
            raw_output.flush()
            os.fsync(raw_output.fileno())
        os.replace(temporary, destination)
    except (OSError, wave.Error) as exc:
        raise AudioRenderError(f"unable to write rendered WAV: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)

    return RenderedSegment(
        segment_id=plan.segment_id,
        path=destination,
        sha256=_digest(destination),
        start_sample=plan.start_sample,
        end_sample=plan.end_sample,
        sample_rate=plan.sample_rate,
        channels=1,
        duration_seconds=frame_count / plan.sample_rate,
        peak=peak,
        silence_ratio=silence_ratio,
        music=music,
        overlap=overlap,
    )
