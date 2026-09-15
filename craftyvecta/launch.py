"""What CraftyVecta does to a Minecraft Java server right before it starts."""

import os
import re
import socket
from dataclasses import dataclass, field
from typing import Optional

from . import command as commands
from . import props, serverfiles
from .config import parse_bool

OVERRIDE_FILE = "vecta.override.properties"
# Override keys handed to the jar. The connection (gateway, token, address)
# and the guard come from the deployment only.
PASSTHROUGH = (
    "name",
    "description",
    "hidden",
    "requiredClientMods",
    "loader",
    "protocols",
    "proxyProtocol",
    "commands",
    "runtimeChecks",
    "heartbeatSeconds",
    "debug",
)
# Override keys CraftyVecta reads itself.
OWN_KEYS = ("enabled", "serverId", "allowOfflineMode")
_UUID = re.compile(r"^[A-Za-z0-9-]+$")


@dataclass
class Server:
    uuid: str
    name: str
    path: str
    type: str
    command: list
    db_port: int


@dataclass
class Result:
    command: list
    port: Optional[int] = None  # the game port, when autoports chose it
    messages: list = field(default_factory=list)  # (level, text)

    def info(self, text):
        self.messages.append(("info", text))

    def warn(self, text):
        self.messages.append(("warning", text))

    def critical(self, text):
        self.messages.append(("critical", text))


def prepare(server, settings, state, is_free):
    """Returns the start command with the vecta jar and readies the server's files."""
    result = Result(list(server.command))
    if server.type != "minecraft-java" or not server.command:
        return result
    overrides = props.read(os.path.join(server.path, OVERRIDE_FILE))
    if not parse_bool(overrides.get("enabled"), settings.default_enabled):
        result.info("vecta is off for this server")
        return result
    if not settings.token:
        result.warn("VECTA_TOKEN is not set; starting without vecta")
        return result
    kind = commands.kind(server.command)
    if kind is None:
        result.warn(
            f"the start command runs neither java nor a .sh script ({server.command[0]}); starting without vecta"
        )
        return result
    if not _UUID.match(server.uuid):
        raise ValueError(f"unexpected server id {server.uuid!r}")
    fixes = serverfiles.inspect(server.path, settings, parse_bool(overrides.get("allowOfflineMode"), False))
    if fixes.refusal:
        result.critical(f"{fixes.refusal}; starting without vecta")
        return result

    command = commands.strip_vecta(server.command, server.path, kind, result)
    port = _game_port(server, command, settings, state, is_free, result)
    server_id, problem = state.claim_id(server.uuid, server.name, overrides.get("serverId"))
    if problem:
        result.warn(f"{problem}; using {server_id}")
    ignored = sorted(set(overrides) - set(PASSTHROUGH) - set(OWN_KEYS))
    if ignored:
        result.warn(f"{OVERRIDE_FILE}: ignoring {', '.join(ignored)}")

    values = {
        "gateway": settings.gateway,
        "token": settings.token,
        "serverId": server_id,
        "name": server.name,
        "address": f"{settings.backend_host}:{port}",
    }
    values.update((key, overrides[key]) for key in PASSTHROUGH if key in overrides)
    config = os.path.join(settings.state_dir, "servers", f"{server.uuid}.properties")
    props.write_atomic(config, props.dump(values), mode=0o600)

    serverfiles.apply(server.path, fixes, result)
    if settings.fix_throttle:
        serverfiles.fix_throttle(server.path, result)
    result.command = commands.inject(command, kind, settings.jar, config)
    result.info(f"joins vecta as {server_id} ({values['address']})")
    return result


def _game_port(server, command, settings, state, is_free, result):
    from_command = _command_port(command)
    if from_command:
        if settings.autoports:
            result.warn("the start command sets --port; autoports skipped")
        return from_command
    path = os.path.join(server.path, "server.properties")
    existing = props.read(path)
    current = _int(existing.get("server-port")) or server.db_port
    if not settings.autoports:
        return current
    port = state.claim_port(server.uuid, current, settings.port_range, is_free)
    changes = {"server-port": str(port)}
    if parse_bool(existing.get("enable-query"), False):
        changes["query.port"] = str(port)
    if parse_bool(existing.get("enable-rcon"), False):
        changes["rcon.port"] = str(port + settings.rcon_offset)
    if props.update(path, changes):
        result.info(f"server.properties: server-port={port}")
    result.port = port
    return port


def _command_port(command):
    for i, arg in enumerate(command):
        if arg == "--port" and i + 1 < len(command):
            return _int(command[i + 1])
        if arg.startswith("--port="):
            return _int(arg.split("=", 1)[1])
    return None


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def port_is_free(port):
    """Whether nothing listens on the TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if os.name != "nt":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True
