from mouse_config_gui.capability import (
    find_capability_by_model_name,
    find_capability_by_usb,
    list_capabilities,
    load_capability,
)

ALL_MODELS = {
    "m607", "m686", "m709", "m711", "m715", "m719", "m721",
    "m908", "m913", "m990", "m990chroma", "generic",
}


def test_list_capabilities_finds_all_models():
    assert set(list_capabilities()) == ALL_MODELS


def test_every_capability_loads_and_has_required_top_level_keys():
    for name in ALL_MODELS:
        cap = load_capability(name)
        assert cap.data["usb"]["vid"]
        assert cap.data["usb"]["pids"]
        assert cap.data["num_profiles"] in (2, 5)
        assert cap.data["led"]["lightmodes"]
        assert cap.data["dpi"]["num_slots"] == 5


def test_load_capability_m908():
    cap = load_capability("m908")
    assert cap.model == "908"
    assert cap.data["dpi"]["num_slots"] == 5
    assert cap.data["led"]["scrollspeed_range"] == [1, 0x3F]
    assert cap.data["led"]["scrollspeed_readback_reliable"] is False


def test_load_capability_m607_has_actual_and_bytecode_dpi():
    cap = load_capability("m607")
    assert cap.data["dpi"]["formats"] == ["actual", "bytecode"]
    assert cap.data["dpi"]["actual_range"] == [100, 7200]


def test_m686_and_m913_have_restricted_lightmodes_and_two_profiles():
    for name in ("m686", "m913"):
        cap = load_capability(name)
        assert cap.data["num_profiles"] == 2
        assert set(cap.data["led"]["lightmodes"]) == {"off", "static", "breathing", "rainbow"}
        assert cap.data["led"]["scrollspeed_range"] is None
        assert cap.data["usb"]["vid"] == 0x25A7


def test_find_capability_by_usb_matches_dedicated_model():
    assert find_capability_by_usb(0x04D9, 0xFC4D) == "m908"
    assert find_capability_by_usb(0x04D9, 0xFC38) == "m607"
    assert find_capability_by_usb(0x25A7, 0xFA35) == "m686"


def test_find_capability_by_usb_prefers_dedicated_over_generic():
    # 0xfc2a is M709's PID but also sits in generic's broad allowlist.
    assert find_capability_by_usb(0x04D9, 0xFC2A) == "m709"


def test_find_capability_by_usb_falls_back_to_generic():
    # 0xfc02 (M901 Perdition) has no dedicated capability file.
    assert find_capability_by_usb(0x04D9, 0xFC02) == "generic"


def test_find_capability_by_usb_returns_none_for_unknown_device():
    assert find_capability_by_usb(0x046D, 0xC52B) is None


def test_find_capability_by_model_name_maps_cli_string_to_file_stem():
    # The capability file stem ("m607") and the CLI's -M value / a config
    # file's "# Model:" line ("607") are different namespaces -- only
    # "generic" happens to be spelled the same in both.
    assert find_capability_by_model_name("607") == "m607"
    assert find_capability_by_model_name("990chroma") == "m990chroma"
    assert find_capability_by_model_name("generic") == "generic"


def test_find_capability_by_model_name_returns_none_for_unknown_model():
    assert find_capability_by_model_name("totally-fake-model") is None
