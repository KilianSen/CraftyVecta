"""The vecta ID and port each Crafty server holds, kept in one JSON file."""

import json
import os
import re
import threading

RESERVED = {"lobby", "api", "www", "play"}
ID_MAX = 32
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:ID_MAX].strip("-")
    return s or "server"


class State:
    def __init__(self, path):
        self.path = os.fspath(path)
        self.lock = threading.RLock()
        try:
            with open(self.path, encoding="utf-8") as f:
                self.servers = json.load(f)["servers"]
        except FileNotFoundError:
            self.servers = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"servers": self.servers}, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    def _taken(self, field, value, uuid):
        return any(key != uuid and entry.get(field) == value for key, entry in self.servers.items())

    def claim_id(self, uuid, name, requested=None):
        """Returns (vecta ID, why requested was refused or None).

        A server keeps its ID across renames. A valid requested ID that no
        other Crafty server holds replaces it.
        """
        with self.lock:
            entry = self.servers.setdefault(uuid, {})
            problem = None
            if requested:
                want = requested.strip().lower()
                if not _ID.match(want) or want in RESERVED:
                    problem = f"serverId {requested!r} is not a valid vecta ID"
                elif self._taken("id", want, uuid):
                    problem = f"serverId {want!r} belongs to another server"
                else:
                    entry["id"] = want
            if not entry.get("id"):
                base = slug(name)
                if base in RESERVED:
                    base += "-server"
                candidate, n = base, 2
                while self._taken("id", candidate, uuid):
                    suffix = f"-{n}"
                    candidate = base[: ID_MAX - len(suffix)].rstrip("-") + suffix
                    n += 1
                entry["id"] = candidate
            self._save()
            return entry["id"], problem

    def claim_port(self, uuid, current, port_range, is_free):
        """Returns a port in port_range that no other Crafty server holds.

        The server keeps its recorded port, else adopts current when that
        fits, else gets the lowest usable one. is_free(port) tells whether
        nothing else listens there.
        """
        lo, hi = port_range
        with self.lock:
            entry = self.servers.setdefault(uuid, {})

            def usable(port):
                return port is not None and lo <= port <= hi and not self._taken("port", port, uuid) and is_free(port)

            port = next((p for p in (entry.get("port"), current) if usable(p)), None)
            if port is None:
                port = next((p for p in range(lo, hi + 1) if usable(p)), None)
            if port is None:
                raise RuntimeError(f"no free port left in {lo}-{hi}")
            if entry.get("port") != port:
                entry["port"] = port
                self._save()
            return port
