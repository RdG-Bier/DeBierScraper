# -*- coding: utf-8 -*-
"""
Zoekmachine-wrapper voor gebruik binnen GitHub Actions, zonder API-key.
Probeert meerdere endpoints tot er resultaten zijn:
  1. DuckDuckGo Lite   (lite.duckduckgo.com/lite/)
  2. DuckDuckGo HTML   (html.duckduckgo.com/html/)
  3. Mojeek            (www.mojeek.com/search)  - kleine onafhankelijke engine
Levert per resultaat {title, url, content}. De Untappd-bierpagina komt in de
resultaten met in de omschrijving 'has a rating of X out of 5, with N ratings'.

Bij problemen wordt de ruwe respons als debug-sample bewaard (docs/debug/),
zodat achteraf te zien is of een engine blokkeert.
"""

import html as html_mod
import logging
import re
import urllib.parse

import utils

log = logging.getLogger("bierscraper")

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
RE_TAG = re.compile(r"<[^>]+>")
_debug_saved = [False]


def _clean(text):
    return html_mod.unescape(RE_TAG.sub("", text or "")).strip()


def _real_url(href):
    m = re.search(r"[?&]uddg=([^&]+)", href)
    if m:
        return urllib.parse.unquote(m.group(1))
    if href.startswith("//"):
        return "https:" + href
    return href


def search(query):
    for engine in (_ddg_lite, _ddg_html, _mojeek):
        try:
            results = engine(query)
        except Exception as exc:
            log.debug("zoek-engine %s faalde: %s", engine.__name__, exc)
            results = []
        if results:
            return results
    return []


def _fetch(url):
    return utils.fetch(url, use_cache=False, headers={"User-Agent": BROWSER_UA})


def _maybe_debug(name, html):
    if not _debug_saved[0]:
        _debug_saved[0] = True
        utils.save_debug_sample("websearch", name, html or "(leeg)")


# --- DuckDuckGo Lite: simpele tabel-layout, minst geneigd te blokkeren ---
RE_LITE = re.compile(
    r'<a[^>]+class="result-link"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
    r'.*?class="result-snippet"[^>]*>(.*?)</td>', re.S | re.I)


def _ddg_lite(query):
    q = urllib.parse.quote_plus(query)
    html = _fetch(f"https://lite.duckduckgo.com/lite/?q={q}")
    _maybe_debug("ddg-lite", html)
    if not html:
        return []
    return _pack((_real_url(h), t, s) for h, t, s in RE_LITE.findall(html))


# --- DuckDuckGo HTML ---
RE_HTML = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)".*?>(.*?)</a>'
    r'.*?class="result__snippet"[^>]*>(.*?)</(?:a|div)>', re.S | re.I)


def _ddg_html(query):
    q = urllib.parse.quote_plus(query)
    html = _fetch(f"https://html.duckduckgo.com/html/?q={q}")
    _maybe_debug("ddg-html", html)
    if not html:
        return []
    return _pack((_real_url(h), t, s) for h, t, s in RE_HTML.findall(html))


# --- Mojeek: onafhankelijke engine, vriendelijk voor scripts ---
RE_MOJEEK = re.compile(
    r'<a[^>]+class="title"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
    r'.*?<p[^>]+class="s"[^>]*>(.*?)</p>', re.S | re.I)


def _mojeek(query):
    q = urllib.parse.quote_plus(query)
    html = _fetch(f"https://www.mojeek.com/search?q={q}")
    _maybe_debug("mojeek", html)
    if not html:
        return []
    return _pack((h, t, s) for h, t, s in RE_MOJEEK.findall(html))


def _pack(triples):
    out = []
    for url, title, snippet in triples:
        out.append({"url": url, "title": _clean(title), "content": _clean(snippet)})
        if len(out) >= 8:
            break
    return out
