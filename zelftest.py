# -*- coding: utf-8 -*-
"""
Zelftest. Draait aan het begin van elke run (zie main.py) en controleert de
scraper op opgeslagen ECHTE voorbeelden van de shoppagina's, plus de gevallen
die eerder fout gingen. Faalt er iets, dan wordt er niet gepubliceerd en
blijft de vorige pagina staan (zie config.ZELFTEST_BLOKKEERT).

Wat dit vangt: fouten die ontstaan door een wijziging in de CODE (een nieuwe
versie die iets stukmaakt). Wat dit niet vangt: een shop die zijn website
verandert; daarvoor is het vangnet in bewaking.py.

Er wordt niets opgehaald van internet en niets in docs/ geschreven: alles
draait op de voorbeelden hieronder en in een tijdelijke map.
"""

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import config

# ---------------------------------------------------------------------------
# Echte voorbeelden (ingekort)
# ---------------------------------------------------------------------------
# Untappd-venuemenu (De Bierschuur): eerst een "Recent Activity"-check-in van
# een bezoeker (GEEN menu-item, maar wel hetzelfde bier als op het menu, zoals
# in het echt), dan een bier boven de 4.00 en een bier eronder.
VENUE_HTML = '<html><body><div class="venue-activity"><ul><li> <div class="avatar"> <a href="/user/joran_6767"><img src="https://assets.untappd.com/profile/c07c311d3364d74d6a6ee46d85be049d_100x100.jpg"/></a> </div> <div class="details"> <span class="time"><a class="timezoner" href="/user/joran_6767/checkin/1613725561">Sat, 07 Nov 2026 16:27:10 +0000</a></span> <h4><a href="/user/joran_6767">joran_6767</a></h4> <h5><a href="/b/omnipollo-bianca-peanut-butter-jelly-lassi-gose/6857067">Brugse Zot</a></h5> <h5>Brouwerij De Halve Maan</h5> <div class="caps small" data-rating="4.5"> <div class="cap cap-100"></div> <div class="cap cap-100"></div> <div class="cap cap-100"></div> <div class="cap cap-100"></div> <div class="cap cap-50"></div> </div> </div> </li></ul></div><div class="menu-area"><ul><li class="menu-item" id="beer"> <div class="beer-info" style="min-height: 50px;"> <div class="beer-label"> <img src="https://labels.untappd.com/6857067"/> </div> <div class="beer-details"> <h5> <a class="track-click" data-href=":" data-track="menu" href="/b/omnipollo-bianca-peanut-butter-jelly-lassi-gose/6857067"> Bianca Peanut Butter Jelly Lassi Gose </a> <em>Sour - Smoothie / Pastry</em> </h5> <h6> <span>6% ABV • N/A IBU • <a class="track-click" data-href=":brewery" data-track="menu" href="/Omnipollo"> Omnipollo</a> • </span> <div class="caps small" data-rating="4.24345"> <div class="cap cap-100"></div> <div class="cap cap-100"></div> <div class="cap cap-100"></div> <div class="cap cap-100"></div> <div class="cap cap-20"></div> </div> <span class="num">(4.24)</span> </h6> </div> </div> </li><li class="menu-item" id="beer"> <div class="beer-info" style="min-height: 50px;"> <div class="beer-label"> <img src="https://labels.untappd.com/6640692"/> </div> <div class="beer-details"> <h5> <a class="track-click" data-href=":" data-track="menu" href="/b/amundsen-brewery-the-summoning/6640692"> The Summoning </a> <em>IPA - New England / Hazy</em> </h5> <h6> <span>7.3% ABV • N/A IBU • <a class="track-click" data-href=":brewery" data-track="menu" href="/AmundsenBryggeri"> Amundsen Brewery</a> • </span> <div class="caps small" data-rating="3.91011"> <div class="cap cap-100"></div> <div class="cap cap-100"></div> <div class="cap cap-100"></div> <div class="cap cap-90"></div> <div class="cap"></div> </div> <span class="num">(3.91)</span> </h6> </div> </div> </li></ul></div></body></html>'
VENUE_VERWACHT = {'naam': 'Bianca Peanut Butter Jelly Lassi Gose', 'brouwerij': 'Omnipollo', 'stijl_ruw': 'Sour - Smoothie / Pastry', 'score': 4.24}

# Product uit de webshop van Beer Dudes (WooCommerce Store API)
WOO_PRODUCT = {'name': 'De Kromme Haring Mudskipper Strata Chinook', 'permalink': 'https://www.beerdudes.club/bier/de-kromme-haring-mudskipper-strata-chinook/', 'is_in_stock': True, 'prices': {'price': '400', 'sale_price': '400', 'currency_minor_unit': 2}, 'categories': [{'id': 63, 'name': 'IPA', 'slug': 'ipa', 'link': 'https://www.beerdudes.club/product-categorie/ipa/'}, {'id': 91, 'name': 'NEIPA', 'slug': 'neipa', 'link': 'https://www.beerdudes.club/product-categorie/neipa/'}], 'attributes': [{'id': 3, 'name': 'Brouwer', 'taxonomy': 'pa_brouwer', 'has_variations': False, 'terms': [{'id': 328, 'name': 'De kromme haring', 'slug': 'de-kromme-haring'}]}, {'id': 1, 'name': 'Kleur', 'taxonomy': 'pa_kleur', 'has_variations': False, 'terms': [{'id': 317, 'name': 'Blond', 'slug': 'blond'}]}, {'id': 2, 'name': 'Land', 'taxonomy': 'pa_land', 'has_variations': False, 'terms': [{'id': 322, 'name': 'Nederland', 'slug': 'nederland'}]}, {'id': 6, 'name': 'Verpakking', 'taxonomy': 'pa_verpakking', 'has_variations': True, 'terms': [{'id': 889, 'name': '6 pack', 'slug': '6-pack'}, {'id': 890, 'name': 'Doos van 24', 'slug': 'doos-van-24'}, {'id': 888, 'name': 'Losse fles', 'slug': 'losse-fles'}]}], 'tags': [{'id': 894, 'name': 'De Kromme Haring special', 'slug': 'de-kromme-haring-special', 'link': 'https://www.beerdudes.club/product-tag/de-kromme-haring-special/'}], 'images': [{'src': 'https://www.beerdudes.club/wp-content/uploads/2026/11/Mudskipper-Shop-Close-2.png', 'thumbnail': 'https://www.beerdudes.club/wp-content/uploads/2026/11/Mudskipper-Shop-Close-2-300x300.png'}], 'short_description': '', 'description': ''}

# Productdata van Bierloods22 (Lightspeed, <product-url>?format=json)
B22_PRODUCT = {'product': {'title': 'One Drop Brewing Co - Walkthrough', 'stock': {'available': True, 'on_stock': True, 'track': True, 'allow_outofstock_sale': False, 'level': 13, 'minimum': 1, 'maximum': 13, 'delivery': {'title': 'binnen 24u verzonden'}}, 'specs': {'781845': {'id': 781845, 'title': 'Stijl:', 'value': ''}, '781842': {'id': 781842, 'title': 'Inhoud:', 'value': '44cl'}, '781840': {'id': 781840, 'title': 'Land:', 'value': 'Australië '}, '781841': {'id': 781841, 'title': 'ABV:', 'value': '10%'}, '781843': {'id': 781843, 'title': 'Untappd:', 'value': '4.23'}}, 'content': '<p>Walkthrough<br />One Drop Brewing Co | Stout - Imperial / Double Pastry</p>'}}


def _controleer(fouten, naam, voorwaarde, detail=""):
    if not voorwaarde:
        fouten.append(naam + (" -> " + str(detail) if detail else ""))


def _test_untappd_menu(fouten):
    import bierbrigadier
    echt_fetch, echt_debug = bierbrigadier.utils.fetch, bierbrigadier.utils.save_debug_sample
    bierbrigadier.utils.fetch = lambda url, **kw: VENUE_HTML
    bierbrigadier.utils.save_debug_sample = lambda *a, **kw: None
    try:
        beers = bierbrigadier.scrape({"key": "zelftest", "label": "zelftest",
                                      "menu_url": "x", "heeft_prijzen": False})
    finally:
        bierbrigadier.utils.fetch, bierbrigadier.utils.save_debug_sample = echt_fetch, echt_debug
    _controleer(fouten, "Untappd-menu: precies 1 bier (check-in en lage score genegeerd)",
                len(beers) == 1, [b.get("naam") for b in beers])
    if beers:
        b = beers[0]
        _controleer(fouten, "Untappd-menu: naam", b.get("naam") == VENUE_VERWACHT["naam"], b.get("naam"))
        _controleer(fouten, "Untappd-menu: brouwerij", b.get("brouwerij") == VENUE_VERWACHT["brouwerij"], b.get("brouwerij"))
        _controleer(fouten, "Untappd-menu: score", b.get("untappd") is not None
                    and abs(b["untappd"] - VENUE_VERWACHT["score"]) < 0.011, b.get("untappd"))
        _controleer(fouten, "Untappd-menu: foto", bool(b.get("afbeelding")), b.get("afbeelding"))
        _controleer(fouten, "Untappd-menu: stijl herkend", b.get("stijl") in config.STYLES, b.get("stijl"))


def _test_webshops(fouten):
    import woocommerce
    site = {"key": "zelftest", "label": "zelftest", "base_url": "https://www.beerdudes.club"}
    echt = woocommerce.FETCH_DETAIL_FALLBACK
    woocommerce.FETCH_DETAIL_FALLBACK = False          # geen productpagina ophalen
    try:
        b = woocommerce._parse_product(json.loads(json.dumps(WOO_PRODUCT)), site, [0])
    finally:
        woocommerce.FETCH_DETAIL_FALLBACK = echt
    _controleer(fouten, "Webshop: product wordt ingelezen", b is not None)
    if b:
        _controleer(fouten, "Webshop: brouwerij uit productkenmerk", b.get("brouwerij") == "De Kromme Haring", b.get("brouwerij"))
        _controleer(fouten, "Webshop: brouwerij uit naam gehaald", b.get("naam") == "Mudskipper Strata Chinook", b.get("naam"))
        _controleer(fouten, "Webshop: prijs", isinstance(b.get("prijs"), float) and b["prijs"] > 0, b.get("prijs"))
        _controleer(fouten, "Webshop: foto", bool(b.get("afbeelding")), b.get("afbeelding"))
    for naam, verwacht in (("Factory Brewing \u2013 Solitary Motion", "Factory Brewing"),
                           ("Messorem -Temporalis #0066", "Messorem"),
                           ("Brasserie du Bas-Canada \u2013 Themis 3000", "Brasserie du Bas-Canada")):
        br, _ = woocommerce._brouwerij_en_land({}, naam, None, None)
        _controleer(fouten, "Webshop: brouwerij voor het streepje (%s)" % naam, br == verwacht, br)

    import bierloods22
    _controleer(fouten, "Bierloods22: op voorraad herkend",
                bierloods22._voorraad_uit_json(B22_PRODUCT) is True)
    uit = json.loads(json.dumps(B22_PRODUCT)); uit["product"]["stock"].update(on_stock=False, level=0)
    _controleer(fouten, "Bierloods22: uitverkocht herkend", bierloods22._voorraad_uit_json(uit) is False)
    _controleer(fouten, "Bierloods22: onbekend blijft onbekend", bierloods22._voorraad_uit_json(None) is None)
    b = {"naam": "Walkthrough", "stijl": "Stout", "stijl_ruw": "Stout", "sterke_voorkeur": False,
         "untappd": 4.23, "inhoud_cl": None, "abv": None, "land": None}
    bierloods22._verrijk_uit_json(b, B22_PRODUCT)
    _controleer(fouten, "Bierloods22: exacte stijl", b["stijl"] == "Stout - Imperial / Double Pastry", b["stijl"])
    _controleer(fouten, "Bierloods22: inhoud en ABV", b["inhoud_cl"] == 44.0 and b["abv"] == 10.0, (b["inhoud_cl"], b["abv"]))


def _test_matching(fouten):
    import untappd_profiel as up
    import utils
    sl = utils.beer_match_key
    _controleer(fouten, "Matching: dubbele brouwerijnaam in biernaam",
                sl("\u0100rpus Brewing Co.", "\u0100rpus X Track QDH Riwaka") == sl("Arpus", "X Track QDH Riwaka"))
    lijst = {sl(*r.split(" - ", 1)): r for r in (
        "\u0100rpus Brewing Co. - \u0100rpus X Track QDH Riwaka X Motueka X Cryo Citra X Hand-Selected Superdelic QIPA",
        "Goose Island Beer Co. - Reserve Bourbon County Brand Stout (2017)",
        "Funky Fluid - Barrel Aged Royal Cookie: Scoop",
        "FUERST WIACEK Berlin - Resonance",
        "Messorem - Temporalis #0060")}
    index, namen = up._woord_index(lijst), up._naam_index(lijst)
    def raak(brouwerij, naam):
        s = sl(brouwerij, naam)
        return (s in lijst or up._naam_match({"brouwerij": brouwerij}, sl(None, naam), namen)
                or up._woord_match(s, index))
    _controleer(fouten, "Matching: ingekorte naam (Drankgigant) wordt herkend",
                raak(None, "Arpus X Track Riwaka X Motueka X Cryo Citra X Superdelic QIPA"))
    _controleer(fouten, "Matching: 'Reserve' is een ander bier",
                not raak("Goose Island", "Bourbon County Brand Stout (2017)"))
    _controleer(fouten, "Matching: 'Barrel Aged' is een ander bier",
                not raak("Funky Fluid", "Royal Cookie: Scoop"))
    _controleer(fouten, "Matching: zelfde naam, andere brouwerij telt niet",
                not raak("Salikatt", "Resonance"))
    _controleer(fouten, "Matching: ander volgnummer telt niet",
                not raak("Messorem", "Temporalis #0061"))

    # via de echte markeerfunctie: tikfout en alcoholpercentage in de naam
    def lijst_van(*regels):
        uit = {}
        for r in regels:
            br, _, nm = r.partition(" - ")
            up._voeg_toe(uit, br, nm)
        return uit
    gehad = lijst_van("Goose Island Beer Co. - Bourbon County Brand Stout (2018) 14.7%")
    hr = lijst_van("Goose Island Beer Co. - Bourbon County Brand Stout (2018) 15.2%",
                   "\u0100rpus Brewing Co. - \u0100rpus X Ophiussa Salted Caramel Ice Cream Stout")
    bieren = {"s": [
        {"brouwerij": "Arpus", "naam": "X Ophiusa Salted Caramel Ice Cream Stout"},          # tikfout
        {"brouwerij": "Goose Island", "naam": "Bourbon County Brand Stout (2018)"},          # zonder %
        {"brouwerij": "Goose Island Beer Co.", "naam": "Bourbon County Brand Stout (2018) 15.2%"},
        {"brouwerij": "Goose Island Beer Co.", "naam": "Bourbon County Brand Stout (2019) 14.7%"}]}
    up._markeer(bieren, gehad, {}, hr)
    tikfout, zonder_pct, pct_152, ander_jaar = bieren["s"]
    _controleer(fouten, "Matching: tikfout in een woord (Ophiusa/Ophiussa)", tikfout.get("voorraad_hr"))
    _controleer(fouten, "Matching: percentage aan één kant wordt genegeerd", zonder_pct.get("gehad"))
    _controleer(fouten, "Matching: 15.2% is niet het gedronken 14.7%-bier",
                pct_152.get("voorraad_hr") and not pct_152.get("gehad"))
    _controleer(fouten, "Matching: ander jaar telt niet", not ander_jaar.get("gehad"))


def _test_scoring(fouten, tmp):
    import scoring
    echt_db = scoring.DB_FILE
    scoring.DB_FILE = tmp / "db.json"
    scoring.DB_FILE.write_text("{}", encoding="utf-8")
    try:
        alle = {"a": [{"brouwerij": "Messorem", "naam": "Temporalis #0065", "prijs": None, "inhoud_cl": None}],
                "voorkeur": [{"brouwerij": "Messorem", "naam": "Temporalis #0065", "prijs": 9.95, "inhoud_cl": 47.3}],
                "goedkoop": [{"brouwerij": "Messorem", "naam": "Temporalis #0065", "prijs": 8.50, "inhoud_cl": 47.3}]}
        scoring.leen_prijzen(alle, {"a"}, voorkeur="voorkeur")
        _controleer(fouten, "Prijs lenen: voorkeursshop wint", alle["a"][0]["prijs"] == 9.95, alle["a"][0]["prijs"])
        _controleer(fouten, "Prijs lenen: gemarkeerd als geleend", alle["a"][0].get("prijs_geleend") is True)
        _controleer(fouten, "Prijsvergelijking: kleine spelfout wordt herkend",
                    scoring.find_price({"brouwerij": "Moersleutel", "naam": "Barcode Silver Aquamarine"},
                                       {"moersleutel barcode silver aquamarin": 12.5}) == 12.5)
        dag = 86400.0
        scoring.werk_historie_bij({"s": [{"brouwerij": "T", "naam": "Oud Bier", "prijs": 10.0}]}, 1_000_000_000.0)
        ronde = {"s": [{"brouwerij": "T", "naam": "Oud Bier", "prijs": 8.0},
                       {"brouwerij": "T", "naam": "Nieuw Bier", "prijs": 7.0},
                       {"brouwerij": "T", "naam": "Twee Maten", "prijs": 5.95, "inhoud_cl": 75.0},
                       {"brouwerij": "T", "naam": "Twee Maten", "prijs": 1.59, "inhoud_cl": 33.0}]}
        scoring.werk_historie_bij(ronde, 1_000_000_000.0 + dag)
        oud, nieuw, m1, m2 = ronde["s"]
        _controleer(fouten, "Historie: prijsdaling herkend", oud.get("prijs_was") == 10.0, oud.get("prijs_was"))
        _controleer(fouten, "Historie: nieuw bier herkend", nieuw.get("nieuw") is True and not oud.get("nieuw"))
        _controleer(fouten, "Historie: twee maten is geen prijsdaling",
                    not m1.get("prijs_was") and not m2.get("prijs_was"))
        db = {"oud bier": {"s": 4.48, "c": None, "ts": 1}, "goed bier": {"s": 4.3, "c": 500, "ts": 1}}
        scoring.DB_FILE.write_text(json.dumps(db), encoding="utf-8")
        shop = [{"brouwerij": "", "naam": "Oud Bier", "untappd": 4.48},
                {"brouwerij": "", "naam": "Goed Bier", "untappd": 4.3}]
        scoring.negeer_shopscores(shop)
        db = json.loads(scoring.DB_FILE.read_text(encoding="utf-8"))
        _controleer(fouten, "Verouderde shopscore wordt genegeerd",
                    shop[0]["untappd"] is None and "s" not in db["oud bier"])
        _controleer(fouten, "Database-score MET aantal blijft staan", db["goed bier"].get("s") == 4.3)
    finally:
        scoring.DB_FILE = echt_db


def _test_paginas(fouten, tmp):
    """Bouwt de drie pagina's met een paar bieren en controleert de JavaScript."""
    import html_builder
    import onderweg
    import scoring
    import upload_pagina
    sites = [s for s in config.SITES if s.get("enabled") is not False][:3]
    def bier(naam, **extra):
        b = {"brouwerij": "Test & Co", "naam": naam, "inhoud_cl": 44.0, "land": "NL", "abv": 9.0,
             "stijl": "IPA - Triple", "stijl_ruw": "IPA - Triple", "sterke_voorkeur": True,
             "untappd": 4.3, "untappd_aantal": 250, "prijs": 7.5, "weblink": "https://example.org/x",
             "afbeelding": None}
        b.update(extra)
        return b
    alle = {s["key"]: [] for s in sites}
    alle[sites[0]["key"]] = [
        bier("Gewoon \"bier\" <b>"), bier("Nieuw", nieuw=True), bier("Gedaald", prijs_was=9.0),
        bier("Geleend", prijs_geleend=True), bier("Gehad", gehad=True),
        bier("Voorraad", voorraad=True, voorraad_r=True),
        bier("Smaak", eigen_top={"r": 4.75, "bier": "Iets 'lekkers'"}),
        bier("Naamgenoot", naamgenoot="Ander - Naamgenoot (al gehad)")]
    scoring.compute_scores(alle)
    html_builder.build_html(alle, sites, tmp / "index.html")
    upload_pagina.bouw(tmp / "lijsten.html")
    onderweg.bouw(tmp / "onderweg.html", sites)
    node = shutil.which("node")
    import re
    for naam in ("index.html", "lijsten.html", "onderweg.html"):
        tekst = (tmp / naam).read_text(encoding="utf-8")
        resten = set(re.findall(r"__[A-Z][A-Z_]+__", tekst)) - {"__anders"}
        _controleer(fouten, "Pagina %s: geen lege plaatshouders" % naam, not resten, resten)
        m = re.search(r"<script>(.*)</script>", tekst, re.S)
        _controleer(fouten, "Pagina %s: script aanwezig" % naam, bool(m))
        if m and node:
            js = tmp / (naam + ".js")
            js.write_text(m.group(1), encoding="utf-8")
            res = subprocess.run([node, "--check", str(js)], capture_output=True, text=True, timeout=60)
            _controleer(fouten, "Pagina %s: JavaScript zonder syntaxfouten" % naam, res.returncode == 0,
                        (res.stderr or "").strip().splitlines()[:4])
    index = (tmp / "index.html").read_text(encoding="utf-8")
    _controleer(fouten, "Voorpagina: geleende prijs heeft een ~", "~&euro; 7.50" in index)
    _controleer(fouten, "Voorpagina: tabblad Alles aanwezig", 'data-key="alles"' in index)
    _controleer(fouten, "Voorpagina: labels aanwezig",
                all(x in index for x in ('class="lbl nieuw"', 'class="badge daling"', 'class="lbl hint"')))


def draai():
    """Voert alle controles uit. Geeft een lijst met foutmeldingen terug
    (leeg = alles in orde)."""
    fouten = []
    tmp = Path(tempfile.mkdtemp(prefix="zelftest_"))
    logging.disable(logging.INFO)             # de testpagina's niet in het logboek melden
    try:
        for test in (_test_untappd_menu, _test_webshops, _test_matching):
            try:
                test(fouten)
            except Exception as e:                       # een crash is ook een mislukte test
                fouten.append("%s crashte: %r" % (test.__name__, e))
        for test in (_test_scoring, _test_paginas):
            try:
                test(fouten, tmp)
            except Exception as e:
                fouten.append("%s crashte: %r" % (test.__name__, e))
    finally:
        logging.disable(logging.NOTSET)
        shutil.rmtree(tmp, ignore_errors=True)
    return fouten


if __name__ == "__main__":
    resultaat = draai()
    print("Zelftest: %s" % ("GESLAAGD" if not resultaat else "%d fout(en)" % len(resultaat)))
    for f in resultaat:
        print("  -", f)
