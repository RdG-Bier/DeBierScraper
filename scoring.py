# -*- coding: utf-8 -*-
"""Score per bier (0-100) en het matchen van hetzelfde bier tussen shops."""

import difflib
import math

import config
import utils


def compute_scores(all_beers):
    """
    all_beers: dict site_key -> lijst van bieren.
    Voegt per bier 'score' toe. Prijsnormalisatie gebeurt over de HELE dataset
    (alle shops samen), zodat scores tussen tabbladen vergelijkbaar zijn.
    """
    flat = [b for beers in all_beers.values() for b in beers]
    ppl_values = [_price_per_liter(b) for b in flat]
    ppl_values = [v for v in ppl_values if v is not None]
    ppl_min = min(ppl_values) if ppl_values else 0
    ppl_max = max(ppl_values) if ppl_values else 1

    for beer in flat:
        beer["score"] = round(_score(beer, ppl_min, ppl_max), 1)


def _price_per_liter(beer):
    price, vol = beer.get("prijs"), beer.get("inhoud_cl")
    if price is None:
        return None
    if config.PRICE_PER_LITER and vol:
        return price / (vol / 100)
    return price  # fallback: absolute prijs


def _score(beer, ppl_min, ppl_max):
    w = config.WEIGHTS
    total = 0.0

    # 1. stijl: sterke voorkeur = vol gewicht, gewone gewenste stijl = 50%
    total += w["style"] if beer.get("sterke_voorkeur") else w["style"] * 0.5

    # 2. untappd-score: lineair van MIN_UNTAPPD (0%) tot UNTAPPD_TOP (100%)
    u = beer.get("untappd")
    if u is None:
        total += w["untappd"] * config.UNKNOWN_UNTAPPD_FRACTION
    else:
        frac = (u - config.MIN_UNTAPPD) / (config.UNTAPPD_TOP - config.MIN_UNTAPPD)
        total += w["untappd"] * max(0.0, min(1.0, frac))

    # 3. aantal ratings: logaritmisch (100 ratings telt relatief zwaarder
    #    dan de stap van 4000 naar 5000)
    c = beer.get("untappd_aantal")
    if c and c > 1:
        frac = math.log10(c) / math.log10(config.COUNT_CAP)
        total += w["count"] * max(0.0, min(1.0, frac))

    # 4. prijs (per liter): goedkoopste in dataset = vol gewicht
    ppl = _price_per_liter(beer)
    if ppl is not None and ppl_max > ppl_min:
        frac = 1 - (ppl - ppl_min) / (ppl_max - ppl_min)
        total += w["price"] * max(0.0, min(1.0, frac))

    return total


def build_price_lookup(all_beers):
    """
    Retourneert dict: site_key -> dict match_key -> prijs.
    Match op genormaliseerde 'brouwerij + naam'; fuzzy fallback voor kleine
    spellingsverschillen (drempel in config.FUZZY_MATCH_THRESHOLD).
    """
    lookup = {}
    for site_key, beers in all_beers.items():
        site_map = {}
        for b in beers:
            key = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            if key and b.get("prijs") is not None:
                site_map.setdefault(key, b["prijs"])
        lookup[site_key] = site_map
    return lookup


def find_price(beer, site_map):
    """Zoek de prijs van dit bier in de map van een andere shop."""
    key = utils.beer_match_key(beer.get("brouwerij"), beer.get("naam"))
    if not key:
        return None
    if key in site_map:
        return site_map[key]
    # fuzzy: alleen vergelijken met keys van vergelijkbare lengte (sneller)
    best_key, best_ratio = None, 0.0
    for other in site_map:
        if abs(len(other) - len(key)) > 12:
            continue
        ratio = difflib.SequenceMatcher(None, key, other).ratio()
        if ratio > best_ratio:
            best_key, best_ratio = other, ratio
    if best_key and best_ratio >= config.FUZZY_MATCH_THRESHOLD:
        return site_map[best_key]
    return None
