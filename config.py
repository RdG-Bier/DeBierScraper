# -*- coding: utf-8 -*-
"""
Centrale configuratie voor de bierscraper.
Alles wat je wilt finetunen (stijlen, gewichten, sites) staat hier.
"""

VERSION = "v31"  # wordt getoond op de webpagina; wijzigt mee met elke nieuwe zip

# ---------------------------------------------------------------------------
# Websites
# type bepaalt welke scraper gebruikt wordt:
#   shopify    -> leest /products.json (zeer betrouwbaar)
#   lightspeed -> leest sitemap.xml en daarna elke productpagina (HTML)
#   hopsandhopes -> leest de listingpagina's (HTML)
# ---------------------------------------------------------------------------
SITES = [
    {
        "key": "debiersalon",
        "label": "De Biersalon",
        "type": "shopify",
        "base_url": "https://debiersalon.nl",
        # Vangnet: JSON-feeds per collectie. De hoofdfeed (/products.json)
        # bleek producten te missen die wel gewoon op voorraad staan.
        # Deze endpoints zijn standaard Shopify en kosten weinig requests.
        "collections": [
            "bieren", "triple-ipa", "double-ipa", "ipa", "stout",
            "wild-ale", "fruit", "mede", "sale", "untappd-toppers",
        ],
        # Collectiepagina's (HTML) waar de exacte Untappd-stijl + score per
        # bier op de tegels staat. Meerdere kleinere collecties i.p.v. één
        # hele grote, zodat elke pagina ook echt bereikt wordt.
        "tile_collections": [
            "triple-ipa", "double-ipa", "ipa", "india-pale-ale", "stout",
            "porter-1", "barleywine", "wild-ale", "fruit", "saison-1",
            "mede", "barrel-aged", "sale", "untappd-toppers",
            "overige-bierstijlen", "bieren",
        ],
    },
    {
        "key": "bierloods22",
        "label": "Bierloods22",
        "type": "bierloods22",
        "base_url": "https://www.bierloods22.nl",
    },
    {
        "key": "drankgigant",
        "label": "Drankgigant",
        "type": "drankgigant",
        "base_url": "https://www.drankgigant.nl",
        "listing_url": "https://www.drankgigant.nl/bieren",
        # ontbrekende scores rechtstreeks op untappd.com opzoeken
        "untappd_lookup": True,
        # alleen bieren met een gevonden Untappd-score >= MIN_UNTAPPD tonen
        # (Drankgigant heeft veel gewone bieren met een 3.xx-score)
        "untappd_min_filter": True,
        # brede stijlen (Stout/IPA/Sour) die ook na verrijking + lookup geen
        # substijl hebben, worden uit dit tabblad weggelaten
        "drop_unrefined_broad": True,
    },
    {
        "key": "bierbrigadier",
        "label": "Bierbrigadier",
        "type": "bierbrigadier",
        "base_url": "http://www.debierbrigadier.nl",
        "menu_url": "https://untappd.com/v/de-bierbrigadier-tilburg/5523441",
    },
    {
        "key": "hopsandhopes",
        "label": "Hops & Hopes",
        "type": "hopsandhopes",
        "base_url": "https://www.hopsandhopes.nl",
        "listing_url": "https://www.hopsandhopes.nl/bieren",
    },
    {
        "key": "beerrepublic",
        "label": "Beer Republic",
        "type": "shopify",
        "base_url": "https://beerrepublic.eu",
    },
]

# ---------------------------------------------------------------------------
# Gewenste bierstijlen. Key = canonieke (Untappd-)naam, value = True als
# "sterke voorkeur". Matching is fuzzy: hoofdletters, streepjes en volgorde
# maken niet uit; zie utils.match_style().
# ---------------------------------------------------------------------------
STYLES = {
    "Sour - Fruited Gose": False,
    "Stout - Imperial / Double": False,
    "Stout - Russian Imperial": False,
    "Sour - Other Gose": False,
    "IPA - Imperial / Double New England / Hazy": False,
    "IPA - Triple": True,
    "IPA - New England / Hazy": False,
    "Sour - Smoothie / Pastry": True,
    "Sour - Other": False,
    "IPA - Triple New England / Hazy": True,
    "IPA - Imperial / Double": True,
    "Stout - Imperial / Double Coffee": False,
    "Stout - Imperial / Double Pastry": True,
    "Sour - Traditional Gose": False,
    "Stout - Pastry": False,
    "Sour - Fruited": False,
    "IPA - Imperial / Double Milkshake": False,
    "Stout - Imperial / Double Milk": False,
    "IPA - Quadruple": True,
    "Stout - Imperial / Double Oatmeal": False,
    "Mede": False,
    "Mead - Braggot": False,
    "Mead - Melomel": False,
    "Mead - Metheglin": False,
    "Mead - Cyser": False,
}

# Extra vertaal-/aliastabel: hoe shops een stijl soms noemen -> canonieke naam.
# Vul gerust aan als een shop eigen benamingen gebruikt.
STYLE_ALIASES = {
    "triple ipa": "IPA - Triple",
    "tipa": "IPA - Triple",
    "double ipa": "IPA - Imperial / Double",
    "dipa": "IPA - Imperial / Double",
    "imperial ipa": "IPA - Imperial / Double",
    "quadruple ipa": "IPA - Quadruple",
    "hazy ipa": "IPA - New England / Hazy",
    "neipa": "IPA - New England / Hazy",
    "new england ipa": "IPA - New England / Hazy",
    "imperial stout": "Stout - Imperial / Double",
    "double stout": "Stout - Imperial / Double",
    "russian imperial stout": "Stout - Russian Imperial",
    "pastry stout": "Stout - Pastry",
    "imperial pastry stout": "Stout - Imperial / Double Pastry",
    "fruited sour": "Sour - Fruited",
    "smoothie sour": "Sour - Smoothie / Pastry",
    "pastry sour": "Sour - Smoothie / Pastry",
    "gose": "Sour - Other Gose",
    "fruited gose": "Sour - Fruited Gose",
    "mead": "Mede",
    "mede": "Mede",
    "braggot": "Mead - Braggot",
    "melomel": "Mead - Melomel",
    "metheglin": "Mead - Metheglin",
    "cyser": "Mead - Cyser",
}

# ---------------------------------------------------------------------------
# Untappd-filter: score >= MIN_UNTAPPD of onbekend
# ---------------------------------------------------------------------------
MIN_UNTAPPD = 4.00
INCLUDE_UNKNOWN_UNTAPPD = True

# ---------------------------------------------------------------------------
# Scoregewichten (samen max 100). Zie scoring.py voor de berekening.
# ---------------------------------------------------------------------------
WEIGHTS = {
    "style": 25,     # sterke voorkeur = vol gewicht, gewone stijl = de helft
    "untappd": 35,   # 4.00 -> ondergrens, UNTAPPD_TOP -> vol gewicht
    "count": 10,     # logaritmisch: meer ratings = betrouwbaarder
    "price": 30,     # goedkoopste (per liter) = vol gewicht
}
UNTAPPD_TOP = 4.60          # score waarbij het untappd-deel maximaal is
UNKNOWN_UNTAPPD_FRACTION = 0.45  # onbekende score krijgt 45% van het untappd-gewicht
COUNT_CAP = 5000            # aantal ratings waarbij het count-deel maximaal is
PRICE_PER_LITER = True      # prijs normaliseren naar EUR/liter (eerlijker bij 33cl vs 44cl)
# Vast venster voor de prijscomponent (voorheen min-max over de dataset, maar
# uitschieters zoals cadeauverpakkingen van 1400 EUR/l drukten daarmee alle
# gewone bieren op vrijwel identieke prijspunten):
PRICE_PPL_BEST = 12.0       # <= 12 EUR/liter -> volle prijspunten
PRICE_PPL_WORST = 40.0      # >= 40 EUR/liter -> nul prijspunten
DEFAULT_VOLUME_CL = 44.0    # aanname als de inhoud onbekend is (meest gangbare blikmaat)
PRICE_CAP_EUR = 20.0        # boven deze absolute prijs wordt een bier veel minder interessant
PRICE_CAP_MALUS = 20        # puntenaftrek voor bieren boven het prijsplafond

# ---------------------------------------------------------------------------
# Techniek
# ---------------------------------------------------------------------------
REQUEST_DELAY = 0.8          # seconden tussen requests (netjes blijven!)
CACHE_MAX_AGE_HOURS = 4      # HTML/JSON-cache; korter dan de 6,5u tussen runs, zodat elke run verse data haalt
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BierScraper/1.0 (persoonlijk gebruik)"
OUTPUT_FILE = "output/bieroverzicht.xlsx"
FUZZY_MATCH_THRESHOLD = 0.90  # voor het matchen van hetzelfde bier tussen shops


# ---------------------------------------------------------------------------
# Extra scoregewicht voor specifieke combinaties (bovenop de basisscore,
# eindresultaat blijft geclipt tussen 0 en 100). "exact" = stijl moet precies
# gelijk zijn; anders is een prefix-match voldoende (bijv. alle Stout-stijlen).
# ---------------------------------------------------------------------------
BONUS_RULES = [
    # "family": True -> hele stijlfamilie telt mee, dus 'IPA - Triple' EN
    #   'IPA - Triple New England / Hazy' krijgen dezelfde bonus.
    # max_price -> volledige bonus; taper_price -> bonus loopt daar naar 0.
    #   Zo valt een bier van 9,50 niet ineens van 24 punten naar niets.
    # min_untappd -> volledige bonus; taper_untappd -> loopt daar naar 0.
    {"style": "IPA - Triple", "family": True,
     "max_price": 9.0, "taper_price": 14.0, "bonus": 18},
    {"style": "IPA - Quadruple", "family": True,
     "max_price": 10.0, "taper_price": 16.0, "bonus": 18},
    {"style": "Stout", "family": True,
     "min_untappd": 4.30, "taper_untappd": 4.10,
     "max_price": 14.0, "taper_price": 20.0, "bonus": 12},
    # generieke topdeal: elke gewenste stijl, hoge score, lage prijs
    {"style": "", "min_untappd": 4.30, "taper_untappd": 4.10,
     "max_price": 10.0, "taper_price": 15.0, "bonus": 10},
]

# ---------------------------------------------------------------------------
# Untappd-lookup (voor shops met "untappd_lookup": True, zoals Drankgigant)
# ---------------------------------------------------------------------------
UNTAPPD_LOOKUP_MAX = 250  # max. nieuwe opzoekingen per run (Algolia is 1 snel verzoek/bier)
UNTAPPD_CACHE_DAYS = 7    # opgezochte bieren zo lang niet opnieuw opvragen
# Scorefilter voor Drankgigant pas toepassen als minstens dit deel van de
# bieren een score heeft (anders is de zoekbron waarschijnlijk plat en zouden
# we het hele tabblad ten onrechte leegvegen):
MIN_SCORE_COVERAGE = 0.30


# ---------------------------------------------------------------------------
# Diagnose: van deze producthandles wordt per run in docs/diagnose_<shop>.json
# vastgelegd of ze gevonden zijn en zo niet, waarom ze zijn afgewezen.
# ---------------------------------------------------------------------------
# Alarmdrempel: zoveel tegels verwacht de scraper minimaal per Shopify-shop.
# Vallen ze weg, dan is dat direct zichtbaar in de log i.p.v. stilletjes tot
# verkeerde stijlen en scores te leiden.
MIN_TILES_WARN = 500

TRACE_HANDLES = (
    "arpus-qdh-riwaka-x-citra-cryo-x-mosaic-cryo-x-nectaron-tipa",
)


# ---------------------------------------------------------------------------
# GitHub-gegevens voor de "Ververs nu"-knop op de webpagina. De knop start de
# workflow via de GitHub API; het benodigde token wordt alleen in de browser
# van de gebruiker bewaard en staat dus NIET in de gepubliceerde pagina.
# GITHUB_WORKFLOW = de bestandsnaam van je workflow in .github/workflows/
# ---------------------------------------------------------------------------
GITHUB_OWNER = "RdG-Bier"
GITHUB_REPO = "DeBierScraper"
GITHUB_WORKFLOW = "main.yml"


# ---------------------------------------------------------------------------
# Untappd-profielkoppeling. Het profiel moet openbaar zijn
# (untappd.com/account/privacy -> account NIET op private).
#   - ingecheckte bieren  -> groene achtergrond ("al gehad")
#   - de voorraadlijsten  -> gele achtergrond ("in voorraad")
# ---------------------------------------------------------------------------
UNTAPPD_USER = "RdG-NL"
UNTAPPD_VOORRAAD_LIJSTEN = ("Voorraad R", "Voorraad H & R")
UNTAPPD_MAX_PAGINAS = 120   # 120 x 25 = tot 3000 bieren per lijst
