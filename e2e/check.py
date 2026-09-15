"""End-to-end check of a fresh CraftyVecta compose stack.

Run from the directory with compose.yaml and .env, after `docker compose up -d --build`
on an empty data/ directory. It creates and starts two Paper servers through Crafty's API
(downloads ~100 MB, needs ~4 GB RAM) and checks registration, autoports and token handling.

    python3 e2e/check.py

CRAFTY_URL and GATEWAY_URL default to the ports in .env (PANEL_PORT, API_PORT).
"""
import json
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

ENV = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
CRAFTY = os.environ.get("CRAFTY_URL", f"https://127.0.0.1:{ENV.get('PANEL_PORT', '8443')}") + "/api/v2"
GATEWAY = os.environ.get("GATEWAY_URL", f"http://127.0.0.1:{ENV.get('API_PORT', '8080')}") + "/api/v1"
CTX = ssl._create_unverified_context()
failures = []


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


token = None
deadline = time.time() + 240
while time.time() < deadline and token is None:
    try:
        creds = json.load(open("data/config/default-creds.txt"))
        status, login = req("POST", f"{CRAFTY}/auth/login", {"username": creds["username"], "password": creds["password"]})
        # A fresh Crafty refuses tokens issued too early in its startup: try one before relying on it.
        if status == 200 and req("GET", f"{CRAFTY}/servers", token=login["data"]["token"])[0] == 200:
            token = login["data"]["token"]
    except (OSError, ValueError):
        pass
    if token is None:
        time.sleep(3)
check("crafty login", token is not None)
if token is None:
    sys.exit(1)


def create(name):
    body = {
        "name": name,
        "monitoring_type": "minecraft_java",
        "minecraft_java_monitoring_data": {"host": "127.0.0.1", "port": 25565},
        "create_type": "minecraft_java",
        "minecraft_java_create_data": {
            "create_type": "download_jar",
            "download_jar_create_data": {
                "category": "mc_java_servers",
                "type": "paper",
                "version": "1.21.11",
                "mem_min": 1,
                "mem_max": 2,
                "server_properties_port": 25565,
                "agree_to_eula": True,
            },
        },
    }
    status, resp = req("POST", f"{CRAFTY}/servers", body, token)
    check(f"create {name}", status in (200, 201), f"{status} {resp}")
    return resp["data"]["new_server_id"]


ids = {name: create(name) for name in ("Survival", "Creative World")}
print("servers:", ids, flush=True)

for name, sid in ids.items():
    jar = f"data/servers/{sid}/paper.jar"
    deadline = time.time() + 300
    while time.time() < deadline:
        _, stats = req("GET", f"{CRAFTY}/servers/{sid}/stats", token=token)
        importing = isinstance(stats, dict) and stats.get("data", {}).get("importing")
        if os.path.exists(jar) and os.path.getsize(jar) > 1_000_000 and not importing:
            break
        time.sleep(3)
    check(f"{name}: jar downloaded", os.path.exists(jar))

for name, sid in ids.items():
    status, resp = req("POST", f"{CRAFTY}/servers/{sid}/action/start_server", token=token)
    check(f"start {name}", status == 200, f"{status} {resp}")
    time.sleep(2)

want = {"survival", "creative-world"}
listed = {}
deadline = time.time() + 240
while time.time() < deadline:
    _, servers = req("GET", f"{GATEWAY}/servers")
    listed = {s["id"]: s for s in (servers or [])} if isinstance(servers, list) else {
        s["id"]: s for s in (servers or {}).get("servers", [])
    }
    if want <= set(listed) and all(listed[i].get("online") for i in want):
        break
    time.sleep(5)
for i in sorted(want):
    s = listed.get(i, {})
    check(f"gateway lists {i} online", bool(s.get("online")), json.dumps(s)[:300])

ports = {}
for name, sid in ids.items():
    p = props(f"data/servers/{sid}/server.properties")
    ports[name] = int(p["server-port"])
    _, detail = req("GET", f"{CRAFTY}/servers/{sid}", token=token)
    db_port = detail["data"]["server_port"]
    check(f"{name}: crafty monitoring port matches server.properties", db_port == ports[name], f"{db_port} vs {ports[name]}")
check("autoports gave distinct ports", len(set(ports.values())) == 2, str(ports))
check("autoports stayed in range", all(25500 <= p <= 25999 for p in ports.values()), str(ports))

vecta_token = ENV["VECTA_CRAFTY_TOKEN"]
logs = sh("docker compose logs --no-color crafty 2>&1") + sh("docker compose exec -T crafty sh -c 'cat /crafty/logs/*.log /crafty/servers/*/logs/latest.log' 2>&1")
check("token absent from crafty and server logs", vecta_token not in logs)
procs = sh("docker compose exec -T crafty ps -eo args")
check("token absent from process args", vecta_token not in procs)
check("java runs with the agent", "-javaagent:/crafty/vecta/vecta.jar" in procs, [l for l in procs.splitlines() if "java" in l][:1])
env_dump = sh("docker compose exec -T crafty sh -c 'for p in $(pgrep java); do tr \"\\0\" \"\\n\" < /proc/$p/environ; done'")
check("no VECTA_* in server process env", "VECTA_" not in env_dump)
modes = sh("docker compose exec -T crafty sh -c 'stat -c \"%a %U %n\" /crafty/app/config/vecta/servers/*.properties'")
check("config files are 0600", all(l.startswith("600 ") for l in modes.strip().splitlines()) and modes.strip(), modes.strip())

hook_lines = [l for l in logs.splitlines() if "CraftyVecta" in l]
print("\n".join(hook_lines[:12]))
check("hook announced itself", any("hooked into server start" in l for l in hook_lines))

for port in ports.values():
    s = socket.socket()
    s.settimeout(2)
    reachable = s.connect_ex(("127.0.0.1", port)) == 0
    s.close()
    check(f"backend port {port} not reachable from the host", not reachable)

print("\nFAILED: " + ", ".join(failures) if failures else "\nALL PASSED")
sys.exit(1 if failures else 0)
