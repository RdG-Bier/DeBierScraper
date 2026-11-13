# -*- coding: utf-8 -*-
"""
Combi-scraper: voegt een Untappd-venuepagina en een webshop van DEZELFDE winkel
samen tot één lijst (gebruikt voor Beer Dudes).

De WEBSHOP is leidend: die bepaalt welke bieren er staan en wat ze kosten,
want daar zie je wat er op dit moment echt te koop is. Het Untappd-menu loopt
vaak achter en toont zonder JavaScript maar een deel. Het menu wordt daarom
alleen gebruikt om webshop-bieren AAN TE VULLEN met wat Untappd beter weet:
score, exacte stijl, brouwerij, ABV en etiket.

Bieren die alleen in de webshop staan, krijgen hun score later via de
Untappd-lookup/database (zet "untappd_lookup": True).
Levert de webshop niets op (storing), dan vallen we terug op het Untappd-menu.

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
    untappd, shop = [], []
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

    if not shop:
        log.warning("%s: webshop leverde niets op; terugval op het Untappd-menu (%d bieren)",
                    site["label"], len(untappd))
        return untappd

    exact = {utils.beer_match_key(u.get("brouwerij"), u.get("naam")): u for u in untappd}
    aangevuld = 0
    for w in shop:
        sleutel = utils.beer_match_key(w.get("brouwerij"), w.get("naam"))
        u = exact.get(sleutel) or next((x for x in untappd if _zelfde_bier(x, w)), None)
        if u is None:
            continue
        aangevuld += 1
        # wat Untappd beter weet, overnemen; prijs, link en inhoud blijven van de webshop
        for veld in ("untappd", "untappd_aantal"):
            if u.get(veld) is not None:
                w[veld] = u[veld]
        if u.get("stijl"):
            w["stijl"], w["stijl_ruw"] = u["stijl"], u.get("stijl_ruw") or u["stijl"]
            w["sterke_voorkeur"] = u.get("sterke_voorkeur", False)
        for veld in ("brouwerij", "abv", "afbeelding", "land", "inhoud_cl"):
            if not w.get(veld) and u.get(veld):
                w[veld] = u[veld]

    log.info("%s: %d bieren uit de webshop, waarvan %d aangevuld vanuit het Untappd-menu (%d items)",
             site["label"], len(shop), aangevuld, len(untappd))
    return shop
