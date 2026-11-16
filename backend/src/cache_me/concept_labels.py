"""Comparison keys only; stored names and distinct concept identities stay intact."""
import unicodedata


def concept_label_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())
