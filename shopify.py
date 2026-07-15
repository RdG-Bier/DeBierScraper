# -*- coding: utf-8 -*-
"""
Scraper voor Shopify-shops (De Biersalon, Beer Republic).
Gebruikt het publieke /products.json endpoint: gestructureerd en stabiel.
Untappd-gegevens staan vaak in tags of in de productomschrijving (body_html);
ontbreken ze daar, dan wordt (optioneel) de productpagina zelf gelezen.
"""

import logging
import re

from bs4 import BeautifulSoup

import config
import utils

log = logging.getLogger("bierscraper")

# Als score/land niet in products.json staat: productpagina erbij pakken?
FETCH_DETAIL_FALLBACK = True
# Veiligheidslimiet zodat een eerste run niet urenlang detailpagina's trekt.
MAX_DETAIL_FETCHES = 800


def scrape(site):
    base = site["base_url"].rstrip("/")
    _parse_product.detail_count = 0  # budget per shop, niet gedeeld

    # Tegel-data van de collectiepagina (indien geconfigureerd): daar staat de
    # precieze Untappd-stijl + score/aantal die NIET in products.json zitten
    tile_map = _scrape_collection_tiles(site) if site.get("collection_url") else {}

    beers = []
    page = 1
    while True:
        data = utils.fetch_json(f"{base}/products.json?limit=250&page={page}")
        if not data or not data.get("products"):
            break
        for product in data["products"]:
            beer = _parse_product(product, base, tile_map)
            if beer:
                beers.append(beer)
        if len(data["products"]) < 250:
            break
        page += 1
        if page > 60:  # noodstop
            break

    log.info("%s: %d producten na stijl/score/voorraad-filter", site["label"], len(beers))
    return beers


RE_TILE_STYLE = re.compile(r'\[\s*"([^"\]]{3,60})"\s*\]')
RE_TILE_SCORE = re.compile(r"(\d[.,]\d{1,2})\s+([\d.,]+)\s*ratings", re.IGNORECASE)


def _scrape_collection_tiles(site):
    """Lees collectiepagina's en bouw: producthandle -> tegel-info
    (stijl, untappd, aantal, land). Tegels tonen bij De Biersalon de exacte
    Untappd-stijl als ["Stout - Imperial / Double"]."""
    tile_map = {}
    for page in range(1, 90):
        html = utils.fetch(f"{site['collection_url']}?page={page}")
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
        if new == 0 and page > 1:
            break
    log.info("%s: tegel-info voor %d producten", site["label"], len(tile_map))
    return tile_map


def _parse_product(p, base, tile_map=None):
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
        return None
    variant = min(available_variants, key=lambda v: float(v.get("price") or 9e9))
    try:
        price = round(float(variant.get("price")), 2)
    except (TypeError, ValueError):
        price = None

    tile = (tile_map or {}).get(p.get("handle")) or {}

    # --- stijl: tegel-info (exacte Untappd-stijl) > product_type/tags > breed ---
    style_candidates = [c for c in [tile.get("stijl"), product_type] if c] + \
        [str(t) for t in tags]
    canon, strong = utils.derive_style(style_candidates, title)
    if not canon:
        return None  # geen (verwante) doelstijl
    style_raw = tile.get("stijl") or product_type or None

    searchable = " ".join([title, product_type, body_text] + [str(t) for t in tags])

    untappd = tile.get("untappd")
    untappd_count = tile.get("untappd_aantal")
    if untappd is None and "untappd" not in tile:  # geen tegel-info aanwezig
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
        return None
    if untappd is None and not config.INCLUDE_UNKNOWN_UNTAPPD:
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
