# -*- coding: utf-8 -*-
"""
Scraper voor Lightspeed-shops (Bierloods22, Beerdome).
Werkwijze:
  1. sitemap.xml lezen -> alle product-URL's
  2. per productpagina de specificaties parsen (brouwerij, stijl, land, ABV,
     inhoud, Untappd, prijs, voorraad)
De parsing is bewust generiek (spec-tabellen, dt/dd, 'label: waarde'-tekst),
omdat Lightspeed-thema's per shop verschillen. Dankzij de cache worden
productpagina's bij een volgende run niet opnieuw opgehaald binnen
CACHE_MAX_AGE_HOURS.
"""

import logging
import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

import config
import utils

log = logging.getLogger("bierscraper")

LABELS = {
    "brouwerij": ["brouwerij", "brewery", "brouwer"],
    "stijl": ["bierstijl", "stijl", "style", "beer style", "biersoort", "soort"],
    "land": ["land", "country", "land van herkomst", "herkomst"],
    "abv": ["alcohol", "alcoholpercentage", "abv", "alc"],
    "inhoud": ["inhoud", "volume", "content", "size"],
    "untappd": ["untappd", "untappd score", "untappd rating"],
}

OUT_OF_STOCK_MARKERS = [
    "uitverkocht", "niet op voorraad", "out of stock", "sold out",
    "niet leverbaar", "tijdelijk uitverkocht",
]


def scrape(site):
    urls = _product_urls_from_sitemap(site)
    log.info("%s: %d product-URL's in sitemap", site["label"], len(urls))
    beers = []
    for url in urls:
        html = utils.fetch(url)
        if not html:
            continue
        beer = _parse_product_page(html, url)
        if beer:
            beers.append(beer)
    log.info("%s: %d bieren na filters", site["label"], len(beers))
    return beers


def _product_urls_from_sitemap(site):
    xml_text = utils.fetch(site["sitemap_url"])
    if not xml_text:
        return []
    urls = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return []
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    # sitemap-index? Dan onderliggende sitemaps ophalen
    sub_sitemaps = [loc.text for loc in root.findall(".//sm:sitemap/sm:loc", ns)]
    loc_elements = [loc.text for loc in root.findall(".//sm:url/sm:loc", ns)]
    for sub in sub_sitemaps:
        sub_xml = utils.fetch(sub)
        if not sub_xml:
            continue
        try:
            sub_root = ET.fromstring(sub_xml.encode("utf-8"))
            loc_elements += [loc.text for loc in sub_root.findall(".//sm:url/sm:loc", ns)]
        except ET.ParseError:
            continue

    for loc in loc_elements:
        if not loc:
            continue
        # Lightspeed-producten eindigen op .html en zitten niet in service/blog-paden
        if loc.endswith(".html") and not re.search(
            r"/(service|blogs?|nieuws|tags?|brands?|merken|page)\b", loc
        ):
            urls.append(loc.strip())
    return sorted(set(urls))


def _parse_product_page(html, url):
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    lower_text = page_text.lower()

    # --- voorraad ---
    if any(marker in lower_text for marker in OUT_OF_STOCK_MARKERS):
        return None

    specs = _extract_specs(soup)

    # --- stijl ---
    style_raw = specs.get("stijl")
    canon, strong = utils.match_style(style_raw)
    if not canon:
        # fallback: breadcrumb / categorie / titel
        crumbs = " ".join(a.get_text(" ", strip=True) for a in soup.select(".breadcrumb a, .breadcrumbs a, nav a"))
        canon, strong = utils.match_style(crumbs)
        if canon:
            style_raw = style_raw or canon
    if not canon:
        return None

    # --- untappd ---
    untappd, untappd_count = utils.parse_untappd(specs.get("untappd") or "")
    if untappd is None:
        untappd, untappd_count = utils.parse_untappd(page_text)
    if untappd is not None and untappd < config.MIN_UNTAPPD:
        return None
    if untappd is None and not config.INCLUDE_UNKNOWN_UNTAPPD:
        return None

    # --- naam & prijs ---
    h1 = soup.find("h1")
    name = h1.get_text(" ", strip=True) if h1 else None
    if not name:
        return None
    price = None
    price_el = soup.select_one("[class*='price']")
    if price_el:
        price = utils.parse_price(price_el.get_text(" ", strip=True))
    if price is None:
        price = utils.parse_price(page_text)

    brewery = specs.get("brouwerij")
    if not brewery:
        brand = soup.select_one("[class*='brand'] a, [class*='merk'] a")
        if brand:
            brewery = brand.get_text(" ", strip=True)

    abv = utils.parse_abv(specs.get("abv") or "") or utils.parse_abv(page_text)
    volume = utils.parse_volume_cl(specs.get("inhoud") or "") or utils.parse_volume_cl(name) \
        or utils.parse_volume_cl(page_text)
    country = utils.parse_country(specs.get("land") or "") or utils.parse_country(page_text)

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


def _extract_specs(soup):
    """Verzamel 'label -> waarde' uit tabellen, dl-lijsten en losse tekstregels."""
    pairs = {}

    for row in soup.select("table tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            pairs[utils.norm(cells[0].get_text())] = cells[1].get_text(" ", strip=True)

    for dl in soup.select("dl"):
        dts, dds = dl.find_all("dt"), dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            pairs[utils.norm(dt.get_text())] = dd.get_text(" ", strip=True)

    for el in soup.select("li, p, div"):
        text = el.get_text(" ", strip=True)
        if 0 < len(text) < 80 and ":" in text:
            label, _, value = text.partition(":")
            if value.strip():
                pairs.setdefault(utils.norm(label), value.strip())

    result = {}
    for field, keywords in LABELS.items():
        for kw in keywords:
            if kw in pairs:
                result[field] = pairs[kw]
                break
    return result


def _clean_name(name, brewery):
    if brewery and name.lower().startswith(brewery.lower()):
        name = name[len(brewery):]
    name = re.sub(r"^[\s\-–|:]+", "", name)
    name = re.sub(r"\b\d{2,4}\s?(cl|ml)\b\.?", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip()
