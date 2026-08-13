from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nxfon.export_hf import ExportRow, export_audiofolder, load_book_registry
from nxfon.rights import RightsError
from nxfon.schemas import RightsDecision


@pytest.fixture
def publish_decision() -> RightsDecision:
    return RightsDecision(
        state="AUTHORIZED_PRIVATE_DISTRIBUTION",
        action="publish",
        source_id="FONBSB-NONDRAMA",
    )


def accepted_rows(tmp_path: Path) -> list[ExportRow]:
    rows: list[ExportRow] = []
    for chapter in (1, 2):
        for verse in (1, 2):
            segment_id = f"{chapter}{verse}" * 32
            audio = tmp_path / f"{segment_id}.wav"
            payload = f"audio-{chapter}-{verse}".encode()
            audio.write_bytes(payload)
            rows.append(
                ExportRow(
                    segment_id=segment_id,
                    audio_path=audio,
                    audio_sha256=hashlib.sha256(payload).hexdigest(),
                    source_sha256="b" * 64,
                    book="MRK",
                    chapter=chapter,
                    verse_start=verse,
                    verse_end=verse,
                    text_original="Wá dó.",
                    text_nfc="Wá dó.",
                    text_acoustic="Wá dó",
                    duration_seconds=2.0,
                    sample_rate=16_000,
                    channels=1,
                    qc_status="accepted",
                )
            )
    return rows


def test_export_is_blocked_before_any_publisher_call(tmp_path: Path) -> None:
    called = False

    def publisher(_: Path) -> None:
        nonlocal called
        called = True

    with pytest.raises(RightsError, match="publish"):
        export_audiofolder([], tmp_path / "export", None, {}, publisher=publisher)
    assert called is False
    assert not (tmp_path / "export").exists()


def test_chapter_split_prevents_clip_level_leakage(
    tmp_path: Path,
    publish_decision: RightsDecision,
) -> None:
    output = tmp_path / "export"
    summary = export_audiofolder(
        accepted_rows(tmp_path),
        output,
        publish_decision,
        {"MRK:1": "train", "MRK:2": "validation"},
        publisher=None,
    )

    assert summary.rows_by_split == {"train": 2, "validation": 2}
    train_rows = [
        json.loads(line) for line in (output / "train" / "metadata.jsonl").read_text().splitlines()
    ]
    validation_rows = [
        json.loads(line)
        for line in (output / "validation" / "metadata.jsonl").read_text().splitlines()
    ]
    assert {row["chapter"] for row in train_rows} == {1}
    assert {row["chapter"] for row in validation_rows} == {2}
    assert all(not Path(row["file_name"]).is_absolute() for row in train_rows)


def test_only_accepted_rows_are_copied(
    tmp_path: Path,
    publish_decision: RightsDecision,
) -> None:
    rows = accepted_rows(tmp_path)
    rows[0] = rows[0].model_copy(update={"qc_status": "rejected"})

    summary = export_audiofolder(
        rows,
        tmp_path / "export",
        publish_decision,
        {"MRK:1": "train", "MRK:2": "validation"},
    )

    assert summary.rows_by_split == {"train": 1, "validation": 2}


def test_nt_registry_contains_twenty_seven_unique_books() -> None:
    books = load_book_registry()

    assert len(books) == 27
    assert len({book["code"] for book in books}) == 27
    assert books[0]["code"] == "MAT"
    assert books[-1]["code"] == "REV"


def test_export_row_rejects_path_traversal_segment_id(tmp_path: Path) -> None:
    valid = accepted_rows(tmp_path)[0]
    payload = valid.model_dump()
    payload["segment_id"] = "../../outside"

    with pytest.raises(ValidationError, match="segment_id"):
        ExportRow.model_validate(payload)
