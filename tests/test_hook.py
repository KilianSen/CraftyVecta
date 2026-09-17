import sys

import pytest

from craftyvecta import hook, launch

# A stand-in for the parts of Crafty's app/classes/shared/server.py the hook uses.
FAKE_SERVER_MODULE = '''
class Servers:
    server_id = "server_id"
    updates = []

    @classmethod
    def update(cls, **values):
        return _Query(cls, values)


class _Query:
    def __init__(self, model, values):
        self.model, self.values = model, values

    def where(self, _condition):
        return self

    def execute(self):
        self.model.updates.append(self.values)


class ServerInstance:
    def __init__(self, path):
        self.server_id = "5b7e1c1a-0000-4000-8000-000000000001"
        self.name = "My Server"
        self.settings = {"type": "minecraft-java", "server_port": 25565}
        self.path = path
        self.reloads = 0

    def setup_server_run_command(self):
        self.server_command = ["java", "-jar", "server.jar", "nogui"]
        self.server_path = self.path

    def reload_server_settings(self):
        self.reloads += 1
'''


@pytest.fixture
def fake_crafty(tmp_path, monkeypatch):
    def write(source):
        shared = tmp_path / "app" / "classes" / "shared"
        shared.mkdir(parents=True, exist_ok=True)
        for d in (tmp_path / "app", tmp_path / "app" / "classes", shared):
            (d / "__init__.py").write_text("")
        (shared / "server.py").write_text(source)
        (tmp_path / "srv").mkdir(exist_ok=True)
        return tmp_path

    monkeypatch.syspath_prepend(str(tmp_path))
    yield write
    for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[name]
    sys.meta_path[:] = [f for f in sys.meta_path if not isinstance(f, hook._Finder)]


def install(root):
    environ = {
        "VECTA_TOKEN": "secret",
        "VECTA_PORT_RANGE": "26000-26010",
        "VECTA_STATE_DIR": str(root / "vecta"),
        "PATH": "/usr/bin",
    }
    hook.install(environ, is_free=lambda p, protocol="tcp": True)
    return environ


def test_hook_wraps_server_start(fake_crafty):
    root = fake_crafty(FAKE_SERVER_MODULE)
    environ = install(root)
    assert environ == {"PATH": "/usr/bin"}

    from app.classes.shared import server

    instance = server.ServerInstance(str(root / "srv"))
    instance.setup_server_run_command()
    assert instance.server_command[0] == "java"
    assert instance.server_command[1] == "-javaagent:/crafty/vecta/vecta.jar"
    assert instance.server_command[3:] == ["-jar", "server.jar", "nogui"]
    assert server.Servers.updates == [{"server_port": 26000}]
    assert instance.reloads == 1


def test_second_install_keeps_the_first(fake_crafty):
    root = fake_crafty(FAKE_SERVER_MODULE)
    install(root)
    hook.install({})  # craftyvecta.pth processed again, VECTA_* already gone
    assert [f.settings.token for f in sys.meta_path if isinstance(f, hook._Finder)] == ["secret"]

    from app.classes.shared import server

    instance = server.ServerInstance(str(root / "srv"))
    instance.setup_server_run_command()
    assert instance.server_command[1] == "-javaagent:/crafty/vecta/vecta.jar"


def test_failure_starts_the_server_unchanged(fake_crafty, monkeypatch, capsys):
    root = fake_crafty(FAKE_SERVER_MODULE)
    install(root)

    def broken(*_args):
        raise RuntimeError("boom")

    monkeypatch.setattr(launch, "prepare", broken)
    from app.classes.shared import server

    instance = server.ServerInstance(str(root / "srv"))
    instance.setup_server_run_command()
    assert instance.server_command == ["java", "-jar", "server.jar", "nogui"]
    assert "My Server: boom; starting without vecta" in capsys.readouterr().err


def test_unsupported_crafty_is_reported(fake_crafty, capsys):
    root = fake_crafty("class ServerInstance:\n    pass\n")
    install(root)
    import app.classes.shared.server  # noqa: F401

    assert "this Crafty version is not supported" in capsys.readouterr().err
