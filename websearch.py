# -*- coding: utf-8 -*-
"""
Eenvoudige zoekmachine-wrapper voor gebruik binnen GitHub Actions.
Gebruikt DuckDuckGo's HTML-endpoint (geen API-key nodig) en levert een lijst
van {title, url, content}. De Untappd-bierpagina komt in deze resultaten met
in de omschrijving de tekst 'has a rating of X out of 5, with N ratings'.
"""

import html as html_mod
import logging
import re
import urllib.parse

import utils

log = logging.getLogger("bierscraper")

DDG_HTML = "https://html.duckduckgo.com/html/?q="
RE_RESULT = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)".*?>(.*?)</a>'
    r'.*?class="result__snippet"[^>]*>(.*?)</(?:a|div)>',
    re.S | re.I)
RE_TAG = re.compile(r"<[^>]+>")


def _clean(text):
    return html_mod.unescape(RE_TAG.sub("", text or "")).strip()


def _real_url(href):
    """DDG verpakt links soms als /l/?uddg=<echte-url>."""
    m = re.search(r"uddg=([^&]+)", href)
    if m:
        return urllib.parse.unquote(m.group(1))
    if href.startswith("//"):
        return "https:" + href
    return href


def search(query):
    q = urllib.parse.quote_plus(query)
    html = utils.fetch(DDG_HTML + q, use_cache=False)
    if not html:
        return []
    results = []
    for href, title, snippet in RE_RESULT.findall(html):
        results.append({
            "url": _real_url(href),
            "title": _clean(title),
            "content": _clean(snippet),
        })
        if len(results) >= 8:
            break
    return results
