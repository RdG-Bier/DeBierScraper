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
import upload_pagina
import hopsandhopes
import shopify
import woocommerce
import bierloods22
import bierbrigadier
import drankgigant
import untappd_lookup
import bewaking
import bronnen
import onderweg
import zelftest
import combi
import untappd_profiel
import utils
import websearch

SCRAPERS = {
    "shopify": shopify.scrape,
    "hopsandhopes": hopsandhopes.scrape,
    "woocommerce": woocommerce.scrape,
    "bierloods22": bierloods22.scrape,
    "bierbrigadier": bierbrigadier.scrape,
    "combi": combi.scrape,
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

    # Zelftest: controleert de scraper op opgeslagen echte voorbeelden. Bij een
    # fout wordt er niet gepubliceerd; de vorige pagina blijft dan staan.
    fouten = zelftest.draai()
    if fouten:
        for f in fouten:
            log.error("ZELFTEST MISLUKT: %s", f)
        if getattr(config, "ZELFTEST_BLOKKEERT", True):
            log.error("Er wordt NIET gepubliceerd; de vorige pagina blijft staan. "
                      "(Zet ZELFTEST_BLOKKEERT = False in config.py om toch door te gaan.)")
            sys.exit(1)
    else:
        log.info("Zelftest geslaagd")

    overgeslagen = [s["label"] for s in sites if s.get("enabled") is False]
    if overgeslagen:
        log.info("Uitgeschakeld in config.py, wordt overgeslagen: %s",
                 ", ".join(overgeslagen))
    sites = [s for s in sites if s.get("enabled") is not False]

    all_beers = {}
    status = bewaking.laad_status()
    for site in sites:
        log.info("=== %s ===", site["label"])
        try:
            beers = SCRAPERS[site["type"]](site)
        except Exception:
            log.exception("Scrapen van %s mislukt; site wordt overgeslagen", site["label"])
            beers = []
        # vangnet: bij 0 of een halvering de vorige gegevens aanhouden
        beers, vangnet_actief = bewaking.controleer(site, beers, status)
        all_beers[site["key"]] = beers
        # vastleggen wat de shop ZELF aanlevert (voor de legenda), vóór het aanvullen
        site["_dekking"] = bronnen.dekking(beers)
        # ruwe data ook als JSON bewaren, handig voor debugging/finetunen.
        # Bij een actief vangnet NIET overschrijven: de vorige ronde blijft de maatstaf.
        if not vangnet_actief:
            raw_path = Path("docs") / f"raw_{site['key']}.json"
            raw_path.parent.mkdir(exist_ok=True)
            raw_path.write_text(json.dumps(beers, indent=2, ensure_ascii=False), encoding="utf-8")

    # cadeau-/proef-/mixpakketten zijn geen individuele bieren: geen
    # Untappd-score mogelijk en niet zinvol in het overzicht -> weglaten
    # (na het bewaren van de ruwe data, zodat die compleet blijft)
    for key, beers in all_beers.items():
        packs = [b for b in beers if utils.is_gift_pack(b.get("naam"))]
        if packs:
            all_beers[key] = [b for b in beers if b not in packs]
            log.info("%s: %d pakket(ten) weggelaten (o.a. %r)",
                     key, len(packs), packs[0].get("naam"))

    import scoring
    # shops met verouderde scores in de webshop: die scores niet gebruiken
    for site in sites:
        if site.get("score_onbetrouwbaar") and all_beers.get(site["key"]):
            n_db = scoring.negeer_shopscores(all_beers[site["key"]])
            log.info("%s: meegeleverde Untappd-scores genegeerd (verouderd); %d verouderde "
                     "scores ook uit de bierdatabase gehaald", site["label"], n_db)
    n_br = scoring.vul_brouwerijen_aan(all_beers)
    log.info("Brouwerij afgeleid uit de productnaam bij %d bieren", n_br)
    # per shop bijhouden wat er wanneer gezien is (labels 'nieuw'/'prijs gedaald', Onderweg)
    scoring.werk_historie_bij(all_beers)
    filled = scoring.enrich_untappd(all_beers)
    log.info("Untappd-scores geleend van andere shops: %d bieren aangevuld", filled)

    # shops met 'untappd_lookup': ontbrekende scores rechtstreeks op
    # untappd.com opzoeken (gelimiteerd en gecachet; zie untappd_lookup.py)
    untappd_lookup.search_fn = websearch.search
    for site in sites:
        if site.get("untappd_lookup") and all_beers.get(site["key"]):
            beers = all_beers[site["key"]]
            try:
                untappd_lookup.enrich_beers(beers, site["key"])
            except Exception:
                log.exception("Untappd-lookup voor %s mislukt; verder zonder",
                              site["label"])

            # Scorefilter alleen toepassen als er DAADWERKELIJK scores bekend
            # zijn voor een substantieel deel. Anders (bijv. zoekmachine plat)
            # zouden we het hele tabblad leegvegen -> dan liever alles tonen.
            with_score = [b for b in beers if b.get("untappd") is not None]
            coverage = len(with_score) / max(1, len(beers))
            if site.get("untappd_min_filter") and coverage >= config.MIN_SCORE_COVERAGE:
                before = len(beers)
                # score onbekend? -> behouden (twijfel valt in het voordeel van
                # het bier). Alleen expliciet TE LAGE scores weglaten.
                all_beers[site["key"]] = [
                    b for b in beers
                    if b.get("untappd") is None or b["untappd"] >= config.MIN_UNTAPPD
                ]
                log.info("%s: scorefilter toegepast (dekking %.0f%%), %d te lage "
                         "bieren weggelaten", site["label"], coverage * 100,
                         before - len(all_beers[site["key"]]))
            elif site.get("untappd_min_filter"):
                log.warning("%s: scorefilter OVERGESLAGEN - te weinig scores "
                            "gevonden (dekking %.0f%%), zoekmachine mogelijk "
                            "geblokkeerd; alle bieren blijven staan",
                            site["label"], coverage * 100)

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

    # Shops zonder eigen prijzen (Untappd-venue-menu's zoals De Bierschuur):
    # laagste prijs van hetzelfde bier bij een andere shop lenen.
    for s in sites:
        if s.get("leen_prijzen") and s["key"] in all_beers:
            scoring.leen_prijzen(all_beers, {s["key"]}, voorkeur=s.get("prijs_bron"))

    # Untappd-profiel: markeer wat je al gehad hebt en wat in voorraad staat
    try:
        untappd_profiel.synchroniseer(all_beers)
    except Exception:
        log.exception("Untappd-profielkoppeling mislukt; verder zonder markering")

    wb = excel_builder.build_workbook(all_beers, sites)
    out = Path(config.OUTPUT_FILE)
    out.parent.mkdir(exist_ok=True)
    wb.save(out)

    # Voor GitHub Pages: mobiele webpagina + Excel in docs/
    docs = Path("docs")
    docs.mkdir(exist_ok=True)
    wb.save(docs / "bieroverzicht.xlsx")
    html_builder.build_html(all_beers, sites, docs / "index.html")
    upload_pagina.bouw(docs / "lijsten.html")
    upload_pagina.schrijf_bekende_bieren(all_beers, docs / "bekende_bieren.json")
    try:
        onderweg.schrijf_status()
        onderweg.bouw(docs / "onderweg.html", sites)
    except Exception:
        log.exception("Onderweg-pagina bijwerken mislukt; de rest is wel gepubliceerd")
    bewaking.bewaar_status(status)

    total = sum(len(v) for v in all_beers.values())
    log.info("Klaar: %d bieren -> %s en docs/index.html", total, out.resolve())


if __name__ == "__main__":
    main()
