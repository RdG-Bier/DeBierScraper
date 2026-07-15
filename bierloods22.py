# -*- coding: utf-8 -*-
"""
Scraper voor Bierloods22 (Lightspeed, maar met een eigen aanpak).
Deze shop heeft GEEN substijlen of specs op productpagina's; alles staat op
de categorie-tegels: 'Brouwerij - Naam | IPA | Untappd: 4.06 | €7,49'.
Werkwijze:
  1. Relevante stijlcategorieën scrapen (stout, ipa, sour-geuze, mede-mead)
  2. Substijl afleiden via de filterpagina's van de shop (Double, New England,
     Imperial, Pastry, ...) - een bier dat in ipa/double én ipa/new-england
     zit is een 'IPA - Imperial / Double New England / Hazy'
  3. Wat overblijft: substijl raden uit de naam, anders de brede stijl houden
     (die kan later nog verfijnd worden via matching met andere shops)
"""

import logging
import re

from bs4 import BeautifulSoup

import config
import utils

log = logging.getLogger("bierscraper")

CATEGORIES = [
    ("https://www.bierloods22.nl/nl/bieren-stijlen/stout/", "Stout"),
    ("https://www.bierloods22.nl/nl/bieren-stijlen/ipa/", "IPA"),
    ("https://www.bierloods22.nl/nl/bieren-stijlen/sour-geuze/", "Sour"),
    ("https://www.bierloods22.nl/nl/bieren-stijlen/mede-mead/", "Mede"),
]
MAX_PAGES = 40

# (categorie, set van filterlabels) -> canonieke stijl; specifiekste eerst
SUBSTYLE_MAP = [
    ("IPA", {"tripel", "new england"}, "IPA - Triple New England / Hazy"),
    ("IPA", {"triple", "new england"}, "IPA - Triple New England / Hazy"),
    ("IPA", {"double", "new england"}, "IPA - Imperial / Double New England / Hazy"),
    ("IPA", {"tripel"}, "IPA - Triple"),
    ("IPA", {"triple"}, "IPA - Triple"),
    ("IPA", {"milkshake"}, "IPA - Imperial / Double Milkshake"),
    ("IPA", {"double"}, "IPA - Imperial / Double"),
    ("IPA", {"new england"}, "IPA - New England / Hazy"),
    ("Stout", {"imperial", "pastry"}, "Stout - Imperial / Double Pastry"),
    ("Stout", {"imperial"}, "Stout - Imperial / Double"),
    ("Stout", {"pastry"}, "Stout - Pastry"),
    ("Mede", set(), "Mede"),
]

NAME_HINTS = utils.NAME_HINTS

RE_TILE = re.compile(
    r"(?P<stijl>[A-Za-z /\-]{2,30})\s*\|\s*Untappd:\s*(?P<score>[\d.,]+|n\.?n\.?b\.?)",
    re.IGNORECASE,
)


def scrape(site):
    tiles = {}          # href -> tile-dict
    filter_labels = {}  # href -> set(labels)

    for cat_url, broad in CATEGORIES:
        _scrape_category(cat_url, broad, tiles)
        # substijl-filterpagina's van deze categorie volgen
        for label, filter_url in _discover_filters(cat_url):
            hrefs = _collect_hrefs(filter_url)
            for href in hrefs:
                filter_labels.setdefault(href, set()).add(label)

    beers = []
    for href, tile in tiles.items():
        beer = _finalize(tile, filter_labels.get(href, set()))
        if beer:
            beers.append(beer)
    log.info("Bierloods22: %d tegels -> %d bieren na filters", len(tiles), len(beers))
    return beers


def _scrape_category(cat_url, broad, tiles):
    for page in range(1, MAX_PAGES + 1):
        url = f"{cat_url}?limit=72&page={page}"
        html = utils.fetch(url)
        if not html:
            break
        if page == 1:
            utils.save_debug_sample("bierloods22", broad.lower() + "-categorie", html)
        new = _parse_tiles(html, broad)
        fresh = {h: t for h, t in new.items() if h not in tiles}
        tiles.update(fresh)
        if not fresh or len(new) < 5:
            break


def _parse_tiles(html, broad):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup.find_all(["script", "style"]):
        t.decompose()
    found = {}
    for a in soup.find_all("a", href=re.compile(r"bierloods22\.nl/(nl|en)/[^/]+\.html$")):
        href = a["href"]
        if href in found:
            continue
        container = a
        for _ in range(7):
            container = container.parent
            if container is None:
                break
            text = container.get_text(" ", strip=True)
            if "Untappd" in text and "€" in text and len(text) < 800:
                tile = _parse_tile(container, text, href, broad)
                if tile:
                    found[href] = tile
                break
    return found


def _parse_tile(container, text, href, broad):
    if re.search(r"uitverkocht|sold out", text, re.IGNORECASE):
        return None
    m = RE_TILE.search(text)
    score = None
    if m and re.match(r"[\d.,]+$", m.group("score")):
        score = float(m.group("score").replace(",", "."))
        if score == 0:
            score = None

    # titel = langste ankertekst/title-attribuut richting dit product
    candidates = []
    for a in container.find_all("a", href=href):
        candidates.append(a.get_text(" ", strip=True))
        if a.get("title"):
            candidates.append(a["title"])
    for h in container.find_all(["h2", "h3", "h4", "h5"]):
        candidates.append(h.get_text(" ", strip=True))
    candidates = [c for c in candidates if c and "€" not in c]
    title = max(candidates, key=len) if candidates else None
    if title:
        # title-attribuut bevat soms 'Merk Merk - Naam': ontdubbel het merk
        title = re.sub(r"^(.{3,60}?)\s+\1", r"\1", title).strip()
    brewery, name = _split_title(title)
    if not name:
        return None

    return {
        "href": href, "broad": broad, "brouwerij": brewery, "naam": name,
        "afbeelding": utils.extract_image(container, "https://www.bierloods22.nl"),
        "untappd": score, "prijs": utils.parse_price(text),
        "volume": utils.parse_volume_cl(text), "abv": utils.parse_abv(text),
    }


def _split_title(title):
    if not title:
        return None, None
    parts = [p.strip() for p in title.split(" - ", 1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, title


def _discover_filters(cat_url):
    """Vind substijl-filterlinks op de categoriepagina (bijv. .../ipa/double/)."""
    html = utils.fetch(f"{cat_url}?limit=24")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    base_path = re.sub(r"https://[^/]+", "", cat_url).rstrip("/")
    wanted = {"double", "new england", "new-england", "tripel", "triple",
              "milkshake", "imperial", "pastry"}
    filters = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        path = re.sub(r"https://[^/]+", "", href).split("?")[0].rstrip("/")
        if not path.startswith(base_path + "/"):
            continue
        segment = path[len(base_path) + 1:]
        if "/" in segment or not segment:
            continue
        label = segment.replace("-", " ").lower()
        if label in wanted:
            full = href if href.startswith("http") else "https://www.bierloods22.nl" + href
            filters.append((label.replace("new england", "new england"), full))
    # ook checkbox-inputs met een value/URL (thema-afhankelijk)
    if filters:
        log.info("Bierloods22 filters gevonden voor %s: %s", cat_url,
                 [f[0] for f in filters])
    return filters


def _collect_hrefs(filter_url):
    hrefs = set()
    for page in range(1, MAX_PAGES + 1):
        html = utils.fetch(f"{filter_url}?limit=72&page={page}")
        if not html:
            break
        found = re.findall(r'href="(https://www\.bierloods22\.nl/(?:nl|en)/[^"/]+\.html)"', html)
        new = set(found) - hrefs
        hrefs |= new
        if not new:
            break
    return hrefs


def _finalize(tile, labels):
    broad = tile["broad"]
    labels = {l.replace("-", " ") for l in labels}

    canon, strong = None, False
    for cat, needed, style in SUBSTYLE_MAP:
        if cat == broad and needed <= labels and (needed or cat == "Mede"):
            canon = style
            break
    if not canon and tile.get("naam"):
        n = utils.norm(f"{tile.get('brouwerij') or ''} {tile['naam']}")
        for pattern, style in NAME_HINTS:
            if re.search(pattern, n):
                if style.startswith(("Stout", "IPA")) and broad not in ("Stout", "IPA"):
                    continue  # naamhint moet passen bij de categorie
                canon = style
                break
    if canon:
        matched, strong = utils.match_style(canon)
        canon = matched or canon
    else:
        # brede stijl aanhouden; wordt evt. later verfijnd via andere shops
        canon = broad

    # untappd-filter
    u = tile.get("untappd")
    if u is not None and u < config.MIN_UNTAPPD:
        return None
    if u is None and not config.INCLUDE_UNKNOWN_UNTAPPD:
        return None

    return {
        "afbeelding": tile.get("afbeelding"),
        "brouwerij": tile.get("brouwerij"),
        "naam": tile.get("naam"),
        "inhoud_cl": tile.get("volume"),
        "land": None,
        "abv": tile.get("abv"),
        "stijl": canon,
        "stijl_ruw": broad,
        "sterke_voorkeur": strong,
        "untappd": u,
        "untappd_aantal": None,
        "prijs": tile.get("prijs"),
        "weblink": tile["href"],
    }
