"""Server config that would keep players from joining through the gateway.

Uploaded servers bring their own config, often from behind a BungeeCord or
Velocity proxy: bound to 127.0.0.1, in offline mode, expecting forwarding
data. inspect() finds what to change before anything is written, so a
refused server stays untouched.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Optional

from . import props
from .config import parse_bool

_ALL_ADDRESSES = {"", "0.0.0.0", "::"}
# The server then expects connection data from a proxy, which the gateway
# doesn't send, so every join is kicked.
FORWARDING = (
    ("spigot.yml", ("settings", "bungeecord"), "BungeeCord forwarding"),
    (os.path.join("config", "paper-global.yml"), ("proxies", "velocity", "enabled"), "Velocity forwarding"),
    ("paper.yml", ("settings", "velocity-support", "enabled"), "Velocity forwarding"),
)
_KEY = re.compile(
    r"""(?P<key>'[^']*'|"[^"]*"|[^\s:#'"][^:#]*?):(?:[ \t]+(?P<value>[^#\s][^#]*?))?[ \t]*(?:#.*)?$"""
)


@dataclass
class Fixes:
    properties: dict = field(default_factory=dict)
    yaml: list = field(default_factory=list)  # (file, key path, old, new, message)
    messages: list = field(default_factory=list)  # (level, text)
    refusal: Optional[str] = None


def inspect(server_dir, settings, allow_offline):
    fixes = Fixes()
    existing = props.read(os.path.join(server_dir, "server.properties"))

    ip = existing.get("server-ip", "").strip()
    if ip not in _ALL_ADDRESSES and ip != settings.backend_host:
        fixes.properties["server-ip"] = ""
        fixes.messages.append(
            ("info", f"server.properties: server-ip={ip} -> all addresses (the gateway connects from outside)")
        )

    forwarded = False
    for file, path, label in FORWARDING:
        text = _read(os.path.join(server_dir, file))
        if text is not None and yaml_replace(text, path, "true", "false")[1]:
            forwarded = True
            fixes.yaml.append((file, path, "true", "false", f"{file}: {label} off (no proxy in front of vecta)"))

    if not parse_bool(existing.get("online-mode"), True):
        if forwarded:
            fixes.properties["online-mode"] = "true"
            fixes.messages.append(
                (
                    "info",
                    "server.properties: online-mode=true; the proxy used to authenticate players, now the "
                    "server does (player UUIDs stay the same if the proxy ran in online mode)",
                )
            )
        elif allow_offline:
            fixes.messages.append(("warning", "online-mode=false: anyone can join under any name (allowOfflineMode=true)"))
        else:
            fixes.refusal = (
                "online-mode=false would let anyone join under any name, including an operator's; set "
                "online-mode=true, or allowOfflineMode=true in vecta.override.properties to accept that"
            )
    return fixes


def apply(server_dir, fixes, result):
    result.messages.extend(fixes.messages)
    if fixes.properties:
        props.update(os.path.join(server_dir, "server.properties"), fixes.properties)
    for file, path, old, new, message in fixes.yaml:
        if _replace_in(os.path.join(server_dir, file), path, old, new):
            result.info(message)


def fix_throttle(server_dir, result):
    """Every player arrives from the gateway's address, so Bukkit's default
    per-address throttle (4 s) would turn most joins away."""
    if _replace_in(os.path.join(server_dir, "bukkit.yml"), ("settings", "connection-throttle"), "4000", "-1"):
        result.info("bukkit.yml: connection-throttle 4000 -> -1 (all players arrive from the gateway)")


def yaml_replace(text, path, old, new):
    """Replaces the scalar at a key path when it equals old.

    Only block mappings are understood, which is how Bukkit, Spigot and
    Paper write their files. Everything else stays byte for byte. Returns
    (text, whether it was replaced).
    """
    lines = text.splitlines(keepends=True)
    stack = []  # [indent of a matched key, indent of its children or None]
    for i, line in enumerate(lines):
        content = line.rstrip("\r\n")
        body = content.lstrip(" ")
        if not body or body.startswith("#"):
            continue
        indent = len(content) - len(body)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if stack:
            if stack[-1][1] is None:
                stack[-1][1] = indent
            if indent != stack[-1][1]:
                continue
        elif indent != 0:
            continue
        m = _KEY.match(body)
        if not m or m.group("key").strip("'\"") != path[len(stack)]:
            continue
        if len(stack) + 1 < len(path):
            if m.group("value") is None:
                stack.append([indent, None])
            continue
        if m.group("value") != old:
            return text, False
        start, end = indent + m.start("value"), indent + m.end("value")
        lines[i] = content[:start] + new + content[end:] + line[len(content) :]
        return "".join(lines), True
    return text, False


def _read(file):
    try:
        with open(file, encoding="utf-8", errors="surrogateescape", newline="") as f:
            return f.read()
    except (FileNotFoundError, NotADirectoryError):
        return None


def _replace_in(file, path, old, new):
    text = _read(file)
    if text is None:
        return False
    text, replaced = yaml_replace(text, path, old, new)
    if replaced:
        props.write_atomic(file, text)
    return replaced
