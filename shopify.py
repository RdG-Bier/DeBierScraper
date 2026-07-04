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
MAX_DETAIL_FETCHES = 400


def scrape(site):
    base = site["base_url"].rstrip("/")
    beers = []
    page = 1
    while True:
        data = utils.fetch_json(f"{base}/products.json?limit=250&page={page}")
        if not data or not data.get("products"):
            break
        for product in data["products"]:
            beer = _parse_product(product, base)
            if beer:
                beers.append(beer)
        if len(data["products"]) < 250:
            break
        page += 1
        if page > 60:  # noodstop
            break

    log.info("%s: %d producten na stijl/score/voorraad-filter", site["label"], len(beers))
    return beers


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
        return None
    variant = min(available_variants, key=lambda v: float(v.get("price") or 9e9))
    try:
        price = round(float(variant.get("price")), 2)
    except (TypeError, ValueError):
        price = None

    # --- stijl: product_type, anders tags, anders bodytekst ---
    style_raw = product_type
    canon, strong = utils.match_style(style_raw)
    if not canon:
        for t in tags:
            canon, strong = utils.match_style(t)
            if canon:
                style_raw = t
                break
    if not canon:
        return None  # geen gewenste stijl

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
                text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
                if untappd is None:
                    untappd, untappd_count = utils.parse_untappd(text)
                if untappd is None:
                    untappd, untappd_count = utils.parse_untappd_html(html)
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

    name = _clean_name(title, vendor)
    return {
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
