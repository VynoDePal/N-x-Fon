# N-x-Fon Fongbe Bible Segmentation Pipeline Design

## 1. Outcome

N-x-Fon builds a reproducible, fail-closed pipeline that can turn an authorized Fongbe (`fon`) non-drama New Testament recording and its exact text into verified audio/transcription pairs. Every accepted clip is between 3 and 15 seconds, preserves Fongbe tone marks, carries source and rights provenance, and is suitable for later ASR or TTS research.

The first validation scope is the Gospel of Mark. The architecture covers all 27 New Testament books without changing the data contract or processing logic.

## 2. Current authorization boundary

The identified source is FCBH/Bible.is `FONBSB`:

- text: *MAWUXÓWÉMA*, © Alliance Biblique du Bénin, 2013;
- audio: *AKƆJIJƐYƆ̌YƆ́ Ɔ́ WÉMA*, ℗ Hosanna, 2016;
- selected variant: Non-Drama only.

Public FCBH terms do not grant the rights needed to download, transform, train on, or redistribute this material as a machine-learning dataset. A private Hugging Face repository does not remove that restriction.

The repository therefore ships in `LICENSE_BLOCKED` state. It must not download FCBH media or protected text. Real ingestion and publication require an explicit rights record proving all three independent grants:

1. `audio_rights = approved`;
2. `text_rights = approved`;
3. `ml_rights = approved`.

The record must also contain a non-empty permission reference, authorized scope, source identity, effective date, and SHA-256 of the archived permission document. Missing, malformed, expired, mismatched, or partial evidence fails closed before protected bytes are read or any network publication begins.

## 3. Scope and non-goals

### In scope

- local ingestion of user-supplied, authorized chapter audio and verse text;
- immutable source inventory and checksums;
- Unicode-safe Fongbe text normalization;
- verse/timing anchors supplied by an authorized source;
- silence/VAD-aware splitting and phrase-preserving merge/split into 3–15 second clips;
- extensible forced-alignment interface for Fongbe CTC models;
- acoustic, textual, alignment, and rights quality controls;
- deterministic manifests and private Hugging Face AudioFolder-compatible export;
- Mark pilot and New Testament book registry;
- architecture and legal decisions recorded in IcePanel;
- automated tests with synthetic or clearly licensed fixtures only.

### Out of scope for the first implementation

- scraping, reverse engineering, or bypassing FCBH/Bible.is access controls;
- bundling FCBH audio, text, CMU indices, or VoxClamantis artifacts;
- transferring CMU Drama timestamps to Non-Drama audio;
- TTS model training;
- speaker identity inference;
- claiming dialect, recording location, equipment, speaker demographics, or source audio properties that are not observed;
- public dataset publication.

## 4. Considered approaches

### Official timing first

Use FCBH verse timing as the primary segmentation signal. This is efficient but blocked because exportability and authorization for `FONBSB` are unconfirmed.

### CMU reconstruction

Reconstruct historical CMU Wilderness alignments. This is rejected as the canonical route because the referenced FONBSB URL appears to select Drama, the desired corpus is Non-Drama, and the chain of data rights is incomplete.

### Independent hybrid alignment — selected

Use authorized official verse timing only as a coarse anchor, then independently run silence/VAD analysis and a pluggable Fongbe CTC aligner. Human review validates a stratified sample and all low-confidence clips. CMU/VoxClamantis may later serve as non-canonical research comparisons only when separately authorized.

## 5. System architecture

N-x-Fon is a Python 3.11+ command-line application organized into focused packages.

1. **Rights Gate** validates permission records before protected source access and before export.
2. **Source Inventory** accepts only local paths, inspects media with `ffprobe`, hashes originals, and records observed properties without rewriting them.
3. **Text Normalizer** preserves `text_original` and produces canonical `text_nfc`. A separate `text_acoustic` representation may remove structural punctuation but never tone marks.
4. **Alignment Orchestrator** combines optional verse anchors, VAD/silence candidates, and a pluggable aligner. The initial deterministic aligner consumes authorized timing manifests; a CTC adapter is a later interchangeable implementation.
5. **Segment Planner** chooses boundaries at linguistic and acoustic pauses. It never cuts inside a known word boundary and rejects unresolvable spans above 15 seconds.
6. **Audio Renderer** creates WAV derivatives from authorized masters. Originals remain immutable and outside Git.
7. **Quality Gate** evaluates duration, clipping, silence ratio, text integrity, confidence, music/overlap flags, and duplicate fingerprints.
8. **Exporter** writes private Hugging Face-compatible metadata only after the rights gate passes again.

The system has no FCBH downloader. Acquisition is an external human/legal process; N-x-Fon starts from an authorized local delivery.

## 6. Processing flow

1. `nxfon rights validate rights.yaml` validates grants and the permission-document checksum.
2. `nxfon ingest source.yaml` inventories local Non-Drama masters and verse text without modifying originals.
3. `nxfon align chapter-manifest.jsonl` resolves verse and word boundaries from supplied anchors and the configured aligner.
4. `nxfon segment aligned.jsonl` creates a deterministic segmentation plan.
5. `nxfon render plan.jsonl` writes derived WAV clips to a controlled working directory.
6. `nxfon qc segments.jsonl` generates accepted, review, and rejected manifests plus aggregate metrics.
7. `nxfon export-hf accepted.jsonl` builds an AudioFolder-compatible private export only after a second rights validation.

Every stage writes content-addressed JSONL and a run record containing configuration digest, input digests, tool versions, start/end time, and counts. Re-running with identical inputs produces identical segment identifiers and metadata ordering.

## 7. Rights state machine

Allowed states are:

- `LICENSE_BLOCKED`: default; metadata-only development with synthetic or permissively licensed fixtures;
- `AUTHORIZED_LOCAL`: authorized local ingestion and processing, no Hub upload unless distribution is included;
- `AUTHORIZED_PRIVATE_DISTRIBUTION`: private Hugging Face upload permitted within the recorded scope;
- `REVOKED`: all new processing and publication blocked; existing controlled copies follow the permission's retention/deletion terms.

State transitions are data-driven and never inferred from repository visibility, a free download button, or the presence of files on disk.

## 8. Data contracts

### Rights record

Required fields:

```yaml
schema_version: "1"
dataset_id: "n-x-fon-bible-15s"
source_id: "FONBSB-NONDRAMA"
audio_rights: "blocked|approved|revoked"
text_rights: "blocked|approved|revoked"
ml_rights: "blocked|approved|revoked"
distribution: "none|private|public"
permission_reference: ""
permission_document_sha256: ""
effective_date: "YYYY-MM-DD"
expires_date: null
authorized_uses: []
```

The committed example remains blocked and contains no permission artifact or protected data.

### Source manifest

Each source row records `source_id`, source organization and URL, Bible/translation identifier, book, chapter, audio variant, local relative path, SHA-256, observed codec/sample rate/channels/bitrate/duration, text/audio copyright strings, license state, permission reference, and unknown metadata as explicit nulls.

### Segment manifest

Each row records:

- stable `segment_id` derived from source digest, book, chapter, verse span, and sample boundaries;
- `audio` relative path and SHA-256;
- `text_original`, `text_nfc`, and `text_acoustic`;
- language `fon`, variant `non_drama`, book/chapter/verse identifiers;
- start/end sample, duration, sample rate and channels;
- alignment method, confidence, timing source and configuration digest;
- speaker ID only when supplied by an authorized source, otherwise null;
- `music`, `overlap`, `clipping`, `duplicate_of`, `qc_status`, and rejection reasons;
- rights state and permission reference.

## 9. Segmentation policy

- hard maximum: `15.000` seconds after rendering and measurement;
- target range: `3.000–12.000` seconds;
- hard minimum for automatic acceptance: `1.000` second;
- preferred boundaries: sentence end, verse end, strong punctuation, validated word boundary, then silence;
- padding: configurable and included in the measured duration;
- a span above 15 seconds is split only at a validated internal word/pause boundary;
- if no safe boundary exists, the span is rejected for human review rather than truncated;
- clips are never time-stretched to satisfy duration;
- empty, punctuation-only, tone-stripped, or non-contiguous transcripts are rejected.

## 10. Fongbe text integrity

`text_original` is byte-preserved from the authorized delivery after UTF-8 decoding. `text_nfc` uses Unicode NFC. `text_acoustic` applies an explicit, versioned punctuation policy while preserving letters, combining marks, apostrophes that affect lexical form, and tone diacritics.

The pipeline rejects replacement characters, invalid UTF-8, accidental ASCII folding, and normalization that changes the sequence of base letters plus combining marks beyond canonical equivalence. Tests include precomposed and decomposed Fongbe strings.

## 11. Quality gates

Automatic acceptance requires:

- measured duration between 1 and 15 seconds;
- non-empty text with intact Unicode normalization;
- no clipping above the configured threshold;
- acceptable leading/trailing silence and total silence ratio;
- alignment confidence at or above the configured threshold;
- no unresolved overlap or significant music;
- no exact or near-duplicate audio/text conflict;
- authorized rights state for the requested action.

The Mark pilot report must include accepted/review/rejected counts, total accepted duration, duration percentiles, confidence distribution, Unicode failures, clipping/music/overlap flags, duplicate counts, and a reproducible sample list for human review. No WER, boundary error, or speaker purity claim is made without corresponding human reference annotations.

## 12. Dataset layout

The target private Hub repository is `VynoDePal/n-x-fon-bible-15s`.

```text
data/
  train/
    audio/*.wav
    metadata.jsonl
  validation/
    audio/*.wav
    metadata.jsonl
  test/
    audio/*.wav
    metadata.jsonl
manifests/
  provenance.jsonl
  rights-summary.json
reports/
  dataset-card-metrics.json
README.md
```

Splits are assigned at the chapter level, not randomly by clip, to reduce adjacent-text and acoustic leakage. The Mark pilot produces a `pilot` configuration; the New Testament release later uses fixed train/validation/test chapter assignments recorded in version control.

Protected permission documents, raw masters, secrets, local paths, and personally identifying speaker metadata are never uploaded to GitHub or Hugging Face.

## 13. Repository layout

```text
src/nxfon/
  cli.py
  rights.py
  inventory.py
  text.py
  alignment.py
  segmentation.py
  audio.py
  qc.py
  export_hf.py
  schemas.py
tests/
  fixtures/
  test_rights.py
  test_text.py
  test_segmentation.py
  test_qc.py
  test_export_hf.py
config/
  rights.blocked.example.yaml
  books.nt.json
docs/
  architecture/
  legal/
```

Runtime data directories are ignored by Git. Dependencies remain minimal: standard library, Pydantic, Typer, PyYAML, and optional audio tooling invoked as subprocesses. Heavy ASR frameworks belong behind optional adapters.

## 14. Error handling and recovery

- validation errors are structured, identify the exact record and field, and return non-zero exit codes;
- stages write to temporary paths and atomically rename completed artifacts;
- a run never overwrites an artifact with a different input digest;
- interrupted runs are resumable from completed content-addressed stages;
- missing `ffmpeg`/`ffprobe`, unsupported media, checksum drift, or rights drift stops the affected stage;
- publication is idempotent by dataset revision and manifest digest;
- logs redact tokens, absolute private paths, and permission-document contents.

## 15. Verification strategy

Implementation follows test-driven development.

- unit tests prove rights fail-closed behavior, Unicode preservation, boundary selection, deterministic IDs, duration enforcement, and QC classifications;
- integration tests generate synthetic WAV fixtures and run ingest → plan → render → QC → local export;
- a negative integration test proves that `LICENSE_BLOCKED` prevents source access and Hub publication before any network client is called;
- property-style cases cover exact 15-second boundaries, decomposed Unicode, empty verses, long unsplittable spans, duplicate timing, and reordered inputs;
- no protected FCBH bytes or text appear in tests, logs, snapshots, or CI artifacts.

## 16. IcePanel model

IcePanel will contain one `N-x-Fon` system with:

- actor: Dataset Curator;
- apps: Rights Gate, Segmentation Pipeline, Quality Control, Dataset Publisher;
- stores: Authorized Source Vault, Manifest Store, Private Hugging Face Dataset;
- external system: FCBH/Bible.is Rights and Delivery.

Connections show that FCBH delivers content only after authorization, every processing path passes through the Rights Gate, and the Publisher can write only to the private dataset after the Quality and Rights gates pass.

Architecture Decision Records capture:

1. Non-Drama-only source policy;
2. independent hybrid alignment instead of CMU Drama timestamp reuse;
3. fail-closed three-layer rights gate;
4. private Hugging Face AudioFolder-compatible export;
5. chapter-level split isolation.

## 17. Release gates

### Technical Alpha

Runs end to end on synthetic/permissively licensed fixtures, creates no FCBH derivative, and remains `LICENSE_BLOCKED`.

### Authorized Mark Pilot

Requires rights evidence, authorized local Mark assets, successful QC, and documented human review. It may remain local if distribution rights are absent.

### Private New Testament Dataset

Requires authorized private distribution, all 27 books processed under one versioned contract, chapter-isolated splits, final QC, dataset card, and explicit approval of the exact release manifest.

## 18. Consequences

This design deliberately delays access to the most useful source material. It adds provenance and validation work but prevents an attractive technical shortcut from producing an unusable or legally exposed corpus. It also keeps the pipeline valuable immediately: the Technical Alpha can be built, tested, reviewed, and later supplied with authorized material without redesign.
