from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from nxfon.schemas import MediaProbe, RightsDecision, SourceMedia


class InventoryError(ValueError):
    """Raised when a source cannot be safely inventoried."""


Probe = Callable[[Path], MediaProbe | Mapping[str, Any]]


def _local_file(path: str | Path, source_root: Path | None) -> Path:
    raw = str(path)
    if urlsplit(raw).scheme or "://" in raw:
        raise InventoryError("source must be a local file")

    candidate = Path(path)
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise InventoryError("local source file is unavailable") from exc

    if source_root is not None:
        try:
            root = source_root.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise InventoryError("source root is unavailable") from exc
        if not resolved.is_relative_to(root):
            raise InventoryError("source escapes configured source root")
    if not resolved.is_file():
        raise InventoryError("local source must be a regular file")
    if resolved.stat().st_size <= 0:
        raise InventoryError("local source must not be empty")
    return resolved


def _streaming_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_source(
    path: str | Path,
    decision: RightsDecision,
    probe: Probe,
    *,
    source_root: Path | None = None,
) -> SourceMedia:
    """Inventory one authorized local source without mutating it."""

    if decision.action != "ingest" or decision.state != "AUTHORIZED_LOCAL":
        raise InventoryError("an authorized ingest decision is required")
    local_path = _local_file(path, source_root)
    try:
        metadata = probe(local_path)
        parsed_probe = (
            metadata if isinstance(metadata, MediaProbe) else MediaProbe.model_validate(metadata)
        )
    except (ValidationError, TypeError, ValueError, OSError) as exc:
        raise InventoryError(f"invalid media probe metadata: {exc}") from exc

    return SourceMedia(
        source_id=decision.source_id,
        path=local_path,
        sha256=_streaming_sha256(local_path),
        size_bytes=local_path.stat().st_size,
        probe=parsed_probe,
    )


def ffprobe_media(path: Path) -> MediaProbe:
    """Probe media with a fixed argv; shell interpretation is never involved."""

    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels,bit_rate:format=duration,bit_rate",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(completed.stdout)
        stream = payload["streams"][0]
        container = payload.get("format", {})
        duration_ms = round(float(container["duration"]) * 1000)
        bitrate = int(stream.get("bit_rate") or container.get("bit_rate") or 0)
        return MediaProbe(
            codec=stream["codec_name"],
            sample_rate=int(stream["sample_rate"]),
            channels=int(stream["channels"]),
            bitrate=bitrate,
            duration_ms=duration_ms,
        )
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        ValidationError,
    ) as exc:
        raise InventoryError(f"ffprobe failed for local source: {exc}") from exc
