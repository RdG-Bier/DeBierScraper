# -*- coding: utf-8 -*-
"""
Bronvermelding per shop: waar komen prijs, score, aantal beoordelingen en
foto vandaan? Wordt gebruikt voor het cijfertje achter de shopnaam op de
tabbladen en voor de uitklapbare legenda op de pagina.

De indeling wordt AFGELEID uit config.SITES (type + vlaggen), zodat de legenda
vanzelf klopt als er een shop bijkomt of een instelling verandert.
"""

import html

import config

SUPERSCRIPT = {1: "\u00b9", 2: "\u00b2", 3: "\u00b3", 4: "\u2074", 5: "\u2075"}

# nummer -> (titel, [(onderdeel, uitleg), ...])
CATEGORIEEN = {
    1: ("Webshop met eigen Untappd-score", [
        ("Prijs", "de actuele verkoopprijs uit de webshop zelf."),
        ("Score", "staat bij het bier in de webshop (door de winkel overgenomen van Untappd)."),
        ("Aantal beoordelingen", "uit de webshop als die het vermeldt; anders van Untappd "
                                 "of van een andere shop met hetzelfde bier."),
        ("Foto", "productfoto van de webshop."),
        ("Assortiment", "wat de webshop op dit moment aanbiedt."),
    ]),
    2: ("Webshop zonder Untappd-score", [
        ("Prijs", "de actuele verkoopprijs uit de webshop zelf."),
        ("Score en aantal", "de webshop toont geen score. Die wordt opgezocht via de "
                            "zoekfunctie van Untappd, of overgenomen van een andere shop met "
                            "hetzelfde bier. Een zoekresultaat wordt 7 dagen onthouden. "
                            "Let op: bij een verkeerde zoektreffer hoort de score bij een ander bier."),
        ("Foto", "productfoto van de webshop."),
        ("Assortiment", "wat de webshop op dit moment aanbiedt."),
    ]),
    3: ("Untappd-menu met prijzen", [
        ("Prijs", "door de winkel zelf ingevuld in hun Untappd-menu."),
        ("Score", "rechtstreeks van Untappd."),
        ("Aantal beoordelingen", "staat niet op de menupagina; aangevuld via de "
                                 "Untappd-zoekfunctie of een andere shop."),
        ("Foto", "het etiket zoals het op Untappd staat."),
        ("Assortiment", "wat de winkel op Untappd heeft gezet. Er is geen webshop; "
                        "het menu kan achterlopen op wat er echt in de winkel ligt."),
    ]),
    4: ("Untappd-menu zonder prijzen", [
        ("Prijs", "GELEEND, herkenbaar aan de ~ ervoor. Het menu toont geen prijzen; "
                  "getoond wordt de prijs van hetzelfde bier bij een andere shop of uit de "
                  "bierdatabase. Het is dus een schatting, geen echte winkelprijs. "
                  "Bieren die nergens anders bekend zijn, hebben geen prijs."),
        ("Score", "rechtstreeks van Untappd."),
        ("Aantal beoordelingen", "staat niet op de menupagina; aangevuld via de "
                                 "Untappd-zoekfunctie of een andere shop."),
        ("Foto", "het etiket zoals het op Untappd staat."),
        ("Assortiment", "wat de winkel op Untappd heeft gezet. Er is geen webshop; "
                        "het menu kan achterlopen op wat er echt in de winkel ligt."),
    ]),
    5: ("Webshop, aangevuld vanuit het Untappd-menu", [
        ("Assortiment", "wat de webshop op dit moment aanbiedt. De webshop is leidend, "
                        "omdat het Untappd-menu kan achterlopen."),
        ("Prijs", "de actuele verkoopprijs uit de webshop."),
        ("Score en aantal", "van Untappd als het bier ook in het Untappd-menu van de winkel "
                            "staat; anders opgezocht via de Untappd-zoekfunctie."),
        ("Stijl en brouwerij", "exacte stijl van Untappd als het bier in het menu staat; "
                               "de brouwerij komt uit de productgegevens van de webshop."),
        ("Foto", "productfoto van de webshop."),
    ]),
}

ALGEMEEN = [
    "Staat hetzelfde bier bij meerdere shops, dan krijgt het overal dezelfde "
    "Untappd-score: die van de bron met de meeste beoordelingen.",
    "Ontbreekt een score, foto of inhoud, dan wordt die aangevuld uit de eigen "
    "bierdatabase (alles wat de scraper ooit heeft gezien).",
    "Een ~ voor de prijs betekent: geleende prijs (schatting).",
    "NIEUW = dit bier is in de afgelopen %d dagen voor het eerst bij deze shop gezien. "
    "'was €...' = de prijs is in de afgelopen %d dagen gedaald." % (
        config.NIEUW_DAGEN, config.PRIJSDALING_DAGEN),
    "Een hartje = jij gaf een ander bier van dezelfde brouwerij in dezelfde stijl een "
    "%.2f (New England / Hazy telt daarbij niet mee: Triple IPA en Triple NEIPA horen "
    "bij elkaar). Dat levert %d bonuspunten op." % (
        config.EIGEN_RATING_BONUS["vanaf"], config.EIGEN_RATING_BONUS["punten"]),
    "'≈ zelfde naam als ...' = een bier met dezelfde naam van een andere brouwerij staat "
    "in je lijsten (bijvoorbeeld een collab die bij twee brouwerijen is gebrouwen). "
    "De kaart wordt dan bewust niet gekleurd.",
    "Tabblad 'Alles' toont elk bier één keer, bij de shop met de laagste echte prijs "
    "(geleende prijzen tellen daarbij niet mee).",
    "Prijs per liter wordt alleen berekend als de inhoud van het blik of de fles bekend is; "
    "anders staat het bier bij die sortering onderaan.",
    "Prijsvergelijking onder een bier: rood = die andere shop is duurder, "
    "fel groen = die andere shop is goedkoper.",
    "Groene kaart = al gehad. Gele kaart = in voorraad (R of H&R).",
]


def categorie(site):
    """Bepaalt uit de config hoe de data van deze shop is opgebouwd (1-5)."""
    soort = site.get("type")
    if soort == "combi":
        return 5
    if soort == "bierbrigadier":          # Untappd-venuemenu
        if site.get("heeft_prijzen") is False or site.get("leen_prijzen"):
            return 4
        return 3
    return 2 if site.get("untappd_lookup") else 1


def tabteken(site):
    return SUPERSCRIPT.get(categorie(site), "")


def dekking(beers):
    """Welk deel van de bieren leverde de shop ZELF met dit gegeven aan?
    Moet direct na het scrapen worden berekend, v\u00f3\u00f3r het aanvullen."""
    n = len(beers)
    if not n:
        return None
    def pct(veld):
        return round(100 * sum(1 for b in beers if b.get(veld) not in (None, "")) / n)
    return {"n": n, "prijs": pct("prijs"), "score": pct("untappd"),
            "aantal": pct("untappd_aantal"), "foto": pct("afbeelding"),
            "brouwerij": pct("brouwerij")}


def _bijzonderheden(site, labels):
    uit = []
    if site.get("_waarschuwing"):
        uit.append("LET OP: " + site["_waarschuwing"])
    if site.get("prijs_bron"):
        uit.append("prijs bij voorkeur overgenomen van %s; anders de laagste prijs elders"
                   % labels.get(site["prijs_bron"], site["prijs_bron"]))
    elif site.get("leen_prijzen"):
        uit.append("geleende prijs = de laagste prijs elders of uit de database")
    if site.get("type") == "bierloods22":
        uit.append("uitverkochte bieren worden weggelaten (voorraad per bier gecontroleerd)")
        uit.append("exacte stijl, inhoud, ABV en land komen uit de productgegevens per bier")
    if site.get("score_onbetrouwbaar"):
        uit.append("de score die de webshop zelf vermeldt wordt NIET gebruikt, omdat die niet "
                   "wordt bijgewerkt; de actuele score komt van een andere shop of wordt opgezocht")
    if site.get("type") == "drankgigant":
        uit.append("de brouwerij wordt afgeleid uit het begin van de productnaam")
    if site.get("untappd_min_filter"):
        uit.append("alleen bieren met een gevonden Untappd-score van %.2f of hoger"
                   % config.MIN_UNTAPPD)
    if site.get("drop_unrefined_broad"):
        uit.append("bieren zonder precieze substijl worden weggelaten")
    return uit


def legenda_html(sites):
    """HTML voor de uitklapbare legenda (inhoud van het paneel)."""
    e = html.escape
    labels = {s["key"]: s["label"] for s in sites}
    per_cat = {}
    for s in sites:
        per_cat.setdefault(categorie(s), []).append(s)

    delen = ['<p class="mini">Het kleine cijfer achter elke shopnaam verwijst naar '
             'de manier waarop de gegevens van die shop zijn opgebouwd.</p>']
    for nr in sorted(per_cat):
        titel, regels = CATEGORIEEN[nr]
        shops = ", ".join(e(s["label"]) for s in per_cat[nr])
        delen.append('<div class="leg-cat"><div class="leg-kop"><span class="leg-nr">%d</span> '
                     '%s</div><div class="leg-shops">%s</div><ul>' % (nr, e(titel), shops))
        for onderdeel, uitleg in regels:
            delen.append("<li><b>%s:</b> %s</li>" % (e(onderdeel), e(uitleg)))
        delen.append("</ul>")
        for s in per_cat[nr]:
            extra = _bijzonderheden(s, labels)
            d = s.get("_dekking")
            if d:
                extra.append("levert zelf aan: prijs %d%%, score %d%%, aantal %d%%, "
                             "foto %d%%, brouwerij %d%% (van %d bieren)"
                             % (d["prijs"], d["score"], d["aantal"], d["foto"],
                                d["brouwerij"], d["n"]))
            if extra:
                delen.append('<p class="leg-shop"><b>%s:</b> %s.</p>'
                             % (e(s["label"]), e("; ".join(extra))))
        delen.append("</div>")

    w = config.WEIGHTS
    delen.append('<div class="leg-cat"><div class="leg-kop">Voor alle shops</div><ul>')
    for regel in ALGEMEEN:
        delen.append("<li>%s</li>" % e(regel))
    delen.append("<li>%s</li>" % e(
        "Het getal rechtsboven elk bier (0-100) is de totaalscore: stijl %d, "
        "Untappd-score %d, aantal beoordelingen %d en prijs per liter %d punten, "
        "plus bonuspunten voor je favoriete stijlen bij een scherpe prijs."
        % (w.get("style", 0), w.get("untappd", 0), w.get("ratings", w.get("count", 0)),
           w.get("price", 0))))
    delen.append("</ul></div>")
    return "".join(delen)
