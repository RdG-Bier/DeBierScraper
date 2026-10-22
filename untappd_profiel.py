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
BESTAND_GEHAD = Path(__file__).parent / "mijn_untappd" / "gehad.txt"
# Twee aparte voorraadlijsten: R (eigen) en H&R (gezamenlijk). De oude
# voorraad.txt wordt nog meegelezen als hij bestaat, zodat niets verdwijnt.
BESTAND_VOORRAAD_R = Path(__file__).parent / "mijn_untappd" / "voorraad_r.txt"
BESTAND_VOORRAAD_HR = Path(__file__).parent / "mijn_untappd" / "voorraad_hr.txt"
BESTAND_VOORRAAD_OUD = Path(__file__).parent / "mijn_untappd" / "voorraad.txt"
BASIS = "https://untappd.com"
API = "https://api.untappd.com/v4"
STAP_HTML = 25
STAP_API = 50
VERTRAGING = 1.0
RE_BEER = re.compile(r"^/b/[^/]+/(\d+)")
RE_BREWERY = re.compile(r"^/w/")


def synchroniseer(all_beers):
    """Markeert de bieren op basis van drie handmatige lijsten in de repository:
    gehad.txt (groen), voorraad_r.txt en voorraad_hr.txt (beide geel, maar met
    eigen label). De lijsten worden gevuld via de 'Lijsten inlezen'-pagina of
    de browser-extensie. De online Untappd-routes (API/cookie) zijn vervallen
    omdat Untappd profielpagina's achter een inlogmuur zet."""
    gehad = _lees_bestand(BESTAND_GEHAD)
    voorraad_r = _lees_bestand(BESTAND_VOORRAAD_R)
    voorraad_hr = _lees_bestand(BESTAND_VOORRAAD_HR)
    # oude losse voorraad.txt: meenemen in R, zodat bestaande data niet verdwijnt
    for sl, naam in _lees_bestand(BESTAND_VOORRAAD_OUD).items():
        voorraad_r.setdefault(sl, naam)

    log.info("Untappd-lijsten: %d gehad, %d voorraad R, %d voorraad H&R",
             len(gehad), len(voorraad_r), len(voorraad_hr))

    _markeer(all_beers, gehad, voorraad_r, voorraad_hr)

    # resultaat bewaren voor de webpagina (teller + eventuele latere routes)
    _bewaar_cache({
        "methode": "bestand",
        "bijgewerkt": time.strftime("%Y-%m-%d %H:%M"),
        "aantal_gehad": len(gehad),
        "aantal_voorraad_r": len(voorraad_r),
        "aantal_voorraad_hr": len(voorraad_hr),
    })


def _markeer(all_beers, gehad, voorraad_r, voorraad_hr):
    gehad_naam = _naam_index(gehad)
    r_naam = _naam_index(voorraad_r)
    hr_naam = _naam_index(voorraad_hr)
    n_gehad = n_r = n_hr = 0

    for bieren in all_beers.values():
        for b in bieren:
            sleutel = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            naam_sleutel = utils.beer_match_key(None, b.get("naam"))

            is_gehad = sleutel in gehad or naam_sleutel in gehad_naam
            is_r = sleutel in voorraad_r or naam_sleutel in r_naam
            is_hr = sleutel in voorraad_hr or naam_sleutel in hr_naam

            if is_gehad:
                b["gehad"] = True
                n_gehad += 1
            # "check-in wint van voorraad": een bier dat je al gedronken hebt
            # telt niet meer als voorraad, ook al staat het nog op een lijst.
            # Zo hoef je je voorraadlijst niet handmatig op te schonen.
            if is_r and not is_gehad:
                b["voorraad_r"] = True
                b["voorraad"] = True
                n_r += 1
            if is_hr and not is_gehad:
                b["voorraad_hr"] = True
                b["voorraad"] = True
                n_hr += 1

    log.info("Untappd: %d gehad gemarkeerd, %d voorraad R, %d voorraad H&R "
             "(check-ins gaan voor op voorraad)", n_gehad, n_r, n_hr)


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

def _naam_index(bron):
    """Extra index op alleen de biernaam, voor shops die de brouwerij anders
    (of helemaal niet) vermelden. Alleen bij namen van voldoende lengte,
    anders zou 'Velvet' ook 'Bistro Raspberry Velvet' kunnen raken."""
    index = {}
    for waarde in (bron or {}).values():
        deel = str(waarde).split(" - ", 1)
        naam = deel[1] if len(deel) == 2 else deel[0]
        sleutel = utils.beer_match_key(None, naam)
        if len(sleutel) >= 8:
            index[sleutel] = waarde
    return index



def _lees_bestand(pad):
    """Lees een handmatige lijst: 'Brouwerij - Bier' per regel, of een
    Untappd CSV-export met een kolom beer_name (+ brewery_name)."""
    if not pad.exists():
        return {}
    try:
        regels = [r.strip() for r in pad.read_text(encoding="utf-8").splitlines()]
    except OSError:
        return {}
    regels = [r for r in regels if r and not r.startswith("#")]
    if not regels:
        return {}
    gevonden = {}
    if "beer_name" in regels[0].lower():
        kolommen = _split_csv(regels[0])
        i_bier = kolommen.index("beer_name") if "beer_name" in kolommen else -1
        i_brouw = kolommen.index("brewery_name") if "brewery_name" in kolommen else -1
        for regel in regels[1:]:
            velden = _split_csv(regel)
            _voeg_toe(gevonden,
                      velden[i_brouw] if 0 <= i_brouw < len(velden) else "",
                      velden[i_bier] if 0 <= i_bier < len(velden) else "")
    else:
        for regel in regels:
            brouw, _, naam = regel.partition(" - ")
            if not naam:
                brouw, naam = "", regel
            _voeg_toe(gevonden, brouw, naam)
    return gevonden


def _voeg_toe(doel, brouwerij, naam):
    naam = (naam or "").strip()
    if len(naam) < 2:
        return
    sleutel = utils.beer_match_key(brouwerij, naam)
    if sleutel:
        doel[sleutel] = f"{(brouwerij or '').strip()} - {naam}".strip(" -")


def _split_csv(regel):
    velden, huidig, quotes = [], "", False
    for teken in regel:
        if teken == '"':
            quotes = not quotes
        elif teken == "," and not quotes:
            velden.append(huidig.strip().lower()); huidig = ""
        else:
            huidig += teken
    velden.append(huidig.strip().lower())
    return velden


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
