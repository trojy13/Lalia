import pytest

from lalia import win32 as w
from lalia.hotkey import HotkeyError, parse


def test_parse_normalises():
    mods, vk, text = parse("shift + ctrl+space")
    assert mods == w.MOD_CONTROL | w.MOD_SHIFT
    assert vk == 0x20
    assert text == "Ctrl+Shift+Space"


def test_function_key_alone_is_allowed():
    assert parse("F9") == (0, 0x78, "F9")


@pytest.mark.parametrize("bad", ["", "Space", "Ctrl+Nope", "Hyper+Space", "A"])
def test_rejected(bad):
    with pytest.raises(HotkeyError):
        parse(bad)
