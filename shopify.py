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
# Telt per reden hoeveel producten zijn afgewezen (voor de diagnose-file)
REJECT = collections.Counter()


def scrape(site):
    base = site["base_url"].rstrip("/")
    _parse_product.detail_count = 0  # budget per shop, niet gedeeld
    REJECT.clear()

    # Bron 1: de hoofdfeed met alle producten.
    # Bron 2: de JSON-feed per collectie. Nodig als vangnet, want gebleken is
    # dat de hoofdfeed soms producten mist (bijv. het Arpus QDH-bier dat wel
    # gewoon op voorraad in de Triple IPA-collectie staat). Collectie-feeds
    # zijn standaard Shopify-endpoints en kosten maar een paar requests.
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
        beer = _parse_product(product, base)
        if beer:
            beers.append(beer)

    log.info("%s: %d bieren na stijl/score/voorraad-filter (afgewezen: %s)",
             site["label"], len(beers), dict(REJECT))
    _write_diagnose(site, len(products), beers, herkomst)
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


def _write_diagnose(site, aantal_producten, beers, herkomst):
    """Klein overzicht per run in docs/, handig om te zien of er iets mist."""
    try:
        path = Path(__file__).parent / "docs" / f"diagnose_{site['key']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "producten_gevonden": aantal_producten,
            "bieren_na_filter": len(beers),
            "bronnen": herkomst,
            "afgewezen": dict(REJECT),
        }, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _parse_product(p, base):
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
    if not available_variants:
        REJECT["niet op voorraad"] += 1
        return None
    variant = min(available_variants, key=lambda v: float(v.get("price") or 9e9))
    try:
        price = round(float(variant.get("price")), 2)
    except (TypeError, ValueError):
        price = None

    # --- stijl: product_type (bevat bij De Biersalon de exacte Untappd-stijl),
    #     anders tags, anders een brede stijl uit de titel ---
    style_candidates = ([product_type] if product_type else []) + [str(t) for t in tags]
    canon, strong = utils.derive_style(style_candidates, title)
    if not canon:
        REJECT["geen doelstijl"] += 1
        return None
    style_raw = product_type or None

    searchable = " ".join([title, product_type, body_text] + [str(t) for t in tags])

    untappd, untappd_count = utils.parse_untappd(searchable)
    country = parse_country_from_tags(tags) or utils.parse_country(searchable)
    abv = utils.parse_abv(variant.get("title") or "") or utils.parse_abv(searchable)
    volume = utils.parse_volume_cl(title) or utils.parse_volume_cl(variant.get("title") or "") \
        or utils.parse_volume_cl(body_text)

    url = f"{base}/products/{p.get('handle')}"

    # --- fallback: detailpagina lezen als kernvelden ontbreken ---
    if FETCH_DETAIL_FALLBACK and (untappd is None or country is None or volume is None):
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
        return None
    if untappd is None and not config.INCLUDE_UNKNOWN_UNTAPPD:
        REJECT["untappd onbekend"] += 1
        return None

    image = None
    images = p.get("images") or []
    if images and isinstance(images[0], dict):
        image = images[0].get("src")

    name = _clean_name(title, vendor)
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
