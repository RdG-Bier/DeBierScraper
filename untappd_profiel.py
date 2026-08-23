# -*- coding: utf-8 -*-
"""
Koppeling met een openbaar Untappd-profiel.

Haalt twee dingen op:
  1. de unieke bieren die de gebruiker ooit heeft ingecheckt  -> "gehad" (groen)
  2. de bieren op de opgegeven voorraadlijsten                -> "voorraad" (geel)

Werkt alleen als het profiel openbaar is (untappd.com/account/privacy).
Resultaten worden bewaard in docs/untappd_profiel.json en samengevoegd met
eerdere runs, zodat een mislukte of geblokkeerde run nooit data weggooit.
Van elke soort pagina wordt een debug-sample bewaard, zodat de parser bij te
stellen is als Untappd zijn opmaak wijzigt.
"""

import json
import logging
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup

import config
import utils

log = logging.getLogger("bierscraper")

CACHE_FILE = Path(__file__).parent / "docs" / "untappd_profiel.json"
BASIS = "https://untappd.com"
STAP = 25          # Untappd toont 25 bieren per pagina
VERTRAGING = 1.0   # seconden extra rust tussen paginas
RE_BEER = re.compile(r"^/b/[^/]+/(\d+)")
RE_BREWERY = re.compile(r"^/w/")


def synchroniseer(all_beers):
    """Haal het profiel op en markeer de bieren in alle shops."""
    gebruiker = getattr(config, "UNTAPPD_USER", "")
    if not gebruiker:
        return
    bewaard = _laad_cache()

    gehad = _haal_bierlijst(f"{BASIS}/user/{gebruiker}/beers", "gehad", gebruiker)
    if gehad:
        bewaard["gehad"] = _samenvoegen(bewaard.get("gehad"), gehad)
    else:
        log.warning("Untappd-profiel: geen ingecheckte bieren opgehaald "
                    "(profiel priv\u00e9 of pagina gewijzigd?); vorige lijst blijft staan")

    voorraad = _haal_lijsten(gebruiker, getattr(config, "UNTAPPD_VOORRAAD_LIJSTEN", ()))
    if voorraad:
        bewaard["voorraad"] = voorraad  # lijsten wisselen; niet samenvoegen
    elif bewaard.get("voorraad"):
        log.warning("Untappd-profiel: voorraadlijsten niet gevonden; vorige blijft staan")

    bewaard["bijgewerkt"] = time.strftime("%Y-%m-%d %H:%M")
    _bewaar_cache(bewaard)
    _markeer(all_beers, bewaard)


# ---------------------------------------------------------------------------
# Ophalen
# ---------------------------------------------------------------------------

def _haal_bierlijst(url, naam, gebruiker):
    """Loop de paginering af en verzamel {sleutel: "brouwerij - bier"}."""
    gevonden = {}
    max_paginas = getattr(config, "UNTAPPD_MAX_PAGINAS", 120)
    for i in range(max_paginas):
        offset = i * STAP
        pagina = url if offset == 0 else f"{url}?offset={offset}"
        html = utils.fetch(pagina, use_cache=(offset > 0))
        if not html:
            break
        if i == 0:
            utils.save_debug_sample("untappd", f"profiel-{naam}", html)
            if _is_prive(html):
                log.warning("Untappd-profiel van %s lijkt priv\u00e9 of onbereikbaar", gebruiker)
                return {}
        nieuw = _parse_bieren(html, gevonden)
        if nieuw == 0:
            break
        time.sleep(VERTRAGING)
    log.info("Untappd-profiel: %d bieren in '%s'", len(gevonden), naam)
    return gevonden


def _haal_lijsten(gebruiker, lijstnamen):
    """Zoek de opgegeven lijsten op het profiel en verzamel hun bieren."""
    if not lijstnamen:
        return {}
    html = utils.fetch(f"{BASIS}/user/{gebruiker}/lists")
    if not html:
        return {}
    utils.save_debug_sample("untappd", "profiel-lijsten", html)
    soup = BeautifulSoup(html, "html.parser")

    gewenst = {utils.norm(n): n for n in lijstnamen}
    urls = {}
    for a in soup.find_all("a", href=True):
        tekst = utils.norm(a.get_text(" ", strip=True))
        if not tekst:
            continue
        for sleutel, origineel in gewenst.items():
            if tekst == sleutel or (sleutel in tekst and len(tekst) < len(sleutel) + 12):
                href = a["href"]
                if href.startswith("/"):
                    href = BASIS + href
                urls.setdefault(origineel, href)
    if not urls:
        log.warning("Untappd-profiel: lijsten %s niet gevonden op /lists",
                    ", ".join(lijstnamen))
        return {}

    alles = {}
    for lijstnaam, url in urls.items():
        bieren = _haal_bierlijst(url, f"lijst-{utils.norm(lijstnaam)}", gebruiker)
        log.info("  voorraadlijst '%s': %d bieren", lijstnaam, len(bieren))
        alles.update(bieren)
    return alles


def _is_prive(html):
    lower = html.lower()
    return ("this account is private" in lower or "dit account is priv" in lower
            or "account is private" in lower)


def _parse_bieren(html, gevonden):
    """Haal bier + brouwerij uit een profiel- of lijstpagina."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup.find_all(["script", "style"]):
        t.decompose()
    nieuw = 0
    for link in soup.find_all("a", href=RE_BEER):
        naam = link.get_text(" ", strip=True)
        if not naam or len(naam) < 2:
            continue
        # brouwerij: dichtstbijzijnde /w/-link in dezelfde kaart
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
# Markeren
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
    log.info("Untappd-profiel: %d bieren gemarkeerd als 'gehad', %d als 'voorraad'",
             n_gehad, n_voorraad)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

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
