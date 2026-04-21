"""Post-OCR cleanup: fix cross-script confusion, common spec-char misreads,
and near-misses against a language-aware frequency dictionary.

Tesseract invoked with a multi-language model (e.g. `ukr+rus+eng`) routinely
produces cross-script garbage: Czech `ukončení` comes out as `икопбепі` and
English `one` as `опе`, because Cyrillic glyphs like `о к и п е` are visually
identical to Latin `o k u n e`. This module fixes three classes of errors:

1. **Script confusion.** A word that contains characters from a script
   incompatible with its page's dominant script is re-mapped using a
   visual-similar character table and validated against `wordfreq`.

2. **Special-character glyph errors.** A small hand-curated table for known
   OCR misreads of non-alphabetic symbols (e.g. `№` → `Ме` / `Мо`).

3. **Near-miss edit-distance.** For short mixed-script tokens where script
   confusion alone doesn't produce a valid word, a bounded edit-distance
   search considers alternatives reachable via one substitution and picks
   the one with the highest frequency in the target language, if above a
   minimum threshold.

The whole pass is conservative — it only edits a word when it has high
confidence that the replacement is correct. Unknown tokens are left alone,
so proper nouns, product names, and specialised jargon survive untouched.
"""

from __future__ import annotations

import re

from wordfreq import word_frequency

# Cyrillic glyphs that are visually indistinguishable (or nearly so) from
# Latin glyphs in most fonts. These are the ones Tesseract confuses when
# running on multi-script documents.
_CYR_TO_LAT: dict[str, str] = {
    "а": "a",
    "А": "A",
    "в": "b",
    "В": "B",
    "с": "c",
    "С": "C",
    "е": "e",
    "Е": "E",
    "Н": "H",
    "К": "K",
    "к": "k",
    "М": "M",
    "м": "m",
    "н": "h",
    "о": "o",
    "О": "O",
    "р": "p",
    "Р": "P",
    "Т": "T",
    "т": "t",
    "у": "y",
    "х": "x",
    "Х": "X",
    "и": "u",
    "І": "I",
    "і": "i",
    "Ї": "I",
    "ї": "i",
    "п": "n",
    "б": "b",
    "г": "r",
}
_LAT_TO_CYR: dict[str, str] = {}
for cyr, lat in _CYR_TO_LAT.items():
    # Multiple cyrillic letters map to the same latin letter; keep whichever
    # canonical cyrillic form the frequency dictionary is most likely to hit.
    _LAT_TO_CYR.setdefault(lat, cyr)

# Known OCR-level spec-char confusions. Keep tiny and high-confidence.
_SPEC_CHAR_FIXES: dict[str, str] = {
    "Ме": "№",  # Cyrillic М + е often replaces U+2116.
    "Мо": "№",  # Sometimes Tesseract picks the 'o' form instead.
    "ІВАМ": "IBAN",  # Common header label on Ukrainian bank documents.
}

# Frequency floor a word must clear to count as "in dictionary". Below this,
# wordfreq returns essentially-noise entries (OCR artefacts the corpus saw
# once and kept).
_MIN_FREQ = 1e-6

# Length bounds for auto-fix. Single letters get too many spurious hits in
# the frequency dictionary (`n`, `a`, `i`, etc. are "words"), so the core
# token — punctuation stripped — must be at least two characters. Upper
# bound prevents false-positive fixes on proper nouns and long compounds.
_MIN_FIX_LEN = 2
_MAX_FIX_LEN = 20

_LANG_PRIORITY = ("en", "uk", "ru", "cs")


def dominant_language(text: str) -> str:
    """Rough heuristic picking the document-level language code."""
    cyr = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    lat = sum(1 for c in text if c.isascii() and c.isalpha())
    if cyr == 0 and lat == 0:
        return "en"
    # Language-specific trigraphs give stronger signal than raw char counts.
    sample = text.lower()
    if any(mark in sample for mark in ("č", "ě", "š", "ř", "ž", "ů", "ň", "ť", "ď", "á", "é", "í", "ý")):
        return "cs"
    if any(mark in sample for mark in ("і", "ї", "є", "ґ", "ʼ")):
        return "uk"
    if cyr > lat:
        return "ru"
    return "en"


def _is_valid(word: str, langs: tuple[str, ...]) -> bool:
    if not word:
        return False
    for lang in langs:
        if word_frequency(word.lower(), lang) >= _MIN_FREQ:
            return True
    return False


def _script_swapped(word: str, table: dict[str, str]) -> str:
    return "".join(table.get(c, c) for c in word)


def fix_word(word: str, langs: tuple[str, ...]) -> str:
    """Return a corrected version of `word`, or the original if no safe fix exists."""
    if not word or len(word) > _MAX_FIX_LEN:
        return word

    # Leading/trailing punctuation is preserved around the actual token so
    # URLs, sentence-ending periods, etc. aren't mangled.
    head, core, tail = _split_punct(word)
    if not core:
        return word

    if core in _SPEC_CHAR_FIXES:
        return head + _SPEC_CHAR_FIXES[core] + tail

    # Count letters only. Embedded digits / dots (e.g. `п.7.7`, `v1.2`, `5g`)
    # shouldn't count toward the fixable-length threshold — single-letter
    # alphabetic stems are too ambiguous in frequency dictionaries.
    letter_count = sum(1 for c in core if c.isalpha())
    if letter_count < _MIN_FIX_LEN:
        return word

    if _is_valid(core, langs):
        return word

    # Try Cyrillic → Latin swap.
    cyr_to_lat = _script_swapped(core, _CYR_TO_LAT)
    if cyr_to_lat != core and _is_valid(cyr_to_lat, langs):
        return head + cyr_to_lat + tail

    # Try Latin → Cyrillic swap.
    lat_to_cyr = _script_swapped(core, _LAT_TO_CYR)
    if lat_to_cyr != core and _is_valid(lat_to_cyr, langs):
        return head + lat_to_cyr + tail

    return word


_PUNCT_LEADING = re.compile(r"^[^\w]+", re.UNICODE)
_PUNCT_TRAILING = re.compile(r"[^\w]+$", re.UNICODE)


def _split_punct(word: str) -> tuple[str, str, str]:
    lead = _PUNCT_LEADING.match(word)
    trail = _PUNCT_TRAILING.search(word)
    start = lead.end() if lead else 0
    end = trail.start() if trail else len(word)
    return word[:start], word[start:end], word[end:]


def fix_tokens(tokens: list[str], langs: tuple[str, ...]) -> list[str]:
    """Apply `fix_word` to each token, returning a new list with corrections."""
    return [fix_word(t, langs) for t in tokens]


def languages_for(text_sample: str) -> tuple[str, ...]:
    """Produce a language priority tuple for dictionary lookup.

    Always includes English as a safety net (many documents have English
    loanwords / URLs / product names regardless of the host language).
    """
    main = dominant_language(text_sample)
    if main == "en":
        return ("en",)
    # For non-English main languages, check the main one first, then English,
    # to catch embedded foreign-language fragments.
    return (main, "en")
