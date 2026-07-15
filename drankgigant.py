# -*- coding: utf-8 -*-
"""
Scraper voor Drankgigant.nl (Magento).
Groot algemeen assortiment (2600+ bieren, vooral Belgisch/Nederlands
klassiek), dus we scrapen gericht via het 'Type bier'-filter: eerst de
precieze categorieën (Imperial Stout, DIPA, Neipa, Gose), daarna de brede
(Stout, IPA, Sour). Tegels tonen naam, prijs (incl. sale) en 'Direct
leverbaar'. Untappd-data heeft deze shop niet; die wordt na het scrapen
geleend van dezelfde bieren bij andere shops (enrichment).

Bieren uit de brede categorieën waarvan ook ná die verrijking geen substijl
bekend is, worden weggelaten (instelling 'drop_unrefined_broad' in config),
zodat dit tabblad niet volloopt met honderden gewone IPA's en stouts.
"""

import logging
import re

from bs4 import BeautifulSoup

import config
import utils

log = logging.getLogger("bierscraper")

# volgorde is belangrijk: precieze categorieën eerst, zodat een bier dat in
# meerdere filters zit de precieze stijl krijgt
TYPE_MAP = [
    ("imperial stout", "Stout - Imperial / Double"),
    ("imperial ipa", "IPA - Imperial / Double"),
    ("dipa", "IPA - Imperial / Double"),
    ("neipa", "IPA - New England / Hazy"),
    ("gose", "Sour - Other Gose"),
    ("stout", "Stout"),
    ("ipa", "IPA"),
    ("sour", "Sour"),
]
MAX_PAGES = 40
RE_PRICE = re.compile(r"(\d{1,3}),\s?(\d{2})\b")
RE_PRODUCT_HREF = re.compile(r"drankgigant\.nl/[a-z0-9\-]+\.html$|^/[a-z0-9\-]+\.html$")
RE_UNAVAILABLE = re.compile(r"uitverkocht|niet leverbaar|sold out", re.IGNORECASE)


def scrape(site):
    listing_html = utils.fetch(site["listing_url"])
    if not listing_html:
        log.warning("Drankgigant: kon %s niet ophalen", site["listing_url"])
        return []
    utils.save_debug_sample(site["key"], "listing", listing_html)

    filters = _discover_type_filters(listing_html, site)
    if not filters:
        log.warning("Drankgigant: geen 'Type bier'-filterlinks gevonden; "
                    "controleer docs/debug/%s-listing.txt", site["key"])
        return []

    beers = {}
    for label, canon_or_broad, url in filters:
        _scrape_type(url, canon_or_broad, beers)
    log.info("Drankgigant: %d bieren na filters", len(beers))
    return list(beers.values())


def _discover_type_filters(html, site):
    """Vind de URL's van de 'Type bier'-filters op de listingpagina."""
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for a in soup.find_all("a", href=True):
        label = utils.norm(a.get_text(" ", strip=True))
        # filterlinks tonen soms 'Stout 100 artikelen'; strip het aantal
        label = re.sub(r"\s*\d+\s*(artikelen|artikel)?$", "", label).strip()
        for type_label, canon in TYPE_MAP:
            if label == type_label and type_label not in found:
                href = a["href"]
                if href.startswith("/"):
                    href = "https://www.drankgigant.nl" + href
                if "drankgigant.nl" in href:
                    found[type_label] = (type_label, canon, href)
    ordered = [found[t] for t, _ in TYPE_MAP if t in found]
    log.info("Drankgigant: filters gevonden: %s", [f[0] for f in ordered])
    return ordered


def _scrape_type(url, canon_or_broad, beers):
    sep = "&" if "?" in url else "?"
    for page in range(1, MAX_PAGES + 1):
        page_url = url if page == 1 else f"{url}{sep}p={page}"
        html = utils.fetch(page_url)
        if not html:
            break
        new = _parse_tiles(html, canon_or_broad, beers)
        if new == 0:
            break


def _parse_tiles(html, canon_or_broad, beers):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup.find_all(["script", "style"]):
        t.decompose()
    new = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not RE_PRODUCT_HREF.search(href):
            continue
        if href.startswith("/"):
            href = "https://www.drankgigant.nl" + href
        if href in beers:
            continue
        name = a.get_text(" ", strip=True)
        if not name or len(name) < 4:
            continue
        container = a
        text = ""
        for _ in range(6):
            container = container.parent
            if container is None:
                break
            text = container.get_text(" ", strip=True)
            if RE_PRICE.search(text) and len(text) < 500:
                break
        else:
            continue
        if container is None or not RE_PRICE.search(text):
            continue
        beer = _parse_tile(name, text, href, canon_or_broad, container)
        if beer:
            beers[href] = beer
            new += 1
    return new


def _parse_tile(name, text, href, canon_or_broad, container=None):
    if RE_UNAVAILABLE.search(text):
        return None

    # prijs: 'Sale 5, 95 6, 95' -> laagste = actieprijs
    prices = [float(f"{m.group(1)}.{m.group(2)}") for m in RE_PRICE.finditer(text)]
    prices = [p for p in prices if 0.5 <= p <= 500]
    price = min(prices) if prices else None

    volume = utils.parse_volume_cl(name) or utils.parse_volume_cl(text)

    # stijl: filtercategorie als basis; naam kan verder verfijnen
    canon = canon_or_broad
    strong = config.STYLES.get(canon, False)
    if canon not in config.STYLES:  # brede categorie -> probeer naamhints
        refined, refined_strong = utils.derive_style([], name)
        if refined and refined in config.STYLES:
            canon, strong = refined, refined_strong

    clean_name = re.sub(r"\b\d{1,3}(?:[.,]\d)?\s?cl\b\.?", "", name, flags=re.IGNORECASE)
    clean_name = re.sub(r"\s+", " ", clean_name).strip()

    return {
        "afbeelding": utils.extract_image(container, "https://www.drankgigant.nl"),
        "brouwerij": None,  # merk zit in de productnaam zelf verwerkt
        "naam": clean_name,
        "inhoud_cl": volume,
        "land": None,
        "abv": None,
        "stijl": canon,
        "stijl_ruw": canon_or_broad,
        "sterke_voorkeur": strong,
        "untappd": None,   # deze shop toont geen Untappd; wordt geleend
        "untappd_aantal": None,
        "prijs": price,
        "weblink": href,
    }
