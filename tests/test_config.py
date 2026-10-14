import json

from lalia import config


def test_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    s = config.Settings(hotkey="Ctrl+Alt+D", custom_words=["Depon"], mic_button_x=10, mic_button_y=20)
    config.save(s, p)
    assert config.load(p) == s


def test_missing_file_gives_defaults(tmp_path):
    assert config.load(tmp_path / "none.json") == config.Settings()


def test_corrupt_file_gives_defaults(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json", encoding="utf-8")
    assert config.load(p) == config.Settings()


def test_bad_values_fall_back_and_unknown_keys_ignored(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({
        "mode": "sideways", "beam_size": 99, "sounds": "yes", "custom_words": "Depon",
        "language": "en", "mic_button_x": "left", "something_new": 1, "paste_delay_ms": -5,
    }), encoding="utf-8")
    s = config.load(p)
    d = config.Settings()
    assert s.mode == d.mode
    assert s.beam_size == 10
    assert s.sounds == d.sounds
    assert s.custom_words == []
    assert s.language == "en"
    assert s.mic_button_x is None
    assert s.paste_delay_ms == 0


def test_copy_is_independent():
    s = config.Settings(custom_words=["a"])
    c = s.copy()
    c.custom_words.append("b")
    assert s.custom_words == ["a"]
