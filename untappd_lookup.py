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
- een cache-VERSIEBUMP vernieuwt alleen missers; gevonden scores blijven geldig
- netwerk-/blokkadefouten worden NIET als misser gecachet en na een reeks
  fouten stopt de run (circuit breaker); bestaande scores blijven in gebruik
- verversing die niets vindt overschrijft een eerder gevonden score niet
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
# LET OP: een versiebump betekent sinds v22 alleen nog "probeer alle MISSERS
# opnieuw met de nieuwe zoeklogica". Gevonden scores (hits) blijven gewoon
# geldig - een score wordt niet fout doordat de code verandert (zie _is_fresh).
# 9 = missers opnieuw proberen met de compacte-code-varianten van v24.
CACHE_VERSION = 9
MISS_CACHE_DAYS = 3
EXTRA_DELAY = 1.0
MATCH_THRESHOLD = 0.55
# tekenreeks-gelijkenis mag pas op zichzelf een match rechtvaardigen als hij
# echt hoog is; zie de eindverificatie in _best_hit
STRICT_SEQ_THRESHOLD = 0.75
# Na zoveel OPEENVOLGENDE netwerk-/blokkadefouten stoppen we de lookups voor
# deze run: de bron ligt er dan uit en 250 kansloze verzoeken maken het alleen
# erger. Bestaande cachescores blijven gewoon in gebruik.
NETFAIL_ABORT = 8

SEARCH_PAGE = "https://untappd.com/search"
RE_APP_ID = re.compile(r"applicationI[Dd]\s*[:=]\s*['\"]([A-Z0-9]{8,12})['\"]")
RE_API_KEYS = re.compile(r"['\"]([a-f0-9]{32})['\"]")

# Ruiswoorden die shops (vooral Drankgigant) aan de productnaam plakken maar
# die NIET in de Untappd-biernaam staan. Weghalen geeft veel meer treffers:
# 'Kees Snake Eyes Triple IPA' -> 'Kees Snake Eyes'
RE_NOISE = re.compile(
    r'\b('
    r'imperial|imp|quadruple|quad|dubbel|tripel|kwart|russian|'
    r'stout|neipa|nedipa|dipa|tipa|ddh|tdh|nepa|xpa|'
    r'sour|gose|porter|barleywine|witbier|weizen|'
    r'pale\s+ale|american\s+ipa|american|new\s+england|hazy|juicy|'
    r'pastry|smoothie|milkshake|single\s+hop|'
    # los 'ba' (zonder cijfers erachter) is vrijwel altijd Barrel Aged;
    # codes als 'BA25.01' blijven intact omdat daar geen woordgrens na 'ba' zit
    r'ba|'
    r'alcoholarm|alcoholvrij|alcohol\s?vrij|non[\- ]?alcoholic|alcohol[\- ]?free|'
    r'blik|can|fles|bottle|krat'
    r')\b', re.IGNORECASE)
# 'IPA', 'Double', 'Triple', 'Ale' en 'White' zitten vaak IN de biernaam
# (Double Haze, White Dog, Triple Sec...). Die halen we alleen weg als ze
# HELEMAAL AAN HET EIND staan, waar ze een stijl-toevoeging zijn.
RE_TRAIL_STYLE = re.compile(
    r'(?:\s+(?:double|triple|ipa|ale|blonde?|lager|pils(?:ener|ner)?|'
    r'saison|white|black|cold|west\s+coast|east\s+coast))+\s*$', re.IGNORECASE)
RE_VOL = re.compile(r'\b\d{1,3}(?:[.,]\d)?\s?(?:cl|ml|l)\b', re.IGNORECASE)
RE_BARREL = re.compile(r'\bwith\b.*$|\(.*?\)|barrel[\- ]?aged', re.IGNORECASE)
# batchcodes zoals 'BA 25.01', 'batch 2', 'BA 25 01'. Verplichte spatie na de
# code, zodat namen als 'BA25.01' (aan elkaar = de Untappd-biernaam van o.a.
# Baxbier) intact blijven; decimalen worden volledig meegenomen zodat er geen
# '.01'-restant in de zoekterm achterblijft.
RE_BATCH = re.compile(r'\b(?:ba|batch|b\.?a\.?)\s+\d[\d.,]*(?:\s+\d[\d.,]*)*',
                      re.IGNORECASE)
# 'B.A.' met punten (zonder cijfers) is altijd Barrel Aged, nooit een naam
RE_BA_DOTTED = re.compile(r'\bb\.\s?a\.?(?=[\s,)]|$)', re.IGNORECASE)
# losse punt (niet tussen twee cijfers): restjes van 'Imp.', 'B.A.' etc.
RE_LONE_DOT = re.compile(r'(?<!\d)\.(?!\d)')
# shops schrijven seriecodes vaak los ('BA 25.01') terwijl Untappd ze aan
# elkaar schrijft ('BA25.01'): korte lettercode + spatie + nummer samenvoegen
RE_COMPACT = re.compile(r'\b([A-Za-z]{2,3})\.?\s+(\d+(?:[.,]\d+)+)\b')


def _clean_query(name):
    """Maak een zoekterm die op de Untappd-biernaam lijkt: haal stijl-,
    volume-, batch- en variantruis eruit, maar spaar woorden die deel van de
    eigenlijke biernaam kunnen zijn (die verwijderen we alleen als trailing
    stijl-achtervoegsel)."""
    n = RE_BARREL.sub(' ', name)
    n = RE_BATCH.sub(' ', n)
    n = RE_BA_DOTTED.sub(' ', n)
    n = RE_VOL.sub(' ', n)
    n = RE_NOISE.sub(' ', n)
    n = RE_LONE_DOT.sub(' ', n)
    n = re.sub(r'\s+', ' ', n).strip(' -,')
    # trailing stijlwoorden herhaald weghalen ('... Double IPA' -> '...')
    prev = None
    while prev != n:
        prev = n
        n = RE_TRAIL_STYLE.sub('', n).strip(' -,')
    n = re.sub(r'\s*[/|]\s*', ' ', n)          # losse scheidingstekens weg
    n = re.sub(r'\s+', ' ', n).strip(' -,/|')
    return n or name.strip()


MAX_QUERY_VARIANTS = 8
# losse verbindingswoorden waarop een afgepelde variant niet mag eindigen
SKIP_TAIL = {"x", "&", "en", "met", "and", "with", "the", "de", "het", "a"}


def _query_variants(name):
    """Zoekvarianten in volgorde van voorkeur, zonder duplicaten.
    Shops plakken vaak eigen toevoegingen achter de biernaam die NIET op
    Untappd staan ('Handlanger MERCILESS Double IPA' heet daar 'Handlanger';
    '10 Years: Liftoff DOUBLE MASHED TIPA' heet er '10 Years: Liftoff').
    Zulke woorden zijn niet te voorspellen, en Algolia geeft nul resultaten
    zodra één zoekwoord niet in de biernaam voorkomt. Daarom proberen we na
    de opgeschoonde naam ook varianten waarbij van achteren telkens een woord
    wordt weggelaten. Seriecodes die de shop los schrijft ('BA 25.01') maar
    Untappd aan elkaar ('BA25.01'), krijgen een eigen compacte variant.
    De naam-verificatie in _best_hit (dekking + brouwerijbonus + compacte
    vergelijking) bewaakt dat een bredere zoekopdracht geen verkeerd bier
    oplevert."""
    variants = []

    def _add(v):
        v = v.strip(' -,:/|')
        if v and v not in variants and len(variants) < MAX_QUERY_VARIANTS:
            variants.append(v)

    cleaned = _clean_query(name)
    _add(cleaned)
    compact = RE_COMPACT.sub(r'\1\2', name)
    if compact != name:
        _add(_clean_query(compact))
    words = cleaned.split()
    while len(words) > 2 and len(variants) < MAX_QUERY_VARIANTS - 1:
        words = words[:-1]
        if words[-1].lower().strip(':,-') in SKIP_TAIL:
            continue  # niet eindigen op een los verbindingswoord
        _add(" ".join(words))
    _add(name)  # volledige naam als laatste vangnet (bijv. te agressieve cleaning)
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
    netfails_row = 0     # opeenvolgende netwerk-/blokkadefouten (circuit breaker)
    netfails_total = 0   # totaal deze run, voor de logregel
    stale_used = 0       # bieren geholpen met een verouderde (maar geldige) cachescore

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
        entry = cache.get(key) or {}

        if (not _is_fresh(entry) and lookups_done < config.UNTAPPD_LOOKUP_MAX
                and netfails_row < NETFAIL_ABORT):
            lookups_done += 1
            fresh = _lookup(name, site_key)
            if fresh.get("netfail"):
                # Bron onbereikbaar of geblokkeerd: we hebben niets over dit
                # bier geleerd. Cache NIET aanpassen - anders staat er 3 dagen
                # een nep-misser en blijft het bier onterecht 'onbekend'.
                # De volgende run probeert het gewoon opnieuw.
                netfails_row += 1
                netfails_total += 1
                if netfails_row >= NETFAIL_ABORT:
                    log.warning("Untappd-lookup %s: %d opeenvolgende netwerk-/"
                                "blokkadefouten - verdere opzoekingen deze run "
                                "overgeslagen; bestaande cachescores blijven "
                                "in gebruik", site_key, netfails_row)
            else:
                netfails_row = 0
                if fresh.get("via") == "algolia":
                    algolia_ok += 1
                if not fresh.get("score") and entry.get("score"):
                    # Verversing van een eerder gevonden bier leverde nu niets
                    # op (Algolia-index hapert wel eens). De oude score is dan
                    # betrouwbaarder dan 'onbekend': behouden, met teller.
                    fresh = dict(entry)
                    fresh["refresh_missed"] = fresh.get("refresh_missed", 0) + 1
                fresh["ts"] = time.time()
                fresh["v"] = CACHE_VERSION
                cache[key] = fresh
                entry = fresh

        if entry.get("score"):
            if not _is_fresh(entry):
                stale_used += 1
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
             "(%d via oudere cachescore), netwerkfouten: %d (cache: %d)",
             site_key, lookups_done, algolia_ok, filled, stale_used,
             netfails_total, len(cache))
    return filled


def _is_fresh(entry):
    """Bepaalt of een cache-entry bruikbaar is zonder nieuwe opzoekactie.
    Hits (mét score) uit een OUDERE cacheversie blijven gewoon geldig binnen
    de normale houdbaarheid: de score zelf verandert niet doordat de
    zoeklogica is aangepast. Alleen missers van een oude versie zijn direct
    'niet vers', zodat ze een nieuwe kans krijgen met de verbeterde logica."""
    if not entry:
        return False
    if entry.get("v") != CACHE_VERSION and not entry.get("score"):
        return False
    age_days = (time.time() - entry.get("ts", 0)) / 86400
    return age_days < (config.UNTAPPD_CACHE_DAYS if entry.get("score") else MISS_CACHE_DAYS)


def _lookup(name, site_key):
    """Eerst Algolia (JSON-API), dan zoekmachine-fallback.
    Geeft {'netfail': True} terug als de bronnen onbereikbaar/geblokkeerd
    waren (= niets over dit bier te concluderen), te onderscheiden van
    {} (= bronnen werkten, maar het bier is echt niet gevonden)."""
    time.sleep(EXTRA_DELAY)
    result = _lookup_algolia(name, site_key)
    if result.get("score"):
        return result
    fb = _lookup_search(name)
    if fb.get("score"):
        return fb
    return result or fb


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
        # Zonder credentials (zoekpagina onbereikbaar/geblokkeerd) kán er
        # niets opgezocht worden. Dat zegt niets over dit bier: netfail.
        return {"netfail": True}

    saw_response = False
    # probeer achtereenvolgens de opgeschoonde term en de volledige naam
    for query in _query_variants(name):
        hits = _algolia_query(query, creds)
        if hits is None:
            continue          # netwerk-/blokkadefout voor deze query
        saw_response = True
        if not hits:
            continue          # geldige respons, maar echt geen resultaten
        result = _best_hit(name, hits)
        if result.get("score"):
            return result
    return {} if saw_response else {"netfail": True}


def _algolia_query(query, creds):
    """Geeft de lijst hits terug ([] = geldige respons zonder resultaten) of
    None als geen enkele API-sleutel een bruikbare respons opleverde
    (netwerkfout, 403/429-blokkade, ongeldige JSON)."""
    q = urllib.parse.quote_plus(query)
    for i, api_key in enumerate(list(creds["keys"])):
        url = (f"https://{creds['app_id']}-dsn.algolia.net/1/indexes/beer"
               f"?query={q}&hitsPerPage=8"
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
    target_compact = target.replace(" ", "")
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
        # bij gelijke namen (weegt stevig mee zodat de juiste brouwerij wint).
        # De overlap telt ook licht apart mee als tiebreaker: anders scoren
        # serie-broertjes ('BA25.01' vs 'BA25.02') identiek en wint de
        # verkeerde als die toevallig eerder in de resultaten staat.
        score = max(name_ratio, beer_overlap) + 0.25 * beer_overlap + brewery_hit * 0.6
        beer_compact = beer.replace(" ", "")
        if len(beer_compact) >= 5 and beer_compact in target_compact:
            # exact dezelfde naam op spaties na ('BA 25.01' vs 'BA25.01'):
            # vrijwel zeker het juiste bier
            score += 0.3
        if score > best_score:
            best, best_score = hit, score

    # drempel op de naamcomponent (niet op de bonus), zodat losse
    # brouwerij-matches zonder naamgelijkenis niet per ongeluk winnen
    if not best:
        return {}
    beer = utils.norm(best.get("beer_name") or "")
    combined = utils.norm(f"{utils.norm(best.get('brewery_name') or '')} {beer}")
    beer_tokens_final = set(beer.split())
    # Primaire toets: hoe goed dekt de shopnaam de woorden van het gevonden
    # bier? (bij een korte Untappd-naam die volledig in de langere shopnaam
    # zit is dit 1.0 - het normale patroon.)
    coverage = len(target_tokens & beer_tokens_final) / max(1, len(beer_tokens_final))
    # Secundair: pure tekenreeks-gelijkenis. Alleen doorslaggevend bij ECHT
    # hoge gelijkenis (typo's/spellingvarianten). Bij een lagere drempel zou
    # 'Snake Venom' via losse letterovereenkomst op 'Snake Eyes' matchen.
    seq = max(
        difflib.SequenceMatcher(None, target_clean, combined).ratio(),
        difflib.SequenceMatcher(None, target_clean, beer).ratio(),
    )
    if coverage < MATCH_THRESHOLD and seq < STRICT_SEQ_THRESHOLD:
        # laatste kans: vergelijk zonder spaties. Vangt namen die de shop
        # anders spelt dan Untappd ('BA 25.01' vs 'BA25.01'); minimale lengte
        # voorkomt toevalstreffers op korte namen.
        beer_compact = beer.replace(" ", "")
        target_compact = target.replace(" ", "")
        if len(beer_compact) < 5 or beer_compact not in target_compact:
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
