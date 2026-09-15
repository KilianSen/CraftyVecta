"""Hooks CraftyVecta into Crafty without changing any Crafty file.

craftyvecta.pth calls install() when Crafty's Python starts. install() waits
for two Crafty modules to be imported and patches them:

- app.classes.shared.server: ServerInstance.setup_server_run_command, the
  step that turns a server's stored start command into the argv Crafty
  passes to Popen, gets the vecta agent (launch.py).
- app.classes.web.base_handler: BaseHandler.finish adds the "with vecta"
  badge to HTML pages (branding.py).
"""

import functools
import logging
import os
import sys
import threading

from . import branding, config, launch
from .state import State

SERVER_MODULE = "app.classes.shared.server"
WEB_MODULE = "app.classes.web.base_handler"
logger = logging.getLogger("craftyvecta")


def install(environ=None, is_free=None):
    """Reads the settings and registers the import hook, once. Never raises.

    Crafty's venv can process craftyvecta.pth more than once (seen on the
    Ubuntu 24.04 image). A second hook would find VECTA_* already removed
    and, inserted first, win with no token.
    """
    for finder in sys.meta_path:
        if isinstance(finder, _Finder):
            return finder
    environ = os.environ if environ is None else environ
    try:
        settings = config.take_env(environ)
    except ValueError as e:
        _say("critical", f"{e}; servers start without vecta")
        return None
    finder = _Finder(settings, is_free or launch.port_is_free)
    sys.meta_path.insert(0, finder)
    return finder


class _Finder:
    def __init__(self, settings, is_free):
        self.settings = settings
        self.is_free = is_free
        self.state = None
        self.lock = threading.Lock()

    def find_spec(self, fullname, path, target=None):
        if fullname == SERVER_MODULE:
            patch = self.patch
        elif fullname == WEB_MODULE and self.settings.branding:
            patch = self.patch_web
        else:
            return None
        for finder in sys.meta_path:
            if isinstance(finder, _Finder) or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(fullname, path, target)
            if spec is not None and spec.loader is not None:
                break
        else:
            return None
        load = spec.loader.exec_module

        def exec_module(module):
            load(module)
            patch(module)

        spec.loader.exec_module = exec_module
        return spec

    def patch_web(self, module):
        branding.patch(module, self.settings, _say)

    def patch(self, module):
        cls = getattr(module, "ServerInstance", None)
        original = getattr(cls, "setup_server_run_command", None)
        servers = getattr(module, "Servers", None)
        if original is None or servers is None:
            _say(
                "critical",
                "this Crafty version is not supported (ServerInstance.setup_server_run_command "
                "not found); servers start without vecta",
            )
            return

        @functools.wraps(original)
        def setup_server_run_command(instance):
            original(instance)
            try:
                self.prepare(instance, servers)
            except Exception as e:  # a vecta problem must not keep the server from starting
                logger.exception("CraftyVecta failed for %s", instance.name)
                _say("critical", f"{instance.name}: {e}; starting without vecta")

        cls.setup_server_run_command = setup_server_run_command
        _say("info", "hooked into server start")

    def prepare(self, instance, servers):
        if not instance.server_command:
            return
        with self.lock:
            if self.state is None:
                self.state = State(os.path.join(self.settings.state_dir, "state.json"))
        server = launch.Server(
            uuid=str(instance.server_id),
            name=instance.name,
            path=instance.server_path,
            type=instance.settings["type"],
            command=instance.server_command,
            db_port=instance.settings["server_port"],
        )
        result = launch.prepare(server, self.settings, self.state, self.is_free)
        for level, text in result.messages:
            _say(level, f"{instance.name}: {text}")
        instance.server_command = result.command
        if result.port is not None and result.port != instance.settings["server_port"]:
            # Crafty pings this port for status and player counts.
            servers.update(server_port=result.port).where(servers.server_id == instance.server_id).execute()
            instance.reload_server_settings()


def _say(level, text):
    message = f"CraftyVecta | {text}"
    getattr(logger, level)(message)
    console = sys.modules.get("app.classes.shared.console")
    if console is None:
        print(message, file=sys.stderr)
    else:
        getattr(console.Console, level)(message)
