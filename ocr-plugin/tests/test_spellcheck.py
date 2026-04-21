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


def test_special_char_regex_numero_sign_with_digits():
    # Prefix-fused misreads: `Мо1224` / `Ме1085-р` → `№1224` / `№1085-р`.
    langs = languages_for("розпорядженням Мо1224 від 2004 року")
    assert fix_word("Мо1224", langs) == "№1224"
    assert fix_word("Ме1085-р", langs) == "№1085-р"


def test_special_char_regex_leaves_non_numero_alone():
    langs = languages_for("Russian word Моя роль is fine.")
    # Only trigger when digits follow — `Моя` stays `Моя`.
    assert fix_word("Моя", langs) == "Моя"


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


def test_detect_tesseract_lang_czech():
    from claude_pdf2md_ocr.spellcheck import detect_tesseract_lang

    # Enough Czech-marked body text — the return should include `ces` and
    # also tack on `eng` for the English fragments found in the same files.
    sample = (
        "Potvrzuji, že jsem si přečetl Kodex chování společnosti Google, "
        "porozuměl mu a budu se jím řídit při výkonu mých služeb. Kodexu "
        "chování je podmínkou mého zaměstnání a jeho nedodržení může vést "
        "k ukončení mého pracovního vztahu."
    )
    assert detect_tesseract_lang(sample) == "ces+eng"


def test_detect_tesseract_lang_ukrainian():
    from claude_pdf2md_ocr.spellcheck import detect_tesseract_lang

    sample = (
        "Договір страхування № C836SHU від 26.06.2025 р. місто Харків. "
        "Страхувальник зобов'язаний повідомити Страховика про настання "
        "страхового випадку протягом трьох робочих днів."
    )
    assert detect_tesseract_lang(sample) == "ukr+eng"


def test_detect_tesseract_lang_returns_none_on_short_sample():
    from claude_pdf2md_ocr.spellcheck import detect_tesseract_lang

    assert detect_tesseract_lang("hi") is None
    assert detect_tesseract_lang("") is None


def test_detect_tesseract_lang_plain_english():
    from claude_pdf2md_ocr.spellcheck import detect_tesseract_lang

    sample = (
        "This Agreement is governed by the laws of Czech Republic in which "
        "I perform my assignment without giving effect to any choice of law."
    )
    assert detect_tesseract_lang(sample) == "eng"
