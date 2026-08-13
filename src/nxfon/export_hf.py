from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Callable, Mapping
from importlib.resources import files
from pathlib import Path
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from nxfon.rights import RightsError
from nxfon.schemas import RightsDecision, Sha256Hex


class BookRecord(TypedDict):
    ordinal: int
    code: str
    name: str


class ExportRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    segment_id: Sha256Hex
    audio_path: Path
    audio_sha256: Sha256Hex
    source_sha256: Sha256Hex
    book: str = Field(min_length=3, max_length=3)
    chapter: int = Field(gt=0)
    verse_start: int = Field(gt=0)
    verse_end: int = Field(gt=0)
    text_original: str = Field(min_length=1)
    text_nfc: str = Field(min_length=1)
    text_acoustic: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0, le=15.0)
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)
    qc_status: Literal["accepted", "review", "rejected"]


class ExportSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    output_root: Path
    rows_by_split: dict[str, int]
    total_rows: int = Field(ge=0)


def load_book_registry(path: Path | None = None) -> list[BookRecord]:
    try:
        text = (
            path.read_text(encoding="utf-8")
            if path is not None
            else files("nxfon").joinpath("data/books.nt.json").read_text(encoding="utf-8")
        )
        payload = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid New Testament registry: {exc}") from exc
    if not isinstance(payload, list) or len(payload) != 27:
        raise ValueError("New Testament registry must contain exactly 27 books")
    books: list[BookRecord] = []
    for expected_ordinal, entry in enumerate(payload, start=1):
        if not isinstance(entry, dict):
            raise ValueError("New Testament registry entry must be an object")
        if set(entry) != {"ordinal", "code", "name"}:
            raise ValueError("New Testament registry entry has unexpected fields")
        record = BookRecord(
            ordinal=entry["ordinal"],
            code=entry["code"],
            name=entry["name"],
        )
        if record["ordinal"] != expected_ordinal:
            raise ValueError("New Testament registry ordinals must be contiguous")
        books.append(record)
    codes = [book["code"] for book in books]
    if len(set(codes)) != 27:
        raise ValueError("New Testament registry codes must be unique")
    return books


def _require_publish(decision: RightsDecision | None) -> RightsDecision:
    if decision is None or decision.action != "publish" or not decision.state.startswith(
        "AUTHORIZED_"
    ):
        raise RightsError("publish authorization is required")
    if decision.state == "AUTHORIZED_LOCAL":
        raise RightsError("publish authorization is required")
    return decision


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_line(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def export_audiofolder(
    rows: list[ExportRow],
    output_root: Path,
    decision: RightsDecision | None,
    split_map: Mapping[str, str],
    *,
    publisher: Callable[[Path], None] | None = None,
) -> ExportSummary:
    """Create a deterministic AudioFolder tree after a fail-closed publication gate."""

    authorized = _require_publish(decision)
    registry_codes = {book["code"] for book in load_book_registry()}
    accepted = sorted(
        (row for row in rows if row.qc_status == "accepted"),
        key=lambda row: row.segment_id,
    )
    if len({row.segment_id for row in accepted}) != len(accepted):
        raise ValueError("accepted segment IDs must be unique")

    prepared: list[tuple[ExportRow, str]] = []
    for row in accepted:
        if row.book not in registry_codes:
            raise ValueError(f"unknown New Testament book code: {row.book}")
        chapter_key = f"{row.book}:{row.chapter}"
        split = split_map.get(chapter_key)
        if not split or "/" in split or split in {".", ".."}:
            raise ValueError(f"missing or invalid chapter split: {chapter_key}")
        if not row.audio_path.is_file():
            raise ValueError(f"audio file is unavailable: {row.segment_id}")
        if _sha256(row.audio_path) != row.audio_sha256:
            raise ValueError(f"audio checksum mismatch: {row.segment_id}")
        prepared.append((row, split))

    output_root.mkdir(parents=True, exist_ok=True)
    metadata_by_split: dict[str, list[str]] = {}
    provenance_by_split: dict[str, list[str]] = {}
    for row, split in prepared:
        split_root = output_root / split
        audio_root = split_root / "audio"
        audio_root.mkdir(parents=True, exist_ok=True)
        relative_audio = Path("audio") / f"{row.segment_id}.wav"
        shutil.copyfile(row.audio_path, split_root / relative_audio)
        metadata_by_split.setdefault(split, []).append(
            _json_line(
                {
                    "book": row.book,
                    "chapter": row.chapter,
                    "duration_seconds": row.duration_seconds,
                    "file_name": relative_audio.as_posix(),
                    "segment_id": row.segment_id,
                    "text": row.text_nfc,
                    "text_acoustic": row.text_acoustic,
                    "text_original": row.text_original,
                    "verse_end": row.verse_end,
                    "verse_start": row.verse_start,
                }
            )
        )
        provenance_by_split.setdefault(split, []).append(
            _json_line(
                {
                    "audio_sha256": row.audio_sha256,
                    "channels": row.channels,
                    "sample_rate": row.sample_rate,
                    "segment_id": row.segment_id,
                    "source_id": authorized.source_id,
                    "source_sha256": row.source_sha256,
                }
            )
        )

    for split in sorted(metadata_by_split):
        split_root = output_root / split
        (split_root / "metadata.jsonl").write_text(
            "".join(metadata_by_split[split]), encoding="utf-8"
        )
        (split_root / "provenance.jsonl").write_text(
            "".join(provenance_by_split[split]), encoding="utf-8"
        )
    (output_root / "rights-summary.json").write_text(
        json.dumps(
            {
                "distribution_state": authorized.state,
                "permission_contents_included": False,
                "source_id": authorized.source_id,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    counts = Counter(split for _, split in prepared)
    rows_by_split = {split: counts[split] for split in sorted(counts)}
    summary = ExportSummary(
        output_root=output_root,
        rows_by_split=rows_by_split,
        total_rows=len(prepared),
    )
    _require_publish(authorized)
    if publisher is not None:
        publisher(output_root)
    return summary
