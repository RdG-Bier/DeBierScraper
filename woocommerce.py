# -*- coding: utf-8 -*-
"""
Scraper voor WooCommerce-shops (Beerdome, sinds hun overstap naar WordPress).
Gebruikt de publieke Store API: /wp-json/wc/store/v1/products
Die levert gestructureerde JSON met naam, prijs, voorraad, categorieën en
omschrijving. Untappd-score staat daar meestal niet in; daarvoor wordt de
productpagina als fallback gelezen (ruwe HTML, incl. data-attributen).
"""

import logging
import re

from bs4 import BeautifulSoup

import config
import utils

log = logging.getLogger("bierscraper")

FETCH_DETAIL_FALLBACK = True
MAX_DETAIL_FETCHES = 500


def scrape(site):
    beers = []
    page = 1
    detail_count = [0]
    while True:
        url = f"{site['api_url']}?per_page=100&page={page}"
        data = utils.fetch_json(url)
        if page == 1 and data:
            import json
            utils.save_debug_sample(site["key"], "api", json.dumps(data[:3], indent=2, ensure_ascii=False))
        if not data:
            break
        if not isinstance(data, list) or not data:
            break
        for product in data:
            beer = _parse_product(product, site, detail_count)
            if beer:
                beers.append(beer)
        if len(data) < 100:
            break
        page += 1
        if page > 40:
            break
    log.info("%s: %d bieren na filters", site["label"], len(beers))
    return beers


def _parse_product(p, site, detail_count):
    if not p.get("is_in_stock", True):
        return None
    name = BeautifulSoup(p.get("name") or "", "html.parser").get_text(" ", strip=True)
    if not name:
        return None

    categories = [c.get("name", "") for c in (p.get("categories") or [])]
    tags = [t.get("name", "") for t in (p.get("tags") or [])]
    desc = BeautifulSoup(
        (p.get("description") or "") + " " + (p.get("short_description") or ""),
        "html.parser",
    ).get_text(" ", strip=True)

    # --- stijl uit categorieën/tags ---
    style_raw, canon, strong = None, None, False
    for candidate in categories + tags:
        canon, strong = utils.match_style(candidate)
        if canon:
            style_raw = candidate
            break
    if not canon:
        canon, strong = utils.match_style(desc[:200])
        if not canon:
            return None
        style_raw = canon

    # --- prijs (Store API geeft centen als string + currency_minor_unit) ---
    price = None
    prices = p.get("prices") or {}
    raw_price = prices.get("sale_price") or prices.get("price")
    if raw_price:
        try:
            minor = int(prices.get("currency_minor_unit", 2))
            price = round(int(raw_price) / (10 ** minor), 2)
        except (TypeError, ValueError):
            price = utils.parse_price(str(raw_price))

    url = p.get("permalink") or site["base_url"]
    searchable = " ".join([name, desc] + categories + tags)

    untappd, untappd_count = utils.parse_untappd(searchable)
    abv = utils.parse_abv(searchable)
    volume = utils.parse_volume_cl(name) or utils.parse_volume_cl(searchable)
    country = None
    for candidate in categories + tags:
        country = utils.parse_country(candidate)
        if country:
            break
    if not country:
        country = utils.parse_country(desc)

    brewery = None
    brands = p.get("brands") or []
    if brands and isinstance(brands, list):
        brewery = brands[0].get("name") if isinstance(brands[0], dict) else str(brands[0])

    # --- fallback: productpagina lezen voor untappd/brouwerij ---
    if FETCH_DETAIL_FALLBACK and untappd is None and detail_count[0] < MAX_DETAIL_FETCHES:
        detail_count[0] += 1
        html = utils.fetch(url)
        if html:
            utils.save_debug_sample(site["key"], "productpagina", html)
            soup = BeautifulSoup(html, "html.parser")
            # scope naar het hoofdproduct (pagina bevat ook 'related products')
            main = soup.select_one("div.product") or soup
            untappd, untappd_count = utils.parse_untappd_soup(main)
            if untappd is None:
                untappd, untappd_count = utils.parse_untappd_html(html)
            text = utils.soup_text(soup)
            if country is None:
                country = utils.parse_country(text)
            if abv is None:
                abv = utils.parse_abv(text)
            if volume is None:
                volume = utils.parse_volume_cl(text)

    if untappd is not None and untappd < config.MIN_UNTAPPD:
        return None
    if untappd is None and not config.INCLUDE_UNKNOWN_UNTAPPD:
        return None

    return {
        "brouwerij": brewery,
        "naam": _clean_name(name, brewery),
        "inhoud_cl": volume,
        "land": country,
        "abv": abv,
        "stijl": canon,
        "stijl_ruw": style_raw,
        "sterke_voorkeur": strong,
        "untappd": untappd,
        "untappd_aantal": untappd_count,
        "prijs": price,
        "weblink": url,
    }


def _clean_name(name, brewery):
    if brewery and name.lower().startswith(brewery.lower()):
        name = name[len(brewery):]
    name = re.sub(r"^[\s\-–|:]+", "", name)
    name = re.sub(r"\b\d{2,4}\s?(cl|ml)\b\.?", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip() or name
