from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RightsState(StrEnum):
    BLOCKED = "blocked"
    APPROVED = "approved"
    REVOKED = "revoked"


class Distribution(StrEnum):
    NONE = "none"
    PRIVATE = "private"
    PUBLIC = "public"


class RightsRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1"]
    dataset_id: str = Field(min_length=1)
    source_id: Literal["FONBSB-NONDRAMA"]
    audio_rights: RightsState
    text_rights: RightsState
    ml_rights: RightsState
    distribution: Distribution
    permission_reference: str
    permission_document_sha256: str
    effective_date: date
    expires_date: date | None
    authorized_uses: tuple[str, ...]

    @field_validator("permission_document_sha256")
    @classmethod
    def validate_optional_sha256(cls, value: str) -> str:
        if value and (len(value) != 64 or any(char not in "0123456789abcdef" for char in value)):
            raise ValueError("permission_document_sha256 must be lowercase SHA-256")
        return value


class RightsDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: Literal["AUTHORIZED_LOCAL", "AUTHORIZED_PRIVATE_DISTRIBUTION", "AUTHORIZED_PUBLIC_DISTRIBUTION"]
    action: Literal["ingest", "publish"]
    source_id: str


class TextRepresentations(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text_original: str
    text_nfc: str
    text_acoustic: str


class MediaProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    codec: str = Field(min_length=1)
    sample_rate: int = Field(gt=0)
    channels: Literal[1, 2]
    bitrate: int = Field(ge=0)
    duration_ms: int = Field(gt=0)


class SourceMedia(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1)
    path: Path
    sha256: str
    size_bytes: int = Field(gt=0)
    probe: MediaProbe

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("sha256 must be lowercase SHA-256")
        return value
