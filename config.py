# -*- coding: utf-8 -*-
"""
Centrale configuratie voor de bierscraper.
Alles wat je wilt finetunen (stijlen, gewichten, sites) staat hier.
"""

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
    },
    {
        "key": "beerrepublic",
        "label": "Beer Republic",
        "type": "shopify",
        "base_url": "https://beerrepublic.eu",
    },
    {
        "key": "bierloods22",
        "label": "Bierloods22",
        "type": "lightspeed",
        "base_url": "https://www.bierloods22.nl",
        "sitemap_url": "https://www.bierloods22.nl/sitemap.xml",
    },
    {
        "key": "beerdome",
        "label": "Beerdome",
        "type": "woocommerce",
        "base_url": "https://www.beerdome.nl",
        "api_url": "https://www.beerdome.nl/wp-json/wc/store/v1/products",
    },
    {
        "key": "hopsandhopes",
        "label": "Hops & Hopes",
        "type": "hopsandhopes",
        "base_url": "https://www.hopsandhopes.nl",
        "listing_url": "https://www.hopsandhopes.nl/bieren",
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
PRICE_CAP_EUR = 20.0        # boven deze absolute prijs wordt een bier veel minder interessant
PRICE_CAP_MALUS = 20        # puntenaftrek voor bieren boven het prijsplafond

# ---------------------------------------------------------------------------
# Techniek
# ---------------------------------------------------------------------------
REQUEST_DELAY = 0.8          # seconden tussen requests (netjes blijven!)
CACHE_MAX_AGE_HOURS = 20     # HTML/JSON-cache; zet op 0 om altijd vers op te halen
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BierScraper/1.0 (persoonlijk gebruik)"
OUTPUT_FILE = "output/bieroverzicht.xlsx"
FUZZY_MATCH_THRESHOLD = 0.90  # voor het matchen van hetzelfde bier tussen shops
