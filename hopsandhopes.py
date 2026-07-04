# -*- coding: utf-8 -*-
"""
Scraper voor Hops & Hopes (maatwerkwebsite).
Op de listingpagina staat per bier al alles: stijl, land, ABV, inhoud,
Untappd-score + aantal ratings en prijs, in het patroon:
    'Stout - Imperial / Double · USA - 13.6% - 35,5 cl Untappd 4.21 (332 x ratings) € 22,50'
We parsen daarom de productkaarten van /bieren, met paginering.
"""

import logging
import re

from bs4 import BeautifulSoup

import config
import utils

log = logging.getLogger("bierscraper")

MAX_PAGES = 80


def scrape(site):
    beers = []
    seen_links = set()
    for page in range(1, MAX_PAGES + 1):
        url = site["listing_url"] if page == 1 else f"{site['listing_url']}?page={page}"
        html = utils.fetch(url)
        if not html:
            break
        if page == 1:
            utils.save_debug_sample(site["key"], "listing", html)
        page_beers = _parse_listing(html, site["base_url"])
        new = [b for b in page_beers if b["weblink"] not in seen_links]
        if not new:
            break
        for b in new:
            seen_links.add(b["weblink"])
        beers.extend(new)
    log.info("%s: %d bieren na filters", site["label"], len(beers))
    return beers


def _parse_listing(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    beers = []

    # Werkelijke kaartstructuur (uit debug-sample):
    # <div class="beer-item"> <h4>Brouwerij</h4> <h3>Biernaam</h3>
    #   <p>Stijl</p> <p>Land - ABV% - Inhoud</p>
    #   <strong>Untappd <span class="score">4.53</span> (345 ratings)</strong>
    cards = soup.select(".beer-item")
    if cards:
        for el in cards:
            beer = _parse_beer_item(el, base_url)
            if beer:
                beers.append(beer)
    else:
        # fallback: generieke aanpak voor het geval het thema ooit wijzigt
        for el in soup.find_all(["article", "li", "div"], recursive=True):
            text = el.get_text(" ", strip=True)
            if "untappd" not in text.lower() or "€" not in text:
                continue
            if text.lower().count("untappd") > 1:
                continue
            link = el.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if href.startswith("/"):
                href = base_url.rstrip("/") + href
            if not href.startswith("http"):
                continue
            beer = _parse_card(el, text, href)
            if beer:
                beers.append(beer)

    unique = {}
    for b in beers:
        unique.setdefault(b["weblink"], b)
    return list(unique.values())


def _parse_beer_item(el, base_url):
    text = el.get_text(" ", strip=True)
    if RE_UITVERKOCHT.search(text):
        return None

    link = el.find("a", href=True)
    if not link:
        return None
    href = link["href"]
    if href.startswith("/"):
        href = base_url.rstrip("/") + href

    brewery_el = el.find("h4")
    name_el = el.find("h3")
    brewery = brewery_el.get_text(" ", strip=True) if brewery_el else None
    name = name_el.get_text(" ", strip=True) if name_el else None
    if not name:
        return None

    # stijl: eerste <p> in .beer-info
    style_raw = None
    for p in el.find_all("p"):
        candidate = p.get_text(" ", strip=True)
        canon, strong = utils.match_style(candidate)
        if canon:
            style_raw = candidate
            break
    else:
        canon, strong = None, False
    if not canon:
        return None

    untappd, untappd_count = utils.parse_untappd(text)
    if untappd is not None and untappd < config.MIN_UNTAPPD:
        return None
    if untappd is None and not config.INCLUDE_UNKNOWN_UNTAPPD:
        return None

    prices = [utils.parse_price(p) for p in re.findall(r"€\s*[\d.,]+", text)]
    prices = [p for p in prices if p]

    return {
        "brouwerij": brewery,
        "naam": name,
        "inhoud_cl": utils.parse_volume_cl(text),
        "land": utils.parse_country(text),
        "abv": utils.parse_abv(text),
        "stijl": canon,
        "stijl_ruw": style_raw,
        "sterke_voorkeur": strong,
        "untappd": untappd,
        "untappd_aantal": untappd_count,
        "prijs": min(prices) if prices else None,
        "weblink": href,
    }


RE_STYLE_LINE = re.compile(
    r"((?:Stout|IPA|Sour|Mead|Mede|Porter|Barleywine|Lager|Pilsner|Wild Ale|Saison)"
    r"(?:\s*-\s*[A-Za-z/ ]+)?)"
)
RE_UITVERKOCHT = re.compile(r"uitverkocht|sold out|niet op voorraad", re.IGNORECASE)


def _parse_card(el, text, href):
    if RE_UITVERKOCHT.search(text):
        return None

    style_m = RE_STYLE_LINE.search(text)
    style_raw = style_m.group(1).strip() if style_m else None
    canon, strong = utils.match_style(style_raw)
    if not canon:
        return None

    untappd, untappd_count = utils.parse_untappd(text)
    if untappd is not None and untappd < config.MIN_UNTAPPD:
        return None
    if untappd is None and not config.INCLUDE_UNKNOWN_UNTAPPD:
        return None

    # naam: heading in de kaart, anders linktekst
    name_el = el.find(["h2", "h3", "h4"])
    name = name_el.get_text(" ", strip=True) if name_el else el.find("a").get_text(" ", strip=True)
    if not name:
        return None

    # brouwerij staat bij Hops & Hopes vaak als aparte regel/element boven de naam
    brewery = None
    brewery_el = el.find(class_=re.compile(r"brand|brouwerij|brewery", re.IGNORECASE))
    if brewery_el:
        brewery = brewery_el.get_text(" ", strip=True)

    # prijs: laagste bedrag in de kaart is de actuele (sale)prijs
    prices = [utils.parse_price(p) for p in re.findall(r"€\s*[\d.,]+", text)]
    prices = [p for p in prices if p]
    price = min(prices) if prices else None

    return {
        "brouwerij": brewery,
        "naam": name,
        "inhoud_cl": utils.parse_volume_cl(text),
        "land": utils.parse_country(text),
        "abv": utils.parse_abv(text),
        "stijl": canon,
        "stijl_ruw": style_raw,
        "sterke_voorkeur": strong,
        "untappd": untappd,
        "untappd_aantal": untappd_count,
        "prijs": price,
        "weblink": href,
    }
