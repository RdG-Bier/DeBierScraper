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
    if config.PRICE_PER_LITER:
        # onbekende inhoud: neem de standaard blikmaat aan, anders zou een
        # absolute prijs vergeleken worden met prijzen-per-liter (oneerlijk)
        return price / ((vol or config.DEFAULT_VOLUME_CL) / 100)
    return price


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

    # 5. prijsplafond: boven PRICE_CAP_EUR (absolute prijs) wordt een bier
    #    veel minder interessant -> stevige puntenaftrek
    price = beer.get("prijs")
    if price is not None and price > config.PRICE_CAP_EUR:
        total -= config.PRICE_CAP_MALUS

    # 6. bonusregels: specifieke combinaties wegen net iets zwaarder
    for rule in config.BONUS_RULES:
        if _matches_bonus_rule(beer, rule):
            total += rule["bonus"]

    return max(0.0, min(100.0, total))


def _matches_bonus_rule(beer, rule):
    style = beer.get("stijl") or ""
    if rule.get("exact"):
        if style != rule["style"]:
            return False
    elif not style.startswith(rule["style"]):
        return False

    if "max_price" in rule:
        price = beer.get("prijs")
        if price is None or price >= rule["max_price"]:
            return False

    if "min_untappd" in rule:
        u = beer.get("untappd")
        if u is None or u < rule["min_untappd"]:
            return False

    return True


def enrich_untappd(all_beers):
    """De Untappd-score is een wereldwijd gemiddelde en dus shop-onafhankelijk.
    Toont een shop (zoals Beer Republic) de score niet, dan lenen we hem van
    hetzelfde bier bij een andere shop. Ook brede stijlen (Bierloods22 kent
    alleen 'Stout'/'IPA'/'Sour') worden verfijnd naar de precieze substijl
    van hetzelfde bier elders (matching op brouwerij + naam)."""
    known_score, known_style, known_volume = {}, {}, {}
    for beers in all_beers.values():
        for b in beers:
            # sanity guard: een Untappd-score buiten 0-5 kan nooit kloppen
            # (bijv. een jaartal dat per ongeluk als score is gelezen)
            if b.get("untappd") is not None and not (0 < b["untappd"] <= 5):
                b["untappd"] = None
            key = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            if not key:
                continue
            if b.get("inhoud_cl") and key not in known_volume:
                known_volume[key] = b["inhoud_cl"]
            if b.get("untappd") is not None and key not in known_score:
                known_score[key] = (b["untappd"], b.get("untappd_aantal"))
            if b.get("stijl") in config.STYLES and key not in known_style:
                known_style[key] = b["stijl"]

    filled = refined = 0
    for beers in all_beers.values():
        for b in beers:
            key = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            if b.get("untappd") is None:
                hit = known_score.get(key) or _fuzzy_get(known_score, key)
                if hit:
                    b["untappd"], b["untappd_aantal"] = hit
                    filled += 1
                    # geleende score kan alsnog onder de grens liggen; het bier
                    # blijft staan, maar de score maakt hem laag in de ranking
            elif b.get("untappd_aantal") is None:
                # score is al bekend (bijv. rechtstreeks van Untappd zelf),
                # maar het aantal ratings ontbreekt: dat lenen we los erbij
                hit = known_score.get(key) or _fuzzy_get(known_score, key)
                if hit and hit[1] is not None:
                    b["untappd_aantal"] = hit[1]
                    filled += 1
            if b.get("stijl") not in config.STYLES:  # brede stijl
                style = known_style.get(key) or _fuzzy_get(known_style, key)
                if style:
                    b["stijl"] = style
                    b["sterke_voorkeur"] = config.STYLES.get(style, False)
                    refined += 1
            if not b.get("inhoud_cl"):
                vol = known_volume.get(key) or _fuzzy_get(known_volume, key)
                if vol:
                    b["inhoud_cl"] = vol
                    refined += 1
    return filled + refined


def _fuzzy_get(mapping, key):
    if not key:
        return None
    best_key, best_ratio = None, 0.0
    for other in mapping:
        if abs(len(other) - len(key)) > 12:
            continue
        ratio = difflib.SequenceMatcher(None, key, other).ratio()
        if ratio > best_ratio:
            best_key, best_ratio = other, ratio
    if best_key and best_ratio >= config.FUZZY_MATCH_THRESHOLD:
        return mapping[best_key]
    return None


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
