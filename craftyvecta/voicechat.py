"""Simple Voice Chat through the gateway.

All Crafty servers share one container, so each needs its own voice port, and
clients must send voice to the public address the gateway assigned
(voice_host). CraftyVecta picks the port and declares it as a side port. The
jar then runs hooks/sideport.sh with the assigned address, which writes
voice_host (vecta's examples/sideport-hooks/simple-voice-chat.sh).
"""

import os
import re

from . import props

SIDE_PORT = "voicechat"
MODS = os.path.join("config", "voicechat", "voicechat-server.properties")
PLUGINS = os.path.join("plugins", "voicechat", "voicechat-server.properties")
# voicechat-fabric-1.21.1-2.6.22.jar, voicechat-bukkit-2.5.0.jar, voicechat-1.19.2-2.3.4.jar.
# Addons such as voicechat_interaction don't match.
_JAR = re.compile(r"^voicechat-(?:(?:fabric|forge|neoforge|quilt|bukkit|paper|spigot)-)?\d[^/]*\.jar$", re.I)
_ALL_ADDRESSES = {"", "*", "0.0.0.0", "::"}


def config_file(server_dir, forced=False):
    """Returns Simple Voice Chat's server config path, or None when the server doesn't run it.

    forced: the override says voiceChat=true, so a path is returned even
    without a recognizable jar.
    """
    for folder, file in (("mods", MODS), ("plugins", PLUGINS)):
        try:
            names = os.listdir(os.path.join(server_dir, folder))
        except OSError:
            continue
        if any(_JAR.match(name) for name in names):
            return os.path.join(server_dir, file)
    if not forced:
        return None
    for file in (MODS, PLUGINS):
        if os.path.isfile(os.path.join(server_dir, file)):
            return os.path.join(server_dir, file)
    has = lambda folder: os.path.isdir(os.path.join(server_dir, folder))  # noqa: E731
    return os.path.join(server_dir, PLUGINS if has("plugins") and not has("mods") else MODS)


def configure(path, port, backend_host, result):
    """Sets the voice port and clears a bind address the gateway can't reach.

    Creates the file on a first start; the mod adds its defaults and keeps
    these keys.
    """
    existing = props.read(path)
    changes = {"port": str(port)}
    bind = existing.get("bind_address", "").strip()
    if bind not in _ALL_ADDRESSES and bind != backend_host:
        changes["bind_address"] = ""
    rel = os.path.relpath(path, os.path.dirname(os.path.dirname(os.path.dirname(path))))
    if props.update(path, changes):
        result.info(f"{rel}: " + ", ".join(f"{k}={v}" for k, v in changes.items()))
