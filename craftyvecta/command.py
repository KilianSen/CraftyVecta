"""Finding the JVM in a start command and adding the vecta agent to it."""

import os
import re

from . import props

_JAVA = {"java", "java.exe", "javaw", "javaw.exe"}
_SHELLS = {"sh", "bash", "dash"}
# Forge/NeoForge's run.sh reads its JVM options from this file.
JVM_ARGS_FILE = "user_jvm_args.txt"
_ARGFILE_OPTION = re.compile(r'(?<!\S)(?:"-(?:javaagent:|D)[^"]*"|-(?:javaagent:|D)\S*)(?!\S)')


def kind(command):
    """"java" for a command that runs java, "script" for a .sh script, else None."""
    exe = os.path.basename(command[0]).lower()
    if exe in _JAVA:
        return "java"
    if exe.endswith(".sh") or (exe in _SHELLS and len(command) > 1 and command[1].lower().endswith(".sh")):
        return "script"
    return None


def is_vecta_option(arg):
    a = arg.strip('"')
    return a.startswith("-Dvecta.") or (a.startswith("-javaagent:") and "vecta" in a.lower())


def _label(arg):
    a = arg.strip('"')
    return a.split("=", 1)[0] if a.startswith("-D") else "-javaagent (vecta)"


def strip_vecta(command, server_dir, kind_, result):
    """Removes vecta agents and -Dvecta.* options that came with the server.

    They would start a second vecta, or override CraftyVecta's settings: the
    jar lets system properties win over its config file. The stored command
    keeps them and only this start drops them; argument files (@file, and
    user_jvm_args.txt for scripts) are cleaned in place. Values aren't
    logged, they may hold an old token.
    """
    removed = [_label(a) for a in command if is_vecta_option(a)]
    kept = [a for a in command if not is_vecta_option(a)]
    if removed:
        result.warn(f"start command: ignoring {', '.join(removed)}")
    files = [a[1:] for a in kept if a.startswith("@") and not a.startswith("@@")]
    if kind_ == "script":
        files.append(JVM_ARGS_FILE)
    for name in dict.fromkeys(files):
        _clean_argfile(server_dir, name, result)
    return kept


def _clean_argfile(server_dir, name, result):
    root = os.path.realpath(server_dir)
    file = os.path.realpath(os.path.join(root, name))
    try:
        if os.path.commonpath([root, file]) != root or not os.path.isfile(file):
            return
    except ValueError:  # another drive
        return
    with open(file, encoding="utf-8", errors="surrogateescape", newline="") as f:
        lines = f.read().splitlines(keepends=True)
    removed = []

    def drop(m):
        if not is_vecta_option(m.group(0)):
            return m.group(0)
        removed.append(_label(m.group(0)))
        return ""

    out = []
    for line in lines:
        cleaned = line if line.lstrip().startswith("#") else _ARGFILE_OPTION.sub(drop, line)
        if cleaned != line and not cleaned.strip():
            continue
        out.append(cleaned)
    if removed:
        props.write_atomic(file, "".join(out))
        result.warn(f"{name}: removed {', '.join(removed)}")


def inject(command, kind_, jar, config):
    options = [f"-javaagent:{jar}", f"-Dvecta.config={config}"]
    if kind_ == "java":
        return [command[0], *options, *command[1:]]
    # A script starts java itself; the java launcher (Java 9+) adds JDK_JAVA_OPTIONS.
    return ["env", "JDK_JAVA_OPTIONS=" + " ".join(_quote(o) for o in options), *command]


def _quote(option):
    return f'"{option}"' if any(c.isspace() for c in option) else option
