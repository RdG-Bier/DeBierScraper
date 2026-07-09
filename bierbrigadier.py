# -*- coding: utf-8 -*-
"""
Scraper voor De Bierbrigadier (Tilburg).
Belangrijk: dit leest NIET hun eigen website, maar hun officiële Untappd-
menupagina (untappd.com/v/de-bierbrigadier-tilburg/...). Untappd toont daar
het actuele winkelaanbod inclusief prijzen, per categorie gegroepeerd - en
gebruikt daarbij hun eigen, exacte bierstijl-taxonomie, wat de matching juist
extra betrouwbaar maakt (geen aliassen nodig, de naam staat er al precies zo).

Let op: Untappd kan geautomatiseerd verkeer vanaf cloud-IP's (zoals GitHub
Actions) blokkeren, ook als het via andere kanalen wel toegankelijk is.
Controleer bij de eerste run docs/raw_bierbrigadier.json; blijft die leeg,
dan blokkeert Untappd het verzoek en is een aangepaste aanpak nodig.
"""

import logging
import re

from bs4 import BeautifulSoup

import config
import utils

log = logging.getLogger("bierscraper")

RE_BEER_HREF = re.compile(r"^/b/[a-z0-9\-]+/\d+/?$")
RE_BREWERY_HREF = re.compile(r"^/w/[a-z0-9\-]+/\d+/?$")
RE_ABV = re.compile(r"([\d.,]+)\s?%\s*ABV", re.IGNORECASE)
RE_SERVING = re.compile(r"([\d.,]+)\s?(cl|ml)\s+([A-Za-z]+)\s+([\d.,]+)\s*EUR", re.IGNORECASE)
RE_SCORE = re.compile(r"\(([\d.,]+|N/?A)\)")
MAX_CONTAINER_CHARS = 450  # voorkomt dat we per ongeluk een hele lijst pakken


def scrape(site):
    html = utils.fetch(site["menu_url"])
    if not html:
        log.warning("Bierbrigadier: kon Untappd-menupagina niet ophalen")
        return []
    utils.save_debug_sample(site["key"], "untappd-menu", html)

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    beers = []
    seen = set()
    for a in soup.find_all("a", href=RE_BEER_HREF):
        href = a["href"].rstrip("/")
        if href in seen:
            continue
        seen.add(href)
        beer = _parse_item(a, href)
        if beer:
            beers.append(beer)

    log.info("Bierbrigadier: %d bier-links op de menupagina, %d na filters",
              len(seen), len(beers))
    return beers


def _parse_item(anchor, href):
    # Klim omhoog tot de container zowel 'ABV' als 'EUR' bevat, met een
    # lengtelimiet zodat we niet per ongeluk een hele sectie/lijst grijpen.
    container = anchor
    text = ""
    for _ in range(6):
        container = container.parent
        if container is None:
            return None
        text = container.get_text(" ", strip=True)
        if len(text) > MAX_CONTAINER_CHARS:
            return None
        if "ABV" in text and "EUR" in text:
            break
    else:
        return None

    name = anchor.get_text(" ", strip=True)
    if not name:
        return None

    # Stijl: eerst de exacte Untappd-taxonomie herkennen in de tekst (zeer
    # betrouwbaar, dit IS de bron van die taxonomie), anders structureel
    # (cursieve tekst direct na de naam), anders opgeven.
    canon = utils.find_style_in_text(text)
    style_raw = canon
    if not canon:
        style_el = anchor.find_next(["em", "i"])
        if style_el:
            style_raw = style_el.get_text(" ", strip=True)
            canon, _ = utils.match_style(style_raw)
    if not canon:
        return None
    strong = config.STYLES.get(canon, False)

    brewery = None
    b_link = container.find("a", href=RE_BREWERY_HREF)
    if b_link:
        brewery = b_link.get_text(" ", strip=True)

    abv = None
    m = RE_ABV.search(text)
    if m:
        try:
            abv = float(m.group(1).replace(",", "."))
        except ValueError:
            abv = None

    untappd = None
    sm_score = RE_SCORE.search(text)
    if sm_score:
        raw = sm_score.group(1)
        if raw.upper().replace("/", "") != "NA":
            try:
                untappd = float(raw.replace(",", "."))
                if untappd == 0:
                    untappd = None
            except ValueError:
                untappd = None

    volume = price = None
    sv = RE_SERVING.search(text)
    if sv:
        try:
            volume = float(sv.group(1).replace(",", "."))
            if sv.group(2).lower() == "ml":
                volume /= 10
        except ValueError:
            volume = None
        try:
            price = round(float(sv.group(4).replace(",", ".")), 2)
        except ValueError:
            price = None

    if untappd is not None and untappd < config.MIN_UNTAPPD:
        return None
    if untappd is None and not config.INCLUDE_UNKNOWN_UNTAPPD:
        return None

    return {
        "brouwerij": brewery,
        "naam": name,
        "inhoud_cl": volume,
        "land": None,  # niet vermeld op de Untappd-menupagina
        "abv": abv,
        "stijl": canon,
        "stijl_ruw": style_raw,
        "sterke_voorkeur": strong,
        "untappd": untappd,
        "untappd_aantal": None,  # aantal ratings staat niet op deze pagina
        "prijs": price,
        "weblink": f"https://untappd.com{href}",
    }
