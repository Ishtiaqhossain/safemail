"""Shared helper: strip an HTML email body down to readable text.

Used by providers whose messages may be HTML-only (Apple/iCloud, Microsoft) so the
classifier still sees meaningful text.
"""
import html
import re


def strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return html.unescape(re.sub(r"\s+", " ", s)).strip()
