# -*- coding: utf-8 -*-
"""Score per bier (0-100) en het matchen van hetzelfde bier tussen shops."""

import difflib
import json
import math
import time
from pathlib import Path

import config
import utils

DB_FILE = Path(__file__).parent / "docs" / "bierdatabase.json"


def compute_scores(all_beers):
    """
    all_beers: dict site_key -> lijst van bieren.
    Voegt per bier 'score' toe. Prijsnormalisatie gebeurt over de HELE dataset
    (alle shops samen), zodat scores tussen tabbladen vergelijkbaar zijn.
    """
    flat = [b for beers in all_beers.values() for b in beers]
    for beer in flat:
        beer["score"] = round(_score(beer), 1)


def _price_per_liter(beer):
    price, vol = beer.get("prijs"), beer.get("inhoud_cl")
    if price is None:
        return None
    if config.PRICE_PER_LITER:
        # onbekende inhoud: neem de standaard blikmaat aan, anders zou een
        # absolute prijs vergeleken worden met prijzen-per-liter (oneerlijk)
        return price / ((vol or config.DEFAULT_VOLUME_CL) / 100)
    return price


def _score(beer):
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

    # 4. prijs (per liter): vast venster (config.PRICE_PPL_BEST/WORST),
    #    robuust tegen extreme uitschieters in de dataset
    ppl = _price_per_liter(beer)
    if ppl is not None:
        frac = (config.PRICE_PPL_WORST - ppl) / (config.PRICE_PPL_WORST - config.PRICE_PPL_BEST)
        total += w["price"] * max(0.0, min(1.0, frac))

    # 5. prijsplafond: boven PRICE_CAP_EUR (absolute prijs) wordt een bier
    #    veel minder interessant -> stevige puntenaftrek
    price = beer.get("prijs")
    if price is not None and price > config.PRICE_CAP_EUR:
        total -= config.PRICE_CAP_MALUS

    # 6. bonusregels: specifieke combinaties wegen net iets zwaarder
    for rule in config.BONUS_RULES:
        total += rule["bonus"] * _bonus_factor(beer, rule)

    # 7. eigen smaak: gaf je deze brouwerij in deze stijlfamilie eerder een topcijfer?
    top = beer.get("eigen_top")
    if top:
        cfg = config.EIGEN_RATING_BONUS
        frac = (top["r"] - cfg["vanaf"]) / max(0.01, 5.0 - cfg["vanaf"])
        total += cfg["punten"] + (cfg["punten_top"] - cfg["punten"]) * max(0.0, min(1.0, frac))

    return max(0.0, min(100.0, total))


def _bonus_factor(beer, rule):
    """Hoeveel van de bonus verdient dit bier (0.0 - 1.0)?
    Vroeger was dit alles-of-niets: 8,99 euro gaf de volle bonus en 9,01 niets,
    waardoor een 4,46-bier van 12,99 lager eindigde dan een 4,14-bier van 7,89.
    Nu loopt de bonus geleidelijk af, zodat kleine verschillen in prijs of
    score ook maar kleine verschillen in punten geven."""
    style = beer.get("stijl") or ""
    doel = rule.get("style") or ""
    if doel:
        if rule.get("family"):
            if not style.startswith(doel):
                return 0.0
        elif rule.get("exact"):
            if style != doel:
                return 0.0
        elif not style.startswith(doel):
            return 0.0

    factor = 1.0

    if "max_price" in rule:
        price = beer.get("prijs")
        if price is None:
            return 0.0
        grens, taper = rule["max_price"], rule.get("taper_price", rule["max_price"])
        if price > grens:
            if taper <= grens or price >= taper:
                return 0.0
            factor *= (taper - price) / (taper - grens)

    if "min_untappd" in rule:
        u = beer.get("untappd")
        if u is None:
            return 0.0
        grens, taper = rule["min_untappd"], rule.get("taper_untappd", rule["min_untappd"])
        if u < grens:
            if taper >= grens or u <= taper:
                return 0.0
            factor *= (u - taper) / (grens - taper)

    return max(0.0, min(1.0, factor))


def enrich_untappd(all_beers):
    """De Untappd-score is een wereldwijd gemiddelde en dus shop-onafhankelijk.
    Toont een shop (zoals Beer Republic) de score niet, dan lenen we hem van
    hetzelfde bier bij een andere shop. Ook brede stijlen (Bierloods22 kent
    alleen 'Stout'/'IPA'/'Sour') worden verfijnd naar de precieze substijl
    van hetzelfde bier elders (matching op brouwerij + naam)."""
    db = _load_db()
    known_score = {k: (v["s"], v.get("c")) for k, v in db.items() if v.get("s")}
    known_style = {k: v["st"] for k, v in db.items() if v.get("st") in config.STYLES}
    known_volume = {k: v["v"] for k, v in db.items() if v.get("v")}
    known_image = {k: v["img"] for k, v in db.items() if v.get("img")}
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
            if b.get("untappd") is not None:
                huidig = known_score.get(key)
                nieuw_n = b.get("untappd_aantal") or 0
                if huidig is None or nieuw_n > (huidig[1] or 0):
                    # de bron met de meeste ratings is het meest actueel
                    known_score[key] = (b["untappd"], b.get("untappd_aantal"))
            if b.get("afbeelding") and key not in known_image:
                known_image[key] = b["afbeelding"]
            if b.get("stijl") in config.STYLES and key not in known_style:
                known_style[key] = b["stijl"]

    filled = refined = 0
    for beers in all_beers.values():
        for b in beers:
            key = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            hit = known_score.get(key) or _fuzzy_get(known_score, key)
            if hit:
                # Untappd-score is een wereldwijd gemiddelde en dus voor ALLE
                # shops gelijk. Shops cachen op verschillende momenten, dus
                # we gebruiken overal dezelfde waarde: die met de meeste
                # ratings. Anders scoort hetzelfde bier per tabblad anders
                # (en kon een duurdere shop zelfs hoger uitkomen).
                eigen_n = b.get("untappd_aantal") or 0
                if b.get("untappd") is None or (hit[1] or 0) > eigen_n:
                    if b.get("untappd") != hit[0] or b.get("untappd_aantal") != hit[1]:
                        b["untappd"], b["untappd_aantal"] = hit
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
            if not b.get("afbeelding"):
                img = known_image.get(key) or _fuzzy_get(known_image, key)
                if img:
                    b["afbeelding"] = img

    _update_db(db, all_beers)
    return filled + refined


def _load_db():
    """Permanente bierdatabase: alles wat ooit bij een shop gezien is (score,
    stijl, inhoud, etiket) blijft bewaard. Zo houden bieren die elders snel
    uitverkocht raken hun Untappd-score voor toekomstige matches."""
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def werk_historie_bij(all_beers, nu=None):
    """Houdt per bier PER SHOP bij: wanneer het daar voor het eerst en voor het
    laatst gezien is, en tegen welke prijs. Daaruit volgen de labels
    'nieuw binnen' en 'prijs gedaald', en de Onderweg-pagina kan zien of een
    besteld bier al bij de shop is binnengekomen.

    Opslag in de bierdatabase onder "sh": {shop: {"e": eerst gezien, "l": laatst
    gezien, "p": prijs, "pv": vorige (hogere) prijs, "pd": moment van daling}}.
    De allereerste keer dat een shop wordt bijgehouden, geldt niets als nieuw
    (anders zou het hele assortiment 'nieuw' zijn)."""
    nu = nu or time.time()
    db = _load_db()
    bekende_shops = {shop for e in db.values() for shop in (e.get("sh") or {})}
    dag = 86400.0
    for shop, beers in all_beers.items():
        eerste_keer = shop not in bekende_shops
        # Verkoopt een shop hetzelfde bier in meerdere maten (33 cl en 75 cl), dan
        # staan er twee prijzen onder één naam. Daar volgen we de prijs niet,
        # anders lijkt het flesje een 'prijsdaling' van de grote fles.
        aantal = {}
        for b in beers:
            k = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            aantal[k] = aantal.get(k, 0) + 1
        for b in beers:
            key = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            if not key:
                continue
            entry = db.setdefault(key, {"ts": nu})
            rec = entry.setdefault("sh", {}).get(shop)
            prijs = None if (b.get("prijs_geleend") or aantal.get(key, 0) > 1) else b.get("prijs")
            if rec is not None and aantal.get(key, 0) > 1:
                for veld in ("p", "pv", "pd"):
                    rec.pop(veld, None)
            if rec is None:
                rec = entry["sh"][shop] = {"e": 0 if eerste_keer else nu, "l": nu}
                if prijs is not None:
                    rec["p"] = prijs
            else:
                rec["l"] = nu
                if prijs is not None:
                    oud = rec.get("p")
                    if oud is not None and prijs < oud - 0.005:
                        rec["pv"], rec["pd"] = oud, nu
                    elif oud is not None and prijs > oud + 0.005:
                        rec.pop("pv", None)
                        rec.pop("pd", None)
                    rec["p"] = prijs
            if rec.get("e") and nu - rec["e"] <= config.NIEUW_DAGEN * dag:
                b["nieuw"] = True
            if rec.get("pd") and rec.get("pv") and nu - rec["pd"] <= config.PRIJSDALING_DAGEN * dag:
                b["prijs_was"] = rec["pv"]
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    DB_FILE.write_text(json.dumps(db, indent=1, ensure_ascii=False), encoding="utf-8")


def vul_brouwerijen_aan(all_beers):
    """Sommige shops (Drankgigant) noemen de brouwerij alleen vooraan in de
    productnaam, zonder scheidingsteken: "De Moersleutel Motor Oil Imperial
    Stout". We herkennen de brouwerij aan de hand van alle brouwerijen die de
    andere shops en de bierdatabase al kennen, en splitsen hem af."""
    # index: genormaliseerde brouwerijnaam (woorden) -> meest gebruikte schrijfwijze
    telling = {}
    def tel(brouwerij):
        sleutel = tuple(utils.beer_match_key(None, brouwerij).split())
        if sleutel and len("".join(sleutel)) >= 3:
            telling.setdefault(sleutel, {}).setdefault(brouwerij.strip(), 0)
            telling[sleutel][brouwerij.strip()] += 1
    for beers in all_beers.values():
        for b in beers:
            if b.get("brouwerij"):
                tel(b["brouwerij"])
    for entry in _load_db().values():
        nm = entry.get("nm") or ""
        if " - " in nm:
            tel(nm.split(" - ", 1)[0])
    index = {k: max(v, key=v.get) for k, v in telling.items()}
    langste = max((len(k) for k in index), default=0)

    aangevuld = 0
    for beers in all_beers.values():
        for b in beers:
            if b.get("brouwerij") or not b.get("naam"):
                continue
            woorden = b["naam"].split()
            tokens = utils.beer_match_key(None, b["naam"]).split()
            for n in range(min(langste, len(tokens) - 1), 0, -1):   # langste eerst
                label = index.get(tuple(tokens[:n]))
                if not label:
                    continue
                # hoeveel oorspronkelijke woorden horen bij de brouwerij?
                doel = " ".join(tokens[:n])
                for i in range(1, len(woorden)):
                    if utils.beer_match_key(None, " ".join(woorden[:i])) == doel:
                        b["brouwerij"] = label
                        b["naam"] = " ".join(woorden[i:])
                        aangevuld += 1
                        break
                break
    return aangevuld


def leen_prijzen(all_beers, doel_keys, voorkeur=None):
    """Voor shops zonder eigen prijzen (zoals De Bierschuur, een Untappd-venue-
    menu): geef elk bier de LAAGSTE prijs van hetzelfde bier. Bron is zowel de
    huidige andere shops ALS de permanente bierdatabase, die prijzen onthoudt
    van bieren die nu nergens meer in de schappen liggen. Ook de afbeelding
    wordt zo nodig uit de database geleend. De Bierschuur is Belgisch en ligt
    doorgaans onder de laagste NL-prijs, dus de laagst gevonden prijs is een
    veilige ondergrens."""
    # 0) optionele voorkeursbron (bijv. De Vershoek -> Bierloods22): als het
    #    bier daar ligt, wordt DIE prijs gebruikt, ook als hij elders lager is.
    voorkeur_prijs = {}
    if voorkeur:
        for b in all_beers.get(voorkeur, []):
            if b.get("prijs") is None:
                continue
            sl = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            if sl:
                voorkeur_prijs[sl] = {"prijs": b["prijs"], "vol": b.get("inhoud_cl")}

    # 1) laagste prijs (per liter) uit de HUIDIGE andere shops
    laagste = {}   # sleutel -> {"prijs","vol","ppl"}
    for key, beers in all_beers.items():
        if key in doel_keys:
            continue
        for b in beers:
            if b.get("prijs") is None:
                continue
            sl = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            if not sl:
                continue
            vol = b.get("inhoud_cl") or 44.0
            ppl = b["prijs"] / (vol / 100.0)
            if sl not in laagste or ppl < laagste[sl]["ppl"]:
                laagste[sl] = {"prijs": b["prijs"], "vol": b.get("inhoud_cl"), "ppl": ppl}

    # 2) de database erbij: die kent vaak nog meer prijzen (en afbeeldingen)
    db = _load_db()
    db_prijs = {k: v["pr"] for k, v in db.items() if v.get("pr")}
    db_img = {k: v["img"] for k, v in db.items() if v.get("img")}

    geleend = img_geleend = 0
    for key in doel_keys:
        for b in all_beers.get(key, []):
            sl = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            # prijs lenen: kies de laagste tussen live-shops en database
            if b.get("prijs") is None and voorkeur_prijs:
                vk = voorkeur_prijs.get(sl) or _fuzzy_get(voorkeur_prijs, sl)
                if vk:
                    b["prijs"] = vk["prijs"]
                    b["prijs_geleend"] = True
                    if not b.get("inhoud_cl") and vk.get("vol"):
                        b["inhoud_cl"] = vk["vol"]
                    geleend += 1
            if b.get("prijs") is None:
                kand = []
                live = laagste.get(sl) or _fuzzy_get(laagste, sl)
                if live:
                    kand.append(live)
                uitdb = db_prijs.get(sl) or _fuzzy_get(db_prijs, sl)
                if uitdb:
                    kand.append(uitdb)
                if kand:
                    beste = min(kand, key=lambda x: x["ppl"])
                    b["prijs"] = beste["prijs"]
                    b["prijs_geleend"] = True
                    if not b.get("inhoud_cl") and beste.get("vol"):
                        b["inhoud_cl"] = beste["vol"]
                    geleend += 1
            # afbeelding lenen uit de database als die ontbreekt
            if not b.get("afbeelding"):
                img = db_img.get(sl) or _fuzzy_get(db_img, sl)
                if img:
                    b["afbeelding"] = img
                    img_geleend += 1
    return geleend


def _update_db(db, all_beers):
    now = time.time()
    for beers in all_beers.values():
        for b in beers:
            key = utils.beer_match_key(b.get("brouwerij"), b.get("naam"))
            if not key:
                continue
            entry = db.setdefault(key, {})
            if not entry.get("nm") and b.get("naam"):
                # leesbare naam bewaren: dient als naslag voor de uploadpagina,
                # ook lang nadat een bier uit de schappen is verdwenen
                entry["nm"] = f"{(b.get('brouwerij') or '').strip()} - {b['naam']}".strip(" -")
            if b.get("untappd") is not None:
                new_count = b.get("untappd_aantal") or 0
                if not entry.get("s") or new_count >= (entry.get("c") or 0):
                    entry["s"], entry["c"] = b["untappd"], b.get("untappd_aantal")
            if b.get("stijl") in config.STYLES:
                entry["st"] = b["stijl"]
            if b.get("inhoud_cl") and not entry.get("v"):
                entry["v"] = b["inhoud_cl"]
            if b.get("afbeelding") and not entry.get("img"):
                entry["img"] = b["afbeelding"]
            # laagste prijs onthouden (geleende prijzen niet; die zijn zelf al
            # een schatting). Zo blijft een eens-gevonden prijs beschikbaar,
            # ook als het bier nu nergens meer in de schappen ligt.
            if b.get("prijs") is not None and not b.get("prijs_geleend"):
                vol = b.get("inhoud_cl") or 44.0
                ppl = b["prijs"] / (vol / 100.0)  # prijs per liter, eerlijke vergelijking
                if not entry.get("pr") or ppl < entry["pr"]["ppl"]:
                    entry["pr"] = {"prijs": b["prijs"], "vol": b.get("inhoud_cl"), "ppl": ppl}
            entry["ts"] = now
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    DB_FILE.write_text(json.dumps(db, indent=1, ensure_ascii=False), encoding="utf-8")


_FUZZY_REGISTER = {}     # id(lijst) -> (lijst, aantal, register)


def _fuzzy_register(mapping):
    """Register per opzoeklijst: woordbegin (4 letters) -> namen met dat woord.
    Eén keer opbouwen per lijst; daarna hoeft een zoekopdracht alleen de namen
    te bekijken die minstens één woordbegin delen in plaats van alle duizenden."""
    c = _FUZZY_REGISTER.get(id(mapping))
    if c and c[0] is mapping and c[1] == len(mapping):
        return c[2]
    register = {}
    for pos, naam in enumerate(mapping):
        for stuk in {w[:4] for w in naam.split() if len(w) >= 3}:
            register.setdefault(stuk, []).append((pos, naam))
    _FUZZY_REGISTER[id(mapping)] = (mapping, len(mapping), register)
    return register


def _fuzzy_get(mapping, key):
    """Zoekt de best gelijkende naam (minimaal FUZZY_MATCH_THRESHOLD).
    Versneld in twee stappen: (1) alleen kandidaten die een woordbegin delen,
    (2) wegstrepen wat op grond van lengte of letters nooit de drempel haalt.
    Alleen wat overblijft wordt letter voor letter vergeleken."""
    if not key:
        return None
    drempel = config.FUZZY_MATCH_THRESHOLD
    register = _fuzzy_register(mapping)
    kandidaten = {}
    for stuk in {w[:4] for w in key.split() if len(w) >= 3}:
        for pos, naam in register.get(stuk, ()):
            kandidaten[pos] = naam
    lk = len(key)
    sm = difflib.SequenceMatcher(None)
    sm.set_seq2(key)
    best_key, best_ratio = None, 0.0
    for pos in sorted(kandidaten):                      # vaste volgorde, zoals voorheen
        other = kandidaten[pos]
        lo = len(other)
        if abs(lo - lk) > 12 or 2.0 * min(lo, lk) < drempel * (lo + lk):
            continue
        sm.set_seq1(other)
        if sm.quick_ratio() < drempel:
            continue
        ratio = sm.ratio()
        if ratio > best_ratio:
            best_key, best_ratio = other, ratio
    if best_key and best_ratio >= drempel:
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
    # kleine spellingsverschillen: via de versnelde vergelijking (zelfde drempel)
    return _fuzzy_get(site_map, key)
