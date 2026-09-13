# -*- coding: utf-8 -*-
"""
Bouwt docs/lijsten.html: een pagina om je Untappd-lijsten in te lezen via
een schermopname (video), losse schermafbeeldingen of geplakte tekst.

Alles gebeurt in de browser zelf (OCR via Tesseract.js vanaf een CDN); er
gaat dus niets naar een server. Het resultaat kan worden opgeslagen in deze
browser (kleurt de bieren meteen) en/of gekopieerd naar de bestanden
mijn_untappd/gehad.txt en voorraad.txt in de repository.
"""

import logging

import config

log = logging.getLogger("bierscraper")

PAGINA = """<!DOCTYPE html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lijsten inlezen</title>
<script src="https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js"></script>
<style>
:root { --groen:#1f4e44; --gehad:#d6f0d8; --wens:#fdf0c8; }
* { box-sizing:border-box; }
body { font-family:-apple-system,'Segoe UI',Arial,sans-serif; margin:0; background:#f5f5f2; color:#222; }
header { background:var(--groen); color:#fff; padding:14px 16px; }
header h1 { margin:0; font-size:1.1rem; }
header a { color:#fff; font-size:.8rem; }
main { padding:12px; max-width:760px; margin:0 auto; }
.kaart { background:#fff; border-radius:12px; padding:14px; margin-bottom:12px;
         box-shadow:0 1px 3px rgba(0,0,0,.08); }
h2 { font-size:.95rem; margin:0 0 8px; }
.mini { font-size:.78rem; color:#666; line-height:1.45; }
label.keuze { display:inline-flex; align-items:center; gap:6px; margin:4px 14px 4px 0;
              font-size:.88rem; }
input[type=file] { width:100%; margin:8px 0; font-size:.85rem; }
textarea { width:100%; min-height:150px; padding:10px; border:1px solid #ccc;
           border-radius:8px; font-family:monospace; font-size:.78rem; }
button { background:var(--groen); color:#fff; border:none; border-radius:8px;
         padding:10px 14px; font-size:.85rem; cursor:pointer; margin:4px 6px 4px 0; }
button.grijs { background:#777; }
button:disabled { opacity:.5; cursor:default; }
.balk { height:8px; background:#e3e3e3; border-radius:4px; overflow:hidden; margin:8px 0; }
.balk div { height:100%; width:0; background:var(--groen); transition:width .2s; }
.status { font-size:.8rem; color:#444; min-height:1.2em; }
.telling { font-weight:700; color:var(--groen); }
.doel-gehad { background:var(--gehad); }
.doel-wens { background:var(--wens); }
</style></head>
<body>
<header>
  <h1>&#128220; Lijsten inlezen</h1>
  <a href="index.html">&larr; terug naar het bieroverzicht</a>
</header>
<main>

<div class="kaart" id="doelkaart">
  <h2>1. Waar horen deze bieren bij?</h2>
  <label class="keuze"><input type="radio" name="doel" value="had" checked onchange="zetDoel()">
    Al gehad <span style="background:var(--gehad);padding:1px 8px;border-radius:4px">groen</span></label>
  <label class="keuze"><input type="radio" name="doel" value="wens" onchange="zetDoel()">
    In voorraad <span style="background:var(--wens);padding:1px 8px;border-radius:4px">geel</span></label>
  <p class="mini">Je kunt dit in meerdere rondes doen: eerst je check-ins inlezen,
  daarna omschakelen naar voorraad en je lijsten erdoorheen halen.</p>
</div>

<div class="kaart">
  <h2>2a. Schermopname (snelst voor lange lijsten)</h2>
  <p class="mini">Maak op je telefoon een schermopname terwijl je <b>rustig</b> door je
  Untappd-lijst scrollt. Laad die video hier; de pagina pakt er beeldjes uit en
  leest de biernamen. Scroll niet te snel: ongeveer een half scherm per seconde
  werkt het beste.</p>
  <input type="file" accept="video/*" id="video" onchange="leesVideo(this.files[0])">
  <div class="mini">Beeldje elke
    <select id="interval"><option value="0.6">0,6 s</option><option value="1" selected>1 s</option>
    <option value="1.5">1,5 s</option></select> seconde
  </div>
</div>

<div class="kaart">
  <h2>2b. Schermafbeeldingen</h2>
  <p class="mini">Of kies een of meer screenshots tegelijk.</p>
  <input type="file" accept="image/*" multiple id="fotos" onchange="leesFotos(this.files)">
</div>

<div class="kaart">
  <h2>2c. Tekst plakken</h2>
  <p class="mini">Eén bier per regel, het liefst als <i>Brouwerij - Biernaam</i>.
  Een CSV-export van Untappd mag ook.</p>
  <textarea id="plakveld" placeholder="Funky Fluid - Velvet"></textarea>
  <button onclick="leesPlak()">Toevoegen aan de lijst</button>
</div>

<div class="kaart">
  <h2>3. Voortgang</h2>
  <div class="balk"><div id="balk"></div></div>
  <div class="status" id="status">Nog niets ingelezen.</div>
</div>

<div class="kaart" id="resultaatkaart">
  <h2>4. Resultaat <span class="telling" id="telling"></span></h2>
  <p class="mini">Controleer en verbeter gerust; OCR maakt soms fouten. Eén bier per regel.</p>
  <textarea id="resultaat" placeholder="Hier verschijnen de gevonden bieren."></textarea>
  <div>
    <button onclick="bewaar()">Opslaan in deze browser</button>
    <button class="grijs" onclick="kopieer()">Kopieer alles</button>
    <button class="grijs" onclick="download()">Download .txt</button>
    <button class="grijs" onclick="leeg()">Wissen</button>
  </div>
  <p class="mini" id="opslaguitleg">Opslaan in deze browser kleurt de bieren meteen in het
  overzicht. Wil je het blijvend vastleggen (ook op andere apparaten), plak de lijst dan in
  <code>mijn_untappd/gehad.txt</code> of <code>voorraad.txt</code> in je GitHub-repository.</p>
</div>

</main>
<script>
var doel = "had";
function zetDoel(){
  doel = document.querySelector('input[name=doel]:checked').value;
  document.getElementById('doelkaart').className =
    "kaart " + (doel === "had" ? "doel-gehad" : "doel-wens");
  toonTelling();
}

/* ---------- tekstverwerking ---------- */
var gevonden = {};   // sleutel -> "Brouwerij - Bier"

var RE_STIJL = /\\b(IPA|Stout|Sour|Porter|Lager|Pilsner|Pale Ale|Barleywine|Barley Wine|Mead|Mede|Gose|Saison|Wild Ale|Brown Ale|Red Ale|Amber|Witbier|Weizen|Quadrupel|Tripel|Dubbel|Blonde|Cider|Fruit Beer|Smoothie)\\b/i;
var RE_RUIS = /(%\\s*ABV|\\bABV\\b|Toegevoegd|Added|Untappd|Check-?in|Totaal|Sorteer|Producent|Soort|Filter|^\\s*[\\d.,]+\\s*$|^[^A-Za-z0-9]*$)/i;

function isStijlregel(r){
  if(!RE_STIJL.test(r)) return false;
  var woorden = r.trim().split(/\\s+/).length;
  return woorden <= 8;
}
function schoon(r){
  return r.replace(/[|_«»•©®]/g,' ').replace(/\\s+/g,' ').trim();
}
function sleutelVan(tekst){
  var s = tekst.toLowerCase();
  s = s.normalize ? s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'') : s;
  s = s.replace(/[^a-z0-9]+/g,' ');
  s = s.replace(/\\b(brewery|brewing|brouwerij|company|co|craft|bryggeri|bryghus|brasserie|birrificio|cervejaria|browar)\\b/g,' ');
  return s.replace(/\\s+/g,' ').trim();
}
function voegToe(brouwerij, naam){
  naam = schoon(naam || ""); brouwerij = schoon(brouwerij || "");
  if(naam.length < 3 || RE_RUIS.test(naam) || isStijlregel(naam)) return false;
  var regel = (brouwerij ? brouwerij + " - " : "") + naam;
  var sl = sleutelVan(regel);
  if(!sl || gevonden[sl]) return false;
  gevonden[sl] = regel;
  return true;
}

/* In de Untappd-app staat per bier: naam / brouwerij / stijl / ABV / score.
   De stijlregel is het betrouwbaarste ankerpunt: de twee regels erboven
   zijn dan de biernaam en de brouwerij. */
function verwerkOcr(tekst){
  var regels = tekst.split(/\\r?\\n/).map(schoon).filter(function(r){ return r.length > 1; });
  var nieuw = 0;
  for(var i = 0; i < regels.length; i++){
    if(isStijlregel(regels[i]) && i >= 2){
      if(voegToe(regels[i-1], regels[i-2])) nieuw++;
    }
  }
  if(nieuw === 0){   // geen stijlregels herkend: alles wat op een naam lijkt
    regels.forEach(function(r){
      if(!RE_RUIS.test(r) && !isStijlregel(r) && r.length >= 4 && /[a-z]/i.test(r)){
        if(voegToe("", r)) nieuw++;
      }
    });
  }
  toonResultaat();
  return nieuw;
}

function toonResultaat(){
  var lijst = Object.keys(gevonden).sort().map(function(k){ return gevonden[k]; });
  document.getElementById('resultaat').value = lijst.join("\\n");
  toonTelling();
}
function toonTelling(){
  var n = Object.keys(gevonden).length;
  document.getElementById('telling').textContent =
    n ? "(" + n + " bieren, doel: " + (doel === "had" ? "al gehad" : "voorraad") + ")" : "";
}
function status(t){ document.getElementById('status').textContent = t; }
function balk(p){ document.getElementById('balk').style.width = Math.round(p*100) + "%"; }

/* ---------- OCR ---------- */
async function ocr(bron){
  var res = await Tesseract.recognize(bron, 'eng');
  return res.data.text || "";
}
function tekenOpCanvas(bron, breedte, hoogte){
  var c = document.createElement('canvas');
  var schaal = Math.min(1, 1100 / breedte);
  c.width = Math.round(breedte * schaal); c.height = Math.round(hoogte * schaal);
  var ctx = c.getContext('2d');
  ctx.drawImage(bron, 0, 0, c.width, c.height);
  return c;
}

async function leesVideo(bestand){
  if(!bestand) return;
  var video = document.createElement('video');
  video.muted = true; video.playsInline = true;
  video.src = URL.createObjectURL(bestand);
  status("Video laden...");
  await new Promise(function(r){ video.onloadedmetadata = r; });
  var stap = parseFloat(document.getElementById('interval').value) || 1;
  var duur = video.duration || 0;
  var totaal = Math.min(Math.ceil(duur / stap), 150);
  var nieuw = 0;
  for(var i = 0; i < totaal; i++){
    var t = i * stap;
    video.currentTime = Math.min(t, Math.max(0, duur - 0.05));
    await new Promise(function(r){ video.onseeked = r; });
    var c = tekenOpCanvas(video, video.videoWidth, video.videoHeight);
    status("Beeldje " + (i+1) + " van " + totaal + " lezen... (" +
           Object.keys(gevonden).length + " bieren gevonden)");
    balk((i+1) / totaal);
    try { nieuw += verwerkOcr(await ocr(c)); } catch(e){ }
  }
  balk(1);
  status("Klaar. " + Object.keys(gevonden).length + " bieren gevonden. Controleer de lijst hieronder.");
  URL.revokeObjectURL(video.src);
}

async function leesFotos(bestanden){
  if(!bestanden || !bestanden.length) return;
  for(var i = 0; i < bestanden.length; i++){
    status("Afbeelding " + (i+1) + " van " + bestanden.length + " lezen...");
    balk((i+1) / bestanden.length);
    try { verwerkOcr(await ocr(bestanden[i])); } catch(e){ }
  }
  balk(1);
  status("Klaar. " + Object.keys(gevonden).length + " bieren gevonden.");
}

function leesPlak(){
  var tekst = document.getElementById('plakveld').value || "";
  var regels = tekst.split(/\\r?\\n/).map(schoon).filter(function(r){ return r.length > 2; });
  if(!regels.length) return;
  var kop = regels[0].toLowerCase();
  if(kop.indexOf('beer_name') >= 0){
    var kolommen = splitsCsv(regels[0]);
    var iB = kolommen.indexOf('beer_name'), iBr = kolommen.indexOf('brewery_name');
    regels.slice(1).forEach(function(r){
      var v = splitsCsv(r);
      voegToe(iBr >= 0 ? v[iBr] : "", iB >= 0 ? v[iB] : "");
    });
  } else {
    regels.forEach(function(r){
      var d = r.split(/\\s+-\\s+/);
      if(d.length === 2){ voegToe(d[0], d[1]); } else { voegToe("", r); }
    });
  }
  document.getElementById('plakveld').value = "";
  toonResultaat();
  status(Object.keys(gevonden).length + " bieren in de lijst.");
}
function splitsCsv(regel){
  var uit=[], cur="", q=false;
  for(var i=0;i<regel.length;i++){
    var c=regel[i];
    if(c === '"'){ q = !q; }
    else if(c === ',' && !q){ uit.push(cur.trim().toLowerCase()); cur=""; }
    else { cur += c; }
  }
  uit.push(cur.trim().toLowerCase());
  return uit;
}

/* ---------- opslaan ---------- */
function huidigeLijst(){
  return (document.getElementById('resultaat').value || "")
    .split(/\\r?\\n/).map(function(r){ return r.trim(); })
    .filter(function(r){ return r.length > 2; });
}
function bewaar(){
  var sleutel = doel === "had" ? "untappd_had" : "untappd_wens";
  var items = huidigeLijst().map(function(r){
    var d = r.split(/\\s+-\\s+/);
    var brouw = d.length === 2 ? d[0] : "", naam = d.length === 2 ? d[1] : r;
    return { vol: sleutelVan(brouw + " " + naam), naam: sleutelVan(naam) };
  });
  try {
    var bestaand = JSON.parse(localStorage.getItem(sleutel) || "[]");
    var samen = bestaand.concat(items), uniek = {}, uit = [];
    samen.forEach(function(e){ if(e.vol && !uniek[e.vol]){ uniek[e.vol] = 1; uit.push(e); } });
    localStorage.setItem(sleutel, JSON.stringify(uit));
    status("Opgeslagen: " + uit.length + " bieren onder '" +
           (doel === "had" ? "al gehad" : "voorraad") + "'. Open het overzicht om ze te zien.");
  } catch(e){ status("Opslaan mislukt (opslag vol of geblokkeerd)."); }
}
function kopieer(){
  var t = document.getElementById('resultaat');
  t.select(); t.setSelectionRange(0, 999999);
  try { document.execCommand('copy'); status("Gekopieerd naar het klembord."); }
  catch(e){ status("Kopieren mislukt; selecteer de tekst handmatig."); }
}
function download(){
  var naam = doel === "had" ? "gehad.txt" : "voorraad.txt";
  var blob = new Blob([huidigeLijst().join("\\n") + "\\n"], {type:"text/plain"});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = naam; a.click();
  status("Gedownload als " + naam + ". Upload dit bestand naar mijn_untappd/ in je repository.");
}
function leeg(){
  gevonden = {}; toonResultaat(); balk(0); status("Lijst gewist.");
}
zetDoel();
</script>
</body></html>"""


def bouw(output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(PAGINA, encoding="utf-8")
    log.info("Uploadpagina geschreven naar %s", output_path)
