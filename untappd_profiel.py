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
BESTAND_RATINGS = Path(__file__).parent / "mijn_untappd" / "mijn_ratings.json"
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

    log.info("Untappd-lijsten: %d gehad, %d voorraad R, %d voorraad H&R",
             len(gehad), len(voorraad_r), len(voorraad_hr))

    _markeer(all_beers, gehad, voorraad_r, voorraad_hr)
    ratings = laad_ratings()
    n_top = markeer_eigen_ratings(all_beers, ratings)
    log.info("Eigen beoordelingen: %d bekend, %d bieren krijgen een smaakbonus",
             len(ratings), n_top)

    # resultaat bewaren voor de webpagina (teller + eventuele latere routes)
    _bewaar_cache({
        "methode": "bestand",
        "bijgewerkt": time.strftime("%Y-%m-%d %H:%M"),
        "aantal_gehad": len(gehad),
        "aantal_voorraad_r": len(voorraad_r),
        "aantal_voorraad_hr": len(voorraad_hr),
    })


# ---------------------------------------------------------------------------
# Vangnet-matching op woorden. Shops korten namen soms in: Drankgigant noemt
# "Ārpus X Track QDH Riwaka ... Hand-Selected Superdelic QIPA" gewoon
# "Arpus X Track Riwaka ... Superdelic QIPA". Exact matchen faalt dan.
# Regels (bewust streng, om verkeerde matches te voorkomen):
#   - alle woorden van de kortste naam zitten in de langste
#   - minimaal 4 betekenisvolle woorden, en >= 60% dekking
#   - GETALLEN moeten exact gelijk zijn (Temporalis #0060 != #0061,
#     BCBS 2018 != 2019, "7 Year" != "8 Year")
# ---------------------------------------------------------------------------
_STOPWOORDEN = {"x", "and", "with", "w", "the", "of", "by"}

# Extra woorden die GEEN ander bier aanduiden (ruis die shops weglaten/toevoegen)
_NEUTRAAL = {"qdh", "tdh", "ddh", "dh", "hand", "selected", "cellar", "series",
             "rackhouse", "ipa", "collab", "collaboration", "edition"}
# Woorden die juist een VARIANT aanduiden: als dit het verschil is, is het
# een ander bier (Reserve BCBS, Barrel Aged Royal Cookie, Vanilla Bean Abraxas)
_VARIANT = {"reserve", "ba", "barrel", "aged", "bourbon", "rum", "whisky", "whiskey",
            "cognac", "brandy", "port", "sherry", "tequila", "mezcal", "wine", "oak",
            "maple", "vanilla", "coffee", "chocolate", "coconut", "cherry", "nitro",
            "alcoholarm", "alcoholvrij", "alcoholfree", "na", "nuchtere", "light",
            "double", "triple", "quadruple", "imperial", "mash", "special", "version",
            "variant", "grand", "cru", "xl", "mini", "blend", "anniversary", "bean"}
# "barrel aged" is wel neutraal als de kortste naam zelf al een vat noemt
# ("Kentucky Bourbon 2023" vs "Kentucky Bourbon Barrel Aged 2023")
_VAT = {"bourbon", "rum", "whisky", "whiskey", "cognac", "brandy", "port", "sherry",
        "barrel", "ba", "tequila", "wine"}


def _extra_ok(extra, klein):
    """Mogen deze extra woorden in de langste naam het verschil zijn?"""
    if not extra:
        return True
    neutraal = set(_NEUTRAAL)
    if klein & _VAT:
        neutraal |= {"barrel", "aged", "ba"}
    rest = extra - neutraal
    if not rest:
        return True
    # precies één onbekend woord dat geen variant is = waarschijnlijk een
    # collab-partner ("x Finback", "x Lua", "PULP")
    return len(rest) == 1 and not (rest & _VARIANT)


def _woorden(sleutel):
    return {w for w in sleutel.split() if w not in _STOPWOORDEN}


def _getallen(woorden):
    return {w for w in woorden if any(c.isdigit() for c in w)}


def _woord_index(lijst):
    """Bouwt een index woord -> [(woordenset, sleutel)] voor snel zoeken."""
    index = {}
    for sleutel in lijst:
        ws = _woorden(sleutel)
        if len(ws) < 4:
            continue
        for w in ws:
            index.setdefault(w, []).append((ws, sleutel))
    return index


def _woord_zoek(sleutel, index):
    """Zoekt via de woord-regels; geeft de gevonden lijst-sleutel terug of None."""
    ws = _woorden(sleutel)
    if len(ws) < 4:
        return None
    # alleen kandidaten die het zeldzaamste woord delen (snel en precies)
    zeldzaam = min(ws, key=lambda w: len(index.get(w, ())) or 10**9)
    for kws, kandidaat in index.get(zeldzaam, ()):
        klein, groot = (ws, kws) if len(ws) <= len(kws) else (kws, ws)
        if (len(klein) >= 4 and klein <= groot
                and len(klein) / len(groot) >= 0.6
                and _getallen(ws) == _getallen(kws)
                and _extra_ok(groot - klein, klein)):
            return kandidaat
    return None


def _woord_match(sleutel, index):
    return _woord_zoek(sleutel, index) is not None


def _brouwerij_past(shop_brouwerij, lijstregel):
    """Naam-only matching mag alleen als de brouwerij ontbreekt of overeenkomt.
    Anders wordt Salikatt 'Resonance' groen door FUERST WIACEK 'Resonance'."""
    if not shop_brouwerij:
        return True                     # shop noemt geen brouwerij (Drankgigant)
    deel = str(lijstregel).split(" - ", 1)
    if len(deel) < 2:
        return True                     # lijstregel zonder brouwerij
    a = {w for w in utils.beer_match_key(None, shop_brouwerij).split() if len(w) >= 3}
    b = {w for w in utils.beer_match_key(None, deel[0]).split() if len(w) >= 3}
    return not a or not b or bool(a & b)


def _naam_match(b, naam_sleutel, naam_index):
    regel = naam_index.get(naam_sleutel)
    return regel is not None and _brouwerij_past(b.get("brouwerij"), regel)


def _markeer(all_beers, gehad, voorraad_r, voorraad_hr):
    gehad_naam = _naam_index(gehad)
    r_naam = _naam_index(voorraad_r)
    hr_naam = _naam_index(voorraad_hr)
    gehad_w, r_w, hr_w = _woord_index(gehad), _woord_index(voorraad_r), _woord_index(voorraad_hr)
    n_gehad = n_r = n_hr = 0

    for bieren in all_beers.values():
        for b in bieren:
            sleutel = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            naam_sleutel = utils.beer_match_key(None, b.get("naam"))

            is_gehad = (sleutel in gehad or _naam_match(b, naam_sleutel, gehad_naam)
                        or _woord_match(sleutel, gehad_w))
            is_r = (sleutel in voorraad_r or _naam_match(b, naam_sleutel, r_naam)
                    or _woord_match(sleutel, r_w))
            is_hr = (sleutel in voorraad_hr or _naam_match(b, naam_sleutel, hr_naam)
                     or _woord_match(sleutel, hr_w))

            # Zelfde biernaam bij een ANDERE brouwerij in je lijsten (bijv. de
            # collab-tweeling Azvex/Lolev "Peregrine Falcon"): niet kleuren,
            # wel een hint tonen zodat je hem niet over het hoofd ziet.
            if not (is_gehad or is_r or is_hr):
                for index, etiket in ((gehad_naam, "al gehad"), (r_naam, "in voorraad R"),
                                      (hr_naam, "in voorraad H&R")):
                    regel = index.get(naam_sleutel)
                    if regel is not None and not _brouwerij_past(b.get("brouwerij"), regel):
                        b["naamgenoot"] = "%s (%s)" % (regel, etiket)
                        break

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


# ---------------------------------------------------------------------------
# Eigen Untappd-beoordelingen. Bestand mijn_untappd/mijn_ratings.json wordt
# gevuld door de 'Lijsten inlezen'-pagina zodra je een check-in-CSV uploadt
# (de extensie levert de kolommen eigen_rating en stijl). Vorm:
#   {"Brouwerij - Biernaam": [4.75, "IPA - Triple New England / Hazy"], ...}
# ---------------------------------------------------------------------------
def laad_ratings():
    try:
        data = json.loads(BESTAND_RATINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    uit = {}
    for regel, waarde in (data.items() if isinstance(data, dict) else []):
        try:
            cijfer = float(waarde[0] if isinstance(waarde, (list, tuple)) else waarde)
        except (TypeError, ValueError, IndexError):
            continue
        stijl = waarde[1] if isinstance(waarde, (list, tuple)) and len(waarde) > 1 else ""
        if 0 < cijfer <= 5:
            uit[regel] = (cijfer, stijl or "")
    return uit


def _familie(stijl):
    """IPA / Stout / Sour / Mead: de 'insteek' van een bier."""
    woord = (stijl or "").split(" - ")[0].strip().split(" ")[0].lower()
    return {"mede": "mead"}.get(woord, woord)


def markeer_eigen_ratings(all_beers, ratings):
    """Bieren van een brouwerij waaraan jij in dezelfde stijlfamilie een
    topcijfer gaf, krijgen 'eigen_top' (gebruikt voor de bonus en een label)."""
    grens = config.EIGEN_RATING_BONUS["vanaf"]
    beste = {}   # (brouwerij-sleutel, familie) -> (cijfer, biernaam)
    for regel, (cijfer, stijl) in ratings.items():
        if cijfer < grens or " - " not in regel:
            continue
        brouwerij, naam = regel.split(" - ", 1)
        sleutel = (utils.beer_match_key(None, brouwerij), _familie(stijl))
        if sleutel[0] and sleutel[1] and cijfer > beste.get(sleutel, (0, ""))[0]:
            beste[sleutel] = (cijfer, naam)
    n = 0
    for bieren in all_beers.values():
        for b in bieren:
            if not b.get("brouwerij"):
                continue
            hit = beste.get((utils.beer_match_key(None, b["brouwerij"]), _familie(b.get("stijl"))))
            if hit:
                b["eigen_top"] = {"r": hit[0], "bier": hit[1]}
                n += 1
    return n


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
