# -*- coding: utf-8 -*-
"""
Koppeling met een Untappd-account: welke bieren heb je al gehad (groen) en
welke staan op je voorraadlijsten (geel)?

BELANGRIJK: Untappd zet sinds enige tijd een inlogmuur voor profielpagina's.
Ook bij een openbaar profiel krijgt een script alleen "You must log in to
continue" te zien. Er zijn daarom twee werkende routes, in deze volgorde:

  1. OFFICIELE API (aanbevolen). Zet in GitHub twee secrets:
       UNTAPPD_CLIENT_ID en UNTAPPD_CLIENT_SECRET
     Aanvragen via https://untappd.com/api/register (gratis, persoonlijk).
  2. SESSIECOOKIE. Log in op untappd.com in een browser, kopieer de waarde
     van de cookie 'untappd_user_v3_e' en zet die in het secret
       UNTAPPD_COOKIE
     Werkt direct, maar verloopt na verloop van tijd.

Zonder een van beide blijft de markering leeg; je kunt dan nog altijd
handmatig lijsten plakken in het paneel "Mijn Untappd" op de website.

Resultaten staan in docs/untappd_profiel.json en worden samengevoegd met
eerdere runs, zodat een mislukte run nooit data weggooit.
"""

import json
import logging
import os
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

import config
import utils

log = logging.getLogger("bierscraper")

CACHE_FILE = Path(__file__).parent / "docs" / "untappd_profiel.json"
BASIS = "https://untappd.com"
API = "https://api.untappd.com/v4"
STAP_HTML = 25
STAP_API = 50
VERTRAGING = 1.0
RE_BEER = re.compile(r"^/b/[^/]+/(\d+)")
RE_BREWERY = re.compile(r"^/w/")


def synchroniseer(all_beers):
    gebruiker = getattr(config, "UNTAPPD_USER", "")
    if not gebruiker:
        return
    bewaard = _laad_cache()
    lijstnamen = getattr(config, "UNTAPPD_VOORRAAD_LIJSTEN", ())

    cid = os.environ.get("UNTAPPD_CLIENT_ID", "").strip()
    secret = os.environ.get("UNTAPPD_CLIENT_SECRET", "").strip()
    cookie = os.environ.get("UNTAPPD_COOKIE", "").strip()

    gehad, voorraad, methode = {}, {}, "geen"
    if cid and secret:
        methode = "api"
        gehad, voorraad = _via_api(gebruiker, lijstnamen, cid, secret)
    elif cookie:
        methode = "cookie"
        gehad, voorraad = _via_html(gebruiker, lijstnamen, cookie)
    else:
        log.warning("Untappd-profiel: geen API-sleutels en geen cookie ingesteld. "
                    "Untappd vereist inloggen voor profielpagina's, dus de "
                    "markering blijft leeg. Zie untappd_profiel.py voor uitleg.")

    if gehad:
        bewaard["gehad"] = _samenvoegen(bewaard.get("gehad"), gehad)
    if voorraad:
        bewaard["voorraad"] = voorraad
    bewaard["methode"] = methode
    bewaard["bijgewerkt"] = time.strftime("%Y-%m-%d %H:%M")
    _bewaar_cache(bewaard)
    _markeer(all_beers, bewaard)


# ---------------------------------------------------------------------------
# Route 1: officiele API
# ---------------------------------------------------------------------------

def _api_url(pad, cid, secret, **params):
    delen = [f"client_id={cid}", f"client_secret={secret}"]
    delen += [f"{k}={v}" for k, v in params.items()]
    return f"{API}/{pad}?" + "&".join(delen)


def _via_api(gebruiker, lijstnamen, cid, secret):
    gehad = {}
    offset = 0
    for _ in range(getattr(config, "UNTAPPD_MAX_PAGINAS", 120)):
        data = utils.fetch_json(_api_url(f"user/beers/{gebruiker}", cid, secret,
                                         limit=STAP_API, offset=offset),
                                use_cache=False)
        if not data:
            break
        nieuw = _uit_json(data, gehad)
        if nieuw == 0:
            break
        offset += STAP_API
        time.sleep(VERTRAGING)
    log.info("Untappd-API: %d ingecheckte bieren voor %s", len(gehad), gebruiker)

    voorraad = {}
    lijsten = utils.fetch_json(_api_url(f"user/lists/{gebruiker}", cid, secret),
                               use_cache=False)
    ids = _lijst_ids(lijsten, lijstnamen)
    if not ids and lijstnamen:
        log.warning("Untappd-API: voorraadlijsten %s niet gevonden", ", ".join(lijstnamen))
    for naam, lijst_id in ids.items():
        offset = 0
        aantal_voor = len(voorraad)
        for _ in range(60):
            data = utils.fetch_json(_api_url(f"list/details/{lijst_id}", cid, secret,
                                             limit=STAP_API, offset=offset),
                                    use_cache=False)
            if not data or _uit_json(data, voorraad) == 0:
                break
            offset += STAP_API
            time.sleep(VERTRAGING)
        log.info("  lijst '%s': %d bieren", naam, len(voorraad) - aantal_voor)
    return gehad, voorraad


def _lijst_ids(data, lijstnamen):
    """Zoek de list_id's van de gewenste lijsten in het API-antwoord."""
    gewenst = {utils.norm(n): n for n in lijstnamen}
    gevonden = {}

    def loop(obj):
        if isinstance(obj, dict):
            naam = obj.get("list_name") or obj.get("name")
            lid = obj.get("list_id") or obj.get("id")
            if naam and lid:
                sleutel = utils.norm(str(naam))
                for g, origineel in gewenst.items():
                    if sleutel == g:
                        gevonden.setdefault(origineel, lid)
            for v in obj.values():
                loop(v)
        elif isinstance(obj, list):
            for v in obj:
                loop(v)

    loop(data or {})
    return gevonden


def _uit_json(data, doel):
    """Haal alle (brouwerij, bier)-combinaties uit een API-antwoord. Werkt op
    elke vorm, zodat kleine verschillen tussen endpoints niet uitmaken."""
    nieuw = 0

    def loop(obj, brouwerij=""):
        nonlocal nieuw
        if isinstance(obj, dict):
            eigen_brouwerij = brouwerij
            br = obj.get("brewery")
            if isinstance(br, dict) and br.get("brewery_name"):
                eigen_brouwerij = br["brewery_name"]
            elif obj.get("brewery_name"):
                eigen_brouwerij = obj["brewery_name"]
            naam = obj.get("beer_name")
            if naam:
                sleutel = utils.beer_match_key(eigen_brouwerij, naam)
                if sleutel and sleutel not in doel:
                    doel[sleutel] = f"{eigen_brouwerij} - {naam}".strip(" -")
                    nieuw += 1
            for v in obj.values():
                loop(v, eigen_brouwerij)
        elif isinstance(obj, list):
            for v in obj:
                loop(v, brouwerij)

    loop(data or {})
    return nieuw


# ---------------------------------------------------------------------------
# Route 2: HTML met sessiecookie
# ---------------------------------------------------------------------------

def _cookie_headers(cookie):
    waarde = cookie if "=" in cookie else f"untappd_user_v3_e={cookie}"
    return {"Cookie": waarde, "User-Agent": utils.BROWSER_UA}


def _via_html(gebruiker, lijstnamen, cookie):
    kop = _cookie_headers(cookie)
    gehad = _html_bierlijst(f"{BASIS}/user/{gebruiker}/beers", "gehad", kop)
    if not gehad:
        log.warning("Untappd-cookie werkt niet (of is verlopen): geen bieren opgehaald")
        return {}, {}

    voorraad = {}
    html = utils.fetch(f"{BASIS}/user/{gebruiker}/lists", use_cache=False, headers=kop)
    if html:
        utils.save_debug_sample("untappd", "profiel-lijsten", html)
        soup = BeautifulSoup(html, "html.parser")
        gewenst = {utils.norm(n): n for n in lijstnamen}
        for a in soup.find_all("a", href=True):
            tekst = utils.norm(a.get_text(" ", strip=True))
            if tekst in gewenst:
                url = a["href"]
                if url.startswith("/"):
                    url = BASIS + url
                gevonden = _html_bierlijst(url, f"lijst-{tekst}", kop)
                log.info("  lijst '%s': %d bieren", gewenst[tekst], len(gevonden))
                voorraad.update(gevonden)
    return gehad, voorraad


def _html_bierlijst(url, naam, kop):
    gevonden = {}
    for i in range(getattr(config, "UNTAPPD_MAX_PAGINAS", 120)):
        offset = i * STAP_HTML
        pagina = url if offset == 0 else f"{url}?offset={offset}"
        html = utils.fetch(pagina, use_cache=False, headers=kop)
        if not html:
            break
        if i == 0:
            utils.save_debug_sample("untappd", f"profiel-{naam}", html)
            if "must log in" in html.lower():
                log.warning("Untappd: inlogmuur - cookie ontbreekt of is verlopen")
                return {}
        if _parse_bieren(html, gevonden) == 0:
            break
        time.sleep(VERTRAGING)
    log.info("Untappd-HTML: %d bieren in '%s'", len(gevonden), naam)
    return gevonden


def _parse_bieren(html, gevonden):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup.find_all(["script", "style"]):
        t.decompose()
    nieuw = 0
    for link in soup.find_all("a", href=RE_BEER):
        naam = link.get_text(" ", strip=True)
        if not naam or len(naam) < 2:
            continue
        brouwerij = ""
        houder = link
        for _ in range(5):
            houder = houder.parent
            if houder is None:
                break
            b = houder.find("a", href=RE_BREWERY)
            if b:
                brouwerij = b.get_text(" ", strip=True)
                break
        sleutel = utils.beer_match_key(brouwerij, naam)
        if not sleutel or sleutel in gevonden:
            continue
        gevonden[sleutel] = f"{brouwerij} - {naam}".strip(" -")
        nieuw += 1
    return nieuw


# ---------------------------------------------------------------------------
# Markeren + cache
# ---------------------------------------------------------------------------

def _markeer(all_beers, bewaard):
    gehad = bewaard.get("gehad") or {}
    voorraad = bewaard.get("voorraad") or {}
    n_gehad = n_voorraad = 0
    for bieren in all_beers.values():
        for b in bieren:
            sleutel = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            naam_sleutel = utils.beer_match_key(None, b.get("naam"))
            if sleutel in gehad or (len(naam_sleutel) >= 8 and naam_sleutel in gehad):
                b["gehad"] = True
                n_gehad += 1
            if sleutel in voorraad or (len(naam_sleutel) >= 8 and naam_sleutel in voorraad):
                b["voorraad"] = True
                n_voorraad += 1
    if gehad or voorraad:
        log.info("Untappd: %d bieren gemarkeerd als 'gehad', %d als 'voorraad'",
                 n_gehad, n_voorraad)


def _samenvoegen(oud, nieuw):
    samen = dict(oud or {})
    samen.update(nieuw or {})
    return samen


def _laad_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _bewaar_cache(data):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
