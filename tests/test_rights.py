from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from nxfon.rights import RightsError, validate_rights
from nxfon.schemas import RightsRecord


def blocked_record() -> RightsRecord:
    return RightsRecord.model_validate(
        {
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
        }
    )


def approved_record(permission: Path, *, distribution: str = "private") -> RightsRecord:
    return blocked_record().model_copy(
        update={
            "audio_rights": "approved",
            "text_rights": "approved",
            "ml_rights": "approved",
            "distribution": distribution,
            "permission_reference": permission.name,
            "permission_document_sha256": hashlib.sha256(permission.read_bytes()).hexdigest(),
            "authorized_uses": ["machine_learning"],
        }
    )


def test_blocked_record_denies_ingest_before_file_access(tmp_path: Path) -> None:
    with pytest.raises(RightsError, match="audio_rights"):
        validate_rights(blocked_record(), tmp_path, action="ingest", today=date(2026, 8, 13))


def test_private_publish_requires_private_distribution(tmp_path: Path) -> None:
    permission = tmp_path / "grant.pdf"
    permission.write_bytes(b"authorized-fixture")
    with pytest.raises(RightsError, match="distribution"):
        validate_rights(
            approved_record(permission, distribution="none"),
            tmp_path,
            action="publish",
            today=date(2026, 8, 13),
        )


def test_permission_checksum_must_match(tmp_path: Path) -> None:
    permission = tmp_path / "grant.pdf"
    permission.write_bytes(b"authorized-fixture")
    record = approved_record(permission).model_copy(
        update={"permission_document_sha256": "0" * 64}
    )
    with pytest.raises(RightsError, match="checksum"):
        validate_rights(record, tmp_path, action="ingest", today=date(2026, 8, 13))


def test_approved_private_record_allows_ingest_and_publish(tmp_path: Path) -> None:
    permission = tmp_path / "grant.pdf"
    permission.write_bytes(b"authorized-fixture")
    record = approved_record(permission)
    ingest = validate_rights(record, tmp_path, action="ingest", today=date(2026, 8, 13))
    publish = validate_rights(record, tmp_path, action="publish", today=date(2026, 8, 13))
    assert ingest.state == "AUTHORIZED_LOCAL"
    assert publish.state == "AUTHORIZED_PRIVATE_DISTRIBUTION"


def test_expired_permission_is_rejected(tmp_path: Path) -> None:
    permission = tmp_path / "grant.pdf"
    permission.write_bytes(b"authorized-fixture")
    record = approved_record(permission).model_copy(update={"expires_date": date(2026, 8, 12)})
    with pytest.raises(RightsError, match="expired"):
        validate_rights(record, tmp_path, action="ingest", today=date(2026, 8, 13))
