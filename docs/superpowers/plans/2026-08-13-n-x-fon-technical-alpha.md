# N-x-Fon Technical Alpha Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested, fail-closed Fongbe Bible segmentation pipeline that runs end to end on synthetic fixtures and cannot ingest or publish protected FCBH content while rights remain blocked.

**Architecture:** A Python 3.11+ CLI separates rights validation, Unicode-safe text handling, local source inventory, alignment/segmentation, audio rendering, quality control, and Hugging Face export. Every stage consumes and emits deterministic typed records; protected-content access and network publication are guarded independently.

**Tech Stack:** Python 3.11+, Pydantic 2, Typer, PyYAML, pytest, Ruff, mypy, standard-library `wave`/`audioop` alternatives, and optional `ffmpeg`/`ffprobe` subprocesses.

## Global Constraints

- Language is Fongbe, ISO 639-3 `fon`.
- Source variant is `FONBSB-NONDRAMA`; Drama data and CMU Drama timestamps are excluded.
- Accepted clips are at least 1.000 seconds and at most 15.000 seconds; the target range is 3.000–12.000 seconds.
- Preserve `text_original`, Unicode NFC `text_nfc`, and tone-preserving `text_acoustic`.
- The default and committed state is `LICENSE_BLOCKED`.
- Protected source access requires approved audio, text, and ML rights plus a verified permission-document SHA-256.
- Private Hugging Face export additionally requires `distribution: private` or `distribution: public`.
- No FCBH audio, protected Bible text, CMU indices, tokens, permission documents, or personal speaker metadata may enter Git, tests, logs, or CI artifacts.
- Originals are immutable; derived artifacts are content-addressed and written atomically.
- The first technical pilot uses synthetic audio and non-Biblical Fongbe fixture text.

---

## File map

- `pyproject.toml`: packaging, dependencies, CLI entry point, Ruff, mypy, and pytest configuration.
- `src/nxfon/schemas.py`: shared enums and immutable records.
- `src/nxfon/rights.py`: three-layer rights and permission checksum gate.
- `src/nxfon/text.py`: Fongbe normalization and integrity checks.
- `src/nxfon/inventory.py`: local-file-only source inspection and hashing.
- `src/nxfon/alignment.py`: validated timing spans and aligner protocol.
- `src/nxfon/segmentation.py`: deterministic 1–15 second boundary planner.
- `src/nxfon/audio.py`: atomic WAV rendering and measurement.
- `src/nxfon/qc.py`: clip classifications and metrics.
- `src/nxfon/export_hf.py`: guarded AudioFolder-compatible local export.
- `src/nxfon/cli.py`: commands that compose the modules without bypassing gates.
- `config/rights.blocked.example.yaml`: safe committed rights configuration.
- `config/books.nt.json`: canonical 27-book registry.
- `tests/fixtures/`: generated, non-protected test inputs only.
- `tests/`: unit and integration tests matching each module.
- `.github/workflows/ci.yml`: offline checks with no protected assets or secrets.
- `README.md`: operator workflow, legal boundary, and release gates.

### Task 1: Package foundation and fail-closed rights gate

**Files:**
- Create: `pyproject.toml`
- Create: `src/nxfon/__init__.py`
- Create: `src/nxfon/schemas.py`
- Create: `src/nxfon/rights.py`
- Create: `config/rights.blocked.example.yaml`
- Create: `tests/test_rights.py`

**Interfaces:**
- Produces: `RightsRecord`, `RightsState`, `Distribution`, `validate_rights(record, permission_root, action) -> RightsDecision`.
- `action` is `"ingest"` or `"publish"`; publishing requires an allowed distribution value.

- [ ] **Step 1: Write failing rights tests**

```python
from pathlib import Path

import pytest

from nxfon.rights import RightsError, validate_rights
from nxfon.schemas import RightsRecord


def blocked_record() -> RightsRecord:
    return RightsRecord.model_validate({
        "schema_version": "1",
        "dataset_id": "n-x-fon-bible-15s",
        "source_id": "FONBSB-NONDRAMA",
        "audio_rights": "blocked",
        "text_rights": "blocked",
        "ml_rights": "blocked",
        "distribution": "none",
        "permission_reference": "",
        "permission_document_sha256": "",
        "effective_date": "2026-08-13",
        "expires_date": None,
        "authorized_uses": [],
    })


def test_blocked_record_denies_ingest_before_file_access(tmp_path: Path) -> None:
    with pytest.raises(RightsError, match="audio_rights"):
        validate_rights(blocked_record(), tmp_path, action="ingest")


def test_private_publish_requires_private_distribution(tmp_path: Path) -> None:
    record = blocked_record().model_copy(update={
        "audio_rights": "approved",
        "text_rights": "approved",
        "ml_rights": "approved",
        "distribution": "none",
        "permission_reference": "grant.pdf",
        "permission_document_sha256": "0" * 64,
        "authorized_uses": ["machine_learning"],
    })
    (tmp_path / "grant.pdf").write_bytes(b"not-the-declared-file")
    with pytest.raises(RightsError, match="distribution"):
        validate_rights(record, tmp_path, action="publish")
```

- [ ] **Step 2: Verify the test fails because `nxfon` does not exist**

Run: `python -m pytest tests/test_rights.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'nxfon'`.

- [ ] **Step 3: Implement immutable schemas and ordered validation**

```python
class RightsError(ValueError):
    pass


def validate_rights(record: RightsRecord, permission_root: Path, action: str) -> RightsDecision:
    for field in ("audio_rights", "text_rights", "ml_rights"):
        if getattr(record, field) != RightsState.APPROVED:
            raise RightsError(f"{field} must be approved")
    if action == "publish" and record.distribution not in {Distribution.PRIVATE, Distribution.PUBLIC}:
        raise RightsError("distribution does not authorize publication")
    permission = permission_root / record.permission_reference
    if not record.permission_reference or not permission.is_file():
        raise RightsError("permission document is unavailable")
    observed = hashlib.sha256(permission.read_bytes()).hexdigest()
    if not hmac.compare_digest(observed, record.permission_document_sha256):
        raise RightsError("permission document checksum mismatch")
    return RightsDecision(state="AUTHORIZED", action=action, source_id=record.source_id)
```

Add expiry validation against an injected `today` value so tests remain deterministic. Reject unknown actions and require `machine_learning` in `authorized_uses` for ingestion.

- [ ] **Step 4: Verify rights tests pass**

Run: `python -m pytest tests/test_rights.py -q`

Expected: all rights tests pass.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/nxfon config/rights.blocked.example.yaml tests/test_rights.py
git commit -m "feat: add fail-closed rights gate"
```

### Task 2: Tone-preserving Fongbe normalization

**Files:**
- Create: `src/nxfon/text.py`
- Create: `tests/test_text.py`

**Interfaces:**
- Consumes: `TextRepresentations` from `schemas.py`.
- Produces: `normalize_fongbe(text: str) -> TextRepresentations` and `TextIntegrityError`.

- [ ] **Step 1: Write failing normalization tests**

```python
import unicodedata

import pytest

from nxfon.text import TextIntegrityError, normalize_fongbe


def test_normalization_preserves_tones_and_original_bytes() -> None:
    original = "É wá ɖò xwé mɛ̌."
    decomposed = unicodedata.normalize("NFD", original)
    result = normalize_fongbe(decomposed)
    assert result.text_original == decomposed
    assert result.text_nfc == original
    assert "ɖ" in result.text_acoustic
    assert "ɛ̌" in unicodedata.normalize("NFC", result.text_acoustic)


@pytest.mark.parametrize("text", ["", "   ", "...", "bad\ufffdtext"])
def test_invalid_or_non_lexical_text_is_rejected(text: str) -> None:
    with pytest.raises(TextIntegrityError):
        normalize_fongbe(text)
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_text.py -q`

Expected: import fails because `nxfon.text` is missing.

- [ ] **Step 3: Implement explicit normalization**

Use `unicodedata.normalize("NFC", text)`, reject replacement/control characters, collapse Unicode whitespace only in `text_acoustic`, remove structural punctuation through a named allow/deny policy, and verify at least one Unicode letter remains. Never encode to ASCII and never strip combining marks.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_text.py -q`

Expected: all normalization tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nxfon/text.py tests/test_text.py
git commit -m "feat: preserve Fongbe text integrity"
```

### Task 3: Local-only source inventory

**Files:**
- Create: `src/nxfon/inventory.py`
- Create: `tests/test_inventory.py`

**Interfaces:**
- Consumes: authorized local file path and `RightsDecision` for action `ingest`.
- Produces: `inventory_source(path, decision, probe) -> SourceMedia`.
- `probe(path) -> MediaProbe` is injected so tests do not require `ffprobe`.

- [ ] **Step 1: Write failing inventory tests**

```python
from pathlib import Path

import pytest

from nxfon.inventory import InventoryError, inventory_source


def test_inventory_hashes_local_bytes_without_modifying_source(tmp_path: Path, authorized_decision) -> None:
    source = tmp_path / "chapter.wav"
    source.write_bytes(b"immutable-audio-fixture")
    before = source.stat().st_mtime_ns
    media = inventory_source(source, authorized_decision, lambda _: {
        "codec": "pcm_s16le", "sample_rate": 16000, "channels": 1,
        "bitrate": 256000, "duration_ms": 2000,
    })
    assert media.sha256 == "e8cb4ab2780542ff2d4bd8d226d8d4905d63f724c224bfc444d6427c033ae64e"
    assert source.stat().st_mtime_ns == before


def test_inventory_refuses_urls(authorized_decision) -> None:
    with pytest.raises(InventoryError, match="local"):
        inventory_source("https://example.invalid/audio.mp3", authorized_decision, lambda _: {})
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_inventory.py -q`

Expected: import fails because `nxfon.inventory` is missing.

- [ ] **Step 3: Implement local path validation, streaming SHA-256, and probe parsing**

Reject URI schemes, symlinks escaping the configured source root, non-regular files, zero-byte files, unsupported channel counts, and non-positive duration. The production probe invokes `ffprobe` with a fixed argument list and parses JSON; it never invokes a shell.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_inventory.py -q`

Expected: all inventory tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nxfon/inventory.py tests/test_inventory.py
git commit -m "feat: inventory authorized local sources"
```

### Task 4: Alignment records and deterministic segment planner

**Files:**
- Create: `src/nxfon/alignment.py`
- Create: `src/nxfon/segmentation.py`
- Create: `tests/test_segmentation.py`

**Interfaces:**
- Produces: `TimedToken(start_sample, end_sample, text, confidence, boundary_kind)`.
- Produces: `plan_segments(tokens, sample_rate, policy, source_sha256) -> list[SegmentPlan]`.

- [ ] **Step 1: Write failing boundary tests**

```python
from nxfon.alignment import TimedToken
from nxfon.segmentation import SegmentationPolicy, plan_segments


def token(start: float, end: float, text: str, punctuation: str = "") -> TimedToken:
    return TimedToken(
        start_sample=int(start * 16000), end_sample=int(end * 16000),
        text=text + punctuation, confidence=0.99,
        boundary_kind="sentence" if punctuation else "word",
    )


def test_planner_never_exceeds_fifteen_seconds() -> None:
    tokens = [token(i * 2.0, (i + 1) * 2.0, f"w{i}", "." if i in {4, 7} else "") for i in range(8)]
    plans = plan_segments(tokens, 16000, SegmentationPolicy(), "a" * 64)
    assert plans
    assert max(plan.duration_seconds for plan in plans) <= 15.0


def test_unsplittable_long_token_requires_review() -> None:
    plans = plan_segments([token(0, 16, "longword")], 16000, SegmentationPolicy(), "a" * 64)
    assert plans[0].qc_status == "review"
    assert "no_safe_boundary" in plans[0].rejection_reasons


def test_segment_ids_are_stable_when_input_is_repeated() -> None:
    tokens = [token(0, 3, "é"), token(3, 6, "wá", ".")]
    first = plan_segments(tokens, 16000, SegmentationPolicy(), "a" * 64)
    second = plan_segments(tokens, 16000, SegmentationPolicy(), "a" * 64)
    assert [p.segment_id for p in first] == [p.segment_id for p in second]
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_segmentation.py -q`

Expected: alignment/segmentation imports fail.

- [ ] **Step 3: Implement validated spans and boundary ranking**

Validate monotonic, non-overlapping sample spans. Rank candidate cuts as sentence, verse, strong punctuation, word plus silence, then word. Accumulate toward 12 seconds, cut before 15 seconds, and mark an individually unsplittable token for review. Derive IDs with SHA-256 over canonical JSON containing source digest and exact sample boundaries.

- [ ] **Step 4: Verify GREEN and exact-boundary behavior**

Run: `python -m pytest tests/test_segmentation.py -q`

Expected: all planner tests pass, including an exact 15.000-second accepted span and a 15.001-second safely split span.

- [ ] **Step 5: Commit**

```bash
git add src/nxfon/alignment.py src/nxfon/segmentation.py tests/test_segmentation.py
git commit -m "feat: plan bounded deterministic segments"
```

### Task 5: Atomic WAV rendering and quality classification

**Files:**
- Create: `src/nxfon/audio.py`
- Create: `src/nxfon/qc.py`
- Create: `tests/test_audio_qc.py`

**Interfaces:**
- Produces: `render_wav(source, plan, output_root) -> RenderedSegment`.
- Produces: `classify_segment(rendered, text, policy) -> QCResult`.

- [ ] **Step 1: Write failing synthetic WAV tests**

Create a 16 kHz mono PCM fixture in the test with `wave.open`, render samples `[16000:48000]`, and assert the output is exactly 2 seconds, mono, 16 kHz, atomically placed, and hashed. Add cases for clipping, excessive silence, music/overlap flags, empty text, and a measured duration above 15 seconds.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_audio_qc.py -q`

Expected: audio/QC imports fail.

- [ ] **Step 3: Implement PCM WAV renderer and measurable QC**

Use the standard-library `wave` module for the Alpha renderer. Write to a sibling temporary file, flush and `os.fsync`, then `os.replace`. Compute peak amplitude and frame-based silence ratio from PCM16 samples. Treat supplied `music` and `overlap` flags as explicit observations; do not infer them without a detector.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_audio_qc.py -q`

Expected: rendering and classification tests pass with no temporary files left behind.

- [ ] **Step 5: Commit**

```bash
git add src/nxfon/audio.py src/nxfon/qc.py tests/test_audio_qc.py
git commit -m "feat: render and classify audio segments"
```

### Task 6: Guarded Hugging Face local export and New Testament registry

**Files:**
- Create: `src/nxfon/export_hf.py`
- Create: `config/books.nt.json`
- Create: `tests/test_export_hf.py`

**Interfaces:**
- Consumes: accepted `RenderedSegment` rows and a publish-authorized `RightsDecision`.
- Produces: `export_audiofolder(rows, output_root, decision, split_map) -> ExportSummary`.

- [ ] **Step 1: Write failing export tests**

```python
def test_export_is_blocked_before_any_publisher_call(tmp_path, blocked_decision) -> None:
    called = False

    def publisher(_: Path) -> None:
        nonlocal called
        called = True

    with pytest.raises(RightsError):
        export_audiofolder([], tmp_path, blocked_decision, {}, publisher=publisher)
    assert called is False


def test_chapter_split_prevents_clip_level_leakage(tmp_path, publish_decision, accepted_rows) -> None:
    summary = export_audiofolder(
        accepted_rows, tmp_path, publish_decision,
        {"MRK:1": "train", "MRK:2": "validation"}, publisher=None,
    )
    assert summary.rows_by_split == {"train": 2, "validation": 2}
    assert not (tmp_path / "train" / "metadata.jsonl").read_text().count('"chapter": 2')
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_export_hf.py -q`

Expected: exporter import fails.

- [ ] **Step 3: Implement deterministic local export**

Validate the 27 unique NT book codes, require chapter-level split mapping, copy only accepted rendered clips, use relative POSIX paths, sort metadata by `segment_id`, and write `metadata.jsonl`, `provenance.jsonl`, and `rights-summary.json` without permission contents. Invoke an optional publisher only after the entire export and second rights check succeed.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_export_hf.py -q`

Expected: export tests pass and no network call occurs when blocked.

- [ ] **Step 5: Commit**

```bash
git add src/nxfon/export_hf.py config/books.nt.json tests/test_export_hf.py
git commit -m "feat: create guarded private dataset export"
```

### Task 7: CLI composition and end-to-end Technical Alpha

**Files:**
- Create: `src/nxfon/cli.py`
- Create: `tests/test_cli_integration.py`
- Create: `README.md`
- Create: `.gitignore`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Produces commands: `rights validate`, `ingest`, `segment`, `qc`, and `export-hf`.
- Each command emits JSON on stdout and diagnostic text on stderr; non-zero exit codes classify validation, rights, dependency, and processing failures.

- [ ] **Step 1: Write failing blocked-path and synthetic happy-path CLI tests**

Use Typer's `CliRunner`. First assert blocked ingestion exits non-zero and does not call the injected inventory function. Then generate a six-second PCM WAV and authorized temporary permission record, supply timed non-Biblical Fongbe tokens, and run local ingest → segment → QC → export. Assert every emitted clip is at most 15 seconds and all metadata text is NFC.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_cli_integration.py -q`

Expected: CLI import fails.

- [ ] **Step 3: Implement commands and operator documentation**

Commands must call the rights gate before reading protected paths and again before invoking publication. The README states the two copyrights, explains that repository and dataset privacy do not grant rights, documents the blocked Alpha commands, and gives the exact authorized-local workflow without download instructions for FCBH.

- [ ] **Step 4: Run focused integration tests**

Run: `python -m pytest tests/test_cli_integration.py -q`

Expected: blocked and synthetic flows pass.

- [ ] **Step 5: Run the full local verification matrix**

```bash
python -m pytest -q
python -m ruff check .
python -m mypy src
python -m build
```

Expected: every command exits 0 with zero test failures, lint errors, type errors, or build errors.

- [ ] **Step 6: Commit**

```bash
git add src/nxfon/cli.py tests/test_cli_integration.py README.md .gitignore .github/workflows/ci.yml
git commit -m "feat: complete Technical Alpha workflow"
```

### Task 8: Architecture records and release evidence

**Files:**
- Create: `docs/architecture/icepanel-map.md`
- Create: `docs/legal/rights-boundary.md`
- Create: `reports/technical-alpha.json`

**Interfaces:**
- Produces a machine-readable verification report with source commit, commands, counts, and `rights_state: LICENSE_BLOCKED`.

- [ ] **Step 1: Write architecture and legal records from the approved design**

Record the IcePanel object names, connection directions, five ADR titles, current IcePanel domain blocker, and exact rights boundary. Do not embed the permission document, protected content, or credentials.

- [ ] **Step 2: Generate fresh release evidence**

Run the full verification matrix from Task 7, then write `reports/technical-alpha.json` containing the observed command exit codes, test count, package artifact names and SHA-256 values, and the statement that only synthetic/permissively licensed fixtures were processed.

- [ ] **Step 3: Re-run verification after report creation**

```bash
python -m pytest -q
python -m ruff check .
python -m mypy src
python -m build
```

Expected: every command exits 0 at the exact final tree.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture docs/legal reports/technical-alpha.json
git commit -m "docs: record Technical Alpha evidence"
```

## Plan self-review

- Every specification component needed for the Technical Alpha maps to Tasks 1–8.
- FCBH acquisition, protected data, real model training, and public distribution remain outside the Alpha.
- Rights checks precede both local protected-source access and publication-client invocation.
- All shared names (`RightsRecord`, `RightsDecision`, `TimedToken`, `SegmentPlan`, `RenderedSegment`) are introduced before their consumers.
- Tests observe behavior through injected probes/publishers and synthetic PCM rather than network mocks or protected fixtures.
- The final verification matrix covers behavior, lint, static types, and package build at the final tree.
