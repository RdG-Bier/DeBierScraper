# -*- coding: utf-8 -*-
"""
Combi-scraper: voegt een Untappd-venuepagina en een webshop van DEZELFDE winkel
samen tot één lijst (gebruikt voor Beer Dudes).

Waarom: de Untappd-pagina is rijk (score, aantal ratings, foto, stijl, prijs)
maar toont zonder JavaScript alleen het eerste menu. De webshop toont juist het
volledige assortiment, maar zonder Untappd-scores.

Werkwijze:
  1. Untappd-venue scrapen (bierbrigadier-scraper) -> rijke gegevens
  2. Webshop scrapen (woocommerce-scraper)          -> volledig assortiment
  3. Samenvoegen op naam: komt een bier in beide voor, dan wint Untappd en
     vult de webshop alleen lege velden aan (foto, inhoud, link).
     Bieren die alleen in de webshop staan, worden toegevoegd; hun score komt
     later via de Untappd-lookup/database (zet "untappd_lookup": True).

Config-velden: "menu_url" (Untappd-venue) en "api_url" (WooCommerce Store API).
"""

import logging

import bierbrigadier
import utils
import woocommerce

log = logging.getLogger("bierscraper")


def _tokens(b):
    return set(utils.beer_match_key(b.get("brouwerij"), b.get("naam")).split())


def _zelfde_bier(a, b):
    """Zelfde bier als de kleinste woordenset volledig in de grootste zit.
    Vangt 'Frontaal Go With The Flow' (webshop) vs 'Go With the Flow 2026'
    van Frontaal Brewing Co. (Untappd) op. Minimaal 3 woorden, anders te los."""
    ta, tb = _tokens(a), _tokens(b)
    klein, groot = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return len(klein) >= 3 and klein <= groot


def scrape(site):
    untappd = []
    shop = []
    if site.get("menu_url"):
        try:
            untappd = bierbrigadier.scrape(site)
        except Exception:
            log.exception("%s: Untappd-deel mislukt", site["label"])
    if site.get("api_url"):
        try:
            shop = woocommerce.scrape(site)
        except Exception:
            log.exception("%s: webshop-deel mislukt", site["label"])

    resultaat = list(untappd)
    exact = {utils.beer_match_key(b.get("brouwerij"), b.get("naam")): b for b in untappd}
    aangevuld = toegevoegd = 0
    for w in shop:
        sleutel = utils.beer_match_key(w.get("brouwerij"), w.get("naam"))
        match = exact.get(sleutel)
        if match is None:
            match = next((u for u in untappd if _zelfde_bier(u, w)), None)
        if match is not None:
            # Untappd wint; webshop vult alleen lege velden aan
            for veld in ("afbeelding", "inhoud_cl", "land", "prijs"):
                if not match.get(veld) and w.get(veld):
                    match[veld] = w[veld]
            aangevuld += 1
        else:
            resultaat.append(w)
            toegevoegd += 1

    log.info("%s: %d van Untappd, %d uit webshop (%d aangevuld, %d extra) -> %d totaal",
             site["label"], len(untappd), len(shop), aangevuld, toegevoegd, len(resultaat))
    return resultaat
