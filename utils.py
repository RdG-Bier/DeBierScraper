# -*- coding: utf-8 -*-
"""Hulpfuncties: HTTP met cache + rate limiting, parsers en normalisatie."""

import hashlib
import json
import logging
import re
import time
import unicodedata
from pathlib import Path

import requests

import config

log = logging.getLogger("bierscraper")

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

_session = requests.Session()
_session.headers.update({"User-Agent": config.USER_AGENT, "Accept-Language": "nl,en;q=0.8"})
_last_request = [0.0]


def fetch(url, use_cache=True, timeout=25):
    """Haal een URL op, met schijfcache en nette vertraging tussen requests."""
    key = hashlib.md5(url.encode()).hexdigest()
    cache_file = CACHE_DIR / f"{key}.cache"
    if use_cache and config.CACHE_MAX_AGE_HOURS > 0 and cache_file.exists():
        age_h = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_h < config.CACHE_MAX_AGE_HOURS:
            return cache_file.read_text(encoding="utf-8", errors="replace")

    wait = config.REQUEST_DELAY - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    log.info("GET %s", url)
    try:
        resp = _session.get(url, timeout=timeout)
        _last_request[0] = time.time()
        if resp.status_code != 200:
            log.warning("HTTP %s voor %s", resp.status_code, url)
            return None
        text = resp.text
        cache_file.write_text(text, encoding="utf-8")
        return text
    except requests.RequestException as exc:
        log.warning("Request mislukt voor %s: %s", url, exc)
        return None


def fetch_json(url, use_cache=True):
    text = fetch(url, use_cache=use_cache)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("Geen geldige JSON op %s", url)
        return None


# ---------------------------------------------------------------------------
# Normalisatie & stijlen
# ---------------------------------------------------------------------------

def norm(text):
    """Kleine letters, geen accenten/leestekens, enkele spaties."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _style_tokens(style):
    return set(norm(style).split())


_CANON = {s: _style_tokens(s) for s in config.STYLES}


def match_style(raw_style):
    """
    Map een stijl-string van een shop naar een van de gewenste canonieke stijlen.
    Retourneert (canonieke_naam, sterke_voorkeur) of (None, False).
    Werkt op tokenniveau, zodat 'Stout - Imperial / Double Pastry' ook matcht
    als de shop 'Imperial Pastry Stout' schrijft.
    """
    if not raw_style:
        return None, False
    n = norm(raw_style)
    if n in config.STYLE_ALIASES:
        canon = config.STYLE_ALIASES[n]
        return canon, config.STYLES.get(canon, False)

    tokens = set(n.split())
    best, best_score = None, 0.0
    for canon, ctokens in _CANON.items():
        if not ctokens:
            continue
        # Stijlen van één woord (zoals 'Mede') alleen exact matchen: 'mede'
        # is ook een gewoon Nederlands woord en zit in menu's/lopende tekst.
        if len(ctokens) == 1:
            if n == next(iter(ctokens)):
                return canon, config.STYLES.get(canon, False)
            continue
        # canonieke stijl moet (vrijwel) volledig in de shop-stijl zitten
        overlap = len(ctokens & tokens) / len(ctokens)
        if overlap == 1.0:
            # exacte tokenset wint; specifiekere (langere) stijl gaat voor
            score = 1.0 + len(ctokens) / 10.0
            # maar de shop-stijl mag niet véél meer tokens hebben die op een
            # andere canon duiden ('imperial stout' mag niet op 'Stout - Pastry')
            if score > best_score:
                best, best_score = canon, score
    if best:
        return best, config.STYLES.get(best, False)

    # omgekeerde richting: shoplabel is een DEEL van een canonieke stijl
    # ('Stout - Imperial' -> 'Stout - Imperial / Double'); kortste canon wint
    if len(tokens) >= 2:
        candidates = [(canon, ctokens) for canon, ctokens in _CANON.items()
                      if len(ctokens) > 1 and tokens <= ctokens]
        if candidates:
            best = min(candidates, key=lambda x: len(x[1]))[0]
            return best, config.STYLES.get(best, False)
    return None, False


# trefwoorden in naam/omschrijving om een substijl af te leiden
NAME_HINTS = [
    (r"\btipa\b|triple\s+ipa", "IPA - Triple"),
    (r"quadruple\s+ipa|\bqipa\b", "IPA - Quadruple"),
    (r"russian\s+imperial", "Stout - Russian Imperial"),
    (r"imperial\s+pastry\s+stout", "Stout - Imperial / Double Pastry"),
    (r"imperial\s+stout|\bris\b", "Stout - Imperial / Double"),
    (r"pastry\s+stout", "Stout - Pastry"),
    (r"pastry\s+sour|smoothie", "Sour - Smoothie / Pastry"),
    (r"fruited\s+gose", "Sour - Fruited Gose"),
    (r"\bgose\b", "Sour - Other Gose"),
    (r"fruited\s+sour|fruit\s+sour", "Sour - Fruited"),
    (r"\bdipa\b|double\s+ipa|imperial\s+ipa", "IPA - Imperial / Double"),
    (r"\bneipa\b|new\s+england|\bhazy\b", "IPA - New England / Hazy"),
    (r"\bmead\b|\bmede\b|melomel|metheglin|braggot|cyser", "Mede"),
]

# brede families: als een shop alleen 'Stout'/'IPA'/'Sour' als label heeft,
# nemen we het bier mee met die brede stijl (later verfijnd via andere shops)
BROAD_FAMILIES = [
    ("gose", "Sour - Other Gose"), ("mead", "Mede"), ("mede", "Mede"),
    ("stout", "Stout"), ("ipa", "IPA"), ("sour", "Sour"),
]


def derive_style(candidates, name_text=""):
    """Bepaal de stijl: (1) exacte/gedeeltelijke match op stijl-labels,
    (2) trefwoorden in labels+naam, (3) brede familie.
    Retourneert (stijl, sterke_voorkeur) of (None, False)."""
    for c in candidates:
        canon, strong = match_style(c)
        if canon:
            return canon, strong
    searchable = norm(" ".join(str(c) for c in candidates if c) + " " + (name_text or ""))
    for pattern, style in NAME_HINTS:
        if re.search(pattern, searchable):
            canon, strong = match_style(style)
            return (canon or style), strong
    for keyword, family in BROAD_FAMILIES:
        if re.search(rf"\b{keyword}\b", searchable):
            canon, strong = match_style(family)
            if canon:
                return canon, strong
            return family, False
    return None, False


# ---------------------------------------------------------------------------
# Veldparsers (regex op vrije tekst)
# ---------------------------------------------------------------------------

RE_UNTAPPD = re.compile(
    r"untappd[^0-9]{0,25}([0-4][.,]\d{1,3})\s*(?:\(?\s*([\d.,]+)\s*(?:x\s*)?(?:ratings?|beoordelingen)?\)?)?",
    re.IGNORECASE,
)
RE_ABV = re.compile(r"(\d{1,2}(?:[.,]\d{1,2})?)\s?%")
RE_VOLUME = re.compile(r"(\d{2,4}(?:[.,]\d)?)\s?(cl|ml|l)\b", re.IGNORECASE)
RE_PRICE = re.compile(r"€\s*([\d.]{1,6},\d{2}|\d+[.,]\d{2})")


def parse_untappd(text):
    """Zoek 'Untappd 4.21 (332 ratings)' in vrije tekst -> (score, aantal)."""
    if not text:
        return None, None
    m = RE_UNTAPPD.search(text)
    if not m:
        return None, None
    score = float(m.group(1).replace(",", "."))
    count = None
    if m.group(2):
        digits = re.sub(r"[^\d]", "", m.group(2))
        count = int(digits) if digits else None
    return score, count


def parse_abv(text):
    if not text:
        return None
    m = RE_ABV.search(text)
    if m:
        val = float(m.group(1).replace(",", "."))
        if 0 < val <= 60:
            return val
    return None


def parse_volume_cl(text):
    """Inhoud naar centiliters."""
    if not text:
        return None
    m = RE_VOLUME.search(text)
    if not m:
        return None
    val = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    if unit == "ml":
        val /= 10
    elif unit == "l":
        val *= 100
    return round(val, 1) if 1 <= val <= 500 else None


def parse_price(text):
    if not text:
        return None
    m = RE_PRICE.search(text)
    if not m:
        return None
    raw = m.group(1)
    # NL-notatie: 1.234,56 -> 1234.56
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return round(float(raw), 2)
    except ValueError:
        return None


COUNTRY_WORDS = {
    "nederland": "Nederland", "netherlands": "Nederland", "the netherlands": "Nederland",
    "belgie": "België", "belgium": "België", "duitsland": "Duitsland", "germany": "Duitsland",
    "usa": "USA", "verenigde staten": "USA", "united states": "USA", "engeland": "Engeland",
    "england": "Engeland", "uk": "Verenigd Koninkrijk", "united kingdom": "Verenigd Koninkrijk",
    "schotland": "Schotland", "scotland": "Schotland", "polen": "Polen", "poland": "Polen",
    "zweden": "Zweden", "sweden": "Zweden", "noorwegen": "Noorwegen", "norway": "Noorwegen",
    "denemarken": "Denemarken", "denmark": "Denemarken", "spanje": "Spanje", "spain": "Spanje",
    "frankrijk": "Frankrijk", "france": "Frankrijk", "italie": "Italië", "italy": "Italië",
    "estland": "Estland", "estonia": "Estland", "letland": "Letland", "latvia": "Letland",
    "litouwen": "Litouwen", "lithuania": "Litouwen", "finland": "Finland", "ierland": "Ierland",
    "ireland": "Ierland", "canada": "Canada", "roemenie": "Roemenië", "romania": "Roemenië",
    "tsjechie": "Tsjechië", "czech republic": "Tsjechië", "oostenrijk": "Oostenrijk",
    "austria": "Oostenrijk", "hongarije": "Hongarije", "hungary": "Hongarije",
    "zwitserland": "Zwitserland", "switzerland": "Zwitserland", "japan": "Japan",
    "australie": "Australië", "australia": "Australië", "nieuw zeeland": "Nieuw-Zeeland",
    "new zealand": "Nieuw-Zeeland", "brazilie": "Brazilië", "brazil": "Brazilië",
    "oekraine": "Oekraïne", "ukraine": "Oekraïne", "griekenland": "Griekenland",
    "greece": "Griekenland", "slovenie": "Slovenië", "slovenia": "Slovenië",
    "slowakije": "Slowakije", "slovakia": "Slowakije", "portugal": "Portugal",
    "ijsland": "IJsland", "iceland": "IJsland", "mexico": "Mexico", "china": "China",
    "rusland": "Rusland", "russia": "Rusland", "spain": "Spanje",
}


def parse_country(text):
    if not text:
        return None
    n = " " + norm(text) + " "
    # 'New England' is een bierstijl, geen land
    n = n.replace(" new england ", " ")
    for word, country in COUNTRY_WORDS.items():
        if f" {word} " in n:
            return country
    return None


def beer_match_key(brewery, name):
    """Genormaliseerde sleutel om hetzelfde bier tussen shops te matchen."""
    combined = f"{brewery or ''} {name or ''}"
    n = norm(combined)
    # inhoud, verpakking en ruis eruit
    n = re.sub(r"\b\d{2,4}\s?(cl|ml|l)\b", " ", n)
    n = re.sub(r"\b(can|blik|bottle|fles|krat|4 pack|sixpack)\b", " ", n)
    # brouwerij-achtervoegsels: 'White Dog Brewery' moet 'White Dog' matchen
    n = re.sub(r"\b(brewery|brewing(\s+(co|company))?|brew\s+co|craft\s+brewery"
               r"|brouwerij|bierbrouwerij|bryghus|bryggeri|brasserie|birrificio"
               r"|cervejaria|browar|co|company)\b\.?", " ", n)
    return re.sub(r"\s+", " ", n).strip()


# Untappd-score verstopt in ruwe HTML: data-attributen of JSON-blobs,
# bijv. data-untappd-score="4.32", "untappd_rating":4.32, "rating":"4.32"
RE_UNTAPPD_HTML = [
    # geen spaties in de 'gap': alleen attribuut/JSON-context zoals
    # data-untappd-score="4.32" of "untappd_rating":4.15 (voorkomt valse
    # matches in lopende tekst zoals 'untappd hier 3.5 km')
    re.compile(r'untappd[\w\-"\':=]{0,40}?([0-4]\.\d{1,3})', re.IGNORECASE),
    re.compile(r'"untappd[^"]*"\s*:\s*"?([0-4]\.\d{1,3})"?', re.IGNORECASE),
    re.compile(r'data-(?:untappd-)?(?:score|rating)\s*=\s*"([0-4]\.\d{1,3})"', re.IGNORECASE),
]
RE_UNTAPPD_COUNT_HTML = re.compile(
    r"(?:untappd_?count|ratings?_count|review_count|checkin_count"
    r"|(?<![a-z_])count|(?<![a-z_])checkins?|(?<![a-z_])aantal"
    r"|(?<![a-z_])beoordelingen|(?<![a-z_])ratings(?![a-z]))"
    r'["\':= ]{1,5}"?([\d.,]{1,9})',
    re.IGNORECASE,
)


def parse_untappd_html(html):
    """Zoek Untappd-score/aantal in ruwe HTML-broncode (dus incl. attributen
    en ingebedde JSON), als fallback op de zichtbare tekst."""
    if not html:
        return None, None
    score = None
    for pattern in RE_UNTAPPD_HTML:
        m = pattern.search(html)
        if m:
            score = float(m.group(1))
            break
    if score is None:
        return None, None
    count = None
    m = RE_UNTAPPD_COUNT_HTML.search(html)
    if m:
        digits = re.sub(r"[^\d]", "", m.group(1))
        if digits:
            count = int(digits)
    return score, count


_saved_samples = set()


# Score met het AANTAL vóór de score, zoals bij Beerdome en De Biersalon:
# 'Untappd (987 ratings) ..... 4.21'
RE_UNTAPPD_COUNT_FIRST = re.compile(
    r"untappd\D{0,15}\(?\s*([\d.,]{1,9})\s*(?:x\s*)?(?:ratings?|beoordelingen)\)?"
    r"\D{0,200}?([0-4][.,]\d{1,2})",
    re.IGNORECASE | re.DOTALL,
)

# Bekende selector-combinaties per shopthema: (score-selector, count-selector)
UNTAPPD_SELECTORS = [
    (".untappd-score .score", ".untappd-rating-title"),   # Beerdome / Hops & Hopes
    (".score-text", ".aantalr"),                          # De Biersalon
    ("[class*='untappd'] [class*='score']", "[class*='untappd'] [class*='count']"),
]


def parse_untappd_soup(soup):
    """Untappd-score/aantal uit een BeautifulSoup-document, via bekende
    selectors en daarna tekstpatronen. Score 0.0 = nog geen rating = None."""
    for score_sel, count_sel in UNTAPPD_SELECTORS:
        el = soup.select_one(score_sel)
        if not el:
            continue
        m = re.search(r"([0-4][.,]\d{1,2})", el.get_text(" ", strip=True))
        if not m:
            continue
        score = float(m.group(1).replace(",", "."))
        count = None
        cel = soup.select_one(count_sel)
        if cel:
            cm = re.search(r"([\d.,]{1,9})", cel.get_text(" ", strip=True))
            if cm:
                digits = re.sub(r"[^\d]", "", cm.group(1))
                count = int(digits) if digits else None
        if score == 0:
            return None, count
        return score, count

    text = soup_text(soup)
    score, count = parse_untappd(text)
    if score is None:
        m = RE_UNTAPPD_COUNT_FIRST.search(text)
        if m:
            digits = re.sub(r"[^\d]", "", m.group(1))
            count = int(digits) if digits else None
            score = float(m.group(2).replace(",", "."))
    if score == 0:
        score = None
    return score, count


def soup_text(soup):
    """Zichtbare tekst ZONDER script/style-inhoud (die bevatten woorden als
    'Out of stock' in vertaaltabellen en gaven valse voorraad-matches)."""
    for tag in soup.find_all(["script", "style", "noscript", "template"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def save_debug_sample(site_key, name, content):
    """Bewaar één voorbeeldbestand per site in docs/debug/ zodat de ruwe
    bron (HTML/JSON) achteraf te inspecteren is via de GitHub-repository."""
    key = f"{site_key}-{name}"
    if key in _saved_samples or not content:
        return
    _saved_samples.add(key)
    debug_dir = Path(__file__).parent / "docs" / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / f"{key}.txt").write_text(content[:400000], encoding="utf-8", errors="replace")
