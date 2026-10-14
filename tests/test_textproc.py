from lalia import textproc


def fin(text, **kw):
    opts = {"replacements": [], "spoken_punctuation": False, "trailing_space": False}
    opts.update(kw)
    return textproc.finalize(text, **opts)


def test_whitespace_collapsed_and_trailing_space():
    assert fin("  Καλημέρα   σας. ") == "Καλημέρα σας."
    assert fin("Καλημέρα σας.", trailing_space=True) == "Καλημέρα σας. "


def test_empty_stays_empty():
    assert fin("", trailing_space=True) == ""
    assert fin("   ", trailing_space=True) == ""


def test_subtitle_credit_dropped():
    assert fin("Υπότιτλοι AUTHORWAVE") == ""
    assert fin("Η συνταγή είναι έτοιμη. Ευχαριστούμε που παρακολουθήσατε!") == "Η συνταγή είναι έτοιμη."
    # accents and case do not matter
    assert fin("ΕΥΧΑΡΙΣΤΟΥΜΕ ΠΟΥ ΠΑΡΑΚΟΛΟΥΘΗΣΑΤΕ.") == ""


def test_real_short_thanks_is_kept():
    assert fin("Ευχαριστώ.") == "Ευχαριστώ."


def test_replacements_accent_and_case_insensitive():
    out = fin("Πάρτε δεπόν δύο φορές.", replacements=["depon => Depon", "δεπον => Depon"])
    assert out == "Πάρτε Depon δύο φορές."


def test_replacement_newline():
    assert fin("Πρώτη γραμμή αλλαγή δεύτερη", replacements=["αλλαγή => \\n"]) == "Πρώτη γραμμή\nδεύτερη"


def test_replacement_whole_words_only():
    assert fin("Το κομμάτι", replacements=["κόμμα => ,"]) == "Το κομμάτι"


def test_spoken_punctuation():
    assert fin("Γεια σου κόμμα τι κάνεις ερωτηματικό", spoken_punctuation=True) == "Γεια σου, τι κάνεις;"
    assert fin("Πρώτο τελεία νέα γραμμή Δεύτερο", spoken_punctuation=True) == "Πρώτο.\nΔεύτερο"
    assert fin("Ώρα άνω κάτω τελεία δέκα", spoken_punctuation=True) == "Ώρα: δέκα"


def test_spoken_punctuation_when_whisper_already_punctuated():
    assert fin("Γεια σου, κόμμα, τι κάνεις;", spoken_punctuation=True) == "Γεια σου, τι κάνεις;"


def test_spoken_punctuation_off_leaves_words():
    assert fin("Γεια σου κόμμα") == "Γεια σου κόμμα"


def test_normalize():
    assert textproc.normalize("Ευχαριστώ, ΠΟΛΎ!") == "ευχαριστω πολυ"
