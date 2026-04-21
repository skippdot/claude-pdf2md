"""Unit tests for the post-OCR spellcheck / script-fixup module."""

from __future__ import annotations

from claude_pdf2md_ocr.spellcheck import dominant_language, fix_word, languages_for


def test_cyrillic_token_becomes_latin_one_in_english_context():
    langs = languages_for("This Agreement shall be governed by English law.")
    assert "en" in langs
    # `опе` is all-Cyrillic but visually identical to English `one`.
    assert fix_word("опе", langs) == "one"


def test_word_already_valid_is_left_alone():
    langs = languages_for("This is an English document.")
    assert fix_word("agreement", langs) == "agreement"
    assert fix_word("Google", langs) == "Google"


def test_unknown_token_stays_untouched():
    langs = languages_for("English context.")
    # A random all-Cyrillic token that maps to nothing meaningful — must NOT
    # be "corrected" into a random Latin-looking sequence.
    assert fix_word("ыъьюяжщ", langs) == "ыъьюяжщ"


def test_special_char_fix_numero_sign():
    langs = languages_for("ДОГОВІР Ме C836SHU")
    assert fix_word("Ме", langs) == "№"
    assert fix_word("Мо", langs) == "№"


def test_iban_label_fixed():
    langs = languages_for("IBAN UA573808380000026505700276244 в АТ ПРАВЕКС БАНК")
    assert fix_word("ІВАМ", langs) == "IBAN"


def test_punctuation_preserved():
    langs = languages_for("English prose.")
    # A period trailing the word must be preserved on replacement.
    assert fix_word("опе.", langs) == "one."
    assert fix_word("(опе)", langs) == "(one)"


def test_dominant_language_czech():
    assert dominant_language("Toto je česká věta s háčky ř š č.") == "cs"


def test_dominant_language_ukrainian():
    assert dominant_language("Договір страхування № 123 для Харкова.") == "uk"


def test_dominant_language_english():
    assert dominant_language("The quick brown fox jumps over the lazy dog.") == "en"


def test_single_letter_not_auto_corrected():
    # Regression: `п.7.7` in a Ukrainian legal document was being "fixed" to
    # `n.7.7` because `n` passes wordfreq as a single-letter English token.
    langs = languages_for("Ukrainian legal document п.7.7 section.")
    assert fix_word("п", langs) == "п"
    assert fix_word("п.7.7", langs) == "п.7.7"


def test_dominant_language_russian():
    # Cyrillic-only text without Ukrainian markers (і ї є ґ ʼ) should fall
    # through to Russian rather than misclassifying as Ukrainian.
    assert dominant_language("Это русский текст без характерных украинских букв.") == "ru"
