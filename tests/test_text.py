from __future__ import annotations

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


def test_acoustic_text_removes_structural_punctuation_but_keeps_apostrophe() -> None:
    result = normalize_fongbe("É ɖɔ̀: n'í, é wá!")
    assert result.text_acoustic == "É ɖɔ̀ n'í é wá"


@pytest.mark.parametrize("text", ["", "   ", "...", "bad\ufffdtext", "bad\u0000text"])
def test_invalid_or_non_lexical_text_is_rejected(text: str) -> None:
    with pytest.raises(TextIntegrityError):
        normalize_fongbe(text)
