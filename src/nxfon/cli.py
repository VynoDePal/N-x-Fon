from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Annotated, Any, Literal, Never, cast

import typer
import yaml
from pydantic import ValidationError

from nxfon.alignment import TimedToken
from nxfon.audio import RenderedSegment
from nxfon.export_hf import ExportRow, export_audiofolder
from nxfon.inventory import InventoryError, ffprobe_media, inventory_source
from nxfon.qc import QCPolicy, classify_segment
from nxfon.rights import RightsError, validate_rights
from nxfon.schemas import MediaProbe, RightsDecision, RightsRecord
from nxfon.segmentation import SegmentationError, SegmentationPolicy, plan_segments

app = typer.Typer(help="Fail-closed Fongbe audio/transcription pipeline.")
rights_app = typer.Typer(help="Inspect the three-layer legal gate.")
app.add_typer(rights_app, name="rights")


def _emit(payload: Any, *, err: bool = False) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True), err=err)


def _die(kind: str, error: Exception, code: int) -> Never:
    _emit({"error": kind, "message": str(error)}, err=True)
    raise typer.Exit(code=code)


def _decision(
    rights_file: Path,
    permission_root: Path,
    action: Literal["ingest", "publish"],
) -> RightsDecision:
    try:
        payload = yaml.safe_load(rights_file.read_text(encoding="utf-8"))
        record = RightsRecord.model_validate(payload)
        return validate_rights(record, permission_root, action=action)
    except (OSError, yaml.YAMLError, ValidationError, RightsError) as exc:
        _die("rights", exc, 20)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        _die("input", exc, 10)


def _write_jsonl(path: Path, models: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(
                model.model_dump(mode="json", exclude_computed_fields=True),
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
            for model in models
        ),
        encoding="utf-8",
    )


def _wav_probe(path: Path) -> MediaProbe:
    try:
        with wave.open(str(path), "rb") as source:
            if source.getsampwidth() != 2 or source.getcomptype() != "NONE":
                raise InventoryError("WAV probe requires PCM16")
            sample_rate = source.getframerate()
            channels = source.getnchannels()
            duration_ms = round(source.getnframes() / sample_rate * 1000)
            return MediaProbe(
                codec="pcm_s16le",
                sample_rate=sample_rate,
                channels=cast(Literal[1, 2], channels),
                bitrate=sample_rate * channels * 16,
                duration_ms=duration_ms,
            )
    except (OSError, EOFError, wave.Error, ValidationError) as exc:
        raise InventoryError(f"WAV probe failed: {exc}") from exc


@rights_app.command("validate")
def validate_command(
    rights_file: Path,
    permission_root: Path,
    action: Annotated[Literal["ingest", "publish"], typer.Option("--action")] = "ingest",
) -> None:
    decision = _decision(rights_file, permission_root, action)
    _emit(decision.model_dump(mode="json"))


@app.command()
def ingest(
    source: Path,
    rights_file: Annotated[Path, typer.Option("--rights-file")],
    permission_root: Annotated[Path, typer.Option("--permission-root")],
    output: Annotated[Path, typer.Option("--output")],
    probe: Annotated[str, typer.Option("--probe")] = "ffprobe",
    source_root: Annotated[Path | None, typer.Option("--source-root")] = None,
) -> None:
    decision = _decision(rights_file, permission_root, "ingest")
    if probe not in {"ffprobe", "wav"}:
        _die("validation", ValueError("probe must be 'ffprobe' or 'wav'"), 10)
    try:
        media = inventory_source(
            source,
            decision,
            _wav_probe if probe == "wav" else ffprobe_media,
            source_root=source_root,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(media.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (InventoryError, OSError) as exc:
        _die("ingest", exc, 30)
    _emit({"output": str(output), "sha256": media.sha256, "status": "inventoried"})


@app.command()
def segment(
    tokens_file: Path,
    rights_file: Annotated[Path, typer.Option("--rights-file")],
    permission_root: Annotated[Path, typer.Option("--permission-root")],
    source_sha256: Annotated[str, typer.Option("--source-sha256")],
    output: Annotated[Path, typer.Option("--output")],
    sample_rate: Annotated[int, typer.Option("--sample-rate")] = 16_000,
) -> None:
    _decision(rights_file, permission_root, "ingest")
    try:
        tokens = [TimedToken.model_validate(item) for item in _read_jsonl(tokens_file)]
        plans = plan_segments(tokens, sample_rate, SegmentationPolicy(), source_sha256)
        _write_jsonl(output, plans)
    except (ValidationError, SegmentationError, OSError) as exc:
        _die("segment", exc, 30)
    _emit({"output": str(output), "segments": len(plans), "status": "planned"})


@app.command()
def qc(
    manifest_file: Path,
    rights_file: Annotated[Path, typer.Option("--rights-file")],
    permission_root: Annotated[Path, typer.Option("--permission-root")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    _decision(rights_file, permission_root, "ingest")
    try:
        results = [
            classify_segment(
                RenderedSegment.model_validate(item["rendered"]),
                str(item["text"]),
                QCPolicy(),
            )
            for item in _read_jsonl(manifest_file)
        ]
        _write_jsonl(output, results)
    except (KeyError, ValidationError, ValueError, OSError) as exc:
        _die("qc", exc, 30)
    _emit({"output": str(output), "segments": len(results), "status": "classified"})


@app.command("export-hf")
def export_hf(
    rows_file: Path,
    split_map_file: Path,
    output_root: Path,
    rights_file: Annotated[Path, typer.Option("--rights-file")],
    permission_root: Annotated[Path, typer.Option("--permission-root")],
) -> None:
    decision = _decision(rights_file, permission_root, "publish")
    try:
        rows = [ExportRow.model_validate(item) for item in _read_jsonl(rows_file)]
        split_map = json.loads(split_map_file.read_text(encoding="utf-8"))
        if not isinstance(split_map, dict):
            raise ValueError("split map must be a JSON object")
        summary = export_audiofolder(rows, output_root, decision, split_map)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError, RightsError) as exc:
        _die("export", exc, 30)
    _emit(summary.model_dump(mode="json"))


if __name__ == "__main__":
    app()
