from pathlib import Path

import pytest

from mouse_config_gui import device_cli


class FakeResult:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_detect_model_returns_none_when_no_device(monkeypatch):
    monkeypatch.setattr(
        device_cli.subprocess, "run", lambda *a, **k: FakeResult(stdout="")
    )
    assert device_cli.detect_model() is None


def test_detect_model_matches_known_pid(monkeypatch):
    stdout = "Bus 001 Device 005: ID 04d9:fc4d Holtek Semiconductor, Inc.\n"
    monkeypatch.setattr(
        device_cli.subprocess, "run", lambda *a, **k: FakeResult(stdout=stdout)
    )
    assert device_cli.detect_model() == "m908"


def test_detect_model_falls_back_to_generic_for_unknown_pid(monkeypatch):
    # 0xfc02 (M901 Perdition) is only in generic's PID allowlist -- no dedicated
    # capability file claims it.
    stdout = "Bus 001 Device 005: ID 04d9:fc02 Holtek Semiconductor, Inc.\n"
    monkeypatch.setattr(
        device_cli.subprocess, "run", lambda *a, **k: FakeResult(stdout=stdout)
    )
    assert device_cli.detect_model() == "generic"


def test_detect_model_matches_dedicated_model_over_generic_fallback(monkeypatch):
    # 0xfc2a is M709's own PID, but also appears in generic's broad allowlist --
    # the dedicated m709.yaml descriptor must win.
    stdout = "Bus 001 Device 005: ID 04d9:fc2a Holtek Semiconductor, Inc.\n"
    monkeypatch.setattr(
        device_cli.subprocess, "run", lambda *a, **k: FakeResult(stdout=stdout)
    )
    assert device_cli.detect_model() == "m709"


def test_detect_model_matches_non_04d9_vendor(monkeypatch):
    # m686/m913 are a distinct wireless family on VID 0x25a7, not 0x04d9.
    stdout = "Bus 001 Device 007: ID 25a7:fa35 Generic\n"
    monkeypatch.setattr(
        device_cli.subprocess, "run", lambda *a, **k: FakeResult(stdout=stdout)
    )
    assert device_cli.detect_model() == "m686"


def test_detect_model_ignores_unrelated_vid(monkeypatch):
    stdout = "Bus 001 Device 003: ID 046d:c52b Logitech, Inc.\n"
    monkeypatch.setattr(
        device_cli.subprocess, "run", lambda *a, **k: FakeResult(stdout=stdout)
    )
    assert device_cli.detect_model() is None


def test_detect_model_returns_none_if_lsusb_missing(monkeypatch):
    def raise_not_found(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(device_cli.subprocess, "run", raise_not_found)
    assert device_cli.detect_model() is None


def test_apply_config_builds_correct_argv(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return FakeResult()

    monkeypatch.setattr(device_cli.subprocess, "run", fake_run)
    device_cli.apply_config(Path("/tmp/config.ini"), model="908")

    assert captured["argv"] == ["mouse_m908", "-c", "/tmp/config.ini", "-M", "908"]


def test_apply_config_omits_model_flag_when_none(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return FakeResult()

    monkeypatch.setattr(device_cli.subprocess, "run", fake_run)
    device_cli.apply_config(Path("/tmp/config.ini"))

    assert captured["argv"] == ["mouse_m908", "-c", "/tmp/config.ini"]


def test_apply_macros_builds_correct_argv(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return FakeResult()

    monkeypatch.setattr(device_cli.subprocess, "run", fake_run)
    device_cli.apply_macros(Path("/tmp/config.ini"), model="908")

    assert captured["argv"] == ["mouse_m908", "-m", "/tmp/config.ini", "-M", "908"]


def test_read_config_builds_correct_argv(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return FakeResult()

    monkeypatch.setattr(device_cli.subprocess, "run", fake_run)
    device_cli.read_config(Path("/tmp/out.ini"))

    assert captured["argv"] == ["mouse_m908", "-R", "/tmp/out.ini"]


def test_set_active_profile_builds_correct_argv(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return FakeResult()

    monkeypatch.setattr(device_cli.subprocess, "run", fake_run)
    device_cli.set_active_profile(3, model="607")

    assert captured["argv"] == ["mouse_m908", "-p", "3", "-M", "607"]


def test_apply_config_raises_mouse_not_found_on_detect_failure(monkeypatch):
    monkeypatch.setattr(
        device_cli.subprocess,
        "run",
        lambda *a, **k: FakeResult(
            stderr="Couldn't detect mouse.\n- Check hardware and permissions",
            returncode=1,
        ),
    )
    with pytest.raises(device_cli.MouseNotFoundError):
        device_cli.apply_config(Path("/tmp/config.ini"))


def test_apply_config_raises_generic_error_on_other_failure(monkeypatch):
    monkeypatch.setattr(
        device_cli.subprocess,
        "run",
        lambda *a, **k: FakeResult(
            stderr="Could not open configuration file.", returncode=1
        ),
    )
    with pytest.raises(device_cli.MouseCliError) as exc_info:
        device_cli.apply_config(Path("/tmp/config.ini"))
    assert not isinstance(exc_info.value, device_cli.MouseNotFoundError)


def test_list_models_parses_lines(monkeypatch):
    monkeypatch.setattr(
        device_cli.subprocess,
        "run",
        lambda *a, **k: FakeResult(stdout="908\n607\ngeneric\n"),
    )
    assert device_cli.list_models() == ["908", "607", "generic"]


def test_cli_not_installed_raises_mouse_cli_error(monkeypatch):
    def raise_not_found(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(device_cli.subprocess, "run", raise_not_found)
    with pytest.raises(device_cli.MouseCliError):
        device_cli.list_models()
