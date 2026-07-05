import pytest

from mouse_config_gui.keymap import is_valid_button_mapping, is_valid_macro_action


@pytest.mark.parametrize(
    "value",
    [
        "",
        "left",
        "right",
        "middle",
        "forward",
        "backward",
        "dpi+",
        "dpi-cycle",
        "profile_switch",
        "none",
        "a",
        "F1",
        "Num_Return",
        "super_l+shift_l+2",
        "ctrl_l+alt_l+Delete",
        "fire:mouse_left:5:1",
        "fire:a:255:255",
        # A real M908's own -R output for its stock Fire button -- delay=0 is
        # accepted by mouse_m908 (plain uint8_t cast, no floor), even though
        # keymap.md documents delay as "1-255".
        "fire:mouse_left:3:0",
        "fire:mouse_left:0:0",
        "snipe:200",
        "snipe:1100",
        "macro1",
        "macro15",
        "macro1:25",
        "macro1:while",
        "macro1:until",
        "media_play",
        "compatibility_copy",
        "0x11aa22bb",
        "0x00000000",
    ],
)
def test_valid_mappings(value):
    assert is_valid_button_mapping(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "not_a_real_token",
        "super_l+",
        "super_l+bogus_key",
        "bogus_mod+a",
        # Case matters: mouse_m908's key-name map is exact-case ("Delete", not
        # "delete"/"DELETE") -- a mismatch doesn't error upstream, it silently
        # encodes to a null byte, so the validator must reject it instead.
        "super_l+delete",
        "super_l+DELETE",
        "fire:mouse_left:5:256",
        "fire:bogus_button:5:1",
        "snipe:150",
        "snipe:1200",
        "macro0",
        "macro16",
        "macro1:0",
        "macro1:256",
        "0x1",
        "0x00",
        "0xzz",
        "0X11AA22BB",
    ],
)
def test_invalid_mappings(value):
    assert is_valid_button_mapping(value) is False


def test_macro_bound_respects_num_macro_slots():
    assert is_valid_button_mapping("macro5", num_macro_slots=5) is True
    assert is_valid_button_mapping("macro6", num_macro_slots=5) is False


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("down", "a"),
        ("up", "a"),
        ("down", "Ctrl_l"),
        ("down", "mouse_left"),
        ("down", "mouse_right"),
        ("down", "mouse_middle"),
        ("down", "mouse_forward"),
        ("down", "mouse_backward"),
        ("delay", "1"),
        ("delay", "255"),
        ("move_left", "1"),
        ("move_left", "120"),
        ("move_right", "60"),
        ("move_up", "60"),
        ("move_down", "60"),
    ],
)
def test_valid_macro_actions(kind, value):
    assert is_valid_macro_action(kind, value) is True


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("down", "not_a_key"),
        ("down", "left"),  # button-mapping token, not a macro down/up target
        ("delay", "0"),
        ("delay", "256"),
        ("move_left", "0"),
        ("move_left", "121"),
        ("bogus_kind", "a"),
        ("delay", ""),
        ("delay", "-5"),
        ("delay", "5.5"),
        # str.isdigit() disagrees with int(): "²".isdigit() is True but
        # int("²") raises ValueError -- these must return False, not crash.
        ("delay", "²"),
        ("move_left", "①"),
    ],
)
def test_invalid_macro_actions(kind, value):
    assert is_valid_macro_action(kind, value) is False


def test_valid_macro_action_accepts_unicode_decimal_digits():
    # Unlike superscripts/circled numbers, Arabic-indic digits ARE valid
    # decimal digits int() can parse -- \d+ (not ASCII-only) is intentional.
    assert is_valid_macro_action("delay", "١٢٣") is True
