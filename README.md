# CraftyVecta

[Crafty Controller 4](https://gitlab.com/crafty-controller/crafty-4) with
[vecta](https://github.com/KilianSen/vecta) built in. Every Minecraft Java
server Crafty starts joins the vecta gateway on its own. Players connect to
`play.example.com` and get routed, and no server port has to be published.

No Crafty file is changed. The image is the official Crafty image plus the
vecta server jar and a small Python package that Crafty's interpreter loads at
startup (`craftyvecta.pth`). The package wraps one method,
`ServerInstance.setup_server_run_command`, which turns a server's stored start
command into process arguments. Each start then runs:

```
java -javaagent:/crafty/vecta/vecta.jar -Dvecta.config=/crafty/app/config/vecta/servers/<uuid>.properties <the server's own arguments>
```

The command stored in Crafty never changes.

## Quick start

```
cp .env.example .env          # domain, cookie secret, Crafty's owner token
docker compose up -d --build
```

- **Panel:** `https://<host>:8443`. The first login is in `data/config/default-creds.txt`.
- **Players:** `play.example.com`, through the gateway on port 25565. For DNS
  and Nginx Proxy Manager, see the vecta README.
- **Voice chat:** servers with Simple Voice Chat work without setup, through
  the gateway's side ports (24500-24599, TCP and UDP). See [Voice chat and
  other side ports](#voice-chat-and-other-side-ports).
- **Servers:** create them in Crafty as usual. The port you enter doesn't matter.

The compose file runs two containers on a private network. Only the panel
(8443) and the gateway (25565, API on 8080, side ports 24500-24599) are
published. Minecraft servers
listen inside the network, so the gateway is the only way in and vecta's guard
isn't needed. Someone who publishes a server port on purpose can still join it
directly.

The build fetches vecta from GitHub. Set `VECTA_SRC=../vecta` to build from a
local checkout instead.

## What happens when a server starts

| Step | What |
|---|---|
| Check | Only `minecraft-java` servers started with `java` or a `.sh` script (e.g. Forge/NeoForge `run.sh`) are changed. Anything else starts unchanged, with a console warning. |
| Offline mode | A server with `online-mode=false` and no proxy forwarding isn't registered, because anyone could join it under any name. `allowOfflineMode=true` in its override file accepts that. The server still starts, unreachable through vecta. |
| Autoports | The server gets a port from `VECTA_PORT_RANGE` that no other Crafty server holds, and keeps it. A port already inside the range is kept. `server-port` in `server.properties` (and `query.port` / `rcon.port` when those are enabled) and Crafty's monitoring port are updated. A `--port` in the start command wins over autoports. |
| ID | The server name as a slug (`My Server` → `my-server`), unique across Crafty and kept on rename. |
| Register | The jar reads its config from `app/config/vecta/servers/`: gateway, token, ID, name, and `address` = `VECTA_BACKEND_HOST:<port>`. A script gets the agent through `JDK_JAVA_OPTIONS`, which Java 9 and newer read. |
| Old vecta settings | vecta agents and `-Dvecta.*` options that came with the server are dropped: from the start command for this start, and from argument files such as `user_jvm_args.txt` in place. They would start a second vecta or override CraftyVecta's settings. |
| Reachability | A `server-ip` other than all addresses is cleared, since the gateway connects from outside. BungeeCord or Velocity forwarding (`spigot.yml`, `config/paper-global.yml`, `paper.yml`) is switched off, since the gateway sends no forwarding data and every join would be kicked. If forwarding was on, `online-mode=false` becomes `true`: the proxy authenticated players before, so their UUIDs stay the same if it ran in online mode. |
| Voice chat | A server with Simple Voice Chat gets its own UDP port from `VECTA_VOICE_PORT_RANGE` and declares it as a side port (see below). |
| Throttle | Every player arrives from the gateway's address, so Bukkit/Paper's default `connection-throttle: 4000` in `bukkit.yml` becomes `-1`. For a new server the file exists only after the first start, so this applies from the second. |

These steps matter most for uploaded servers, which bring their own config,
often from behind a BungeeCord or Velocity proxy.

The jar itself detects loader, mods, channels and versions, and adds `/hub`,
`/server` and `/global` (see the vecta server jar README).

## Settings

Environment of the `crafty` container:

| Variable | Default | Meaning |
|---|---|---|
| `VECTA_TOKEN` | required | Owner token Crafty registers with. |
| `VECTA_GATEWAY` | `http://vecta:8080` | Gateway API URL. |
| `VECTA_BACKEND_HOST` | `crafty` | Host the gateway dials servers at. |
| `VECTA_DEFAULT_ENABLED` | `true` | vecta for servers without an override. |
| `VECTA_AUTOPORTS` | `true` | Assign ports (see above). |
| `VECTA_PORT_RANGE` | `25500-25999` | Ports autoports hands out. |
| `VECTA_RCON_OFFSET` | `1000` | `rcon.port` = game port + offset, for servers with RCON on. |
| `VECTA_FIX_THROTTLE` | `true` | The `bukkit.yml` change above. |
| `VECTA_VOICE_CHAT` | `true` | Simple Voice Chat through vecta, for servers without an override. |
| `VECTA_VOICE_PORT_RANGE` | `24000-24499` | Internal UDP ports voice chat gets. |
| `VECTA_JAR` / `VECTA_STATE_DIR` / `VECTA_HOOKS_DIR` | `/crafty/vecta/vecta.jar` / `app/config/vecta` / `/crafty/vecta/hooks` | Paths. |
| `VECTA_BRANDING` | `true` | The "with vecta" badge in the panel (see Branding). |
| `VECTA_DOMAIN` | | Public domain, shown in the panel's footer. |
| `VECTA_PUBLIC_URL` | | The gateway's public server list, linked from the badge. |

CraftyVecta removes every `VECTA_*` variable from Crafty's environment at
startup. Server processes inherit that environment, and the jar lets such
variables override its config file.

### Per server

An optional `vecta.override.properties` in the server directory, editable in
Crafty's file manager:

```properties
enabled=true
serverId=survival
description=Vanilla survival
hidden=false
requiredClientMods=create,sophisticatedbackpacks
```

Also accepted: `name`, `loader`, `protocols`, `proxyProtocol`, `commands`,
`runtimeChecks`, `heartbeatSeconds` and `debug` (see the jar's settings).
`allowOfflineMode=true` registers a server that runs with `online-mode=false`
(see the table above). `voiceChat`, `sidePorts` and `sidePortHook` are
described in the next section. `serverId` is refused when another Crafty server holds
it. Gateway, token and address can't be overridden. Changes apply on the next
start.

## Voice chat and other side ports

The gateway only routes the Minecraft connection. Mods with a port of their
own use vecta's side ports: the gateway assigns a public port from its range
(`VECTA_SIDEPORT_RANGE` in `.env`, default `24500-24599`, published for TCP
and UDP) and forwards it to the server. The jar then runs a hook that tells
the mod its public address. See vecta's
[side ports documentation](https://github.com/KilianSen/vecta/blob/master/docs/side-ports.md).

**Simple Voice Chat** needs no setup. CraftyVecta recognizes the mod or plugin
(`voicechat-*.jar` in `mods/` or `plugins/`) and before each start:

- gives the server its own UDP port from `VECTA_VOICE_PORT_RANGE`, since all
  servers share one container, and writes it to `port` in
  `voicechat-server.properties` (a `bind_address` the gateway can't reach is
  cleared);
- declares that port as the side port `voicechat`.

The jar registers before the server starts and writes `voice_host` (the
gateway's public address for the port), so voice chat works from the first
start. Players reach it at `VECTA_DOMAIN`, or at `VECTA_SIDEPORT_HOST` when
the domain points at a proxy that can't forward a port range (such as Nginx
Proxy Manager). The public port stays the same across restarts while it's
free.

In `vecta.override.properties`:

| Key | Meaning |
|---|---|
| `voiceChat=false` | Leave Simple Voice Chat alone. `true` sets it up even when the jar isn't recognized. |
| `sidePorts=map:tcp:8100,votes:tcp:8192` | More side ports, as `name:protocol:port`. The name `voicechat` is taken. Pick ports no other Crafty server uses. |
| `sidePortHook=./hooks/ports.sh` | Runs in the server directory for each of those side ports, with the assigned address in its environment (see vecta's docs). Without it, the assignment is only logged. |

A side port is reachable by anyone who knows the public port, without
vecta's routing in front. Don't declare RCON or other admin ports.

## Branding

The panel shows that it runs with vecta. Crafty's own logo and credits stay:

- a "with vecta" badge next to Crafty's logo and on the login page, linking to
  `VECTA_PUBLIC_URL` when set;
- "· vecta" after the page title;
- a footer line: "Players join through vecta at `VECTA_DOMAIN`".

The hook adds one stylesheet and one script from `/static/assets/vecta/` to
Crafty's HTML pages. No template is changed. If a Crafty release changes the
markup, the script adds nothing. `VECTA_BRANDING=false` turns it off.

## Gateway on another host

Set `VECTA_GATEWAY` to the gateway's API URL and `VECTA_BACKEND_HOST` to the
address the gateway reaches Crafty at. Publish `VECTA_PORT_RANGE` on the Crafty
container, firewall that range to the gateway, and limit Crafty's owner to that
address with `allowedNetworks` in the gateway config.

## Security

- **One user for everything.** Crafty runs every server as the same user, so
  any plugin or mod can read what Crafty can: its database, the other servers'
  files and the vecta token. That's Crafty's model with or without vecta. Panel
  users who can upload files or edit a start command can run code in the whole
  container, so grant those permissions only to people you'd trust with it.
- **Side port hooks** run as the Crafty user, like the servers themselves.
  Panel users who can edit `vecta.override.properties` can already upload
  mods, so `sidePortHook` gives them nothing new.
- **The token is scoped.** Crafty has its own owner in
  [gateway.json](gateway.json), allowed to register only the Crafty container's
  address (`CRAFTY_IP/32`). A leaked token can re-point IDs among Crafty's own
  servers and send `/global`. It can't touch other owners' servers or make the
  gateway dial anywhere else.
- **Out of sight of panel users.** The token never appears on a command line or
  in Crafty's log. The config files live outside the server directories, so
  they're not in server backups or the file manager.

## Updating Crafty

Set `CRAFTY_VERSION` and rebuild. If a Crafty release renames the hooked
method, Crafty's console shows `CraftyVecta | this Crafty version is not
supported …` at startup and servers start without vecta. The rest of Crafty
keeps working.

## Development

```
pip install pytest
python -m pytest
```

The tests need no Crafty: the hook runs against a stand-in for Crafty's server
module.

[e2e/check.py](e2e/check.py) checks a real stack: start a fresh one
(`docker compose up -d --build` with an empty `data/`), then run
`python3 e2e/check.py` next to `compose.yaml`. It creates and starts two Paper
servers through Crafty's API and checks that both register at the gateway, get
distinct ports and load the agent, and that the token appears in no log,
process argument or server environment.

[e2e/uploads.py](e2e/uploads.py) does the same for uploaded servers: it imports
three zips through Crafty's API. One comes from behind a proxy (bound to
127.0.0.1, offline mode, BungeeCord and Velocity forwarding on). One is a
genuine offline-mode server. One is started by `run.sh`, with an old vecta
agent in `user_jvm_args.txt`. It checks that the first and last register with
their config fixed, and that the offline-mode server doesn't.

### CI

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs the unit tests and
validates `compose.yaml` on every push. It then builds the image for
`linux/amd64` and `linux/arm64`, with the vecta jar built from vecta's `master`.

- **Publishing:** version tags (`v1.2.3`) publish the image to
  `ghcr.io/<owner>/<repo>` as `1.2.3` and `latest`. A manual run can publish
  too (the `push` input, tagged with the commit SHA), and `vecta_ref` picks the
  vecta branch, tag or commit.
- **Using a published image:** set `CRAFTYVECTA_IMAGE` to it, then
  `docker compose pull crafty && docker compose up -d`.

## License

GPL-3.0, like Crafty Controller, which CraftyVecta extends. The vecta server
jar built into the image is Apache-2.0.
