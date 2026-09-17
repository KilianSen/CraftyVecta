import dataclasses
import os

import pytest

from craftyvecta import launch, props
from craftyvecta.config import Settings
from craftyvecta.state import State

UUID = "5b7e1c1a-0000-4000-8000-000000000001"
PAPER = ["java", "-Xms1G", "-Xmx2G", "-jar", "paper.jar", "nogui"]


@pytest.fixture
def env(tmp_path):
    server_dir = tmp_path / "servers" / UUID
    server_dir.mkdir(parents=True)
    (server_dir / "server.properties").write_text("server-port=25565\nenable-query=true\nquery.port=25565\n")
    settings = Settings(token="secret", state_dir=str(tmp_path / "vecta"))
    return server_dir, settings, State(tmp_path / "vecta" / "state.json")


def run(env, command=PAPER, settings=None, type="minecraft-java"):
    server_dir, default_settings, state = env
    server = launch.Server(UUID, "My Server", str(server_dir), type, list(command), 25565)
    return launch.prepare(server, settings or default_settings, state, lambda p, protocol="tcp": True)


def config_path(env):
    return os.path.join(env[1].state_dir, "servers", UUID + ".properties")


def config_of(env):
    return props.read(config_path(env))


def messages(result, level):
    return [text for lvl, text in result.messages if lvl == level]


def test_injects_agent_and_writes_config(env):
    _, settings, _ = env
    r = run(env)
    assert r.command == ["java", f"-javaagent:{settings.jar}", f"-Dvecta.config={config_path(env)}", *PAPER[1:]]
    assert "secret" not in " ".join(r.command)
    assert r.port == 25565
    assert config_of(env) == {
        "gateway": "http://vecta:8080",
        "token": "secret",
        "serverId": "my-server",
        "name": "My Server",
        "address": "crafty:25565",
    }
    assert messages(r, "warning") == [] and messages(r, "critical") == []


def test_forge_args_file_command(env):
    cmd = ["java", "@user_jvm_args.txt", "@libraries/net/neoforged/neoforge/21.1.1/unix_args.txt", "nogui"]
    r = run(env, cmd)
    assert r.command[1].startswith("-javaagent:")
    assert r.command[3:] == cmd[1:]


def test_script_gets_the_agent_through_jdk_java_options(env):
    _, settings, _ = env
    r = run(env, ["sh", "run.sh", "nogui"])
    options = f"JDK_JAVA_OPTIONS=-javaagent:{settings.jar} -Dvecta.config={config_path(env)}"
    assert r.command == ["env", options, "sh", "run.sh", "nogui"]
    assert config_of(env)["serverId"] == "my-server"


def test_old_vecta_options_are_removed(env):
    server_dir, settings, _ = env
    (server_dir / "user_jvm_args.txt").write_text(
        "# JVM arguments\n-Xmx4G\n-javaagent:vecta.jar=token=old\n-Dvecta.gateway=https://old.example -XX:+UseG1GC\n"
    )
    r = run(env, ["java", "-Dvecta.token=old", "-javaagent:libs/VectaMine.jar", "@user_jvm_args.txt", "nogui"])
    assert r.command == [
        "java",
        f"-javaagent:{settings.jar}",
        f"-Dvecta.config={config_path(env)}",
        "@user_jvm_args.txt",
        "nogui",
    ]
    assert (server_dir / "user_jvm_args.txt").read_text() == "# JVM arguments\n-Xmx4G\n -XX:+UseG1GC\n"
    assert messages(r, "warning") == [
        "start command: ignoring -Dvecta.token, -javaagent (vecta)",
        "user_jvm_args.txt: removed -javaagent (vecta), -Dvecta.gateway",
    ]


def test_script_cleans_user_jvm_args(env):
    server_dir = env[0]
    (server_dir / "user_jvm_args.txt").write_text("-Xmx4G -javaagent:vecta.jar\n")
    run(env, ["./run.sh"])
    assert (server_dir / "user_jvm_args.txt").read_text() == "-Xmx4G \n"


def test_proxy_backend_is_made_reachable(env):
    server_dir = env[0]
    (server_dir / "server.properties").write_text("server-port=25565\nserver-ip=127.0.0.1\nonline-mode=false\n")
    (server_dir / "spigot.yml").write_text("settings:\n  bungeecord: true\n  timeout-time: 60\n")
    (server_dir / "config").mkdir()
    paper = "proxies:\n  bungee-cord:\n    online-mode: true\n  velocity:\n    enabled: true\n    online-mode: true\n    secret: ''\n"
    (server_dir / "config" / "paper-global.yml").write_text(paper)

    r = run(env)
    assert r.command[1].startswith("-javaagent:")
    p = props.read(server_dir / "server.properties")
    assert (p["server-ip"], p["online-mode"]) == ("", "true")
    assert (server_dir / "spigot.yml").read_text() == "settings:\n  bungeecord: false\n  timeout-time: 60\n"
    assert (server_dir / "config" / "paper-global.yml").read_text() == paper.replace("enabled: true", "enabled: false")
    assert messages(r, "critical") == []


def test_offline_mode_is_refused(env):
    server_dir = env[0]
    original = "server-port=25565\nserver-ip=127.0.0.1\nonline-mode=false\n"
    (server_dir / "server.properties").write_text(original)
    r = run(env)
    assert r.command == PAPER
    assert (server_dir / "server.properties").read_text() == original
    assert config_of(env) == {}
    [critical] = messages(r, "critical")
    assert "online-mode=false" in critical and "allowOfflineMode=true" in critical


def test_offline_mode_allowed_by_override(env):
    server_dir = env[0]
    (server_dir / "server.properties").write_text("server-port=25565\nonline-mode=false\n")
    (server_dir / launch.OVERRIDE_FILE).write_text("allowOfflineMode=true\n")
    r = run(env)
    assert r.command[1].startswith("-javaagent:")
    assert messages(r, "warning") == ["online-mode=false: anyone can join under any name (allowOfflineMode=true)"]
    assert "allowOfflineMode" not in config_of(env)


def test_server_ip_of_the_backend_host_is_kept(env):
    server_dir, settings, _ = env
    (server_dir / "server.properties").write_text("server-port=25565\nserver-ip=10.0.0.5\n")
    run(env, settings=dataclasses.replace(settings, backend_host="10.0.0.5"))
    assert props.read(server_dir / "server.properties")["server-ip"] == "10.0.0.5"


def test_autoports_move_a_conflicting_server(env):
    server_dir, settings, state = env
    state.claim_port("other", 25565, settings.port_range, lambda p: True)
    (server_dir / "server.properties").write_text("server-port=25565\nenable-query=true\nenable-rcon=true\n")
    r = run(env)
    assert r.port == 25500
    assert props.read(server_dir / "server.properties") == {
        "server-port": "25500",
        "enable-query": "true",
        "enable-rcon": "true",
        "query.port": "25500",
        "rcon.port": "26500",
    }
    assert config_of(env)["address"] == "crafty:25500"


def test_port_from_command_line_wins(env):
    server_dir, _, _ = env
    r = run(env, PAPER + ["--port", "25700"])
    assert r.port is None
    assert config_of(env)["address"] == "crafty:25700"
    assert props.read(server_dir / "server.properties")["server-port"] == "25565"
    assert messages(r, "warning") == ["the start command sets --port; autoports skipped"]


def test_autoports_off(env):
    server_dir, settings, _ = env
    (server_dir / "server.properties").write_text("server-port=12345\n")
    r = run(env, settings=dataclasses.replace(settings, autoports=False, backend_host="10.0.0.5"))
    assert r.port is None
    assert config_of(env)["address"] == "10.0.0.5:12345"


@pytest.mark.parametrize(
    "kwargs, override, expected_warning",
    [
        ({"type": "minecraft-bedrock"}, None, None),
        ({"command": ["python3", "server.py"]}, None, "runs neither java nor a .sh script"),
        ({"settings": Settings(token="")}, None, "VECTA_TOKEN is not set"),
        ({}, "enabled=false\n", None),
    ],
)
def test_servers_left_unchanged(env, kwargs, override, expected_warning):
    server_dir = env[0]
    if override:
        (server_dir / launch.OVERRIDE_FILE).write_text(override)
    command = kwargs.pop("command", PAPER)
    r = run(env, command, **kwargs)
    assert r.command == command
    assert r.port is None
    found = messages(r, "warning")
    if expected_warning:
        assert len(found) == 1 and expected_warning in found[0]
    else:
        assert found == []
    assert config_of(env) == {}


def test_override_file(env):
    server_dir = env[0]
    (server_dir / launch.OVERRIDE_FILE).write_text(
        "serverId=survival\nhidden=true\nrequiredClientMods=create\ntoken=evil\naddress=1.2.3.4:1\n"
    )
    r = run(env)
    config = config_of(env)
    assert (config["serverId"], config["hidden"], config["requiredClientMods"]) == ("survival", "true", "create")
    assert (config["token"], config["address"]) == ("secret", "crafty:25565")
    assert messages(r, "warning") == [f"{launch.OVERRIDE_FILE}: ignoring address, token"]


def test_throttle_fix_only_touches_the_default(env):
    server_dir = env[0]
    bukkit = server_dir / "bukkit.yml"
    bukkit.write_bytes(b"settings:\r\n  connection-throttle: 4000\r\n  shutdown-message: Bye\r\n")
    run(env)
    assert bukkit.read_bytes() == b"settings:\r\n  connection-throttle: -1\r\n  shutdown-message: Bye\r\n"

    bukkit.write_text("settings:\n  connection-throttle: 1000\n")
    run(env)
    assert bukkit.read_text() == "settings:\n  connection-throttle: 1000\n"


SVC_FABRIC = "voicechat-fabric-1.21.1-2.6.22.jar"


def voice_file(server_dir, folder="config"):
    return server_dir / folder / "voicechat" / "voicechat-server.properties"


def test_simple_voice_chat_gets_a_port_and_a_side_port(env):
    server_dir, settings, state = env
    (server_dir / "mods").mkdir()
    (server_dir / "mods" / SVC_FABRIC).write_bytes(b"")
    r = run(env)
    assert props.read(voice_file(server_dir)) == {"port": "24000"}
    config = config_of(env)
    assert config["sidePorts"] == "voicechat:udp:24000"
    assert config["sidePortHook"] == f"sh {settings.hooks_dir}/sideport.sh"
    assert "Simple Voice Chat on UDP 24000, public address assigned by the gateway" in messages(r, "info")
    assert messages(r, "warning") == []

    # Another server gets the next port; this one keeps its own.
    state.claim_port("other", None, settings.voice_port_range, lambda p: True, field="voicePort")
    run(env)
    assert config_of(env)["sidePorts"] == "voicechat:udp:24000"


def test_simple_voice_chat_plugin_config_is_fixed(env):
    server_dir = env[0]
    (server_dir / "plugins").mkdir()
    (server_dir / "plugins" / "voicechat-bukkit-2.6.1.jar").write_bytes(b"")
    f = voice_file(server_dir, "plugins")
    f.parent.mkdir(parents=True)
    f.write_text("# Simple Voice Chat server config\nport=24454\nbind_address=127.0.0.1\nvoice_host=old:1\n")
    run(env)
    # SVC's default port fits the voice range, so the server keeps it.
    assert f.read_text() == "# Simple Voice Chat server config\nport=24454\nbind_address=\nvoice_host=old:1\n"
    assert config_of(env)["sidePorts"] == "voicechat:udp:24454"


@pytest.mark.parametrize(
    "jar, override, settings_kw, expected",
    [
        ("voicechat_interaction-fabric-1.21.1-1.0.0.jar", None, {}, None),
        (None, "voiceChat=true\n", {}, "voicechat:udp:24000"),
        (SVC_FABRIC, "voiceChat=false\n", {}, None),
        (SVC_FABRIC, None, {"voice_chat": False}, None),
        (None, "voiceChat=true\n", {"voice_chat": False}, "voicechat:udp:24000"),
    ],
)
def test_simple_voice_chat_detection(env, jar, override, settings_kw, expected):
    server_dir, settings, _ = env
    (server_dir / "mods").mkdir()
    if jar:
        (server_dir / "mods" / jar).write_bytes(b"")
    if override:
        (server_dir / launch.OVERRIDE_FILE).write_text(override)
    run(env, settings=dataclasses.replace(settings, **settings_kw))
    assert config_of(env).get("sidePorts") == expected
    assert voice_file(server_dir).exists() == bool(expected)


def test_simple_voice_chat_without_free_port(env):
    server_dir, settings, state = env
    (server_dir / "mods").mkdir()
    (server_dir / "mods" / SVC_FABRIC).write_bytes(b"")
    small = dataclasses.replace(settings, voice_port_range=(24000, 24000))
    state.claim_port("other", 24000, small.voice_port_range, lambda p: True, field="voicePort")
    r = run(env, settings=small)
    assert "sidePorts" not in config_of(env)
    assert r.command[1].startswith("-javaagent:")
    assert messages(r, "warning") == [
        "Simple Voice Chat: no free port left in 24000-24000; voice chat is not reachable through vecta"
    ]


def test_own_side_ports_and_hook(env):
    server_dir, settings, _ = env
    (server_dir / "mods").mkdir()
    (server_dir / "mods" / SVC_FABRIC).write_bytes(b"")
    (server_dir / launch.OVERRIDE_FILE).write_text(
        "sidePorts=map:tcp:8100, voicechat:udp:1, bad, map:udp:1, votes:tcp:8192\nsidePortHook=./hooks/ports.sh --quiet\n"
    )
    r = run(env)
    config = config_of(env)
    assert config["sidePorts"] == "voicechat:udp:24000,map:tcp:8100,votes:tcp:8192"
    assert config["sidePortHook"] == f"sh {settings.hooks_dir}/sideport.sh ./hooks/ports.sh --quiet"
    assert messages(r, "warning") == [
        f"{launch.OVERRIDE_FILE}: sidePorts: ignoring 'voicechat:udp:1' (name already in use)",
        f"{launch.OVERRIDE_FILE}: sidePorts: ignoring 'bad' (expected name:tcp|udp:port)",
        f"{launch.OVERRIDE_FILE}: sidePorts: ignoring 'map:udp:1' (name already in use)",
    ]


def test_side_port_hook_without_side_ports(env):
    server_dir = env[0]
    (server_dir / launch.OVERRIDE_FILE).write_text("sidePortHook=./x.sh\n")
    r = run(env)
    assert "sidePortHook" not in config_of(env)
    assert messages(r, "warning") == [f"{launch.OVERRIDE_FILE}: sidePortHook without sidePorts is ignored"]
