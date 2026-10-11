from __future__ import annotations

import re
import unicodedata


ENGLISH_HINTS = {
    "and",
    "apply",
    "company",
    "experience",
    "for",
    "job",
    "opportunity",
    "remote",
    "requirements",
    "role",
    "team",
    "the",
    "to",
    "work",
    "you",
}


def is_probably_english(text: str) -> bool:
    """Reject listings dominated by non-Latin scripts without adding a dependency.

    Job descriptions commonly contain names, symbols, and a few foreign words, so the
    check intentionally stays conservative.  It rejects text whose alphabetic content
    is mostly Arabic, Cyrillic, CJK, or another non-Latin script while allowing normal
    English listings and short English titles.
    """

    letters = [character for character in text if character.isalpha()]
    if not letters:
        return True

    latin_letters = sum(
        1 for character in letters if "LATIN" in unicodedata.name(character, "")
    )
    latin_ratio = latin_letters / len(letters)
    if latin_ratio < 0.65:
        return False

    words = re.findall(r"[a-z]+", text.casefold())
    if len(words) < 8:
        return True

    # A high Latin-script ratio is already a strong signal.  English hints keep the
    # borderline range from accepting long Latin-script listings in another language.
    if latin_ratio >= 0.90:
        return True
    return any(word in ENGLISH_HINTS for word in words)
