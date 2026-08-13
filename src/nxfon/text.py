from __future__ import annotations

import unicodedata

from nxfon.schemas import TextRepresentations


class TextIntegrityError(ValueError):
    """Raised when text cannot safely represent a spoken Fongbe utterance."""


_LEXICAL_APOSTROPHES = {"'", "’", "ʼ"}  # noqa: RUF001 - intentional Unicode apostrophes


def _validate_characters(text: str) -> None:
    if "\ufffd" in text:
        raise TextIntegrityError("replacement character is not allowed")
    for character in text:
        category = unicodedata.category(character)
        if category.startswith("C") and character not in {"\n", "\r", "\t"}:
            raise TextIntegrityError("control characters are not allowed")


def _acoustic_form(text_nfc: str) -> str:
    characters: list[str] = []
    for character in text_nfc:
        category = unicodedata.category(character)
        if category.startswith("P") and character not in _LEXICAL_APOSTROPHES:
            characters.append(" ")
        else:
            characters.append(character)
    return " ".join("".join(characters).split())


def normalize_fongbe(text: str) -> TextRepresentations:
    """Create lossless and acoustic representations without removing tone marks."""

    _validate_characters(text)
    text_nfc = unicodedata.normalize("NFC", text)
    if not any(unicodedata.category(character).startswith("L") for character in text_nfc):
        raise TextIntegrityError("text must contain at least one letter")
    text_acoustic = _acoustic_form(text_nfc)
    if not text_acoustic:
        raise TextIntegrityError("acoustic text is empty")
    return TextRepresentations(
        text_original=text,
        text_nfc=text_nfc,
        text_acoustic=text_acoustic,
    )
