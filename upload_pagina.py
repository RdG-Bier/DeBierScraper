# -*- coding: utf-8 -*-
"""
Bouwt docs/lijsten.html: een pagina om je Untappd-lijsten in te lezen via
een schermopname (video), losse schermafbeeldingen of geplakte tekst.

Alles gebeurt in de browser zelf (OCR via Tesseract.js vanaf een CDN); er
gaat dus niets naar een server. Het resultaat kan worden opgeslagen in deze
browser (kleurt de bieren meteen) en/of gekopieerd naar de bestanden
mijn_untappd/gehad.txt en voorraad.txt in de repository.
"""

import json
import logging

import config
import utils

log = logging.getLogger("bierscraper")

PAGINA = r"""<!DOCTYPE html>
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
input[type=file] { width:100%; margin:8px 0; font-size:16px; }
/* 16px font voorkomt dat iOS de pagina inzoomt bij het tikken in een veld */
#zoekbier, #overboekzoek { width:100%; padding:14px 16px; font-size:16px; border:1px solid #ccc;
            border-radius:10px; margin:6px 0 2px; -webkit-appearance:none; box-sizing:border-box; }
textarea { width:100%; min-height:150px; padding:10px; border:1px solid #ccc;
           border-radius:8px; font-family:monospace; font-size:16px; }
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
.zoekresultaten { margin-top:6px; }
.zoekrij { display:flex; justify-content:space-between; align-items:center; gap:8px;
           padding:8px 4px; border-bottom:1px solid #eee; font-size:.85rem; }
.zoekrij .plus { background:var(--groen); color:#fff; border:none; border-radius:6px;
                 padding:6px 12px; font-size:.8rem; cursor:pointer; white-space:nowrap; }
.zoekrij .plus.erin { background:#999; }
.zoekrij .bn { color:#666; font-size:.78rem; }
.overboekrij { display:flex; align-items:center; gap:10px; padding:9px 4px;
               border-bottom:1px solid #eee; font-size:.9rem; cursor:pointer; }
.overboekrij input { width:20px; height:20px; flex:0 0 auto; }
.overboekrij .bn { color:#888; font-size:.78rem; }
</style></head>
<body>
<header>
  <h1>&#128220; Lijsten inlezen</h1>
  <a href="index.html">&larr; terug naar het bieroverzicht</a>
</header>
<main>

<div class="kaart" id="overboekkaart" style="border:2px solid var(--groen)">
  <h2>&#128260; Overboeken: voorraad &rarr; check-ins</h2>
  <p class="mini">Opgedronken? Vink hieronder aan welke bieren uit je voorraad
  (R &eacute;n H&amp;R samen) je gedronken hebt. Bij &#8220;overboeken&#8221;
  worden ze toegevoegd aan je check-ins (groen) en meteen uit de voorraadlijst
  gehaald. Werkt op mobiel; je GitHub-token moet ingesteld zijn.</p>
  <button class="grijs" onclick="laadOverboekLijst()">&#8635; Voorraadlijst laden</button>
  <span class="mini" id="overboekstatus" style="margin-left:8px"></span>
  <input id="overboekzoek" type="search" placeholder="Zoek in je voorraad&hellip;"
         oninput="toonOverboek()" autocomplete="off" style="margin-top:8px">
  <div id="overboekresultaten" class="zoekresultaten"></div>
  <div class="rij" style="margin-top:8px">
    <button id="overboekknop" onclick="voerOverboekUit()" disabled>Vink bieren aan om over te boeken</button>
  </div>
</div>

<div class="kaart" id="doelkaart">
  <h2>1. Welke lijst?</h2>
  <label class="keuze"><input type="radio" name="doel" value="had" checked onchange="zetDoel()">
    Check-ins (al gehad) <span style="background:var(--gehad);padding:1px 8px;border-radius:4px">groen</span></label>
  <label class="keuze"><input type="radio" name="doel" value="voorraad_r" onchange="zetDoel()">
    Voorraad R <span style="background:var(--wens);padding:1px 8px;border-radius:4px">geel</span></label>
  <label class="keuze"><input type="radio" name="doel" value="voorraad_hr" onchange="zetDoel()">
    Voorraad H&amp;R <span style="background:var(--wens);padding:1px 8px;border-radius:4px">geel</span></label>
  <p class="mini">Elke lijst heeft een eigen bestand. Een CSV-upload vervangt
  de hele lijst; losse bieren toevoegen (blok 2e) voegt juist toe.</p>
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
  <h2>2d. CSV-bestand uploaden</h2>
  <p class="mini">Heb je een CSV van de Untappd-extensie of een Untappd-export?
  Kies het bestand hieronder. De kolommen <i>beer_name/brewery_name</i> of
  <i>brouwerij_naam</i> worden automatisch gebruikt.</p>
  <input type="file" accept=".csv,text/csv,text/plain" multiple id="csvbestand"
         onchange="leesCsvBestanden(this.files)">
</div>

<div class="kaart">
  <h2>2e. Zoeken &amp; losse bieren toevoegen (werkt op mobiel)</h2>
  <p class="mini">Zoek in alle bieren die de scraper ooit heeft gezien en voeg
  er een toe aan de gekozen lijst. Zit een bier er niet bij (pre-order), tik
  dan rechtsboven op &#8220;handmatig&#8221; en voer het in als
  <i>Brouwerij - Biernaam</i> (exact zoals op Untappd).</p>
  <input id="zoekbier" type="search" placeholder="Zoek op brouwerij of biernaam&hellip;"
         oninput="zoekInDatabase()" autocomplete="off">
  <div id="zoekresultaten" class="zoekresultaten"></div>
  <div class="rij" style="margin-top:4px">
    <button class="grijs" onclick="handmatigToevoegen()">&#10133; Handmatig invoeren</button>
  </div>
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
    <button onclick="opslaanInRepo('vervang')">&#128190; Opslaan in GitHub (vervang lijst)</button>
    <button onclick="opslaanInRepo('voegtoe')">&#10133; Toevoegen aan GitHub-lijst</button>
  </div>
  <div style="margin-top:6px">
    <button class="grijs" onclick="bewaar()">Alleen in deze browser</button>
    <button class="grijs" onclick="kopieer()">Kopieer</button>
    <button class="grijs" onclick="download()">Download .txt</button>
    <button class="grijs" onclick="leeg()">Wissen</button>
  </div>
  <p class="mini" id="opslaguitleg"><b>Opslaan in GitHub</b> schrijft rechtstreeks naar het
  lijstbestand, dus het werkt op elk apparaat (ook mobiel) zodra je hier je GitHub-token hebt
  ingesteld via het bieroverzicht &rarr; &#8220;Vververs nu&#8221;.
  <br>&#8226; <b>Vervang lijst</b>: voor een CSV-upload van je hele Untappd-lijst.
  <br>&#8226; <b>Toevoegen</b>: voor losse bieren uit de zoekfunctie; bestaande regels blijven staan.
  <br>Na het opslaan de scraper draaien (of op de volgende run wachten) om de kleuren te zien.</p>
</div>

</main>
<script>
var doel = "had";
// koppel doel -> bestandsnaam in de repository
var DOELBESTAND = { had: "gehad.txt", voorraad_r: "voorraad_r.txt", voorraad_hr: "voorraad_hr.txt" };
var DOELLABEL = { had: "check-ins", voorraad_r: "voorraad R", voorraad_hr: "voorraad H&R" };
var GH_OWNER = "__GH_OWNER__", GH_REPO = "__GH_REPO__", GH_PAD = "mijn_untappd/";
function zetDoel(){
  doel = document.querySelector('input[name=doel]:checked').value;
  document.getElementById('doelkaart').className =
    "kaart " + (doel === "had" ? "doel-gehad" : "doel-wens");  // beide voorraden geel
  toonTelling();
}

/* ---------- tekstverwerking ---------- */
var gevonden = {};       // herkende bieren (genormaliseerd)
var onzeker = {};        // wel als bier herkend, maar niet in onze database
var exacteSleutels = {}; // strikte sleutels (incl. cijfers) voor CSV-ontdubbeling
var BEKEND = [];       // alle bieren die de scraper kent
var INDEX = {};        // woord -> lijst met nummers uit BEKEND
var bekendGeladen = false;

function schoon(r){
  return (r || "").replace(/[|_«»•©®]/g,' ').replace(/\s+/g,' ').trim();
}
function woorden(s){
  s = (s || "").toLowerCase();
  s = s.normalize ? s.normalize('NFD').replace(/[\u0300-\u036f]/g,'') : s;
  return s.replace(/[^a-z0-9]+/g,' ').split(' ').filter(function(w){ return w.length > 1; });
}
function laadBekend(){
  return fetch('bekende_bieren.json').then(function(r){ return r.json(); })
   .then(function(lijst){
     BEKEND = lijst.map(function(e){
       var nt = woorden(e.n).filter(function(w){ return w.length >= 4; });
       return { b: e.b, n: e.n, nt: nt, bt: woorden(e.b) };
     }).filter(function(e){ return e.nt.length > 0; });
     INDEX = {};
     BEKEND.forEach(function(e, i){
       e.nt.concat(e.bt).forEach(function(w){
         if(!INDEX[w]) INDEX[w] = [];
         if(INDEX[w][INDEX[w].length-1] !== i) INDEX[w].push(i);
       });
     });
     bekendGeladen = true;
     status(BEKEND.length + " bekende bieren geladen. Kies hierboven een bestand.");
   }).catch(function(){
     status("Let op: bekende_bieren.json niet gevonden; draai eerst de scraper. "
            + "Tekst plakken werkt wel.");
   });
}

/* Zoek de beste echte match voor een gelezen regel. Bijna alle woorden van de
   biernaam moeten voorkomen, anders wordt het afgewezen. Zo verdwijnt OCR-
   rommel en worden kleine leesfouten vanzelf rechtgezet. */
function zoekBier(regel){
  var kand = {};
  woorden(regel).forEach(function(w){ kand[w] = 1; });
  if(Object.keys(kand).length < 2) return null;
  var mogelijk = {};
  for(var w in kand){
    (INDEX[w] || []).forEach(function(i){ mogelijk[i] = 1; });
  }
  var best = null, bestScore = 0;
  for(var i in mogelijk){
    var e = BEKEND[i];
    var raakN = 0;
    e.nt.forEach(function(w){ if(kand[w]) raakN++; });
    if(raakN < e.nt.length * 0.8) continue;      // naam moet vrijwel compleet zijn
    var raakB = 0;
    e.bt.forEach(function(w){ if(kand[w]) raakB++; });
    var score = (raakN + raakB * 0.5) / (e.nt.length + e.bt.length * 0.5 || 1);
    if(score > bestScore){ best = e; bestScore = score; }
  }
  return bestScore >= 0.55 ? best : null;
}

function voegBekendToe(treffer){
  var regel = (treffer.b ? treffer.b + " - " : "") + treffer.n;
  var sl = woorden(regel).join(' ');
  if(gevonden[sl]) return false;
  gevonden[sl] = regel;
  return true;
}

/* Ankerregels: in de app staat onder elk bier een stijl-, beoordelings- of
   datumregel. De twee regels daarboven zijn de biernaam en de brouwerij.
   Ruim geschreven, zodat OCR-typfouten ("Becordeling", "gadronken op")
   ook nog herkend worden. */
var RE_ANKER = /(dronken\s*op|ordeling|rating|toegevoegd|checked\s*in|resultat)/i;
var RE_STIJL = /\b(IPA|Stout|Sour|Porter|Lager|Pilsner|Pale Ale|Barleywine|Barley Wine|Mead|Mede|Gose|Saison|Wild Ale|Brown Ale|Red Ale|Witbier|Weizen|Quadrupel|Tripel|Dubbel|Cider|Smoothie)\b/i;
function isAnker(r){
  if(RE_ANKER.test(r)) return true;
  return RE_STIJL.test(r) && r.trim().split(/\s+/).length <= 8;
}
/* Ziet dit eruit als een echte naam, of als OCR-gruis? */
function isNaamachtig(t){
  t = (t || "").trim();
  if(t.length < 3 || t.length > 60) return false;
  var letters = (t.match(/[a-zA-Z\u00C0-\u024F ]/g) || []).length;
  if(letters / t.length < 0.65) return false;
  var woorden = t.split(/\s+/).filter(function(w){ return /^[a-zA-Z\u00C0-\u024F]+$/.test(w); });
  if(!woorden.length) return false;
  var langste = 0;
  woorden.forEach(function(w){ if(w.length > langste) langste = w.length; });
  return langste >= 4;
}

function verwerkOcr(tekst){
  var regels = tekst.split(/\r?\n/)
    .map(function(r){ return r.replace(/[|_«»•©®]/g,' ').replace(/\s+/g,' ').trim(); })
    .filter(function(r){ return r.length > 1; });
  var nieuw = 0;
  for(var i = 0; i < regels.length; i++){
    if(!isAnker(regels[i]) || i < 2) continue;
    var naam = regels[i-2], brouw = regels[i-1];
    if(isAnker(naam) || isAnker(brouw)) continue;
    if(!isNaamachtig(naam) || !isNaamachtig(brouw)) continue;

    // eerst proberen te normaliseren tegen de bieren die we kennen
    var treffer = bekendGeladen ? (zoekBier(brouw + " " + naam) || zoekBier(naam)) : null;
    if(treffer){ if(voegBekendToe(treffer)) nieuw++; continue; }
    // onbekend (bijv. een check-in uit 2024): bewaren als "controleren"
    var regel = brouw + " - " + naam;
    var sl = woorden(regel).join(' ');
    if(sl && !gevonden[sl] && !onzeker[sl]){ onzeker[sl] = regel; nieuw++; }
  }
  toonResultaat();
  return nieuw;
}

var SCHEIDING = "# --- hieronder niet in de database gevonden: controleer even ---";
function toonResultaat(){
  var zeker = Object.keys(gevonden).sort().map(function(k){ return gevonden[k]; });
  var twijfel = Object.keys(onzeker).sort().map(function(k){ return onzeker[k]; });
  var tekst = zeker.join("\n");
  if(twijfel.length){ tekst += (tekst ? "\n\n" : "") + SCHEIDING + "\n" + twijfel.join("\n"); }
  document.getElementById('resultaat').value = tekst;
  toonTelling();
}
function toonTelling(){
  var n = Object.keys(gevonden).length, t = Object.keys(onzeker).length;
  var tekst = "";
  if(n || t){
    tekst = "(" + n + " herkend";
    if(t) tekst += " + " + t + " te controleren";
    tekst += ", doel: " + DOELLABEL[doel] + ")";
  }
  document.getElementById('telling').textContent = tekst;
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
           (Object.keys(gevonden).length + Object.keys(onzeker).length) + " bieren)");
    balk((i+1) / totaal);
    try { nieuw += verwerkOcr(await ocr(c)); } catch(e){ }
  }
  balk(1);
  status("Klaar. " + Object.keys(gevonden).length + " herkend, " +
         Object.keys(onzeker).length + " te controleren.");
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
  status("Klaar. " + Object.keys(gevonden).length + " herkend, " +
         Object.keys(onzeker).length + " te controleren.");
}

function leesPlak(){
  var n = verwerkTekst(document.getElementById('plakveld').value || "");
  document.getElementById('plakveld').value = "";
  status(n + " bieren toegevoegd. Controleer de lijst hieronder.");
}
// Splitst een CSV-regel op puntkomma. De extensie exporteert altijd met ';'
// (biernamen bevatten vaak komma's maar zelden een puntkomma). Velden tussen
// dubbele quotes mogen de puntkomma bevatten; "" is een letterlijk aanhalingsteken.
function splitsCsv(regel){
  var uit=[], cur="", q=false;
  for(var i=0;i<regel.length;i++){
    var c=regel[i];
    if(c === '"'){
      if(q && regel[i+1] === '"'){ cur += '"'; i++; }
      else { q = !q; }
    } else if(c === ';' && !q){
      uit.push(cur.trim()); cur="";
    } else { cur += c; }
  }
  uit.push(cur.trim());
  return uit;
}

/* Namen uit een CSV of geplakte tekst komen rechtstreeks van Untappd en zijn
   dus al correct. Ze worden NIET tegen de database gematcht: dat is bedoeld
   om rommelige OCR-tekst op te schonen, maar het plakte hier verschillende
   bieren op elkaar (tien SOMA-bieren werden samen "SOMA Beer - Lag", negen
   sours werden "All the Coconut"). We bewaren ze daarom letterlijk en
   ontdubbelen alleen op de naam zelf. */
function bewaarExact(regel){
  regel = schoon(regel);
  if(regel.length < 3) return;
  // Ontdubbelen op een STRIKTE sleutel die cijfers en # behoudt. woorden()
  // gooit losse cijfers weg (nuttig tegen OCR-ruis), maar dan zouden namen
  // die alleen in een nummer verschillen ten onrechte samenvallen:
  // "Hot Cakes #7/#8/#9" of "7 vs 8 Year Anniversary".
  var sl = regel.toLowerCase();
  sl = sl.normalize ? sl.normalize('NFD').replace(/[\u0300-\u036f]/g,'') : sl;
  sl = sl.replace(/[^a-z0-9#]+/g,' ').replace(/\s+/g,' ').trim();
  if(!sl || exacteSleutels[sl]) return;
  exacteSleutels[sl] = true;
  // toon-sleutel (via woorden) apart bijhouden zodat markeer()/opslaan blijft werken
  var toon = woorden(regel).join(' ');
  if(gevonden[toon] || onzeker[toon]){
    // botst met een reeds herkende naam op toon-niveau: gebruik de strikte
    // sleutel als opslagsleutel zodat beide bewaard blijven
    gevonden[sl] = regel;
  } else {
    gevonden[toon] = regel;
  }
}

// Gedeelde CSV/tekst-verwerking: gebruikt door plakveld EN bestandsupload.
function verwerkTekst(tekst){
  var regels = tekst.split(/\r?\n/).map(schoon).filter(function(r){ return r.length > 2; });
  if(!regels.length) return 0;
  var voor = Object.keys(gevonden).length + Object.keys(onzeker).length;
  var kop = regels[0].toLowerCase();
  if(kop.indexOf(';') >= 0 &&
     (kop.indexOf('beer_name') >= 0 || kop.indexOf('brouwerij_naam') >= 0
      || kop.indexOf('brouwerij') >= 0)){
    var kolommen = splitsCsv(regels[0]).map(function(k){ return k.toLowerCase(); });
    var iCombi = kolommen.indexOf('brouwerij_naam');
    var iB = kolommen.indexOf('beer_name');
    if(iB < 0) iB = kolommen.indexOf('naam');
    var iBr = kolommen.indexOf('brewery_name');
    if(iBr < 0) iBr = kolommen.indexOf('brouwerij');
    regels.slice(1).forEach(function(r){
      var v = splitsCsv(r);
      var regel;
      if(iCombi >= 0 && v[iCombi]){ regel = v[iCombi]; }
      else { regel = (((iBr >= 0 ? v[iBr] : "") + " - " + (iB >= 0 ? v[iB] : ""))
                      .replace(/^\s*-\s*|\s*-\s*$/g,"")).trim(); }
      if(!regel) return;
      bewaarExact(regel);
    });
  } else {
    regels.forEach(function(r){ bewaarExact(r); });
  }
  toonResultaat();
  return (Object.keys(gevonden).length + Object.keys(onzeker).length) - voor;
}

function leesCsvBestanden(bestanden){
  if(!bestanden || !bestanden.length) return;
  var klaar = 0, totaalNieuw = 0;
  Array.prototype.forEach.call(bestanden, function(bestand){
    var lezer = new FileReader();
    lezer.onload = function(){
      totaalNieuw += verwerkTekst(String(lezer.result || ""));
      klaar++;
      if(klaar === bestanden.length){
        status(bestanden.length + " bestand(en) verwerkt: " + totaalNieuw
               + " bieren toegevoegd. Controleer de lijst hieronder.");
      }
    };
    lezer.onerror = function(){ klaar++; status("Kon een bestand niet lezen."); };
    lezer.readAsText(bestand);
  });
}

/* ---------- opslaan ---------- */
function huidigeLijst(){
  return (document.getElementById('resultaat').value || "")
    .split(/\r?\n/).map(function(r){ return r.trim(); })
    .filter(function(r){ return r.length > 2 && r.charAt(0) !== "#"; });
}
function bewaar(){
  var sleutel = { had: "untappd_had", voorraad_r: "untappd_voorraad_r",
                  voorraad_hr: "untappd_voorraad_hr" }[doel] || "untappd_wens";
  var items = huidigeLijst().map(function(r){
    var d = r.split(/\s+-\s+/);
    var brouw = d.length === 2 ? d[0] : "", naam = d.length === 2 ? d[1] : r;
    return { vol: sleutelVan(brouw + " " + naam), naam: sleutelVan(naam) };
  });
  try {
    var bestaand = JSON.parse(localStorage.getItem(sleutel) || "[]");
    var samen = bestaand.concat(items), uniek = {}, uit = [];
    samen.forEach(function(e){ if(e.vol && !uniek[e.vol]){ uniek[e.vol] = 1; uit.push(e); } });
    localStorage.setItem(sleutel, JSON.stringify(uit));
    status("Opgeslagen: " + uit.length + " bieren onder '" +
           DOELLABEL[doel] + "'. Open het overzicht om ze te zien.");
  } catch(e){ status("Opslaan mislukt (opslag vol of geblokkeerd)."); }
}
function kopieer(){
  var t = document.getElementById('resultaat');
  t.select(); t.setSelectionRange(0, 999999);
  try { document.execCommand('copy'); status("Gekopieerd naar het klembord."); }
  catch(e){ status("Kopieren mislukt; selecteer de tekst handmatig."); }
}
function download(){
  var naam = DOELBESTAND[doel];
  var blob = new Blob([huidigeLijst().join("\n") + "\n"], {type:"text/plain"});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = naam; a.click();
  status("Gedownload als " + naam + ". Upload dit bestand naar mijn_untappd/ in je repository.");
}
function leeg(){
  gevonden = {}; onzeker = {}; exacteSleutels = {}; toonResultaat(); balk(0); status("Lijst gewist.");
}
/* ============ zoeken in de database + losse bieren toevoegen ============ */
function zoekInDatabase(){
  var q = (document.getElementById('zoekbier').value || "").trim().toLowerCase();
  var box = document.getElementById('zoekresultaten');
  if(q.length < 2){ box.innerHTML = ""; return; }
  if(!bekendGeladen){ box.innerHTML = '<p class="mini">Database laden\u2026 (draai eerst de scraper)</p>'; return; }
  var qt = q.split(/\s+/).filter(function(w){ return w.length > 0; });
  var treffers = [];
  for(var i=0;i<BEKEND.length && treffers.length < 40;i++){
    var e = BEKEND[i];
    var hooi = (e.b + " " + e.n).toLowerCase();
    if(qt.every(function(w){ return hooi.indexOf(w) >= 0; })) treffers.push(e);
  }
  if(!treffers.length){
    box.innerHTML = '<p class="mini">Niets gevonden. Tik op &#8220;Handmatig invoeren&#8221; '
      + 'als dit een pre-order of onbekend bier is.</p>';
    return;
  }
  box.innerHTML = treffers.map(function(e){
    var regel = (e.b ? e.b + " - " : "") + e.n;
    var sl = woorden(regel).join(' ');
    var erin = !!gevonden[sl];
    return '<div class="zoekrij"><div><b>' + escapeHtml(e.n) + '</b><br>'
      + '<span class="bn">' + escapeHtml(e.b) + '</span></div>'
      + '<button class="plus' + (erin ? ' erin' : '') + '" '
      + 'onclick="voegUitZoek(this, ' + JSON.stringify(regel).replace(/"/g,'&quot;') + ')">'
      + (erin ? '\u2713 erin' : '\u002b toevoegen') + '</button></div>';
  }).join('');
}
function escapeHtml(s){ return (s||"").replace(/[&<>"]/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }

function voegUitZoek(knop, regel){
  var sl = woorden(regel).join(' ');
  if(gevonden[sl]){ return; }
  gevonden[sl] = regel;
  knop.classList.add('erin'); knop.textContent = '\u2713 erin';
  toonResultaat();
  status('Toegevoegd: ' + regel);
}
function handmatigToevoegen(){
  var naam = prompt("Voer het bier in als 'Brouwerij - Biernaam'\n(exact zoals op Untappd):", "");
  if(!naam) return;
  naam = naam.trim();
  if(naam.length < 3){ return; }
  var sl = woorden(naam).join(' ');
  if(gevonden[sl]){ status('Stond al in de lijst.'); return; }
  gevonden[sl] = naam;
  toonResultaat();
  status('Handmatig toegevoegd: ' + naam);
}

/* ============ opslaan in de GitHub-repository ============ */
function ghToken(){ try { return localStorage.getItem("gh_token") || ""; } catch(e){ return ""; } }

/* Alfabetisch sorteren zonder dat accenten de volgorde verstoren:
   "Ārpus" hoort bij de A, niet achter de Z. */
function alfabetisch(a, b){
  return String(a).localeCompare(String(b), "nl", { sensitivity: "base", numeric: true });
}

/* ============ GitHub-bestand lezen/schrijven (herbruikbaar) ============ */
function ghHeaders(token){
  return { "Accept":"application/vnd.github+json", "Authorization":"Bearer " + token,
           "X-GitHub-Api-Version":"2022-11-28" };
}
async function ghLeesBestand(bestand, token){
  // retourneert {regels, sha} of {regels:[], sha:null} als het niet bestaat
  var api = "https://api.github.com/repos/" + GH_OWNER + "/" + GH_REPO + "/contents/" + GH_PAD + bestand;
  var r = await fetch(api, { headers: ghHeaders(token) });
  if(r.status === 404) return { regels: [], sha: null };
  if(r.status !== 200) throw new Error("lezen mislukt (" + r.status + ")");
  var d = await r.json();
  var tekst = decodeURIComponent(escape(atob(d.content.replace(/\s/g,''))));
  return { regels: tekst.split(/\r?\n/), sha: d.sha };
}
async function ghSchrijfBestand(bestand, regels, sha, token, label){
  var api = "https://api.github.com/repos/" + GH_OWNER + "/" + GH_REPO + "/contents/" + GH_PAD + bestand;
  var kop = regels.filter(function(l){ return l.trim().indexOf('#') === 0; });
  var bieren = regels.filter(function(l){ return l.trim() && l.trim().indexOf('#') !== 0; });
  var header = kop.length ? kop : ["# " + label + " - bijgewerkt via Lijsten inlezen"];
  var inhoud = header.join("\n") + "\n" + bieren.sort(function(a,b){
    return alfabetisch(a, b); }).join("\n") + "\n";
  var body = { message: "Lijst " + bestand + " bijgewerkt (" + bieren.length + " bieren)",
               content: btoa(unescape(encodeURIComponent(inhoud))) };
  if(sha) body.sha = sha;
  var pr = await fetch(api, { method:"PUT", headers: ghHeaders(token), body: JSON.stringify(body) });
  if(pr.status === 401 || pr.status === 403) throw new Error("token");
  if(pr.status !== 200 && pr.status !== 201) throw new Error("schrijven mislukt (" + pr.status + ")");
  return bieren.length;
}
function strikteSleutel(regel){
  var sl = regel.toLowerCase();
  sl = sl.normalize ? sl.normalize('NFD').replace(/[\u0300-\u036f]/g,'') : sl;
  return sl.replace(/[^a-z0-9#]+/g,' ').replace(/\s+/g,' ').trim();
}

/* ============ overboeken: voorraad -> check-ins ============ */
var OVERBOEK = {};   // sleutel -> {regel, bron: "voorraad_r"|"voorraad_hr"}

function laadOverboekLijst(){
  // leest de voorraadlijsten uit de repository en toont ze als aanvinkbare lijst
  var vink = document.getElementById('overboekstatus');
  var token = ghToken();
  if(!token){
    vink.textContent = "Stel eerst je GitHub-token in (bieroverzicht \u2192 Token).";
    return;
  }
  vink.textContent = "Voorraadlijsten laden\u2026";
  return Promise.all([ghLeesBestand("voorraad_r.txt", token), ghLeesBestand("voorraad_hr.txt", token)])
   .then(function(res){
     OVERBOEK = {};
     [["voorraad_r", res[0]], ["voorraad_hr", res[1]]].forEach(function(paar){
       paar[1].regels.forEach(function(r){
         r = r.trim();
         if(!r || r.indexOf('#') === 0) return;
         var sl = strikteSleutel(r);
         if(sl && !OVERBOEK[sl]) OVERBOEK[sl] = { regel: r, bron: paar[0] };
       });
     });
     vink.textContent = Object.keys(OVERBOEK).length + " bieren in voorraad geladen.";
     toonOverboek();
   })
   .catch(function(e){ vink.textContent = "Laden mislukt: " + e.message; });
}

function toonOverboek(){
  var q = (document.getElementById('overboekzoek').value || "").toLowerCase();
  var qt = q.split(/\s+/).filter(function(w){ return w.length > 0; });
  var box = document.getElementById('overboekresultaten');
  var sleutels = Object.keys(OVERBOEK).sort(function(a,b){
    return alfabetisch(OVERBOEK[a].regel, OVERBOEK[b].regel); });
  var html = "", getoond = 0;
  sleutels.forEach(function(sl){
    var e = OVERBOEK[sl];
    if(q && !qt.every(function(w){ return e.regel.toLowerCase().indexOf(w) >= 0; })) return;
    if(getoond >= 150) return;
    getoond++;
    var label = e.bron === "voorraad_r" ? "R" : "H&R";
    html += '<label class="overboekrij"><input type="checkbox" value="' + sl + '" '
      + (e.gekozen ? 'checked ' : '') + 'onchange="kiesOverboek(this)">'
      + '<span>' + escapeHtml(e.regel) + ' <span class="bn">(' + label + ')</span></span></label>';
  });
  box.innerHTML = html || '<p class="mini">Geen bieren gevonden.</p>';
  telOverboek();
}
function kiesOverboek(cb){ if(OVERBOEK[cb.value]) OVERBOEK[cb.value].gekozen = cb.checked; telOverboek(); }
function telOverboek(){
  var n = Object.keys(OVERBOEK).filter(function(k){ return OVERBOEK[k].gekozen; }).length;
  document.getElementById('overboekknop').textContent =
    n ? "\u2713 " + n + " bier(en) overboeken naar check-ins" : "Vink bieren aan om over te boeken";
  document.getElementById('overboekknop').disabled = (n === 0);
}

async function voerOverboekUit(){
  var token = ghToken();
  if(!token){ alert("Geen GitHub-token. Stel het in via het bieroverzicht \u2192 Token."); return; }
  var gekozen = Object.keys(OVERBOEK).filter(function(k){ return OVERBOEK[k].gekozen; });
  if(!gekozen.length) return;

  var status2 = document.getElementById('overboekstatus');
  status2.textContent = "Overboeken\u2026";
  try {
    // 1) toevoegen aan check-ins (gehad.txt)
    var gehad = await ghLeesBestand("gehad.txt", token);
    var zien = {};
    gehad.regels.forEach(function(r){ if(r.trim() && r.indexOf('#')!==0) zien[strikteSleutel(r)] = 1; });
    gekozen.forEach(function(sl){ if(!zien[sl]){ gehad.regels.push(OVERBOEK[sl].regel); zien[sl] = 1; } });
    await ghSchrijfBestand("gehad.txt", gehad.regels, gehad.sha, token, DOELLABEL.had);

    // 2) verwijderen uit de voorraadlijst(en) waar ze vandaan komen
    var perBron = { voorraad_r: [], voorraad_hr: [] };
    gekozen.forEach(function(sl){ perBron[OVERBOEK[sl].bron].push(sl); });
    for(var bron in perBron){
      if(!perBron[bron].length) continue;
      var weg = {}; perBron[bron].forEach(function(sl){ weg[sl] = 1; });
      var vb = await ghLeesBestand(bron + ".txt", token);
      var over = vb.regels.filter(function(r){
        if(!r.trim() || r.indexOf('#') === 0) return true;  // commentaar behouden
        return !weg[strikteSleutel(r)];
      });
      await ghSchrijfBestand(bron + ".txt", over, vb.sha, token,
                             bron === "voorraad_r" ? "voorraad R" : "voorraad H&R");
    }
    status2.textContent = gekozen.length + " bier(en) overgeboekt naar check-ins. "
      + "Draai de scraper of wacht op de volgende run; ze worden dan groen.";
    // lijst opnieuw laden zodat de overgeboekte bieren verdwijnen
    setTimeout(laadOverboekLijst, 1500);
  } catch(e){
    if(e.message === "token"){ alert("Token afgewezen. Heeft het Contents: Read and write?"); }
    status2.textContent = "Overboeken mislukt: " + e.message;
  }
}

async function opslaanInRepo(modus){
  // modus: "vervang" (CSV = hele lijst) of "voegtoe" (losse aanvullingen)
  var token = ghToken();
  if(!token){
    alert("Geen GitHub-token gevonden. Open het bieroverzicht, tik op "
      + "\u201cVververs nu\u201d en stel daar eenmalig je token in. "
      + "Dat token wordt in deze browser bewaard en ook hier gebruikt.");
    return;
  }
  var bestand = DOELBESTAND[doel];
  var pad = GH_PAD + bestand;
  var nieuweRegels = huidigeLijst();   // de bieren uit het resultaatveld
  if(!nieuweRegels.length){ status("Niets om op te slaan."); return; }

  status("Opslaan in GitHub\u2026");
  var api = "https://api.github.com/repos/" + GH_OWNER + "/" + GH_REPO + "/contents/" + pad;
  var headers = { "Accept":"application/vnd.github+json", "Authorization":"Bearer " + token,
                  "X-GitHub-Api-Version":"2022-11-28" };

  // bestaande inhoud + sha ophalen (nodig om te updaten)
  var bestaand = [], sha = null;
  try {
    var r = await fetch(api, { headers: headers });
    if(r.status === 200){
      var d = await r.json();
      sha = d.sha;
      var tekst = decodeURIComponent(escape(atob(d.content.replace(/\s/g,''))));
      bestaand = tekst.split(/\r?\n/);
    } else if(r.status !== 404){
      status("Kon bestand niet lezen (code " + r.status + ")."); return;
    }
  } catch(e){ status("Geen verbinding met GitHub."); return; }

  // commentaarregels en handmatige-marker behouden
  var kop = bestaand.filter(function(l){ return l.trim().indexOf('#') === 0; });
  var bestaandeBieren = bestaand.filter(function(l){ return l.trim() && l.trim().indexOf('#') !== 0; });

  var eindlijst;
  if(modus === "vervang"){
    eindlijst = nieuweRegels.slice();
  } else {
    // toevoegen: samenvoegen en ontdubbelen op strikte sleutel
    var zien = {}, uit = [];
    bestaandeBieren.concat(nieuweRegels).forEach(function(r){
      var sl = r.toLowerCase().normalize ? r.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'') : r.toLowerCase();
      sl = sl.replace(/[^a-z0-9#]+/g,' ').replace(/\s+/g,' ').trim();
      if(sl && !zien[sl]){ zien[sl] = 1; uit.push(r); }
    });
    eindlijst = uit;
  }

  var header = kop.length ? kop : ["# " + DOELLABEL[doel] + " - bijgewerkt via Lijsten inlezen"];
  var inhoud = header.join("\n") + "\n" + eindlijst.sort(function(a,b){
    return alfabetisch(a, b); }).join("\n") + "\n";

  var body = { message: "Lijst " + bestand + " bijgewerkt (" + eindlijst.length + " bieren)",
               content: btoa(unescape(encodeURIComponent(inhoud))) };
  if(sha) body.sha = sha;

  try {
    var pr = await fetch(api, { method:"PUT", headers: headers, body: JSON.stringify(body) });
    if(pr.status === 200 || pr.status === 201){
      status("Opgeslagen in " + bestand + " (" + eindlijst.length + " bieren). "
        + "Draai de scraper of wacht op de volgende run om de kleuren te zien.");
    } else if(pr.status === 401 || pr.status === 403){
      alert("Token afgewezen. Controleer of het token schrijfrechten (Contents: Read and write) heeft.");
      status("Opslaan mislukt: token.");
    } else {
      status("Opslaan mislukt (code " + pr.status + ").");
    }
  } catch(e){ status("Opslaan mislukt: geen verbinding."); }
}

zetDoel();
laadBekend();
</script>
</body></html>"""


def schrijf_bekende_bieren(all_beers, output_path):
    """Lijst met alle bieren die we kennen, als naslag voor de uploadpagina.
    Daarmee kan die pagina gelezen tekst toetsen aan echte bieren: rommel uit
    een schermopname valt af en typfouten worden vanzelf rechtgezet."""
    gezien, uit = set(), []
    for bieren in all_beers.values():
        for b in bieren:
            naam = (b.get("naam") or "").strip()
            if not naam:
                continue
            sleutel = utils.beer_match_key(b.get("brouwerij"), naam)
            if not sleutel or sleutel in gezien:
                continue
            gezien.add(sleutel)
            uit.append({"b": (b.get("brouwerij") or "").strip(), "n": naam})
    # Ook alles wat ooit gezien is meenemen: check-ins gaan jaren terug en die
    # bieren liggen allang niet meer in de schappen.
    uit_db = 0
    db_pad = output_path.parent / "bierdatabase.json"
    if db_pad.exists():
        try:
            db = json.loads(db_pad.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            db = {}
        for sleutel, gegevens in db.items():
            if sleutel in gezien:
                continue
            gezien.add(sleutel)
            naam = (gegevens or {}).get("nm")
            if naam:
                brouwerij, _, biernaam = naam.partition(" - ")
                uit.append({"b": brouwerij if biernaam else "", "n": biernaam or naam})
            else:
                uit.append({"b": "", "n": sleutel})  # alleen sleutelwoorden bekend
            uit_db += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(uit, ensure_ascii=False), encoding="utf-8")
    log.info("Bekende bieren voor de uploadpagina: %d (%d uit de shops, %d uit "
             "de database)", len(uit), len(uit) - uit_db, uit_db)


def bouw(output_path):
    gh_owner = getattr(config, "GITHUB_OWNER", "")
    gh_repo = getattr(config, "GITHUB_REPO", "")
    inhoud = PAGINA.replace("__GH_OWNER__", gh_owner).replace("__GH_REPO__", gh_repo)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(inhoud, encoding="utf-8")
    log.info("Uploadpagina geschreven naar %s", output_path)
