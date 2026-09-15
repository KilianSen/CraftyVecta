"""The "with vecta" badge on Crafty's pages.

The hook wraps BaseHandler.finish, which every Crafty page, the login screen
and error pages go through, and adds one stylesheet and one script to HTML
responses. The script (static/vecta/brand.js) puts the badge next to Crafty's
logo and keeps Crafty's own logo and credits. Where Crafty's markup has
changed, it adds nothing.
"""

import functools
import html
import logging

STATIC_DIR = "assets/vecta/"
_MARKER = b"vecta/brand.js"
logger = logging.getLogger("craftyvecta")


def tags(css_url, js_url, settings):
    attrs = {"data-domain": settings.domain, "data-status-url": settings.public_url}
    extra = "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in attrs.items() if v)
    link = f'<link rel="stylesheet" href="{html.escape(css_url, quote=True)}">'
    script = f'<script src="{html.escape(js_url, quote=True)}" defer{extra}></script>'
    return link.encode(), script.encode()


def inject(page, link, script):
    """Inserts the tags before </head>, else before </body>, once."""
    if _MARKER in page:
        return page
    lower = page.lower()
    for tag in (b"</head>", b"</body>"):
        at = lower.find(tag)
        if at != -1:
            return page[:at] + link + script + page[at:]
    return page


def patch(module, settings, say):
    cls = getattr(module, "BaseHandler", None)
    original = getattr(cls, "finish", None)
    if original is None:
        say("warning", "Crafty's BaseHandler was not found; the panel shows no vecta badge")
        return

    @functools.wraps(original)
    def finish(handler, chunk=None):
        if isinstance(chunk, (bytes, str)) and "text/html" in str(handler._headers.get("Content-Type", "")):
            try:
                chunk = _add_badge(handler, chunk, settings)
            except Exception:  # branding must never break a page
                logger.exception("CraftyVecta could not add the badge")
        return original(handler, chunk)

    cls.finish = finish


def _add_badge(handler, chunk, settings):
    page = chunk.encode("utf-8") if isinstance(chunk, str) else chunk
    link, script = tags(_static_url(handler, "brand.css"), _static_url(handler, "brand.js"), settings)
    return inject(page, link, script)


def _static_url(handler, name):
    try:
        return handler.static_url(STATIC_DIR + name)  # adds ?v=<hash> for caching
    except Exception:
        return "/static/" + STATIC_DIR + name
