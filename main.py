# -*- coding: utf-8 -*-
"""
Bierscraper - haalt bierdata van 5 webshops en zet die in één Excelbestand.

Gebruik:
    python main.py                  # alle shops, met cache
    python main.py --no-cache       # alles vers ophalen
    python main.py --site hopsandhopes debiersalon   # alleen deze shops
    python main.py --debug          # extra logging
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import config
import excel_builder
import html_builder
import hopsandhopes
import lightspeed
import shopify
import woocommerce
import bierloods22
import bierbrigadier
import drankgigant

SCRAPERS = {
    "shopify": shopify.scrape,
    "lightspeed": lightspeed.scrape,
    "hopsandhopes": hopsandhopes.scrape,
    "woocommerce": woocommerce.scrape,
    "bierloods22": bierloods22.scrape,
    "bierbrigadier": bierbrigadier.scrape,
    "drankgigant": drankgigant.scrape,
}


def main():
    parser = argparse.ArgumentParser(description="Bierscraper")
    parser.add_argument("--site", nargs="*", help="alleen deze site-keys scrapen")
    parser.add_argument("--no-cache", action="store_true", help="cache negeren")
    parser.add_argument("--debug", action="store_true", help="uitgebreide logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("bierscraper")

    if args.no_cache:
        config.CACHE_MAX_AGE_HOURS = 0

    sites = config.SITES
    if args.site:
        sites = [s for s in sites if s["key"] in args.site]
        if not sites:
            log.error("Onbekende site-key(s). Beschikbaar: %s",
                      ", ".join(s["key"] for s in config.SITES))
            sys.exit(1)

    all_beers = {}
    for site in sites:
        log.info("=== %s ===", site["label"])
        try:
            beers = SCRAPERS[site["type"]](site)
        except Exception:
            log.exception("Scrapen van %s mislukt; site wordt overgeslagen", site["label"])
            beers = []
        all_beers[site["key"]] = beers
        # ruwe data ook als JSON bewaren, handig voor debugging/finetunen
        raw_path = Path("docs") / f"raw_{site['key']}.json"
        raw_path.parent.mkdir(exist_ok=True)
        raw_path.write_text(json.dumps(beers, indent=2, ensure_ascii=False), encoding="utf-8")

    import scoring
    filled = scoring.enrich_untappd(all_beers)
    log.info("Untappd-scores geleend van andere shops: %d bieren aangevuld", filled)

    # shops met 'drop_unrefined_broad': brede stijlen die ook na verrijking
    # niet verfijnd konden worden, weglaten (houdt bijv. Drankgigant compact)
    for site in sites:
        if site.get("drop_unrefined_broad") and site["key"] in all_beers:
            before = len(all_beers[site["key"]])
            all_beers[site["key"]] = [
                b for b in all_beers[site["key"]] if b.get("stijl") in config.STYLES
            ]
            log.info("%s: %d brede/onverfijnde bieren weggelaten",
                     site["label"], before - len(all_beers[site["key"]]))

    wb = excel_builder.build_workbook(all_beers, sites)
    out = Path(config.OUTPUT_FILE)
    out.parent.mkdir(exist_ok=True)
    wb.save(out)

    # Voor GitHub Pages: mobiele webpagina + Excel in docs/
    docs = Path("docs")
    docs.mkdir(exist_ok=True)
    wb.save(docs / "bieroverzicht.xlsx")
    html_builder.build_html(all_beers, sites, docs / "index.html")

    total = sum(len(v) for v in all_beers.values())
    log.info("Klaar: %d bieren -> %s en docs/index.html", total, out.resolve())


if __name__ == "__main__":
    main()
