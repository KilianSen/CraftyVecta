import sys

import pytest

from craftyvecta import branding, hook
from craftyvecta.config import Settings

PAGE = b"<html><head><title>Dashboard</title></head><body>hi</body></html>"

# A stand-in for Crafty's app/classes/web/base_handler.py on top of Tornado.
FAKE_BASE_HANDLER = '''
class RequestHandler:
    def __init__(self, content_type):
        self._headers = {"Content-Type": content_type}
        self.sent = None

    def finish(self, chunk=None):
        self.sent = chunk

    def static_url(self, path):
        return "/static/" + path + "?v=abc"


class BaseHandler(RequestHandler):
    pass
'''


def test_inject_before_head_once():
    link, script = branding.tags("/static/assets/vecta/brand.css", "/static/assets/vecta/brand.js", Settings())
    out = branding.inject(PAGE, link, script)
    assert out == PAGE.replace(b"</head>", link + script + b"</head>")
    assert branding.inject(out, link, script) == out


def test_inject_falls_back_to_body_and_leaves_fragments_alone():
    assert branding.inject(b"<BODY>x</BODY>", b"L", b"S") == b"<BODY>xLS</BODY>"
    assert branding.inject(b"<div>partial</div>", b"L", b"S") == b"<div>partial</div>"


def test_tags_escape_attributes():
    settings = Settings(domain='play."x"', public_url="https://mc-api.example.com/?a=1&b=2")
    _, script = branding.tags("/a.css", "/a.js", settings)
    assert b'data-domain="play.&quot;x&quot;"' in script
    assert b'data-status-url="https://mc-api.example.com/?a=1&amp;b=2"' in script
    assert b"data-" not in branding.tags("/a.css", "/a.js", Settings())[1]


def test_branding_setting():
    assert Settings.from_env({}).branding is True
    assert Settings.from_env({"VECTA_BRANDING": "false"}).branding is False


@pytest.fixture
def fake_web(tmp_path, monkeypatch):
    web = tmp_path / "app" / "classes" / "web"
    web.mkdir(parents=True)
    for d in (tmp_path / "app", tmp_path / "app" / "classes", web):
        (d / "__init__.py").write_text("")
    (web / "base_handler.py").write_text(FAKE_BASE_HANDLER)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield
    for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[name]
    sys.meta_path[:] = [f for f in sys.meta_path if not isinstance(f, hook._Finder)]


def test_hook_adds_badge_to_html_only(fake_web):
    hook.install({"VECTA_DOMAIN": "play.example.com"})
    from app.classes.web import base_handler

    page = base_handler.BaseHandler("text/html; charset=UTF-8")
    page.finish(PAGE.decode())
    assert b'<script src="/static/assets/vecta/brand.js?v=abc" defer data-domain="play.example.com">' in page.sent

    api = base_handler.BaseHandler("application/json")
    api.finish(b'{"status": "ok"}')
    assert api.sent == b'{"status": "ok"}'


def test_branding_off(fake_web):
    hook.install({"VECTA_BRANDING": "off"})
    from app.classes.web import base_handler

    page = base_handler.BaseHandler("text/html")
    page.finish(PAGE)
    assert page.sent == PAGE
