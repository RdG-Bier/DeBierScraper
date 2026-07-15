# -*- coding: utf-8 -*-
"""
Untappd-opzoekmodule v2.
Untappd's zoekfunctie rendert client-side via Algolia; de kale zoekpagina
bevat dus nooit resultaten. Deze module doet wat de browser ook doet:
1. haalt eenmalig de publieke Algolia-credentials van de Untappd-zoekpagina
2. bevraagt rechtstreeks de Algolia 'beer'-index (zelfde API als de site)
3. leest score/aantal van de gevonden bierpagina als die niet al in het
   zoekresultaat zitten

Behoudend opgezet: gelimiteerd aantal opzoekingen per run, vertraging,
permanente cache in docs/untappd_cache.json (incl. missers), en
naam-verificatie zodat een verkeerde match liever geen score oplevert.
"""

import difflib
import json
import logging
import re
import time
import urllib.parse
from pathlib import Path

import config
import utils

log = logging.getLogger("bierscraper")

CACHE_FILE = Path(__file__).parent / "docs" / "untappd_cache.json"
CACHE_VERSION = 2          # entries van oudere versies worden opnieuw opgezocht
EXTRA_DELAY = 1.2          # seconden extra rust per opzoeking
MATCH_THRESHOLD = 0.60

SEARCH_PAGE = "https://untappd.com/search"
RE_APP_ID = re.compile(r"applicationI[Dd]\s*[:=]\s*['\"]([A-Z0-9]{8,12})['\"]")
RE_API_KEYS = re.compile(r"['\"]([a-f0-9]{32})['\"]")
RE_RATING = re.compile(r'data-rating="([\d.]+)"')
RE_RATERS = re.compile(r'([\d.,]+)\s*Ratings', re.IGNORECASE)

_credentials = {"app_id": None, "keys": []}


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
        fresh = (entry and entry.get("v") == CACHE_VERSION
                 and (time.time() - entry.get("ts", 0)) < config.UNTAPPD_CACHE_DAYS * 86400)
        if not fresh:
            if lookups_done >= config.UNTAPPD_LOOKUP_MAX:
                continue  # limiet bereikt; volgende run gaat verder
            lookups_done += 1
            entry = _lookup(name, site_key)
            entry["ts"] = time.time()
            entry["v"] = CACHE_VERSION
            cache[key] = entry

        if entry.get("score"):
            beer["untappd"] = entry["score"]
            beer["untappd_aantal"] = entry.get("count")
            if entry.get("image") and not beer.get("afbeelding"):
                beer["afbeelding"] = entry["image"]
            filled += 1
            if entry.get("style"):
                canon = utils.find_style_in_text(entry["style"])
                if not canon:
                    canon, _ = utils.match_style(entry["style"])
                if canon and beer.get("stijl") not in config.STYLES:
                    beer["stijl"] = canon
                    beer["sterke_voorkeur"] = config.STYLES.get(canon, False)

    _save_cache(cache)
    log.info("Untappd-lookup %s: %d nieuw opgezocht, %d bieren aangevuld "
             "(cache: %d items)", site_key, lookups_done, filled, len(cache))
    return filled


def _get_credentials(site_key):
    """Haal de publieke Algolia app-id + zoeksleutel(s) van de zoekpagina."""
    if _credentials["app_id"]:
        return _credentials
    html = utils.fetch(SEARCH_PAGE)
    if not html:
        return _credentials
    utils.save_debug_sample(site_key, "untappd-zoekpagina", html)
    m = RE_APP_ID.search(html)
    if m:
        _credentials["app_id"] = m.group(1)
    # meerdere 32-hex sleutels kunnen op de pagina staan (search + analytics);
    # we proberen ze simpelweg allemaal, de juiste geeft resultaten
    _credentials["keys"] = list(dict.fromkeys(RE_API_KEYS.findall(html)))
    log.info("Untappd: Algolia app-id %s, %d kandidaat-sleutels",
             _credentials["app_id"], len(_credentials["keys"]))
    return _credentials


def _algolia_search(name, site_key):
    creds = _get_credentials(site_key)
    if not creds["app_id"] or not creds["keys"]:
        return None
    q = urllib.parse.quote_plus(name)
    for i, api_key in enumerate(list(creds["keys"])):
        url = (f"https://{creds['app_id']}-dsn.algolia.net/1/indexes/beer"
               f"?query={q}&hitsPerPage=5"
               f"&x-algolia-application-id={creds['app_id']}"
               f"&x-algolia-api-key={api_key}")
        data = utils.fetch_json(url, use_cache=False)
        if data and "hits" in data:
            if i > 0:  # werkende sleutel vooraan zetten voor volgende calls
                creds["keys"].remove(api_key)
                creds["keys"].insert(0, api_key)
            return data["hits"]
        # 403/foutmelding -> volgende sleutel proberen
    return None


def _lookup(name, site_key):
    """Zoek een bier: eerst via Algolia (de zoek-API van Untappd zelf),
    en als dat niets oplevert via een zoekmachine-omweg (DuckDuckGo) naar
    de Untappd-bierpagina."""
    time.sleep(EXTRA_DELAY)
    result = _lookup_algolia(name, site_key)
    if result.get("score"):
        return result
    ddg = _lookup_duckduckgo(name, site_key)
    return ddg if ddg.get("score") else (result or ddg)


def _lookup_algolia(name, site_key):
    hits = _algolia_search(name, site_key)
    if hits is None:
        log.warning("Untappd/Algolia: zoekopdracht mislukt voor %r", name)
        return {}

    target = utils.norm(name)
    target_tokens = set(target.split())
    best, best_ratio = None, 0.0
    for hit in hits:
        combined = utils.norm(f"{hit.get('brewery_name') or ''} {hit.get('beer_name') or ''}")
        ratio = difflib.SequenceMatcher(None, target, combined).ratio()
        overlap = (len(target_tokens & set(combined.split())) / max(1, len(target_tokens)))
        score = max(ratio, overlap)
        if score > best_ratio:
            best, best_ratio = hit, score
    if not best or best_ratio < MATCH_THRESHOLD:
        return {}

    result = {
        "match": f"{best.get('brewery_name')} - {best.get('beer_name')}",
        "style": best.get("type_name") or best.get("beer_style"),
        "via": "algolia",
    }
    # sommige indexvelden bevatten de rating al; anders bierpagina lezen
    score = best.get("rating_score")
    count = best.get("rating_count") or best.get("rating_counts")
    if isinstance(score, (int, float)) and 0 < float(score) <= 5:
        result["score"] = round(float(score), 2)
        result["count"] = int(count) if count else None
        return result

    bid = best.get("bid") or best.get("objectID")
    slug = (best.get("beer_index") or
            re.sub(r"[^a-z0-9]+", "-",
                   utils.norm(f"{best.get('brewery_name','')}-{best.get('beer_name','')}")).strip("-"))
    if not bid:
        return result
    url = f"https://untappd.com/b/{slug}/{bid}"
    result["url"] = url

    time.sleep(EXTRA_DELAY)
    page = utils.fetch(url, use_cache=False)
    if not page:
        return result
    utils.save_debug_sample(site_key, "untappd-bierpagina", page)
    result.update(_parse_beer_page(page))
    return result


RE_DDG_LINK = re.compile(r"(?:uddg=|href=[\"'])(https?[^\"'&]*untappd\.com(?:%2F|/)b(?:%2F|/)[^\"'&]+)")


def _lookup_duckduckgo(name, site_key):
    """Fallback: zoek de Untappd-bierpagina via DuckDuckGo's HTML-zoekpagina
    en lees die pagina uit. Bierpagina's van Untappd zijn gewoon server-side
    gerenderd (dezelfde soort pagina als het Bierbrigadier-menu)."""
    time.sleep(EXTRA_DELAY)
    q = urllib.parse.quote_plus(f"site:untappd.com/b {name}")
    html = utils.fetch(f"https://html.duckduckgo.com/html/?q={q}", use_cache=False)
    if not html:
        return {}
    utils.save_debug_sample(site_key, "ddg-zoekresultaat", html)

    target_tokens = set(utils.norm(name).split())
    beer_url = None
    for m in RE_DDG_LINK.finditer(html):
        url = urllib.parse.unquote(m.group(1)).split("?")[0]
        um = re.match(r"https?://untappd\.com/b/([a-z0-9\-]+)/\d+", url)
        if not um:
            continue
        slug_tokens = set(um.group(1).replace("-", " ").split())
        overlap = len(target_tokens & slug_tokens) / max(1, len(target_tokens))
        if overlap >= 0.5:
            beer_url = url
            break
    if not beer_url:
        return {}

    time.sleep(EXTRA_DELAY)
    page = utils.fetch(beer_url, use_cache=False)
    if not page:
        return {"url": beer_url, "via": "ddg"}
    utils.save_debug_sample(site_key, "untappd-bierpagina", page)
    result = {"url": beer_url, "via": "ddg"}
    result.update(_parse_beer_page(page))
    return result


def _parse_beer_page(page):
    """Score, aantal ratings en stijl van een Untappd-bierpagina."""
    out = {}
    m = RE_RATING.search(page)
    if m:
        try:
            val = round(float(m.group(1)), 2)
            if 0 < val <= 5:
                out["score"] = val
        except ValueError:
            pass
    m = RE_RATERS.search(page)
    if m:
        digits = re.sub(r"[^\d]", "", m.group(1))
        if digits:
            out["count"] = int(digits)
    sm = re.search(r'class="style"[^>]*>([^<]{3,60})<', page)
    if sm:
        out["style"] = sm.group(1).strip()
    im = re.search(r'(https://assets\.untappd\.com/site/beer_logos/[^"\s]+)', page)
    if im:
        out["image"] = im.group(1)
    return out


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
