# Bierscraper

Scrapt bierdata van 5 webshops en zet die per shop in een tabblad van één
Excelbestand, inclusief score (0-100), prijsvergelijking met de andere shops
en voorwaardelijke opmaak.

## Shops
| Shop | Techniek | Betrouwbaarheid |
|---|---|---|
| De Biersalon | Shopify `/products.json` | Hoog (gestructureerde data) |
| Beer Republic | Shopify `/products.json` | Hoog |
| Bierloods22 | Lightspeed: sitemap + productpagina's | Middel (HTML-parsing) |
| Beerdome | Lightspeed: sitemap + productpagina's | Middel |
| Hops & Hopes | Maatwerk: listingpagina's | Middel |

## Installatie (Windows)
1. Installeer Python 3.10+ via python.org (vink "Add to PATH" aan).
2. Open PowerShell in deze map en voer uit:
   ```
   pip install -r requirements.txt
   ```

## Gebruik
```
python main.py                    # alles scrapen
python main.py --no-cache         # cache negeren, alles vers
python main.py --site hopsandhopes debiersalon   # alleen deze shops
python main.py --debug            # uitgebreide logging
```
Resultaat: `output/bieroverzicht.xlsx` + per shop een `output/raw_<shop>.json`
met de ruwe data (handig om te controleren wat er gevonden is).

**Let op:** de eerste run van de Lightspeed-shops (Bierloods22, Beerdome)
duurt lang: elke productpagina wordt apart opgehaald met een nette pauze van
0,8 sec. Reken op 30-60 min per shop. Dankzij de cache zijn volgende runs
binnen `CACHE_MAX_AGE_HOURS` (standaard 20 uur) veel sneller.

## Hoe de filters werken
- **Stijl**: alleen bieren waarvan de stijl matcht met de lijst in
  `config.STYLES`. Matching is fuzzy op tokenniveau; shop-specifieke
  benamingen kun je toevoegen aan `STYLE_ALIASES`.
- **Untappd**: score >= 4.00 óf onbekend (instelbaar via `MIN_UNTAPPD` en
  `INCLUDE_UNKNOWN_UNTAPPD`).
- **Voorraad**: alleen leverbare bieren (Shopify: `available`-vlag;
  HTML-shops: geen "uitverkocht"-tekst op de pagina).
- **Kolommen**: alleen velden die de shop daadwerkelijk aanbiedt. Dit wordt
  bij elke run opnieuw bepaald, dus als een shop bijv. later Untappd-scores
  toevoegt, verschijnt die kolom vanzelf.

## De score (0-100)
Gewichten staan in `config.WEIGHTS` (standaard: stijl 30, Untappd 35,
aantal ratings 15, prijs 20):
1. **Stijl**: "sterke voorkeur" = vol gewicht, gewone gewenste stijl = 50%.
2. **Untappd-score**: lineair van 4.00 (0%) naar 4.60 (100%). Onbekend =
   45% van het gewicht, zodat nieuwe releases niet onderaan bungelen.
3. **Aantal ratings**: logaritmisch met plafond op 5.000, zodat een score
   met veel check-ins zwaarder telt dan één met 8 ratings.
4. **Prijs**: genormaliseerd naar **euro per liter** (eerlijker dan absolute
   prijs bij 33cl vs 44cl blikken; uitschakelen via `PRICE_PER_LITER`).
   Genormaliseerd over alle shops samen, zodat scores tussen tabbladen
   vergelijkbaar zijn.

Suggesties om later te overwegen:
- Een kleine bonus voor bieren die maar bij één shop verkrijgbaar zijn.
- Een betrouwbaarheidscorrectie: 4.30 met 2.000 ratings > 4.45 met 40 ratings
  (bayesiaans gemiddelde).
- ABV meewegen als je dikke stouts extra wilt belonen.

## Prijsvergelijking tussen shops
Bieren worden gematcht op genormaliseerde `brouwerij + naam` (inhoud,
verpakking en leestekens worden genegeerd), met een fuzzy fallback
(drempel `FUZZY_MATCH_THRESHOLD` = 0.90). Voorwaardelijke opmaak:
- **Rood**: prijs bij de andere shop is hoger dan hier.
- **Felgroen**: prijs bij de andere shop is lager (daar kopen dus!).

## Finetunen als een shop niet goed geparsed wordt
1. Draai `python main.py --site <key> --debug` en bekijk `output/raw_<key>.json`.
2. HTML-parsing bijstellen? De selectors staan per platform in
   `lightspeed.py` en `hopsandhopes.py` (goed becommentarieerd).
3. Mis je een stijlmapping? Voeg een regel toe aan `STYLE_ALIASES` in
   `config.py`.

## Op je iPhone + delen met vrienden (GitHub Pages)
De scraper draait niet op een telefoon, maar kan gratis automatisch in de
cloud draaien via GitHub Actions. Je krijgt dan een webpagina (mobiel
geoptimaliseerd) + downloadbare Excel op een vaste link die je kunt delen.

Eenmalige setup (op je pc, ±10 min):
1. Maak een gratis account op github.com en maak een nieuwe **public** repository
   aan, bijv. `bierscraper`. (Public is nodig voor gratis GitHub Pages.)
2. Upload de inhoud van deze map naar de repository (via "uploading an
   existing file" kan dat zonder git-kennis, sleep alle bestanden erin;
   let op dat de map `.github/workflows/scrape.yml` meekomt).
3. Ga naar **Settings → Pages** en kies bij "Branch": `main` en map `/docs`,
   klik Save.
4. Ga naar het tabblad **Actions**, open "Scrape en publiceer" en klik
   **Run workflow** voor de eerste run (kan 1-2 uur duren door de nette
   vertraging bij de Lightspeed-shops).

Daarna:
- Je pagina staat op `https://<jouwnaam>.github.io/bierscraper/`
  → open op je iPhone, zet op je beginscherm, deel de link met vrienden.
- De Excel is downloadbaar via de knop bovenaan de pagina.
- **Automatisch verversen**: elke ochtend rond 06:00-07:00.
- **Handmatig verversen**: GitHub-app (of github.com in Safari) →
  Actions → Run workflow.

Kanttekening: sommige shops blokkeren soms verkeer vanaf datacenters.
Werkt een shop niet vanuit GitHub Actions maar wel lokaal, laat het weten,
dan kijken we naar een alternatief.

## Nette scraping
Het script wacht 0,8 sec tussen requests, gebruikt een cache en identificeert
zich met een eigen User-Agent. Houd het bij persoonlijk gebruik en draai het
niet vaker dan nodig; controleer bij twijfel de voorwaarden van de shops.
