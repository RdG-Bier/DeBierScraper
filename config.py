# -*- coding: utf-8 -*-
"""
Centrale configuratie voor de bierscraper.
Alles wat je wilt finetunen (stijlen, gewichten, sites) staat hier.
"""

VERSION = "v16"  # wordt getoond op de webpagina; wijzigt mee met elke nieuwe zip

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
        "collection_url": "https://debiersalon.nl/en/collections/bieren",
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
    "style": 30,     # sterke voorkeur = vol gewicht, gewone stijl = de helft
    "untappd": 35,   # 4.00 -> ondergrens, UNTAPPD_TOP -> vol gewicht
    "count": 15,     # logaritmisch: meer ratings = betrouwbaarder
    "price": 20,     # goedkoopste (per liter) = vol gewicht
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
    {"style": "IPA - Triple", "exact": True, "max_price": 9.0, "bonus": 24},
    {"style": "IPA - Quadruple", "exact": True, "max_price": 10.0, "bonus": 24},
    {"style": "Stout", "exact": False, "min_untappd": 4.30, "max_price": 14.0, "bonus": 16},
    # topdeal: elke gewenste stijl met hoge score voor weinig geld
    {"style": "", "exact": False, "min_untappd": 4.30, "max_price": 10.0, "bonus": 12},
]

# ---------------------------------------------------------------------------
# Untappd-lookup (voor shops met "untappd_lookup": True, zoals Drankgigant)
# ---------------------------------------------------------------------------
UNTAPPD_LOOKUP_MAX = 40   # max. nieuwe opzoekingen per run (2 requests per bier)
UNTAPPD_CACHE_DAYS = 7    # opgezochte bieren zo lang niet opnieuw opvragen
