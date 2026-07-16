# -*- coding: utf-8 -*-
"""
Untappd-opzoekmodule v3.
Zoekt voor bieren zonder score de Untappd-rating op via een zoekmachine
(web_search-achtige query naar untappd.com). De zoekresultaten bevatten de
Untappd-bierpagina met daarin exact "(3.92) 3,681 Ratings" en/of
"has a rating of 3.9 out of 5, with 3,681 ratings", plus de bierstijl.
Twee decimalen hebben de voorkeur; anders de 1-decimaal-vorm mét aantal.

Belangrijkste eigenschappen:
- permanente bierdatabase (scoring.py) onthoudt reeds gevonden bieren, dus
  alleen NIEUWE bieren op de shop worden nog opgezocht -> scheelt scrapetijd
- gelimiteerd aantal opzoekingen per run + vertraging (netjes blijven)
- cache onthoudt ook missers, met kortere houdbaarheid zodat nieuwe releases
  later opnieuw geprobeerd worden
- naam-verificatie: het gevonden bier moet op de zoekterm lijken
"""

import difflib
import json
import logging
import re
import time
from pathlib import Path

import config
import utils

log = logging.getLogger("bierscraper")

CACHE_FILE = Path(__file__).parent / "docs" / "untappd_cache.json"
CACHE_VERSION = 3
MISS_CACHE_DAYS = 3        # missers korter bewaren: nieuwe bieren krijgen ratings
EXTRA_DELAY = 1.5

RE_EXACT = re.compile(r'\(([0-5]\.\d{2})\)\s*([\d,\.]+)\s*Ratings', re.IGNORECASE)
RE_TEXT = re.compile(
    r'rating of ([0-5](?:\.\d{1,2})?) out of 5,?\s*with\s*([\d,\.]+)\s*ratings',
    re.IGNORECASE)
RE_STYLE = re.compile(r'\bis a[n]? ([A-Z][A-Za-z\-/ ]+?) which has a rating', re.IGNORECASE)

# wordt door main.py gezet: een functie (query:str) -> list[dict(title,url,content)]
search_fn = None


def enrich_beers(beers, site_key):
    """Vul untappd/aantal/stijl aan voor bieren zonder score."""
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
        fresh = _is_fresh(entry)
        if not fresh:
            if lookups_done >= config.UNTAPPD_LOOKUP_MAX:
                continue  # limiet bereikt; volgende run gaat verder
            if search_fn is None:
                continue  # geen zoekfunctie beschikbaar
            lookups_done += 1
            entry = _lookup(name)
            entry["ts"] = time.time()
            entry["v"] = CACHE_VERSION
            cache[key] = entry

        if entry.get("score"):
            beer["untappd"] = entry["score"]
            beer["untappd_aantal"] = entry.get("count")
            if entry.get("style"):
                canon = utils.find_style_in_text(entry["style"])
                if not canon:
                    canon, _ = utils.match_style(entry["style"])
                if canon and beer.get("stijl") not in config.STYLES:
                    beer["stijl"] = canon
                    beer["sterke_voorkeur"] = config.STYLES.get(canon, False)
            filled += 1

    _save_cache(cache)
    log.info("Untappd-lookup %s: %d nieuw opgezocht, %d aangevuld (cache: %d)",
             site_key, lookups_done, filled, len(cache))
    return filled


def _is_fresh(entry):
    if not entry or entry.get("v") != CACHE_VERSION:
        return False
    age_days = (time.time() - entry.get("ts", 0)) / 86400
    if entry.get("score"):
        return age_days < config.UNTAPPD_CACHE_DAYS
    return age_days < MISS_CACHE_DAYS   # misser: sneller opnieuw proberen


def _lookup(name):
    """Zoek via de zoekmachine naar de Untappd-pagina van dit bier."""
    time.sleep(EXTRA_DELAY)
    try:
        results = search_fn(f"{name} untappd")
    except Exception as exc:
        log.warning("Zoekopdracht mislukt voor %r: %s", name, exc)
        return {}
    if not results:
        return {}

    target = utils.norm(name)
    target_tokens = set(target.split())
    best = None
    best_ratio = 0.0
    for r in results:
        url = r.get("url", "")
        if "untappd.com/b/" not in url:
            continue
        # naamverificatie op basis van de slug in de URL + de titel
        slug = ""
        m = re.search(r"untappd\.com/b/([a-z0-9\-]+)/", url)
        if m:
            slug = m.group(1).replace("-", " ")
        haystack = utils.norm(f"{slug} {r.get('title','')}")
        ratio = difflib.SequenceMatcher(None, target, haystack).ratio()
        overlap = len(target_tokens & set(haystack.split())) / max(1, len(target_tokens))
        score = max(ratio, overlap)
        if score > best_ratio:
            best, best_ratio = r, score
    if not best or best_ratio < 0.55:
        return {}

    text = f"{best.get('title','')} {best.get('content','')}"
    result = {"url": best.get("url"), "match": best.get("title")}

    # score: eerst de exacte (2 decimalen) vorm, anders de tekstvorm
    m = RE_EXACT.search(text)
    if m:
        result["score"] = float(m.group(1))
        result["count"] = _to_int(m.group(2))
    else:
        m = RE_TEXT.search(text)
        if m:
            result["score"] = float(m.group(1))
            result["count"] = _to_int(m.group(2))
    if result.get("score") and not (0 < result["score"] <= 5):
        result.pop("score", None)

    sm = RE_STYLE.search(text)
    if sm:
        result["style"] = sm.group(1).strip()

    return result


def _to_int(s):
    digits = re.sub(r"[^\d]", "", s or "")
    return int(digits) if digits else None


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
