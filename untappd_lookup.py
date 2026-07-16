# -*- coding: utf-8 -*-
"""
Untappd-opzoekmodule v4.
Primaire bron: Untappd's eigen Algolia zoek-API (de 'beer'-index die de site
zelf gebruikt). Dit is een echte JSON-API - geen HTML-scraping - en levert
per bier: rating_score (2-3 decimalen), rating_count, stijl en etiket.
De publieke app-id + search-key worden van de Untappd-zoekpagina gehaald;
verandert Untappd ze, dan pikt de volgende run ze automatisch opnieuw op.

Secundaire bron (fallback): een zoekmachine (websearch.py) die de
Untappd-bierpagina vindt en daar de rating uit leest.

Robuustheid:
- permanente bierdatabase (scoring.py) voorkomt dubbel opzoeken
- gelimiteerd aantal opzoekingen per run + vertraging
- cache onthoudt hits en missers (missers korter)
- naam-verificatie: het gevonden bier moet op de zoekterm lijken
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
CACHE_VERSION = 5
MISS_CACHE_DAYS = 3
EXTRA_DELAY = 1.0
MATCH_THRESHOLD = 0.55

SEARCH_PAGE = "https://untappd.com/search"
RE_APP_ID = re.compile(r"applicationI[Dd]\s*[:=]\s*['\"]([A-Z0-9]{8,12})['\"]")
RE_API_KEYS = re.compile(r"['\"]([a-f0-9]{32})['\"]")

# Ruiswoorden die shops (vooral Drankgigant) aan de productnaam plakken maar
# die NIET in de Untappd-biernaam staan. Weghalen geeft veel meer treffers:
# 'Kees Snake Eyes Triple IPA' -> 'Kees Snake Eyes'
RE_NOISE = re.compile(
    r'\b('
    r'imperial|double|triple|quadruple|quad|dubbel|tripel|kwart|russian|'
    r'stout|ipa|neipa|dipa|tipa|sour|gose|porter|ale|lager|pils|pilsener|'
    r'pilsner|blond|blonde|saison|barleywine|witbier|weizen|'
    r'hazy|pastry|smoothie|milkshake|'
    r'alcoholarm|alcoholvrij|alcoholvrn|non[\- ]?alcoholic|alcohol[\- ]?free|'
    r'blik|can|fles|bottle|krat'
    r')\b', re.IGNORECASE)
RE_VOL = re.compile(r'\b\d{1,3}(?:[.,]\d)?\s?(?:cl|ml|l)\b', re.IGNORECASE)
RE_BARREL = re.compile(r'\bwith\b.*$|\(.*?\)|barrel[\- ]?aged|\bb\.?a\.?\b', re.IGNORECASE)


def _clean_query(name):
    """Maak een zoekterm die op de Untappd-biernaam lijkt: haal stijl-,
    volume- en variantruis eruit."""
    n = RE_BARREL.sub(' ', name)
    n = RE_VOL.sub(' ', n)
    n = RE_NOISE.sub(' ', n)
    n = re.sub(r'\s+', ' ', n).strip(' -,')
    return n


def _query_variants(name):
    """Zoekvarianten in volgorde van voorkeur, zonder duplicaten."""
    variants = []
    cleaned = _clean_query(name)
    for v in (cleaned, name):
        v = v.strip()
        if v and v not in variants:
            variants.append(v)
    return variants

# zoekmachine-fallback (door main.py gezet): (query)->list[{title,url,content}]
search_fn = None
RE_TEXT = re.compile(
    r'rating of ([0-5](?:\.\d{1,3})?) out of 5,?\s*with\s*([\d,\.]+)\s*ratings',
    re.IGNORECASE)
RE_EXACT = re.compile(r'\(([0-5]\.\d{2,3})\)\s*([\d,\.]+)\s*Ratings', re.IGNORECASE)
RE_STYLE_TEXT = re.compile(r'\bis a[n]? ([A-Z][A-Za-z\-/ ]+?) which has a rating', re.IGNORECASE)

_creds = {"app_id": None, "keys": None}


def enrich_beers(beers, site_key):
    cache = _load_cache()
    lookups_done = 0
    filled = 0
    algolia_ok = 0

    # Verdeel de bieren: eerst degene die (nog) geen bruikbare cache-entry
    # hebben en dus opgezocht moeten worden, daarna de rest. Zo raken oude
    # missers/verouderde entries niet 'achteraan de rij' als het limiet klein
    # is. Binnen de op-te-zoeken groep: bieren zonder enige entry eerst.
    def _needs_lookup(b):
        if b.get("untappd") is not None or not b.get("naam"):
            return False
        return not _is_fresh(cache.get(utils.norm(f"{b.get('brouwerij') or ''} {b['naam']}")))

    def _sort_key(b):
        key = utils.norm(f"{b.get('brouwerij') or ''} {b.get('naam','')}")
        entry = cache.get(key)
        # 0 = nooit opgezocht, 1 = verouderde entry (oude versie/misser)
        return 0 if entry is None else 1

    to_process = sorted((b for b in beers if _needs_lookup(b)), key=_sort_key)
    already_ok = [b for b in beers if not _needs_lookup(b)]

    for beer in to_process + already_ok:
        if beer.get("untappd") is not None:
            continue
        name = beer.get("naam")
        if not name:
            continue
        key = utils.norm(f"{beer.get('brouwerij') or ''} {name}")

        entry = cache.get(key)
        if not _is_fresh(entry):
            if lookups_done >= config.UNTAPPD_LOOKUP_MAX:
                continue
            lookups_done += 1
            entry = _lookup(name, site_key)
            entry["ts"] = time.time()
            entry["v"] = CACHE_VERSION
            cache[key] = entry
            if entry.get("via") == "algolia":
                algolia_ok += 1

        if entry.get("score"):
            beer["untappd"] = entry["score"]
            beer["untappd_aantal"] = entry.get("count")
            if entry.get("image") and not beer.get("afbeelding"):
                beer["afbeelding"] = entry["image"]
            if entry.get("style"):
                canon = utils.find_style_in_text(entry["style"]) or utils.match_style(entry["style"])[0]
                if canon and beer.get("stijl") not in config.STYLES:
                    beer["stijl"] = canon
                    beer["sterke_voorkeur"] = config.STYLES.get(canon, False)
            filled += 1

    _save_cache(cache)
    log.info("Untappd-lookup %s: %d opgezocht (%d via Algolia), %d aangevuld "
             "(cache: %d)", site_key, lookups_done, algolia_ok, filled, len(cache))
    return filled


def _is_fresh(entry):
    if not entry or entry.get("v") != CACHE_VERSION:
        return False
    age_days = (time.time() - entry.get("ts", 0)) / 86400
    return age_days < (config.UNTAPPD_CACHE_DAYS if entry.get("score") else MISS_CACHE_DAYS)


def _lookup(name, site_key):
    """Eerst Algolia (JSON-API), dan zoekmachine-fallback."""
    time.sleep(EXTRA_DELAY)
    result = _lookup_algolia(name, site_key)
    if result.get("score"):
        return result
    fb = _lookup_search(name)
    return fb if fb.get("score") else (result or fb)


# ---------------------------------------------------------------------------
# Algolia
# ---------------------------------------------------------------------------

def _get_creds(site_key):
    if _creds["app_id"] is not None:
        return _creds
    html = utils.fetch(SEARCH_PAGE)
    if html:
        utils.save_debug_sample(site_key, "untappd-zoekpagina", html)
        m = RE_APP_ID.search(html)
        _creds["app_id"] = m.group(1) if m else ""
        _creds["keys"] = list(dict.fromkeys(RE_API_KEYS.findall(html)))
        log.info("Untappd/Algolia: app-id=%s, %d kandidaat-sleutels",
                 _creds["app_id"], len(_creds["keys"]))
    else:
        _creds["app_id"], _creds["keys"] = "", []
    return _creds


def _lookup_algolia(name, site_key):
    creds = _get_creds(site_key)
    if not creds["app_id"] or not creds["keys"]:
        return {}

    # probeer achtereenvolgens de opgeschoonde term en de volledige naam
    for query in _query_variants(name):
        hits = _algolia_query(query, creds)
        if not hits:
            continue
        result = _best_hit(name, hits)
        if result.get("score"):
            return result
    return {}


def _algolia_query(query, creds):
    q = urllib.parse.quote_plus(query)
    for i, api_key in enumerate(list(creds["keys"])):
        url = (f"https://{creds['app_id']}-dsn.algolia.net/1/indexes/beer"
               f"?query={q}&hitsPerPage=6"
               f"&x-algolia-application-id={creds['app_id']}"
               f"&x-algolia-api-key={api_key}")
        data = utils.fetch_json(url, use_cache=False)
        if data and "hits" in data:
            if i > 0:
                creds["keys"].remove(api_key)
                creds["keys"].insert(0, api_key)
            return data["hits"]
    return None


def _best_hit(name, hits):
    """Kies de beste hit. Cruciaal bij gelijknamige bieren van verschillende
    brouwerijen (er zijn bijv. meerdere bieren 'Snake Eyes'): de brouwerijnaam
    uit de shopnaam moet zwaar meewegen, anders wordt de verkeerde gekozen."""
    target = utils.norm(name)
    target_clean = utils.norm(_clean_query(name))
    target_tokens = set(target.split()) | set(target_clean.split())
    best, best_score = None, 0.0
    for hit in hits:
        beer = utils.norm(hit.get("beer_name") or "")
        brewery = utils.norm(hit.get("brewery_name") or "")
        combined = utils.norm(f"{brewery} {beer}")
        beer_tokens = set(beer.split())
        brewery_tokens = set(brewery.split())

        # basis: hoe goed dekt de biernaam de (opgeschoonde) zoekterm
        name_ratio = max(
            difflib.SequenceMatcher(None, target, combined).ratio(),
            difflib.SequenceMatcher(None, target_clean, combined).ratio(),
            difflib.SequenceMatcher(None, target_clean, beer).ratio(),
        )
        beer_overlap = len(target_tokens & beer_tokens) / max(1, len(beer_tokens))

        # brouwerij-bonus: hoeveel van de brouwerijwoorden zit in de zoekterm?
        # (shopnaam 'Kees Snake Eyes...' bevat 'kees' -> match met 'brouwerij kees')
        brewery_hit = 0.0
        if brewery_tokens:
            # negeer generieke woorden die in veel brouwerijnamen staan
            meaningful = brewery_tokens - {"brouwerij", "brewing", "brewery",
                                           "company", "co", "de", "the", "craft"}
            check = meaningful or brewery_tokens
            brewery_hit = len(target_tokens & check) / max(1, len(check))

        # eindscore: naamgelijkenis is leidend, brouwerij-match is doorslaggevend
        # bij gelijke namen (weegt stevig mee zodat de juiste brouwerij wint)
        score = max(name_ratio, beer_overlap) + brewery_hit * 0.6
        if score > best_score:
            best, best_score = hit, score

    # drempel op de naamcomponent (niet op de bonus), zodat losse
    # brouwerij-matches zonder naamgelijkenis niet per ongeluk winnen
    if not best:
        return {}
    beer = utils.norm(best.get("beer_name") or "")
    combined = utils.norm(f"{utils.norm(best.get('brewery_name') or '')} {beer}")
    final_name_ratio = max(
        difflib.SequenceMatcher(None, target_clean, combined).ratio(),
        difflib.SequenceMatcher(None, target_clean, beer).ratio(),
        len(target_tokens & set(beer.split())) / max(1, len(set(beer.split()))),
    )
    if final_name_ratio < MATCH_THRESHOLD:
        return {}

    result = {"via": "algolia", "match": f"{best.get('brewery_name')} - {best.get('beer_name')}",
              "style": best.get("type_name") or best.get("beer_style")}
    score = best.get("rating_score")
    if isinstance(score, (int, float)) and 0 < float(score) <= 5:
        result["score"] = round(float(score), 2)
        cnt = best.get("rating_count") or best.get("rating_counts")
        result["count"] = int(cnt) if cnt else None
    img = best.get("beer_label") or best.get("label")
    if img:
        result["image"] = img
    return result


# ---------------------------------------------------------------------------
# Zoekmachine-fallback
# ---------------------------------------------------------------------------

def _lookup_search(name):
    if search_fn is None:
        return {}
    try:
        results = search_fn(f"{name} untappd")
    except Exception as exc:
        log.warning("Zoek-fallback mislukt voor %r: %s", name, exc)
        return {}
    if not results:
        return {}
    target = utils.norm(name)
    target_tokens = set(target.split())
    best, best_ratio = None, 0.0
    for r in results:
        if "untappd.com/b/" not in r.get("url", ""):
            continue
        m = re.search(r"untappd\.com/b/([a-z0-9\-]+)/", r["url"])
        slug = m.group(1).replace("-", " ") if m else ""
        hay = utils.norm(f"{slug} {r.get('title','')}")
        s = max(difflib.SequenceMatcher(None, target, hay).ratio(),
                len(target_tokens & set(hay.split())) / max(1, len(target_tokens)))
        if s > best_ratio:
            best, best_ratio = r, s
    if not best or best_ratio < MATCH_THRESHOLD:
        return {}
    text = f"{best.get('title','')} {best.get('content','')}"
    result = {"via": "search", "url": best.get("url")}
    m = RE_EXACT.search(text) or RE_TEXT.search(text)
    if m:
        val = float(m.group(1))
        if 0 < val <= 5:
            result["score"] = val
            result["count"] = _to_int(m.group(2))
    sm = RE_STYLE_TEXT.search(text)
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
