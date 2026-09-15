"""Reading, in-place editing and writing of Java .properties files."""

import os
import re
import stat

_SEP = re.compile(r"[ \t]*[=:][ \t]*|[ \t]+")
_ESC = re.compile(r"\\(u[0-9a-fA-F]{4}|.)")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "f": "\f"}


def _split(line):
    s = line.lstrip(" \t\f")
    if not s or s[0] in "#!":
        return None
    m = _SEP.search(s)
    if not m:
        return s, ""
    return s[: m.start()], s[m.end() :]


def _unescape(s):
    def sub(m):
        c = m.group(1)
        return chr(int(c[1:], 16)) if len(c) == 5 else _ESCAPES.get(c, c)

    return _ESC.sub(sub, s)


def _read_text(path):
    try:
        with open(path, encoding="utf-8", errors="surrogateescape", newline="") as f:
            return f.read()
    except FileNotFoundError:
        return None


def read(path):
    """Returns the file's keys and values, or {} when it doesn't exist."""
    out = {}
    for line in (_read_text(path) or "").splitlines():
        kv = _split(line)
        if kv:
            out[kv[0]] = _unescape(kv[1])
    return out


def update(path, changes):
    """Sets keys in place and appends missing ones; other lines stay as they are.

    Creates the file if needed. Returns whether anything changed.
    """
    text = _read_text(path) or ""
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    changed, seen = False, set()
    for i, line in enumerate(lines):
        kv = _split(line)
        if kv and kv[0] in changes:
            seen.add(kv[0])
            if kv[1] != changes[kv[0]]:
                lines[i] = f"{kv[0]}={changes[kv[0]]}"
                changed = True
    for key, value in changes.items():
        if key not in seen:
            lines.append(f"{key}={value}")
            changed = True
    if changed:
        write_atomic(path, eol.join(lines) + eol)
    return changed


def escape(value):
    s = str(value).replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
    return "\\" + s if s[:1] in (" ", "\t", "\f") else s


def dump(values):
    lines = ["# Written by CraftyVecta before every start; edits are overwritten."]
    lines += [f"{key}={escape(value)}" for key, value in values.items()]
    return "\n".join(lines) + "\n"


def write_atomic(path, text, mode=None):
    """Replaces the file in one step. mode defaults to the existing file's."""
    path = os.fspath(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if mode is None:
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except FileNotFoundError:
            mode = 0o664
    tmp = f"{path}.craftyvecta.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
