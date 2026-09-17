"""Deployment settings, read once from the Crafty container's environment."""

import os
from dataclasses import dataclass

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def parse_bool(value, default):
    if value is None:
        return default
    v = str(value).strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return default


def parse_range(value):
    lo, sep, hi = value.strip().partition("-")
    lo, hi = int(lo), int(hi if sep else lo)
    if not 1024 <= lo <= hi <= 65535:
        raise ValueError(f"invalid port range {value!r}")
    return lo, hi


@dataclass(frozen=True)
class Settings:
    gateway: str = "http://vecta:8080"
    token: str = ""
    backend_host: str = "crafty"
    default_enabled: bool = True
    autoports: bool = True
    port_range: tuple = (25500, 25999)
    rcon_offset: int = 1000
    fix_throttle: bool = True
    voice_chat: bool = True
    voice_port_range: tuple = (24000, 24499)
    jar: str = "/crafty/vecta/vecta.jar"
    hooks_dir: str = "/crafty/vecta/hooks"
    state_dir: str = "app/config/vecta"
    branding: bool = True
    domain: str = ""
    public_url: str = ""

    @classmethod
    def from_env(cls, env):
        d = cls()
        return cls(
            gateway=env.get("VECTA_GATEWAY", d.gateway).strip().rstrip("/"),
            token=env.get("VECTA_TOKEN", d.token).strip(),
            backend_host=env.get("VECTA_BACKEND_HOST", d.backend_host).strip(),
            default_enabled=parse_bool(env.get("VECTA_DEFAULT_ENABLED"), d.default_enabled),
            autoports=parse_bool(env.get("VECTA_AUTOPORTS"), d.autoports),
            port_range=parse_range(env["VECTA_PORT_RANGE"]) if env.get("VECTA_PORT_RANGE") else d.port_range,
            rcon_offset=int(env.get("VECTA_RCON_OFFSET", d.rcon_offset)),
            fix_throttle=parse_bool(env.get("VECTA_FIX_THROTTLE"), d.fix_throttle),
            voice_chat=parse_bool(env.get("VECTA_VOICE_CHAT"), d.voice_chat),
            voice_port_range=(
                parse_range(env["VECTA_VOICE_PORT_RANGE"]) if env.get("VECTA_VOICE_PORT_RANGE") else d.voice_port_range
            ),
            jar=env.get("VECTA_JAR", d.jar),
            hooks_dir=env.get("VECTA_HOOKS_DIR", d.hooks_dir),
            state_dir=os.path.abspath(env.get("VECTA_STATE_DIR", d.state_dir)),
            branding=parse_bool(env.get("VECTA_BRANDING"), d.branding),
            domain=env.get("VECTA_DOMAIN", d.domain).strip(),
            public_url=env.get("VECTA_PUBLIC_URL", d.public_url).strip(),
        )


def take_env(environ):
    """Reads the settings and removes every VECTA_* variable from environ.

    Server processes inherit Crafty's environment, and the vecta jar lets
    VECTA_* variables override its config file, so a global value would
    replace each server's own serverId, address and so on.
    """
    env = {key: environ.pop(key) for key in list(environ) if key.startswith("VECTA_")}
    return Settings.from_env(env)
