import pytest

from lalia import vocabulary as v

LEX = v.build_lexicon(["Kounelos"], medical=True)


@pytest.mark.parametrize("heard, expected", [
    # what large-v3-turbo actually wrote for Greek-pronounced brand names
    ("Χρειάζομαι δύο κουτιά ογκμεντίν του ενός γραμμαρίου.", "Χρειάζομαι δύο κουτιά Augmentin του ενός γραμμαρίου."),
    ("Η γιατρός έγραψε ξαρέλ το 20 και κόκορ 5 για την υπέρταση.",
     "Η γιατρός έγραψε Xarelto 20 και Concor 5 για την υπέρταση."),
    ("Δώστε του βεντολίν για το άσθημα.", "Δώστε του Ventolin για το άσθμα."),
    ("Ελέγξτε αν έχουμε απόθεμα γλουκοφάζ 850.", "Ελέγξτε αν έχουμε απόθεμα Glucophage 850."),
    ("Πάρτε ένα λίπιτορ και ένα πλάβιξ και βολταρέν.", "Πάρτε ένα Lipitor και ένα Plavix και Voltaren."),
    ("Ο ασθενής παίρνει DEPON 500.", "Ο ασθενής παίρνει Depon 500."),
    ("Η ουσία είναι αμοξικιλίνη με κλαβουλανικό οξύ.", "Η ουσία είναι αμοξικιλλίνη με κλαβουλανικό οξύ."),
    ("Εναλλακτικά η αζυθρομική νη.", "Εναλλακτικά η αζιθρομυκίνη."),
    ("Για τη χολυστερίνη παίρνει ατορβαστατίνη.", "Για τη χοληστερίνη παίρνει ατορβαστατίνη."),
    ("Αμοξικιλίνη δύο φορές.", "Αμοξικιλλίνη δύο φορές."),  # capital kept at the start
    ("Για τον πόνο μπρου φένει.", "Για τον πόνο Brufen."),  # a name split in two
    ("Ο κύριος κουνέλος ήρθε.", "Ο κύριος Kounelos ήρθε."),  # the user's own word
])
def test_corrects_what_whisper_wrote(heard, expected):
    assert LEX.correct(heard) == expected


@pytest.mark.parametrize("text", [
    "Το αέριο της κουζίνας τελείωσε και ο κόκορας λαλούσε όλο το πρωί.",
    "Θα περάσω από την τράπεζα και μετά θα πάω για καφέ με τη Μαρία.",
    "Καλημέρα σας. Η συνταγή είναι έτοιμη, ελέγξτε τη διαθεσιμότητα στην αποθήκη.",
    "Please send the order to the supplier and check the stock tomorrow.",
    "We need a foster family and a concert ticket.",
    "Η υπόταση και η υπέρταση είναι διαφορετικά πράγματα.",
])
def test_leaves_ordinary_text_alone(text):
    assert LEX.correct(text) == text


def test_sound_keys_match_across_alphabets():
    assert v.sound_key("λίπιτορ") == v.sound_key("Lipitor")
    assert v.sound_key("ευθυρόξ") == v.sound_key("Euthyrox")
    assert v.sound_key("Γλουκοφάζ") in v.sound_keys("Glucophage")
    assert v.sound_key("ογκμεντίν") in v.sound_keys("Augmentin")


def test_candidates_for_second_reading():
    c = LEX.candidates("Χρειάζομαι ογκμεντίν και πονστανφόρτε.")
    assert "Augmentin" in c and "Ponstan" in c
    # «αέριου» folds to the everyday «αερίου» (of gas): never offered as Aerius
    assert LEX.candidates("Το αέριο της κουζίνας τελείωσε, μια φιάλη αέριου.") == []


def test_prompt_respects_budget_and_order():
    words = [f"Term{i}" for i in range(200)]
    p = v.build_prompt(words, medical=True, mixed=True, count_tokens=len, budget=400)
    assert p.startswith(v.MIXED_PROMPT)
    assert len(p) <= 400 and "Term0" in p and "Term199" not in p
    assert v.build_prompt([], medical=False, mixed=False) is None


def test_lexicon_ignores_duplicates_and_comments(tmp_path):
    f = tmp_path / "w.txt"
    f.write_text("# comment\nDepon\n depon \n\nAugmentin\n", encoding="utf-8")
    assert v.load_terms(f) == ["Depon", "depon", "Augmentin"]
    assert len(v.Lexicon(v.load_terms(f))) == 2
