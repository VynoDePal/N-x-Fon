from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from nxfon.inventory import InventoryError, inventory_source
from nxfon.schemas import RightsDecision


@pytest.fixture
def authorized_decision() -> RightsDecision:
    return RightsDecision(
        state="AUTHORIZED_LOCAL",
        action="ingest",
        source_id="FONBSB-NONDRAMA",
    )


def test_inventory_hashes_local_bytes_without_modifying_source(
    tmp_path: Path,
    authorized_decision: RightsDecision,
) -> None:
    source = tmp_path / "chapter.wav"
    payload = b"immutable-audio-fixture"
    source.write_bytes(payload)
    before = source.stat().st_mtime_ns

    media = inventory_source(
        source,
        authorized_decision,
        lambda _: {
            "codec": "pcm_s16le",
            "sample_rate": 16_000,
            "channels": 1,
            "bitrate": 256_000,
            "duration_ms": 2_000,
        },
    )

    assert media.sha256 == hashlib.sha256(payload).hexdigest()
    assert media.path == source.resolve()
    assert source.stat().st_mtime_ns == before


def test_inventory_refuses_urls(authorized_decision: RightsDecision) -> None:
    with pytest.raises(InventoryError, match="local"):
        inventory_source(
            "https://example.invalid/audio.mp3",
            authorized_decision,
            lambda _: {},
        )


def test_inventory_refuses_non_ingest_decision(tmp_path: Path) -> None:
    source = tmp_path / "chapter.wav"
    source.write_bytes(b"audio")
    publish_decision = RightsDecision(
        state="AUTHORIZED_PRIVATE_DISTRIBUTION",
        action="publish",
        source_id="FONBSB-NONDRAMA",
    )

    with pytest.raises(InventoryError, match="ingest"):
        inventory_source(source, publish_decision, lambda _: {})


def test_inventory_refuses_symlink_escape(
    tmp_path: Path,
    authorized_decision: RightsDecision,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"audio")
    link = source_root / "chapter.wav"
    link.symlink_to(outside)

    with pytest.raises(InventoryError, match="source root"):
        inventory_source(link, authorized_decision, lambda _: {}, source_root=source_root)


@pytest.mark.parametrize(
    ("probe_result", "message"),
    [
        (
            {
                "codec": "pcm_s16le",
                "sample_rate": 16_000,
                "channels": 3,
                "bitrate": 1,
                "duration_ms": 1,
            },
            "channels",
        ),
        (
            {
                "codec": "pcm_s16le",
                "sample_rate": 16_000,
                "channels": 1,
                "bitrate": 1,
                "duration_ms": 0,
            },
            "duration",
        ),
    ],
)
def test_inventory_rejects_invalid_probe_metadata(
    tmp_path: Path,
    authorized_decision: RightsDecision,
    probe_result: dict[str, int | str],
    message: str,
) -> None:
    source = tmp_path / "chapter.wav"
    source.write_bytes(b"audio")

    with pytest.raises(InventoryError, match=message):
        inventory_source(source, authorized_decision, lambda _: probe_result)
