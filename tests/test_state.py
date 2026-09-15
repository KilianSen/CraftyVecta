import pytest

from craftyvecta.state import State

RANGE = (25500, 25999)


def free(_port):
    return True


def test_ids_are_unique_and_stable(tmp_path):
    s = State(tmp_path / "state.json")
    assert s.claim_id("a", "My Server") == ("my-server", None)
    assert s.claim_id("b", "My Server!") == ("my-server-2", None)
    assert s.claim_id("a", "Renamed") == ("my-server", None)
    assert State(tmp_path / "state.json").claim_id("b", "Other") == ("my-server-2", None)


def test_reserved_empty_and_long_names(tmp_path):
    s = State(tmp_path / "state.json")
    assert s.claim_id("a", "Lobby") == ("lobby-server", None)
    assert s.claim_id("b", "###") == ("server", None)
    assert s.claim_id("c", "x" * 40) == ("x" * 32, None)
    assert s.claim_id("d", "x" * 40) == ("x" * 30 + "-2", None)


def test_requested_id(tmp_path):
    s = State(tmp_path / "state.json")
    s.claim_id("a", "Survival")
    assert s.claim_id("b", "Other", "SURVIVAL") == ("other", "serverId 'survival' belongs to another server")
    assert s.claim_id("b", "Other", "lobby")[1] == "serverId 'lobby' is not a valid vecta ID"
    assert s.claim_id("b", "Other", "creative") == ("creative", None)


def test_ports_adopt_keep_and_avoid_others(tmp_path):
    s = State(tmp_path / "state.json")
    assert s.claim_port("a", 25565, RANGE, free) == 25565
    assert s.claim_port("b", 25565, RANGE, free) == 25500
    assert s.claim_port("a", 30000, RANGE, free) == 25565
    assert s.claim_port("c", None, RANGE, lambda p: p != 25501) == 25502
    assert State(tmp_path / "state.json").claim_port("b", None, RANGE, free) == 25500


def test_busy_recorded_port_is_replaced(tmp_path):
    s = State(tmp_path / "state.json")
    assert s.claim_port("a", 25600, RANGE, free) == 25600
    assert s.claim_port("a", 25600, RANGE, lambda p: p != 25600) == 25500


def test_ports_exhausted(tmp_path):
    s = State(tmp_path / "state.json")
    s.claim_port("a", None, (25500, 25500), free)
    with pytest.raises(RuntimeError, match="no free port"):
        s.claim_port("b", None, (25500, 25500), free)
