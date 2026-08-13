from __future__ import annotations

import hashlib
import hmac
from datetime import date
from pathlib import Path
from typing import Literal

from nxfon.schemas import Distribution, RightsDecision, RightsRecord, RightsState


class RightsError(ValueError):
    """Raised when an action is outside the recorded authorization."""


def _permission_path(permission_root: Path, reference: str) -> Path:
    if not reference:
        raise RightsError("permission document is unavailable")
    root = permission_root.resolve()
    candidate = (root / reference).resolve()
    if not candidate.is_relative_to(root):
        raise RightsError("permission_reference escapes permission root")
    if not candidate.is_file():
        raise RightsError("permission document is unavailable")
    return candidate


def validate_rights(
    record: RightsRecord,
    permission_root: Path,
    *,
    action: Literal["ingest", "publish"],
    today: date | None = None,
) -> RightsDecision:
    """Validate a complete three-layer grant before source access or publication."""

    current_date = today or date.today()
    for field in ("audio_rights", "text_rights", "ml_rights"):
        if getattr(record, field) != RightsState.APPROVED:
            raise RightsError(f"{field} must be approved")
    if "machine_learning" not in record.authorized_uses:
        raise RightsError("authorized_uses must include machine_learning")
    if current_date < record.effective_date:
        raise RightsError("permission is not effective yet")
    if record.expires_date is not None and current_date > record.expires_date:
        raise RightsError("permission has expired")
    if action == "publish" and record.distribution == Distribution.NONE:
        raise RightsError("distribution does not authorize publication")

    permission = _permission_path(permission_root, record.permission_reference)
    observed = hashlib.sha256(permission.read_bytes()).hexdigest()
    if not hmac.compare_digest(observed, record.permission_document_sha256):
        raise RightsError("permission document checksum mismatch")

    state: Literal[
        "AUTHORIZED_LOCAL",
        "AUTHORIZED_PRIVATE_DISTRIBUTION",
        "AUTHORIZED_PUBLIC_DISTRIBUTION",
    ]
    if action == "ingest":
        state = "AUTHORIZED_LOCAL"
    elif record.distribution == Distribution.PRIVATE:
        state = "AUTHORIZED_PRIVATE_DISTRIBUTION"
    else:
        state = "AUTHORIZED_PUBLIC_DISTRIBUTION"
    return RightsDecision(state=state, action=action, source_id=record.source_id)
