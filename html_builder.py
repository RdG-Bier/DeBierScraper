# -*- coding: utf-8 -*-
"""
Bouwt een mobielvriendelijke, zelfstandige HTML-pagina (docs/index.html)
met dezelfde data als het Excelbestand: tab per shop, gesorteerd op score,
prijsvergelijking met kleur, zoekveld. Geschikt voor GitHub Pages.
"""

import datetime
import html
import logging

import config
import scoring

log = logging.getLogger("bierscraper")

CSS = """
:root { --groen:#1f4e44; --geel:#fff2cc; --rood:#ffc7ce; --felgroen:#00e676; }
* { box-sizing:border-box; }
body { font-family:-apple-system,'Segoe UI',Arial,sans-serif; margin:0; background:#f5f5f2; color:#222; }
header { background:var(--groen); color:#fff; padding:14px 16px; position:sticky; top:0; z-index:5; }
header h1 { margin:0; font-size:1.15rem; }
header .sub { font-size:.75rem; opacity:.85; margin-top:2px; }
.tabs { display:flex; overflow-x:auto; background:#fff; border-bottom:1px solid #ddd;
        position:sticky; top:56px; z-index:4; -webkit-overflow-scrolling:touch; }
.tabs button { flex:0 0 auto; border:0; background:none; padding:12px 14px; font-size:.85rem;
               border-bottom:3px solid transparent; color:#555; }
.tabs button.active { color:var(--groen); border-bottom-color:var(--groen); font-weight:600; }
.toolbar { padding:10px 12px; }
.toolbar input { width:100%; padding:10px 12px; font-size:1rem; border:1px solid #ccc;
                 border-radius:10px; -webkit-appearance:none; }
.panel { display:none; padding:0 8px 40px; }
.panel.active { display:block; }
.card { background:#fff; border-radius:12px; margin:8px 4px; padding:12px 14px;
        box-shadow:0 1px 3px rgba(0,0,0,.08); }
.card.strong { background:var(--geel); }
.card .top { display:flex; justify-content:space-between; gap:8px; align-items:baseline; }
.card .name { font-weight:600; font-size:.95rem; }
.card .brewery { color:#666; font-size:.8rem; }
.card .score { background:var(--groen); color:#fff; border-radius:8px; padding:2px 8px;
               font-size:.85rem; font-weight:700; white-space:nowrap; }
.card .rechts { display:flex; flex-direction:column; align-items:flex-end; gap:6px; }
.card .label-img { width:56px; height:56px; object-fit:contain; border-radius:8px;
                   background:#fff; border:1px solid #eee; cursor:zoom-in; }
#lightbox { display:none; position:fixed; inset:0; z-index:50;
            background:rgba(0,0,0,.8); align-items:center; justify-content:center; }
#lightbox.open { display:flex; }
#lightbox .box { position:relative; }
#lightbox img { max-width:88vw; max-height:82vh; border-radius:12px; background:#fff;
                padding:8px; box-shadow:0 8px 40px rgba(0,0,0,.5); }
#lightbox .close { position:absolute; top:-14px; right:-14px; width:36px; height:36px;
                   border-radius:50%; border:none; background:#fff; color:#1f4e44;
                   font-size:1.4rem; font-weight:700; cursor:pointer; line-height:36px;
                   box-shadow:0 2px 8px rgba(0,0,0,.3); }
.card .meta { font-size:.78rem; color:#555; margin-top:6px; }
.card .price-row { margin-top:8px; display:flex; flex-wrap:wrap; gap:6px; font-size:.78rem; }
.badge { border-radius:6px; padding:3px 7px; background:#eee; }
.badge.own { background:var(--groen); color:#fff; font-weight:600; }
.badge.hoger { background:var(--rood); }
.badge.lager { background:var(--felgroen); font-weight:600; }
.card a { color:var(--groen); font-size:.8rem; }
.empty { text-align:center; color:#888; padding:30px 0; }
.dl { display:inline-block; margin-top:6px; color:#fff; text-decoration:underline; font-size:.78rem; }
"""

JS = """
function showTab(key){
  document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('active',b.dataset.key===key));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.dataset.key===key));
}
function openImg(src){
  var lb=document.getElementById('lightbox');
  document.getElementById('lightbox-img').src=src;
  lb.classList.add('open');
}
function closeImg(e){
  // sluiten bij klik op de achtergrond of het kruisje, niet op de foto zelf
  if(!e || e.target.id==='lightbox' || e.target.classList.contains('close')){
    document.getElementById('lightbox').classList.remove('open');
    document.getElementById('lightbox-img').src='';
  }
}
document.addEventListener('keydown',function(e){ if(e.key==='Escape') closeImg(); });
function filter(){
  const q=document.getElementById('zoek').value.toLowerCase();
  document.querySelectorAll('.panel.active .card').forEach(c=>{
    c.style.display=c.textContent.toLowerCase().includes(q)?'':'none';
  });
}
"""


def build_html(all_beers, sites, output_path, excel_name="bieroverzicht.xlsx"):
    price_lookup = scoring.build_price_lookup(all_beers)
    now = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")

    tabs, panels = [], []
    for i, site in enumerate(sites):
        beers = sorted(all_beers.get(site["key"], []),
                       key=lambda b: b.get("score") or 0, reverse=True)
        active = " active" if i == 0 else ""
        tabs.append(
            f'<button class="{active.strip()}" data-key="{site["key"]}" '
            f'onclick="showTab(\'{site["key"]}\')">{html.escape(site["label"])} ({len(beers)})</button>'
        )
        cards = "".join(_card(b, site, sites, price_lookup) for b in beers) \
            or '<div class="empty">Geen bieren gevonden</div>'
        panels.append(f'<div class="panel{active}" data-key="{site["key"]}">{cards}</div>')

    doc = f"""<!DOCTYPE html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bieroverzicht</title><style>{CSS}</style></head>
<body>
<header><h1>🍺 Bieroverzicht</h1>
<div class="sub">Bijgewerkt: {now} &middot; score &ge; 4.00 of onbekend &middot; scraper {config.VERSION}</div>
<a class="dl" href="{excel_name}" download>&#11015; Download als Excel</a></header>
<div class="tabs">{''.join(tabs)}</div>
<div class="toolbar"><input id="zoek" type="search" placeholder="Zoek op naam, brouwerij of stijl…" oninput="filter()"></div>
{''.join(panels)}
<div id="lightbox" onclick="closeImg(event)">
  <div class="box"><button class="close" onclick="closeImg(event)">&times;</button>
  <img id="lightbox-img" src="" alt=""></div>
</div>
<script>{JS}</script></body></html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(doc, encoding="utf-8")
    log.info("HTML geschreven naar %s", output_path)


def _card(beer, site, sites, price_lookup):
    e = lambda v: html.escape(str(v)) if v is not None else ""
    meta_parts = [p for p in [
        e(beer.get("stijl")),
        e(beer.get("land")),
        f"{beer['abv']}%" if beer.get("abv") is not None else None,
        f"{beer['inhoud_cl']} cl" if beer.get("inhoud_cl") is not None else None,
        (f"Untappd {beer['untappd']:.2f}"
         + (f" ({beer['untappd_aantal']})" if beer.get("untappd_aantal") else ""))
        if beer.get("untappd") is not None else "Untappd onbekend",
    ] if p]

    own_price = beer.get("prijs")
    badges = []
    if own_price is not None:
        badges.append(f'<span class="badge own">&euro; {own_price:.2f}</span>')
    for other in sites:
        if other["key"] == site["key"]:
            continue
        p = scoring.find_price(beer, price_lookup.get(other["key"], {}))
        if p is None:
            continue
        cls = ""
        if own_price is not None:
            cls = " hoger" if p > own_price else (" lager" if p < own_price else "")
        badges.append(
            f'<span class="badge{cls}">{html.escape(other["label"])}: &euro; {p:.2f}</span>')

    strong = " strong" if beer.get("sterke_voorkeur") else ""
    img = beer.get("afbeelding")
    big = (img or "").replace("_sm.", "_md.").replace("120x120", "640x640") if img else ""
    img_html = (f'<img class="label-img" src="{e(img)}" alt="" loading="lazy" '
                f'onclick="openImg(\'{e(big)}\')" '
                f'onerror="this.style.display=\'none\'">') if img else ""
    return f"""<div class="card{strong}">
  <div class="top"><div><div class="name">{e(beer.get('naam'))}</div>
  <div class="brewery">{e(beer.get('brouwerij'))}</div></div>
  <div class="rechts"><div class="score">{beer.get('score', 0)}</div>{img_html}</div></div>
  <div class="meta">{' &middot; '.join(meta_parts)}</div>
  <div class="price-row">{''.join(badges)}</div>
  <a href="{e(beer.get('weblink'))}" target="_blank" rel="noopener">Bekijk in shop &rarr;</a>
</div>"""
