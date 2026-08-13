from __future__ import annotations

import hashlib
import json
import struct
import unicodedata
import wave
from datetime import date
from pathlib import Path

import yaml
from typer.testing import CliRunner

from nxfon.audio import RenderedSegment, render_wav
from nxfon.cli import app
from nxfon.export_hf import ExportRow
from nxfon.segmentation import SegmentPlan
from nxfon.text import normalize_fongbe

runner = CliRunner()
SAMPLE_RATE = 16_000


def write_rights(tmp_path: Path, *, approved: bool) -> tuple[Path, Path]:
    permission_root = tmp_path / "permissions"
    permission_root.mkdir()
    permission = permission_root / "grant.txt"
    permission.write_text("synthetic fixture grant", encoding="utf-8")
    state = "approved" if approved else "blocked"
    record = {
        "schema_version": "1",
        "dataset_id": "n-x-fon-bible-15s",
        "source_id": "FONBSB-NONDRAMA",
        "audio_rights": state,
        "text_rights": state,
        "ml_rights": state,
        "distribution": "private" if approved else "none",
        "permission_reference": "grant.txt",
        "permission_document_sha256": hashlib.sha256(permission.read_bytes()).hexdigest(),
        "effective_date": date.today().isoformat(),
        "expires_date": None,
        "authorized_uses": ["machine_learning"] if approved else [],
    }
    rights_file = tmp_path / f"rights-{state}.yaml"
    rights_file.write_text(yaml.safe_dump(record, sort_keys=True), encoding="utf-8")
    return rights_file, permission_root


def write_synthetic_wav(path: Path) -> None:
    samples = [5_000] * (6 * SAMPLE_RATE)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def test_blocked_ingestion_fails_before_inventory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rights_file, permission_root = write_rights(tmp_path, approved=False)
    source = tmp_path / "protected.wav"
    source.write_bytes(b"must-not-be-read")
    called = False

    def forbidden_inventory(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("inventory must not run")

    monkeypatch.setattr("nxfon.cli.inventory_source", forbidden_inventory)
    result = runner.invoke(
        app,
        [
            "ingest",
            str(source),
            "--rights-file",
            str(rights_file),
            "--permission-root",
            str(permission_root),
            "--output",
            str(tmp_path / "inventory.json"),
        ],
    )

    assert result.exit_code != 0
    assert called is False
    assert not (tmp_path / "inventory.json").exists()


def test_synthetic_local_cli_flow_preserves_nfc_and_duration(tmp_path: Path) -> None:
    rights_file, permission_root = write_rights(tmp_path, approved=True)
    source = tmp_path / "synthetic.wav"
    write_synthetic_wav(source)
    inventory_path = tmp_path / "inventory.json"

    ingest = runner.invoke(
        app,
        [
            "ingest",
            str(source),
            "--rights-file",
            str(rights_file),
            "--permission-root",
            str(permission_root),
            "--output",
            str(inventory_path),
            "--probe",
            "wav",
        ],
    )
    assert ingest.exit_code == 0, ingest.output
    inventory = json.loads(inventory_path.read_text())

    original = unicodedata.normalize("NFD", "É wá ɖò xwé mɛ̌.")
    tokens_path = tmp_path / "tokens.jsonl"
    tokens_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "start_sample": 0,
                        "end_sample": 3 * SAMPLE_RATE,
                        "text": original,
                        "confidence": 0.99,
                        "boundary_kind": "sentence",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "start_sample": 3 * SAMPLE_RATE,
                        "end_sample": 6 * SAMPLE_RATE,
                        "text": "Wá dó.",
                        "confidence": 0.99,
                        "boundary_kind": "sentence",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    plans_path = tmp_path / "plans.jsonl"
    segment = runner.invoke(
        app,
        [
            "segment",
            str(tokens_path),
            "--rights-file",
            str(rights_file),
            "--permission-root",
            str(permission_root),
            "--source-sha256",
            inventory["sha256"],
            "--sample-rate",
            str(SAMPLE_RATE),
            "--output",
            str(plans_path),
        ],
    )
    assert segment.exit_code == 0, segment.output
    plans = [SegmentPlan.model_validate_json(line) for line in plans_path.read_text().splitlines()]
    assert plans and max(item.duration_seconds for item in plans) <= 15.0

    rendered: list[RenderedSegment] = [
        render_wav(source, item, tmp_path / "clips") for item in plans
    ]
    qc_input = tmp_path / "qc-input.jsonl"
    qc_input.write_text(
        "".join(
            json.dumps(
                {"rendered": item.model_dump(mode="json"), "text": plan_item.text},
                ensure_ascii=False,
            )
            + "\n"
            for item, plan_item in zip(rendered, plans, strict=True)
        ),
        encoding="utf-8",
    )
    qc_output = tmp_path / "qc.jsonl"
    qc = runner.invoke(
        app,
        [
            "qc",
            str(qc_input),
            "--rights-file",
            str(rights_file),
            "--permission-root",
            str(permission_root),
            "--output",
            str(qc_output),
        ],
    )
    assert qc.exit_code == 0, qc.output
    assert all(
        json.loads(line)["status"] == "accepted" for line in qc_output.read_text().splitlines()
    )

    representations = normalize_fongbe(plans[0].text)
    row = ExportRow(
        segment_id=rendered[0].segment_id,
        audio_path=rendered[0].path,
        audio_sha256=rendered[0].sha256,
        source_sha256=inventory["sha256"],
        book="MRK",
        chapter=1,
        verse_start=1,
        verse_end=2,
        text_original=representations.text_original,
        text_nfc=representations.text_nfc,
        text_acoustic=representations.text_acoustic,
        duration_seconds=rendered[0].duration_seconds,
        sample_rate=rendered[0].sample_rate,
        channels=rendered[0].channels,
        qc_status="accepted",
    )
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text(row.model_dump_json() + "\n", encoding="utf-8")
    split_map = tmp_path / "splits.json"
    split_map.write_text('{"MRK:1":"train"}\n', encoding="utf-8")
    export_root = tmp_path / "dataset"
    export = runner.invoke(
        app,
        [
            "export-hf",
            str(rows_path),
            str(split_map),
            str(export_root),
            "--rights-file",
            str(rights_file),
            "--permission-root",
            str(permission_root),
        ],
    )
    assert export.exit_code == 0, export.output
    metadata = json.loads((export_root / "train" / "metadata.jsonl").read_text())
    assert metadata["text"] == unicodedata.normalize("NFC", metadata["text"])
