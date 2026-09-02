"""Markdown rendering + Pygments syntax highlighting for report export.

The on-screen report (apps/web) is rendered with react-markdown + highlight.js;
the standalone HTML/Markdown exports are rendered on the server so that
print/PDF and downloaded files show *rendered* markdown and highlighted code
without depending on client-side JS.
"""
from __future__ import annotations

import re

import markdown as _markdown
from pygments import highlight as _pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

# 与前端 Markdown.tsx（react-markdown + remark-gfm，不启用 nl2br）对齐。
_EXTENSIONS = ["extra", "codehilite", "sane_lists"]
_EXTENSION_CONFIG = {
    "codehilite": {
        "guess_lang": False,
        "css_class": "codehilite",
        "linenums": False,
    }
}

# LLM-authored content may accidentally include raw HTML; strip the risky tags
# and event-handler attributes so the exported document stays inert.
_TAG_RE = re.compile(
    r"<\s*(/?)\s*(script|iframe|object|embed|link|meta|style|form|input|button)"
    r"(?:\s[^>]*)?>",
    re.IGNORECASE,
)
_ONATTR_RE = re.compile(r"\son[a-z]+(\s*)=(\s*)(\"[^\"]*\"|'[^']*')", re.IGNORECASE)

# Extra CSS so Pygments .codehilite blocks match the existing pre.code look.
_CODEHILITE_CSS = """
.codehilite{border-radius:8px;overflow:auto;margin:8px 0;font-size:12.5px;line-height:1.6;}
.codehilite pre{margin:0;padding:12px 14px;white-space:pre-wrap;word-break:break-word;}
"""


def md_to_html(text: str) -> str:
    """Render Markdown to HTML (GFM-ish) with Pygments-highlighted code blocks."""
    if not text:
        return ""
    rendered = _markdown.markdown(
        text,
        extensions=_EXTENSIONS,
        extension_configs=_EXTENSION_CONFIG,
        output_format="html5",
    )
    rendered = _TAG_RE.sub("", rendered)
    rendered = _ONATTR_RE.sub("", rendered)
    return rendered


def highlight_code(code: str, language: str = "text") -> str:
    """Syntax-highlight a code snippet as a standalone ``<pre>`` block."""
    if not code:
        return ""
    try:
        lexer = get_lexer_by_name(language, stripall=False)
    except ClassNotFound:
        lexer = get_lexer_by_name("text")
    return _pygments_highlight(code, lexer, HtmlFormatter(cssclass="codehilite"))


def codehilite_css() -> str:
    """Pygments style defs + the small wrapper CSS for exported documents."""
    return HtmlFormatter(style="friendly").get_style_defs(".codehilite") + _CODEHILITE_CSS
