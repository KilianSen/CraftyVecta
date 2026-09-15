"""End-to-end check of uploaded servers on a running CraftyVecta compose stack.

Run next to compose.yaml and .env (after e2e/check.py, or on its own). It
uploads three Paper servers as zip imports, the way a panel user would:

- "Proxy Backend": bound to 127.0.0.1, offline mode, BungeeCord and Velocity
  forwarding on. CraftyVecta must undo all of it and register the server.
- "Cracked": offline mode without forwarding. It must not be registered.
- "Script Pack": started by run.sh, with an old vecta agent and a -Dvecta.*
  option in user_jvm_args.txt. The agent must come from JDK_JAVA_OPTIONS and
  the old options must be gone.

Downloads Paper once (~50 MB) and needs ~4.5 GB RAM.

    python3 e2e/uploads.py
"""

import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.getcwd())
from craftyvecta.serverfiles import yaml_replace  # noqa: E402

ENV = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
CRAFTY = os.environ.get("CRAFTY_URL", f"https://127.0.0.1:{ENV.get('PANEL_PORT', '8443')}") + "/api/v2"
GATEWAY = os.environ.get("GATEWAY_URL", f"http://127.0.0.1:{ENV.get('API_PORT', '8080')}") + "/api/v1"
CTX = ssl._create_unverified_context()
PAPER_VERSION = "1.21.11"
failures = []

PROXY_BACKEND = {
    "server.properties": "server-port=25565\nserver-ip=127.0.0.1\nonline-mode=false\n",
    "spigot.yml": "settings:\n  bungeecord: true\n",
    "config/paper-global.yml": "proxies:\n  velocity:\n    enabled: true\n    online-mode: true\n    secret: forwarding-secret\n",
}
CRACKED = {"server.properties": "server-port=25565\nonline-mode=false\n"}
SCRIPT_PACK = {
    "server.properties": "server-port=25565\n",
    "run.sh": '#!/bin/sh\njava @user_jvm_args.txt -jar paper.jar "$@"\n',
    "user_jvm_args.txt": "-Xms512M\n-Xmx1500M\n-javaagent:vecta.jar=token=old-token\n-Dvecta.gateway=http://old.example:8080\n",
}


def req(method, url, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, context=CTX, timeout=120) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def props(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


def yaml_value_is(path, keys, value):
    try:
        text = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return False
    return yaml_replace(text, keys, value, value + "-probe")[1]


def login():
    deadline = time.time() + 240
    while time.time() < deadline:
        try:
            creds = json.load(open("data/config/default-creds.txt"))
            status, resp = req("POST", f"{CRAFTY}/auth/login", {"username": creds["username"], "password": creds["password"]})
            # A fresh Crafty refuses tokens issued too early in its startup: try one before relying on it.
            if status == 200 and req("GET", f"{CRAFTY}/servers", token=resp["data"]["token"])[0] == 200:
                return resp["data"]["token"]
        except (OSError, ValueError):
            pass
        time.sleep(3)
    sys.exit("FAIL crafty login")


def paper_jar():
    path = f"/tmp/craftyvecta-e2e-paper-{PAPER_VERSION}.jar"
    if not os.path.exists(path):
        deadline = time.time() + 180  # Crafty fetches its jar list shortly after starting
        while not os.path.exists("data/config/bigbucket.json") and time.time() < deadline:
            time.sleep(3)
        bucket = json.load(open("data/config/bigbucket.json"))
        bucket = bucket.get("categories", bucket)
        url = bucket["mc_java_servers"]["types"]["paper"]["versions"][PAPER_VERSION]["url"][0]
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (craftyvecta-e2e)"})
        with urllib.request.urlopen(request, timeout=300) as resp, open(path + ".part", "wb") as f:
            f.write(resp.read())
        os.replace(path + ".part", path)
    return path


def upload(token, name, files, jar):
    os.makedirs("data/import/upload", exist_ok=True)
    os.chmod("data/import/upload", 0o777)  # Crafty deletes the archive after importing it
    archive = name.lower().replace(" ", "-") + ".zip"
    with zipfile.ZipFile(os.path.join("data/import/upload", archive), "w") as z:
        z.write(jar, "paper.jar")
        # As Minecraft writes it. Crafty only reads the first line, so it asks for
        # EULA agreement, as it would for a real upload.
        z.writestr(
            "eula.txt",
            "#By changing the setting below to TRUE you are indicating your agreement to our EULA.\n"
            "#Mon Sep 14 12:00:00 UTC 2026\neula=true\n",
        )
        for file, content in files.items():
            z.writestr(file, content)
    os.chmod(os.path.join("data/import/upload", archive), 0o666)
    body = {
        "name": name,
        "monitoring_type": "minecraft_java",
        "minecraft_java_monitoring_data": {"host": "127.0.0.1", "port": 25565},
        "create_type": "minecraft_java",
        "minecraft_java_create_data": {
            "create_type": "import_server",
            "import_server_create_data": {
                "archive_name": archive,
                "archive_internal_path": "",
                "jarfile": "paper.jar",
                "mem_min": 0.5,
                "mem_max": 1.5,
                "server_properties_port": 25565,
            },
        },
    }
    status, resp = req("POST", f"{CRAFTY}/servers", body, token)
    check(f"upload {name}", status in (200, 201), f"{status} {resp}")
    sid = resp["data"]["new_server_id"]
    # Crafty writes a server.properties before it unzips, deletes the archive
    # once the files are in place, and clears "importing" a few seconds later.
    deadline = time.time() + 180
    while time.time() < deadline:
        _, stats = req("GET", f"{CRAFTY}/servers/{sid}/stats", token=token)
        importing = not isinstance(stats, dict) or stats.get("data", {}).get("importing", True)
        if not os.path.exists(os.path.join("data/import/upload", archive)) and not importing:
            break
        time.sleep(3)
    check(f"{name}: imported", os.path.exists(f"data/servers/{sid}/paper.jar"))
    return sid


token = login()
jar = paper_jar()
ids = {
    "Proxy Backend": upload(token, "Proxy Backend", PROXY_BACKEND, jar),
    "Cracked": upload(token, "Cracked", CRACKED, jar),
    "Script Pack": upload(token, "Script Pack", SCRIPT_PACK, jar),
}
print("servers:", ids, flush=True)

status, resp = req("PATCH", f"{CRAFTY}/servers/{ids['Script Pack']}", {"execution_command": "sh run.sh nogui"}, token)
check("Script Pack: start command set to sh run.sh", status == 200, f"{status} {resp}")

for name, sid in ids.items():
    # As in the panel: the first start stops at the EULA, which Crafty can only
    # accept once a start has run; then start again.
    req("POST", f"{CRAFTY}/servers/{sid}/action/start_server", token=token)
    time.sleep(3)
    status, resp = req("POST", f"{CRAFTY}/servers/{sid}/action/eula", token=token)
    check(f"{name}: EULA accepted", status == 200, f"{status} {resp}")
    status, resp = req("POST", f"{CRAFTY}/servers/{sid}/action/start_server", token=token)
    check(f"start {name}", status == 200, f"{status} {resp}")
    time.sleep(2)

want = {"proxy-backend", "script-pack"}
listed = {}
deadline = time.time() + 240
while time.time() < deadline:
    _, servers = req("GET", f"{GATEWAY}/servers")
    listed = {s["id"]: s for s in servers} if isinstance(servers, list) else {}
    if all(listed.get(i, {}).get("online") for i in want):
        break
    time.sleep(5)
for i in sorted(want):
    check(f"gateway lists {i} online", bool(listed.get(i, {}).get("online")), json.dumps(listed.get(i, {}))[:200])
check("gateway does not list cracked", "cracked" not in listed, sorted(listed))

logs = sh("docker compose logs --no-color crafty 2>&1")

backend = f"data/servers/{ids['Proxy Backend']}"
p = props(f"{backend}/server.properties")
check("Proxy Backend: server-ip cleared", p.get("server-ip", "") == "", p.get("server-ip"))
check("Proxy Backend: online-mode=true", p.get("online-mode") == "true", p.get("online-mode"))
check("Proxy Backend: BungeeCord forwarding off", yaml_value_is(f"{backend}/spigot.yml", ("settings", "bungeecord"), "false"))
check(
    "Proxy Backend: Velocity forwarding off",
    yaml_value_is(f"{backend}/config/paper-global.yml", ("proxies", "velocity", "enabled"), "false"),
)

cracked = f"data/servers/{ids['Cracked']}"
check("Cracked: online-mode left false", props(f"{cracked}/server.properties").get("online-mode") == "false")
check("Cracked: refusal logged", "Cracked: online-mode=false would let anyone join" in logs)
config_exists = sh(f"docker compose exec -T crafty sh -c 'test -e /crafty/app/config/vecta/servers/{ids['Cracked']}.properties && echo yes'")
check("Cracked: no vecta config written", "yes" not in config_exists)

pack = f"data/servers/{ids['Script Pack']}"
jvm_args = open(f"{pack}/user_jvm_args.txt", encoding="utf-8").read()
check("Script Pack: old vecta options removed from user_jvm_args.txt", "vecta" not in jvm_args, jvm_args.replace("\n", " | "))
check("Script Pack: removal logged", "Script Pack: user_jvm_args.txt: removed -javaagent (vecta), -Dvecta.gateway" in logs)
java_env = sh(
    "docker compose exec -T -u crafty crafty sh -c "
    "'for p in $(pgrep java); do tr \"\\0\" \"\\n\" < /proc/$p/environ | grep ^JDK_JAVA_OPTIONS=; done'"
)
check("Script Pack: agent passed through JDK_JAVA_OPTIONS", "-javaagent:/crafty/vecta/vecta.jar" in java_env, java_env.strip())

server_logs = sh("docker compose exec -T crafty sh -c 'cat /crafty/servers/*/logs/latest.log' 2>&1")
check("old token absent from all logs", "old-token" not in logs + server_logs)
check("crafty token absent from all logs", ENV["VECTA_CRAFTY_TOKEN"] not in logs + server_logs)

ports = [int(props(f"data/servers/{ids[n]}/server.properties")["server-port"]) for n in ("Proxy Backend", "Script Pack")]
check("registered uploads got distinct ports", len(set(ports)) == 2, str(ports))

print("\nFAILED: " + ", ".join(failures) if failures else "\nALL PASSED")
sys.exit(1 if failures else 0)
