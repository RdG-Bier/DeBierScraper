# -*- coding: utf-8 -*-
"""
Scraper voor Shopify-shops (De Biersalon, Beer Republic).
Gebruikt het publieke /products.json endpoint: gestructureerd en stabiel.
Untappd-gegevens staan vaak in tags of in de productomschrijving (body_html);
ontbreken ze daar, dan wordt (optioneel) de productpagina zelf gelezen.
"""

import collections
import json
import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

import config
import utils

log = logging.getLogger("bierscraper")

# Als score/land niet in products.json staat: productpagina erbij pakken?
FETCH_DETAIL_FALLBACK = True
# Veiligheidslimiet zodat een eerste run niet urenlang detailpagina's trekt.
MAX_DETAIL_FETCHES = 800


MAX_FEED_PAGES = 60
MAX_TILE_PAGES = 60
# Telt per reden hoeveel producten zijn afgewezen (voor de diagnose-file)
REJECT = collections.Counter()
# Details van producten uit config.TRACE_HANDLES (waarom wel/niet opgenomen)
TRACE = {}


def _trace(handle, **info):
    if handle and handle in getattr(config, "TRACE_HANDLES", ()):
        TRACE.setdefault(handle, {}).update(info)

# Op de collectiepagina's staat per bier de exacte Untappd-stijl tussen
# blokhaken, plus score en aantal ratings:
#   ... 440ml · Letland · 10.3% · ["IPA - Triple New England / Hazy"] 4.26 78ratings
RE_TILE_STYLE = re.compile(r'\[\s*"([^"\]]{3,60})"\s*\]')
RE_TILE_SCORE = re.compile(r"(\d[.,]\d{1,2})\s+([\d.,]+)\s*ratings", re.IGNORECASE)


def _scrape_collection_tiles(site):
    """Bouw: producthandle -> tegel-info (stijl, untappd, aantal, land).
    Deze info zit NIET in products.json (het zijn metavelden), dus zonder
    tegels vallen bieren terug op een brede stijl als 'Stout' of 'IPA'.
    We lopen meerdere kleinere stijlcollecties af in plaats van één hele
    grote, zodat we ook echt tot de laatste pagina komen."""
    tile_map = {}
    base = site["base_url"].rstrip("/")
    for coll in site.get("tile_collections", []):
        url = coll if coll.startswith("http") else f"{base}/collections/{coll}"
        gevonden = _tiles_from_collection(url, tile_map, site)
        if gevonden:
            log.info("  tegels uit %s: +%d", coll, gevonden)
    log.info("%s: tegel-info voor %d producten", site["label"], len(tile_map))
    if len(tile_map) < config.MIN_TILES_WARN:
        log.warning("%s: WEINIG TEGELS (%d)! Zonder tegels vallen bieren terug "
                    "op brede stijlen als 'Stout'/'IPA' en kloppen de scores "
                    "niet meer. Controleer de collectie-URL's in config.py.",
                    site["label"], len(tile_map))
    return tile_map


def _tiles_from_collection(url, tile_map, site):
    nieuw_totaal = 0
    leeg_achter_elkaar = 0
    for page in range(1, MAX_TILE_PAGES + 1):
        html = utils.fetch(f"{url}?page={page}")
        if not html:
            break
        if page == 1:
            utils.save_debug_sample(site["key"], "collectie", html)
        soup = BeautifulSoup(html, "html.parser")
        for t in soup.find_all(["script", "style"]):
            t.decompose()
        new = 0
        for a in soup.find_all("a", href=re.compile(r"/products/[a-z0-9\-]+")):
            m = re.search(r"/products/([a-z0-9\-]+)", a["href"])
            handle = m.group(1)
            if handle in tile_map:
                continue
            container = a
            for _ in range(7):
                container = container.parent
                if container is None:
                    break
                text = container.get_text(" ", strip=True)
                if ("ratings" in text.lower() or "untappd" in text.lower()
                        or RE_TILE_STYLE.search(text)) and len(text) < 700:
                    info = {}
                    sm = RE_TILE_STYLE.search(text)
                    if sm:
                        info["stijl"] = sm.group(1)
                    um = RE_TILE_SCORE.search(text)
                    if um:
                        score = float(um.group(1).replace(",", "."))
                        digits = re.sub(r"[^\d]", "", um.group(2))
                        info["untappd"] = score if score > 0 else None
                        info["untappd_aantal"] = int(digits) if digits else None
                    info["land"] = utils.parse_country(text)
                    if info:
                        tile_map[handle] = info
                        new += 1
                    break
        nieuw_totaal += new
        # pas stoppen na twee lege pagina's achter elkaar: één lege pagina kan
        # ook een hikje of een pagina met alleen al bekende bieren zijn
        leeg_achter_elkaar = leeg_achter_elkaar + 1 if new == 0 else 0
        if leeg_achter_elkaar >= 2:
            break
    return nieuw_totaal


def scrape(site):
    base = site["base_url"].rstrip("/")
    _parse_product.detail_count = 0  # budget per shop, niet gedeeld
    REJECT.clear()

    # Bron 1: de hoofdfeed met alle producten.
    # Bron 2: de JSON-feed per collectie. Nodig als vangnet, want gebleken is
    # dat de hoofdfeed soms producten mist (bijv. het Arpus QDH-bier dat wel
    # gewoon op voorraad in de Triple IPA-collectie staat). Collectie-feeds
    # zijn standaard Shopify-endpoints en kosten maar een paar requests.
    tile_map = _scrape_collection_tiles(site) if site.get("tile_collections") else {}

    products = {}
    herkomst = {}

    herkomst["hoofdfeed"] = _collect_feed(f"{base}/products.json", products)
    for handle in site.get("collections", []):
        n = _collect_feed(f"{base}/collections/{handle}/products.json", products)
        if n:
            herkomst[f"collectie:{handle}"] = n

    log.info("%s: %d unieke producten uit %d bron(nen) [%s]", site["label"],
             len(products), len(herkomst),
             ", ".join(f"{k} +{v}" for k, v in herkomst.items()))

    beers = []
    for product in products.values():
        beer = _parse_product(product, base, tile_map)
        if beer:
            beers.append(beer)

    log.info("%s: %d bieren na stijl/score/voorraad-filter (afgewezen: %s)",
             site["label"], len(beers), dict(REJECT))
    _write_diagnose(site, len(products), beers, herkomst, tile_map)
    return beers


def _collect_feed(feed_url, out):
    """Lees een Shopify-JSON-feed volledig uit en voeg nieuwe producten toe
    aan 'out' (handle -> product). Retourneert het aantal NIEUWE producten.
    Een mislukte pagina wordt één keer opnieuw geprobeerd; anders zouden we
    bij een hikje stilletjes de rest van de catalogus overslaan."""
    added = 0
    page = 1
    while page <= MAX_FEED_PAGES:
        url = f"{feed_url}?limit=250&page={page}"
        data = utils.fetch_json(url)
        if not data:
            data = utils.fetch_json(url, use_cache=False)  # één herkansing
        if not data or not isinstance(data.get("products"), list):
            if page == 1:
                log.warning("Feed zonder producten: %s", feed_url)
            break
        batch = data["products"]
        if not batch:
            break
        for p in batch:
            handle = p.get("handle")
            if handle and handle not in out:
                out[handle] = p
                added += 1
        if len(batch) < 250:
            break
        page += 1
    return added


def _write_diagnose(site, aantal_producten, beers, herkomst, tile_map):
    """Klein overzicht per run in docs/, handig om te zien of er iets mist.
    TRACE bevat de details van producten uit config.TRACE_HANDLES: daarmee is
    van een specifiek bier te zien of het gevonden is en zo nee, waarom niet."""
    try:
        path = Path(__file__).parent / "docs" / f"diagnose_{site['key']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "producten_gevonden": aantal_producten,
            "tegels_gevonden": len(tile_map),
            "bieren_na_filter": len(beers),
            "bronnen": herkomst,
            "afgewezen": dict(REJECT),
            "trace": TRACE,
        }, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _parse_product(p, base, tile_map=None):
    handle = p.get("handle")
    title = (p.get("title") or "").strip()
    vendor = (p.get("vendor") or "").strip() or None
    product_type = (p.get("product_type") or "").strip()
    tags = p.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    body_html = p.get("body_html") or ""
    body_text = BeautifulSoup(body_html, "html.parser").get_text(" ", strip=True)

    # --- voorraad: minstens één variant leverbaar ---
    variants = p.get("variants") or []
    available_variants = [v for v in variants if v.get("available")]
    _trace(handle, gevonden_in_feed=True, titel=title,
           tegel_aanwezig=bool((tile_map or {}).get(handle)),
           varianten=[{"available": v.get("available"), "prijs": v.get("price"),
                       "titel": v.get("title")} for v in variants],
           product_type=p.get("product_type"), tags=p.get("tags"))
    if not available_variants:
        REJECT["niet op voorraad"] += 1
        _trace(handle, afgewezen="niet op voorraad")
        return None
    variant = min(available_variants, key=lambda v: float(v.get("price") or 9e9))
    try:
        price = round(float(variant.get("price")), 2)
    except (TypeError, ValueError):
        price = None

    # --- stijl: tegel-info van de collectiepagina heeft voorrang. Die bevat
    #     de exacte Untappd-stijl (metaveld) die NIET in products.json staat;
    #     zonder tegel valt een bier terug op een brede stijl. ---
    tile = (tile_map or {}).get(handle) or {}
    style_candidates = [c for c in [tile.get("stijl"), product_type] if c] + \
        [str(t) for t in tags]
    canon, strong = utils.derive_style(style_candidates, title)
    _trace(handle, tegel=tile or None, stijl_bepaald=canon)
    if not canon:
        REJECT["geen doelstijl"] += 1
        _trace(handle, afgewezen="geen doelstijl")
        return None
    style_raw = tile.get("stijl") or product_type or None

    searchable = " ".join([title, product_type, body_text] + [str(t) for t in tags])

    untappd = tile.get("untappd")
    untappd_count = tile.get("untappd_aantal")
    if untappd is None and "untappd" not in tile:
        untappd, untappd_count = utils.parse_untappd(searchable)
    country = tile.get("land") or parse_country_from_tags(tags) or utils.parse_country(searchable)
    abv = utils.parse_abv(variant.get("title") or "") or utils.parse_abv(searchable)
    volume = utils.parse_volume_cl(title) or utils.parse_volume_cl(variant.get("title") or "") \
        or utils.parse_volume_cl(body_text)

    url = f"{base}/products/{p.get('handle')}"

    # --- fallback: detailpagina lezen als kernvelden ontbreken ---
    if FETCH_DETAIL_FALLBACK and not tile and (untappd is None or country is None or volume is None):
        if _parse_product.detail_count < MAX_DETAIL_FETCHES:
            _parse_product.detail_count += 1
            html = utils.fetch(url)
            if html:
                utils.save_debug_sample(base.split("//")[1], "productpagina", html)
                soup = BeautifulSoup(html, "html.parser")
                if untappd is None:
                    untappd, untappd_count = utils.parse_untappd_soup(soup)
                if untappd is None:
                    untappd, untappd_count = utils.parse_untappd_html(html)
                text = utils.soup_text(soup)
                if country is None:
                    country = utils.parse_country(text)
                if volume is None:
                    volume = utils.parse_volume_cl(text)
                if abv is None:
                    abv = utils.parse_abv(text)

    # --- Untappd-filter ---
    if untappd is not None and untappd < config.MIN_UNTAPPD:
        REJECT["untappd te laag"] += 1
        _trace(handle, afgewezen=f"untappd te laag ({untappd})")
        return None
    if untappd is None and not config.INCLUDE_UNKNOWN_UNTAPPD:
        REJECT["untappd onbekend"] += 1
        _trace(handle, afgewezen="untappd onbekend")
        return None

    image = None
    images = p.get("images") or []
    if images and isinstance(images[0], dict):
        image = images[0].get("src")

    name = _clean_name(title, vendor)
    _trace(handle, opgenomen=True, stijl=canon, untappd=untappd, prijs=price)
    return {
        "afbeelding": image,
        "brouwerij": vendor,
        "naam": name,
        "inhoud_cl": volume,
        "land": country,
        "abv": abv,
        "stijl": canon,
        "stijl_ruw": style_raw or None,
        "sterke_voorkeur": strong,
        "untappd": untappd,
        "untappd_aantal": untappd_count,
        "prijs": price,
        "weblink": url,
    }


_parse_product.detail_count = 0


def parse_country_from_tags(tags):
    for t in tags:
        c = utils.parse_country(str(t))
        if c:
            return c
    return None


def _clean_name(title, vendor):
    """'Brouwerij X - Biernaam 44cl' -> 'Biernaam'."""
    name = title
    if vendor and name.lower().startswith(vendor.lower()):
        name = name[len(vendor):]
    name = re.sub(r"^[\s\-–|:]+", "", name)
    name = re.sub(r"\b\d{2,4}\s?(cl|ml)\b\.?", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip() or title
