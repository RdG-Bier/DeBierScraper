# -*- coding: utf-8 -*-
"""
Untappd-opzoekmodule: zoekt voor bieren zonder score de Untappd-pagina op
(zoeken -> bierpagina) en leest daar score, aantal ratings en exacte stijl.

Bewust behoudend opgezet:
- maximaal UNTAPPD_LOOKUP_MAX opzoekingen per run (config)
- extra vertraging bovenop de normale request-delay
- permanente cache in docs/untappd_cache.json (wordt mee-gecommit), zodat elk
  bier hooguit eens per UNTAPPD_CACHE_DAYS opnieuw wordt opgezocht; ook
  mislukte zoekopdrachten worden onthouden om herhaling te voorkomen
- naam-verificatie: het zoekresultaat moet voldoende lijken op de gezochte
  naam, anders liever geen score dan een verkeerde
"""

import difflib
import json
import logging
import re
import time
import urllib.parse
from pathlib import Path

from bs4 import BeautifulSoup

import config
import utils

log = logging.getLogger("bierscraper")

CACHE_FILE = Path(__file__).parent / "docs" / "untappd_cache.json"
EXTRA_DELAY = 2.0          # seconden extra rust richting untappd.com
MATCH_THRESHOLD = 0.62     # gelijkenis zoekopdracht <-> gevonden bier

RE_RATING = re.compile(r'data-rating="([\d.]+)"')
RE_RATING_ALT = re.compile(r'class="num">\s*\(?([\d.]+)\)?')
RE_RATERS = re.compile(r'([\d.,]+)\s*Ratings', re.IGNORECASE)


def enrich_beers(beers, site_key):
    """Vul untappd/aantal/stijl aan voor bieren zonder score. Retourneert
    het aantal aangevulde bieren."""
    cache = _load_cache()
    lookups_done = 0
    filled = 0

    for beer in beers:
        if beer.get("untappd") is not None:
            continue
        name = beer.get("naam")
        if not name:
            continue
        key = utils.norm(f"{beer.get('brouwerij') or ''} {name}")

        entry = cache.get(key)
        fresh = entry and (time.time() - entry.get("ts", 0)) < config.UNTAPPD_CACHE_DAYS * 86400
        if not fresh:
            if lookups_done >= config.UNTAPPD_LOOKUP_MAX:
                continue  # limiet bereikt; volgende run gaat verder
            lookups_done += 1
            entry = _lookup(name, site_key)
            entry["ts"] = time.time()
            cache[key] = entry

        if entry.get("score"):
            beer["untappd"] = entry["score"]
            beer["untappd_aantal"] = entry.get("count")
            filled += 1
            if entry.get("style"):
                canon = utils.find_style_in_text(entry["style"]) 
                if not canon:
                    canon, _ = utils.match_style(entry["style"])
                if canon and beer.get("stijl") not in config.STYLES:
                    beer["stijl"] = canon
                    beer["sterke_voorkeur"] = config.STYLES.get(canon, False)
            if entry.get("url"):
                beer["weblink_untappd"] = entry["url"]

    _save_cache(cache)
    log.info("Untappd-lookup %s: %d nieuw opgezocht, %d bieren aangevuld "
             "(cache: %d items)", site_key, lookups_done, filled, len(cache))
    return filled


def _lookup(name, site_key):
    """Zoek een bier op untappd.com en lees de bierpagina. Retourneert dict
    met score/count/style/url, of een leeg dict bij geen (betrouwbare) match."""
    time.sleep(EXTRA_DELAY)
    q = urllib.parse.quote_plus(name)
    html = utils.fetch(f"https://untappd.com/search?q={q}", use_cache=False)
    if not html:
        return {}
    utils.save_debug_sample(site_key, "untappd-search", html)

    soup = BeautifulSoup(html, "html.parser")
    beer_url = None
    for item in soup.select(".beer-item, .results-container .item"):
        a = item.find("a", href=re.compile(r"^/b/[a-z0-9\-]+/\d+"))
        if not a:
            continue
        found_text = utils.norm(item.get_text(" ", strip=True)[:120])
        ratio = difflib.SequenceMatcher(None, utils.norm(name), found_text).ratio()
        # ook: alle woorden van de biernaam moeten grotendeels terugkomen
        name_tokens = set(utils.norm(name).split())
        overlap = len(name_tokens & set(found_text.split())) / max(1, len(name_tokens))
        if ratio >= MATCH_THRESHOLD or overlap >= 0.7:
            beer_url = "https://untappd.com" + a["href"].split("?")[0]
            break
    if not beer_url:
        # fallback: eerste bierlink op de pagina, maar met strengere check
        a = soup.find("a", href=re.compile(r"^/b/[a-z0-9\-]+/\d+"))
        if a:
            slug = utils.norm(a["href"].split("/")[2].replace("-", " "))
            name_tokens = set(utils.norm(name).split())
            if name_tokens and len(name_tokens & set(slug.split())) / len(name_tokens) >= 0.6:
                beer_url = "https://untappd.com" + a["href"].split("?")[0]
    if not beer_url:
        return {}

    time.sleep(EXTRA_DELAY)
    page = utils.fetch(beer_url, use_cache=False)
    if not page:
        return {"url": beer_url}
    utils.save_debug_sample(site_key, "untappd-bierpagina", page)

    score = None
    m = RE_RATING.search(page) or RE_RATING_ALT.search(page)
    if m:
        try:
            score = round(float(m.group(1)), 2)
            if not (0 < score <= 5):
                score = None
        except ValueError:
            score = None

    count = None
    m = RE_RATERS.search(page)
    if m:
        digits = re.sub(r"[^\d]", "", m.group(1))
        count = int(digits) if digits else None

    style = None
    psoup = BeautifulSoup(page, "html.parser")
    style_el = psoup.select_one("p.style, .name p.style, [class*='style']")
    if style_el:
        style = style_el.get_text(" ", strip=True)

    return {"score": score, "count": count, "style": style, "url": beer_url}


def _load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=1, ensure_ascii=False),
                          encoding="utf-8")
