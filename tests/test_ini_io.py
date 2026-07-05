from pathlib import Path

from mouse_config_gui import ini_io

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_m908_profile1_fields():
    config = ini_io.load(FIXTURES / "example_m908.ini")
    profile1 = config.profiles[0]

    assert profile1.lightmode == "static"
    assert profile1.color == "50ff00"
    assert profile1.brightness == 2
    assert profile1.speed == 1
    assert profile1.scrollspeed == 1
    assert profile1.report_rate == 500


def test_load_m908_dpi_slots():
    config = ini_io.load(FIXTURES / "example_m908.ini")
    profile1 = config.profiles[0]

    assert [s.enabled for s in profile1.dpi_slots] == [False, True, True, True, False]
    assert [s.value for s in profile1.dpi_slots] == ["200", "1000", "2000", "3000", "6200"]


def test_load_m908_preserves_unmodeled_button_mappings():
    config = ini_io.load(FIXTURES / "example_m908.ini")
    profile1 = config.profiles[0]

    assert profile1.raw["button_fire"] == "fire:mouse_left:5:1"
    assert profile1.raw["button_10"] == "super_l+shift_l+2"
    assert profile1.raw["button_dpi_up"] == "dpi+"


def test_load_m908_empty_profiles_are_valid():
    config = ini_io.load(FIXTURES / "example_m908.ini")
    for profile in config.profiles[2:]:
        assert profile.lightmode is None
        assert profile.raw == {}


def test_load_m908_preserves_macro_blocks():
    config = ini_io.load(FIXTURES / "example_m908.ini")

    assert set(config.macros) == {1, 2, 3}
    assert config.macros[1][:2] == [";# down\tm", ";# up\tm"]


def test_load_generic_dpi_is_bytecode_only():
    config = ini_io.load(FIXTURES / "example_generic.ini")
    profile1 = config.profiles[0]

    assert profile1.dpi_slots[0].value == "0x0400"


def test_save_then_load_round_trips_data(tmp_path):
    original = ini_io.load(FIXTURES / "example_m908.ini")

    out_path = tmp_path / "roundtrip.ini"
    ini_io.save(original, out_path)
    reloaded = ini_io.load(out_path)

    assert reloaded == original


def test_save_round_trips_button_fire_and_macros_verbatim(tmp_path):
    original = ini_io.load(FIXTURES / "example_m908.ini")

    out_path = tmp_path / "roundtrip.ini"
    ini_io.save(original, out_path)
    text = out_path.read_text()

    assert "button_fire=fire:mouse_left:5:1" in text
    assert ";## macro1" in text
    assert ";# down\tm" in text


def test_save_writes_empty_profile_sections(tmp_path):
    original = ini_io.load(FIXTURES / "example_m908.ini")

    out_path = tmp_path / "roundtrip.ini"
    ini_io.save(original, out_path)
    text = out_path.read_text()

    assert "[profile3]" in text
    assert "[profile4]" in text
    assert "[profile5]" in text
