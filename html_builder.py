# -*- coding: utf-8 -*-
"""
Bouwt de mobiele webpagina (docs/index.html): tab per shop, gesorteerd op
score, met zoekveld, filterpaneel, Untappd-markering (al gehad / wenslijst),
swipe tussen shops, vergrootbare etiketten en een handmatige ververs-knop.
"""

import datetime
import html
import logging

import config
import scoring

log = logging.getLogger("bierscraper")

CSS = """
:root { --groen:#1f4e44; --geel:#fff2cc; --rood:#ffc7ce; --felgroen:#00e676;
        --gehad:#d6f0d8; --wens:#fdf0c8; }
* { box-sizing:border-box; }
body { font-family:-apple-system,'Segoe UI',Arial,sans-serif; margin:0; background:#f5f5f2;
       color:#222; overflow-x:hidden; }
header { background:var(--groen); color:#fff; padding:12px 16px; }
header h1 { margin:0; font-size:1.1rem; }
header .sub { font-size:.72rem; opacity:.85; margin-top:2px; }
.acties { display:flex; gap:8px; align-items:center; margin-top:8px; flex-wrap:wrap; }
.knop { background:#fff; color:var(--groen); border:none; border-radius:8px;
        padding:7px 11px; font-size:.78rem; font-weight:600; cursor:pointer; }
.knop.aan { background:#ffd966; }
.knop:disabled { opacity:.55; cursor:default; }
.dl { color:#fff; text-decoration:underline; font-size:.78rem; }
.status { font-size:.72rem; color:#fff; opacity:.9; flex-basis:100%; }

/* tabs blijven altijd bovenin staan, ook bij scrollen */
.tabs { display:flex; overflow-x:auto; background:#fff; border-bottom:1px solid #ddd;
        position:sticky; top:0; z-index:20; -webkit-overflow-scrolling:touch; }
.tabs button { flex:0 0 auto; border:0; background:none; padding:12px 14px; font-size:.85rem;
               border-bottom:3px solid transparent; color:#555; white-space:nowrap; }
.tabs button.active { color:var(--groen); border-bottom-color:var(--groen); font-weight:600; }

.toolbar { padding:10px 12px 4px; }
.toolbar input[type=search] { width:100%; padding:10px 12px; font-size:1rem; border:1px solid #ccc;
                              border-radius:10px; -webkit-appearance:none; }
.paneel { display:none; background:#fff; border-bottom:1px solid #ddd; padding:12px 14px;
          font-size:.82rem; }
.paneel.open { display:block; }
.paneel h4 { margin:0 0 6px; font-size:.85rem; }
.paneel label { display:inline-flex; align-items:center; gap:6px; margin:3px 10px 3px 0; }
.paneel select, .paneel textarea { width:100%; padding:8px 10px; border:1px solid #ccc;
          border-radius:8px; font-size:.85rem; margin:4px 0 8px; -webkit-appearance:none; }
.paneel textarea { min-height:80px; font-family:monospace; font-size:.75rem; }
.paneel .rij { display:flex; gap:8px; flex-wrap:wrap; margin-top:6px; }
.paneel .rij button { background:var(--groen); color:#fff; border:none; border-radius:8px;
                      padding:8px 12px; font-size:.8rem; cursor:pointer; }
.paneel .rij button.grijs { background:#777; }
.paneel details { margin:6px 0; }
.paneel summary { cursor:pointer; color:var(--groen); font-weight:600; }
.mini { font-size:.72rem; color:#666; line-height:1.4; }
.veld2 { display:flex; gap:10px; }
.veld2 > div { flex:1; }

.panel { display:none; padding:0 8px 40px; }
.panel.active { display:block; }
.card { background:#fff; border-radius:12px; margin:8px 4px; padding:12px 14px;
        box-shadow:0 1px 3px rgba(0,0,0,.08); border-left:4px solid transparent; }
.card.sterk { border-left-color:var(--groen); }
.card.gehad { background:var(--gehad); }
.card.wens { background:var(--wens); }
.card .top { display:flex; justify-content:space-between; gap:8px; align-items:flex-start; }
.card .name { font-weight:600; font-size:.95rem; }
.card .brewery { color:#666; font-size:.8rem; }
.card .rechts { display:flex; flex-direction:column; align-items:flex-end; gap:6px; }
.card .score { background:var(--groen); color:#fff; border-radius:8px; padding:2px 8px;
               font-size:.85rem; font-weight:700; white-space:nowrap; }
.card .label-img { width:56px; height:56px; object-fit:contain; border-radius:8px;
                   background:#fff; border:1px solid #eee; cursor:zoom-in; }
.card .meta { font-size:.78rem; color:#555; margin-top:6px; }
.card .vlag { font-size:.7rem; font-weight:700; color:var(--groen); margin-top:4px; }
.card .price-row { margin-top:8px; display:flex; flex-wrap:wrap; gap:6px; font-size:.78rem; }
.badge { border-radius:6px; padding:3px 7px; background:#eee; }
.badge.own { background:var(--groen); color:#fff; font-weight:600; }
.badge.hoger { background:var(--rood); }
.badge.lager { background:var(--felgroen); font-weight:600; }
.card a { color:var(--groen); font-size:.8rem; }
.empty { text-align:center; color:#888; padding:30px 0; }

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
"""

JS = """
var GH_OWNER="__OWNER__", GH_REPO="__REPO__", GH_WF="__WORKFLOW__";
var ACTIONS_URL="https://github.com/"+GH_OWNER+"/"+GH_REPO+"/actions";
var TABS = __TABS__;
var huidigeTab = TABS.length ? TABS[0] : "";

/* ---------- tabs & swipe ---------- */
function showTab(key){
  huidigeTab = key;
  document.querySelectorAll('.tabs button').forEach(function(b){
    b.classList.toggle('active', b.dataset.key===key); });
  document.querySelectorAll('.panel').forEach(function(p){
    p.classList.toggle('active', p.dataset.key===key); });
  var act = document.querySelector('.tabs button.active');
  if(act && act.scrollIntoView){ act.scrollIntoView({inline:'center', block:'nearest'}); }
  window.scrollTo(0, 0);
  pasFiltersToe();
}
function buurTab(stap){
  var i = TABS.indexOf(huidigeTab);
  if(i < 0) return;
  var j = i + stap;
  if(j >= 0 && j < TABS.length){ showTab(TABS[j]); }
}
var tx=0, ty=0;
document.addEventListener('touchstart', function(e){
  if(document.getElementById('lightbox').classList.contains('open')) return;
  tx = e.changedTouches[0].clientX; ty = e.changedTouches[0].clientY;
}, {passive:true});
document.addEventListener('touchend', function(e){
  if(document.getElementById('lightbox').classList.contains('open')) return;
  var dx = e.changedTouches[0].clientX - tx, dy = e.changedTouches[0].clientY - ty;
  if(Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy)*2){ buurTab(dx < 0 ? 1 : -1); }
}, {passive:true});

/* ---------- Untappd: al gehad / wenslijst ---------- */
function norm(s){
  s = (s||"").toLowerCase();
  s = s.normalize ? s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'') : s;
  s = s.replace(/[^a-z0-9]+/g,' ');
  s = s.replace(/\\b\\d{2,4}\\s?(cl|ml|l)\\b/g,' ');
  s = s.replace(/\\b(can|blik|bottle|fles|krat|brewery|brewing|brouwerij|bierbrouwerij|company|co|craft|bryggeri|bryghus|brasserie|birrificio|cervejaria|browar)\\b/g,' ');
  return s.replace(/\\s+/g,' ').trim();
}
function laadLijst(sleutel){
  try { return JSON.parse(localStorage.getItem(sleutel) || "[]"); } catch(e){ return []; }
}
function parseInvoer(tekst){
  var regels = (tekst||"").split(/\\r?\\n/).map(function(r){ return r.trim(); })
                          .filter(function(r){ return r.length > 2; });
  if(!regels.length) return [];
  var kop = regels[0].toLowerCase();
  var uit = [];
  if(kop.indexOf('beer_name') >= 0){         /* Untappd CSV-export */
    var kolommen = splitsCsv(regels[0]);
    var iB = kolommen.indexOf('beer_name'), iBr = kolommen.indexOf('brewery_name');
    for(var i=1; i<regels.length; i++){
      var v = splitsCsv(regels[i]);
      var naam = iB >= 0 ? v[iB] : "", brou = iBr >= 0 ? v[iBr] : "";
      if(naam){ uit.push({vol: norm(brou + " " + naam), naam: norm(naam)}); }
    }
  } else {
    regels.forEach(function(r){
      var naam = r, brou = "";
      var m = r.split(/\\s+-\\s+/);
      if(m.length === 2){ brou = m[0]; naam = m[1]; }
      uit.push({vol: norm(brou + " " + naam), naam: norm(naam)});
    });
  }
  return uit;
}
function splitsCsv(regel){
  var uit=[], cur="", q=false;
  for(var i=0;i<regel.length;i++){
    var c = regel[i];
    if(c === '"'){ q = !q; }
    else if(c === ',' && !q){ uit.push(cur.trim().toLowerCase()); cur=""; }
    else { cur += c; }
  }
  uit.push(cur.trim().toLowerCase());
  return uit;
}
function bewaarUntappd(){
  var had = parseInvoer(document.getElementById('gehadveld').value);
  var wens = parseInvoer(document.getElementById('wensveld').value);
  try {
    localStorage.setItem('untappd_had', JSON.stringify(had));
    localStorage.setItem('untappd_wens', JSON.stringify(wens));
  } catch(e){ alert('Opslaan mislukt (opslag vol of geblokkeerd).'); return; }
  markeer(); pasFiltersToe(); toonAantallen();
}
function wisUntappd(){
  try { localStorage.removeItem('untappd_had'); localStorage.removeItem('untappd_wens'); } catch(e){}
  document.getElementById('gehadveld').value = "";
  document.getElementById('wensveld').value = "";
  markeer(); pasFiltersToe(); toonAantallen();
}
function toonAantallen(){
  document.getElementById('untappd-aantal').textContent =
    laadLijst('untappd_had').length + " gehad, " + laadLijst('untappd_wens').length + " op wenslijst";
}
function bouwIndex(lijst){
  var vol = {}, naam = {};
  lijst.forEach(function(e){
    if(e.vol) vol[e.vol] = 1;
    if(e.naam && e.naam.length >= 6) naam[e.naam] = 1;
  });
  return {vol: vol, naam: naam};
}
function markeer(){
  var had = bouwIndex(laadLijst('untappd_had'));
  var wens = bouwIndex(laadLijst('untappd_wens'));
  document.querySelectorAll('.card').forEach(function(c){
    var k = c.dataset.key, n = c.dataset.naamkey;
    var isHad = had.vol[k] || had.naam[n];
    var isWens = !isHad && (wens.vol[k] || wens.naam[n]);
    c.classList.toggle('gehad', !!isHad);
    c.classList.toggle('wens', !!isWens);
    var vlag = c.querySelector('.vlag');
    vlag.textContent = isHad ? '\\u2713 al gehad' : (isWens ? '\\u2605 wenslijst' : '');
  });
}

/* ---------- filters ---------- */
function togglePaneel(id){
  var p = document.getElementById(id);
  ['filterpaneel','untappdpaneel','tokenpaneel'].forEach(function(x){
    if(x !== id){ document.getElementById(x).classList.remove('open'); }
  });
  p.classList.toggle('open');
}
function pasFiltersToe(){
  var q = (document.getElementById('zoek').value || "").toLowerCase();
  var minU = parseFloat(document.getElementById('f-untappd').value) || 0;
  var maxP = parseFloat(document.getElementById('f-prijs').value) || 0;
  var alleenSterk = document.getElementById('f-sterk').checked;
  var verbergGehad = document.getElementById('f-verberg-gehad').checked;
  var verbergWens = document.getElementById('f-verberg-wens').checked;
  var stijlen = [];
  document.querySelectorAll('.f-stijl:checked').forEach(function(c){ stijlen.push(c.value); });

  document.querySelectorAll('.panel').forEach(function(panel){
    var zichtbaar = 0;
    panel.querySelectorAll('.card').forEach(function(c){
      var ok = true;
      if(q && c.textContent.toLowerCase().indexOf(q) < 0) ok = false;
      if(ok && minU){
        var u = parseFloat(c.dataset.untappd);
        if(isNaN(u) || u < minU) ok = false;
      }
      if(ok && maxP){
        var p = parseFloat(c.dataset.prijs);
        if(isNaN(p) || p > maxP) ok = false;
      }
      if(ok && alleenSterk && c.dataset.sterk !== "1") ok = false;
      if(ok && stijlen.length && stijlen.indexOf(c.dataset.stijl) < 0) ok = false;
      if(ok && verbergGehad && c.classList.contains('gehad')) ok = false;
      if(ok && verbergWens && c.classList.contains('wens')) ok = false;
      c.style.display = ok ? '' : 'none';
      if(ok) zichtbaar++;
    });
    var knop = document.querySelector('.tabs button[data-key="'+panel.dataset.key+'"]');
    if(knop){ knop.textContent = knop.dataset.label + " (" + zichtbaar + ")"; }
  });
}
function resetFilters(){
  document.getElementById('zoek').value = "";
  document.getElementById('f-untappd').value = "";
  document.getElementById('f-prijs').value = "";
  document.getElementById('f-sterk').checked = false;
  document.getElementById('f-verberg-gehad').checked = false;
  document.getElementById('f-verberg-wens').checked = false;
  document.querySelectorAll('.f-stijl').forEach(function(c){ c.checked = false; });
  pasFiltersToe();
}

/* ---------- etiket vergroten ---------- */
function openImg(src){
  var lb = document.getElementById('lightbox');
  document.getElementById('lightbox-img').src = src;
  lb.classList.add('open');
}
function closeImg(e){
  if(!e || e.target.id === 'lightbox' || e.target.classList.contains('close')){
    document.getElementById('lightbox').classList.remove('open');
    document.getElementById('lightbox-img').src = '';
  }
}
document.addEventListener('keydown', function(e){ if(e.key === 'Escape') closeImg(); });

/* ---------- handmatig verversen ---------- */
function tok(){ try { return localStorage.getItem("gh_token") || ""; } catch(e){ return ""; } }
function setStatus(t){ document.getElementById("status").textContent = t || ""; }
function ververs(){
  var t = tok();
  if(!t){ togglePaneel('tokenpaneel'); return; }
  var knop = document.getElementById("verversknop");
  knop.disabled = true; setStatus("Bezig met starten...");
  fetch("https://api.github.com/repos/"+GH_OWNER+"/"+GH_REPO+"/actions/workflows/"+GH_WF+"/dispatches", {
    method:"POST",
    headers:{"Accept":"application/vnd.github+json","Authorization":"Bearer "+t,
             "X-GitHub-Api-Version":"2022-11-28"},
    body: JSON.stringify({ref:"main"})
  }).then(function(r){
    if(r.status === 204){ setStatus("Gestart! Dit duurt een paar minuten."); setTimeout(volgStatus, 12000); }
    else if(r.status === 401 || r.status === 403){
      setStatus("Token afgewezen of verlopen."); togglePaneel('tokenpaneel'); knop.disabled = false; }
    else { setStatus("Starten mislukt (code "+r.status+")."); knop.disabled = false; }
  }).catch(function(){ setStatus("Geen verbinding met GitHub."); knop.disabled = false; });
}
function volgStatus(){
  fetch("https://api.github.com/repos/"+GH_OWNER+"/"+GH_REPO+"/actions/runs?per_page=1")
   .then(function(r){ return r.json(); })
   .then(function(d){
     var run = d.workflow_runs && d.workflow_runs[0];
     if(!run){ setStatus(""); return; }
     if(run.status !== "completed"){ setStatus("Bezig met scrapen... ("+run.status+")"); setTimeout(volgStatus, 15000); }
     else if(run.conclusion === "success"){ setStatus("Klaar! Herlaad de pagina."); document.getElementById("verversknop").disabled = false; }
     else { setStatus("Run mislukt ("+run.conclusion+")."); document.getElementById("verversknop").disabled = false; }
   }).catch(function(){ setStatus(""); });
}
function tokenOpslaan(){
  var v = document.getElementById("tokenveld").value.trim();
  if(!v) return;
  try { localStorage.setItem("gh_token", v); } catch(e){}
  document.getElementById("tokenveld").value = "";
  document.getElementById('tokenpaneel').classList.remove('open');
  ververs();
}
function tokenWissen(){
  try { localStorage.removeItem("gh_token"); } catch(e){}
  setStatus("Token gewist."); document.getElementById('tokenpaneel').classList.remove('open');
}
function openGitHub(){ window.open(ACTIONS_URL, "_blank"); }

/* ---------- start ---------- */
document.addEventListener('DOMContentLoaded', function(){
  var had = laadLijst('untappd_had'), wens = laadLijst('untappd_wens');
  if(had.length){ document.getElementById('gehadveld').value =
      had.map(function(e){ return e.naam; }).join('\\n'); }
  if(wens.length){ document.getElementById('wensveld').value =
      wens.map(function(e){ return e.naam; }).join('\\n'); }
  toonAantallen(); markeer(); pasFiltersToe();
});
"""


def build_html(all_beers, sites, output_path, excel_name="bieroverzicht.xlsx"):
    price_lookup = scoring.build_price_lookup(all_beers)
    now = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")

    n_gehad = sum(1 for bs in all_beers.values() for b in bs if b.get("gehad"))
    n_voorraad = sum(1 for bs in all_beers.values() for b in bs if b.get("voorraad"))
    markering_tekst = ""
    if n_gehad or n_voorraad:
        markering_tekst = (f"<br>&#128994; {n_gehad} al gehad &middot; "
                           f"&#128993; {n_voorraad} in voorraad")

    tabs, panels, stijlen = [], [], set()
    for i, site in enumerate(sites):
        beers = sorted(all_beers.get(site["key"], []),
                       key=lambda b: b.get("score") or 0, reverse=True)
        for b in beers:
            if b.get("stijl"):
                stijlen.add(b["stijl"])
        active = " active" if i == 0 else ""
        label = html.escape(site["label"])
        tabs.append(
            f'<button class="{active.strip()}" data-key="{site["key"]}" data-label="{label}" '
            f'onclick="showTab(\'{site["key"]}\')">{label} ({len(beers)})</button>'
        )
        cards = "".join(_card(b, site, sites, price_lookup) for b in beers) \
            or '<div class="empty">Geen bieren gevonden</div>'
        panels.append(f'<div class="panel{active}" data-key="{site["key"]}">{cards}</div>')

    stijl_opties = "".join(
        f'<label><input type="checkbox" class="f-stijl" value="{html.escape(s)}" '
        f'onchange="pasFiltersToe()"> {html.escape(s)}</label>'
        for s in sorted(stijlen))

    untappd_user = html.escape(getattr(config, "UNTAPPD_USER", "") or "-")
    gh_owner = getattr(config, "GITHUB_OWNER", "")
    gh_repo = getattr(config, "GITHUB_REPO", "")
    gh_wf = getattr(config, "GITHUB_WORKFLOW", "main.yml")
    tab_keys = "[" + ",".join(f'"{s["key"]}"' for s in sites) + "]"
    js = (JS.replace("__OWNER__", gh_owner).replace("__REPO__", gh_repo)
            .replace("__WORKFLOW__", gh_wf).replace("__TABS__", tab_keys))

    doc = f"""<!DOCTYPE html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bieroverzicht</title><style>{CSS}</style></head>
<body>
<header><h1>&#127866; Bieroverzicht</h1>
<div class="sub">Bijgewerkt: {now} &middot; score &ge; 4.00 of onbekend &middot; scraper {config.VERSION}
{markering_tekst}</div>
<div class="acties">
  <button class="knop" id="verversknop" onclick="ververs()">&#8635; Ververs nu</button>
  <button class="knop" onclick="togglePaneel('filterpaneel')">&#9776; Filters</button>
  <button class="knop" onclick="togglePaneel('untappdpaneel')">Mijn Untappd</button>
  <a class="dl" href="{excel_name}" download>&#11015; Excel</a>
  <span class="status" id="status"></span>
</div></header>

<div class="tabs">{''.join(tabs)}</div>
<div class="toolbar">
  <input id="zoek" type="search" placeholder="Zoek op naam, brouwerij of stijl&hellip;"
         oninput="pasFiltersToe()">
</div>

<div class="paneel" id="filterpaneel">
  <h4>Filters</h4>
  <div class="veld2">
    <div>Untappd minimaal
      <select id="f-untappd" onchange="pasFiltersToe()">
        <option value="">alles</option><option value="4.1">4.10+</option>
        <option value="4.2">4.20+</option><option value="4.3">4.30+</option>
        <option value="4.4">4.40+</option>
      </select>
    </div>
    <div>Prijs maximaal
      <select id="f-prijs" onchange="pasFiltersToe()">
        <option value="">geen max</option><option value="5">&euro; 5</option>
        <option value="7.5">&euro; 7,50</option><option value="10">&euro; 10</option>
        <option value="15">&euro; 15</option><option value="20">&euro; 20</option>
      </select>
    </div>
  </div>
  <label><input type="checkbox" id="f-sterk" onchange="pasFiltersToe()"> alleen sterke voorkeur</label>
  <label><input type="checkbox" id="f-verberg-gehad" onchange="pasFiltersToe()"> verberg al gehad</label>
  <label><input type="checkbox" id="f-verberg-wens" onchange="pasFiltersToe()"> verberg wat ik in voorraad heb</label>
  <details><summary>Bierstijlen</summary><div>{stijl_opties}</div></details>
  <div class="rij"><button class="grijs" onclick="resetFilters()">Filters wissen</button></div>
</div>

<div class="paneel" id="untappdpaneel">
  <h4>Mijn Untappd <span class="mini" id="untappd-aantal"></span></h4>
  <p class="mini">Je Untappd-profiel <b>{untappd_user}</b> wordt automatisch uitgelezen:
  ingecheckte bieren krijgen een <b>groene</b> achtergrond, bieren op je
  voorraadlijsten een <b>gele</b>. Dat gebeurt bij elke scrape-run; je hoeft
  hier dus niets te doen. Voorwaarde is wel dat je profiel openbaar staat
  (Untappd &rarr; Settings &rarr; Privacy).<br><br>
  Klopt er iets niet of wil je zelf bieren toevoegen? Dan kun je hieronder
  handmatig lijsten plakken (&eacute;&eacute;n bier per regel, eventueel als
  <i>Brouwerij - Biernaam</i>). Die blijven alleen in deze browser staan en
  vullen de automatische koppeling aan.</p>
  <div>Extra: al gehad<textarea id="gehadveld" placeholder="Brouwerij Kees - Caramel Fudge Stout"></textarea></div>
  <div>Extra: in voorraad<textarea id="wensveld" placeholder="Arpus - QDH Riwaka"></textarea></div>
  <div class="rij">
    <button onclick="bewaarUntappd()">Opslaan</button>
    <button class="grijs" onclick="wisUntappd()">Wissen</button>
  </div>
</div>

<div class="paneel" id="tokenpaneel">
  <h4>Eenmalig instellen</h4>
  <p class="mini">Verversen start de scraper op GitHub. Daarvoor is een token nodig;
  dat wordt <b>alleen in deze browser</b> bewaard. Maak er een aan via
  <a href="https://github.com/settings/personal-access-tokens/new" target="_blank">GitHub
  &rarr; Fine-grained token</a>: bij <i>Repository access</i> alleen <code>{gh_repo}</code>,
  bij <i>Permissions</i> alleen <b>Actions: Read and write</b>.</p>
  <input id="tokenveld" type="password" placeholder="github_pat_..." autocomplete="off"
         style="width:100%;padding:9px 10px;border:1px solid #ccc;border-radius:8px">
  <div class="rij">
    <button onclick="tokenOpslaan()">Opslaan en verversen</button>
    <button class="grijs" onclick="openGitHub()">Liever via GitHub</button>
    <button class="grijs" onclick="tokenWissen()">Token wissen</button>
  </div>
</div>

{''.join(panels)}
<div id="lightbox" onclick="closeImg(event)">
  <div class="box"><button class="close" onclick="closeImg(event)">&times;</button>
  <img id="lightbox-img" src="" alt=""></div>
</div>
<script>{js}</script></body></html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(doc, encoding="utf-8")
    log.info("HTML geschreven naar %s", output_path)


def _matchsleutel(brouwerij, naam):
    """Zelfde normalisatie als in de JS, zodat de Untappd-lijsten matchen."""
    import re
    import unicodedata
    tekst = f"{brouwerij or ''} {naam or ''}".lower()
    tekst = unicodedata.normalize("NFD", tekst)
    tekst = "".join(c for c in tekst if not unicodedata.combining(c))
    tekst = re.sub(r"[^a-z0-9]+", " ", tekst)
    tekst = re.sub(r"\b\d{2,4}\s?(cl|ml|l)\b", " ", tekst)
    tekst = re.sub(r"\b(can|blik|bottle|fles|krat|brewery|brewing|brouwerij|bierbrouwerij"
                   r"|company|co|craft|bryggeri|bryghus|brasserie|birrificio|cervejaria"
                   r"|browar)\b", " ", tekst)
    return re.sub(r"\s+", " ", tekst).strip()


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

    img = beer.get("afbeelding")
    big = (img or "").replace("_sm.", "_md.").replace("120x120", "640x640") if img else ""
    img_html = (f'<img class="label-img" src="{e(img)}" alt="" loading="lazy" '
                f'onclick="openImg(\'{e(big)}\')" '
                f'onerror="this.style.display=\'none\'">') if img else ""

    sterk = " sterk" if beer.get("sterke_voorkeur") else ""
    # markering uit het gekoppelde Untappd-profiel (server-side gezet)
    klassen = ""
    vlag = ""
    if beer.get("voorraad"):
        klassen += " wens"
        vlag = "\u2605 in voorraad"
    if beer.get("gehad"):
        if not beer.get("voorraad"):
            klassen += " gehad"
        vlag = (vlag + " \u00b7 " if vlag else "") + "\u2713 al gehad"
    return f"""<div class="card{sterk}{klassen}"
  data-key="{e(_matchsleutel(beer.get('brouwerij'), beer.get('naam')))}"
  data-naamkey="{e(_matchsleutel(None, beer.get('naam')))}"
  data-stijl="{e(beer.get('stijl'))}"
  data-untappd="{beer.get('untappd') if beer.get('untappd') is not None else ''}"
  data-prijs="{beer.get('prijs') if beer.get('prijs') is not None else ''}"
  data-sterk="{'1' if beer.get('sterke_voorkeur') else '0'}">
  <div class="top"><div><div class="name">{e(beer.get('naam'))}</div>
  <div class="brewery">{e(beer.get('brouwerij'))}</div></div>
  <div class="rechts"><div class="score">{beer.get('score', 0)}</div>{img_html}</div></div>
  <div class="meta">{' &middot; '.join(meta_parts)}</div>
  <div class="vlag">{vlag}</div>
  <div class="price-row">{''.join(badges)}</div>
  <a href="{e(beer.get('weblink'))}" target="_blank" rel="noopener">Bekijk in shop &rarr;</a>
</div>"""
