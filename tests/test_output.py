import ctypes

from lalia import win32 as w
from lalia.micbutton import title_matches
from lalia.output import text_key_events


def test_input_struct_size_matches_windows():
    assert ctypes.sizeof(w.INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


def test_text_key_events_greek_newline_and_surrogates():
    events = text_key_events("Αβ\r\n\t😀")
    assert events[0] == ("unit", ord("Α"))
    assert events[1] == ("unit", ord("β"))
    assert events[2] == ("vk", w.VK_RETURN)  # \r skipped, \n is Enter
    assert events[3] == ("vk", w.VK_TAB)
    assert events[4:] == [("unit", 0xD83D), ("unit", 0xDE00)]  # one emoji = two UTF-16 units


def test_title_matches():
    assert title_matches("Anything", "")
    assert title_matches("ΔΙΟΣΚΟΥΡΙΔΗΣ - Λιανική", "Διοσκουρίδης, FARMAKON")  # capitals drop accents
    assert title_matches("Διοσκουρίδης - Λιανική", "διοσκουριδης")
    assert title_matches("farmakon net", "Διοσκουρίδης, FARMAKON")
    assert title_matches("Document1 - Word", "*- Word")
    assert not title_matches("Notepad", "Διοσκουρίδης, FARMAKON")
