"""Statyczny frontend (self-contained) serwowany przez Flask pod '/'."""

INDEX_HTML = r"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audyt kosztów transportu — MyBed</title>
<style>
  :root{--bg:#0d1117;--panel:#161b22;--panel2:#1c2330;--bd:#2b3444;--tx:#e6edf3;
    --mut:#9aa7b4;--acc:#3b82f6;--ok:#2ea043;--bad:#f85149;--warn:#d29922;--flag:#ff7b72}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--tx);
    font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Ubuntu,sans-serif}
  header{padding:20px 24px;border-bottom:1px solid var(--bd);
    background:linear-gradient(180deg,#11161f,#0d1117)}
  h1{margin:0;font-size:20px;font-weight:650}
  header p{margin:4px 0 0;color:var(--mut);font-size:13px}
  .wrap{max-width:1120px;margin:0 auto;padding:24px}
  .grid{display:grid;grid-template-columns:340px 1fr;gap:24px}
  @media(max-width:880px){.grid{grid-template-columns:1fr}}
  .panel{background:var(--panel);border:1px solid var(--bd);border-radius:12px;padding:18px}
  .panel h2{margin:0 0 14px;font-size:14px;letter-spacing:.02em;text-transform:uppercase;
    color:var(--mut)}
  label{display:block;font-size:12px;color:var(--mut);margin:10px 0 4px}
  input[type=text],input[type=file]{width:100%;background:var(--panel2);border:1px solid var(--bd);
    color:var(--tx);border-radius:8px;padding:8px 10px;font-size:13px}
  input[type=file]{padding:6px}
  .car{border:1px solid var(--bd);border-radius:10px;padding:10px 12px;margin:10px 0;background:#12161d}
  .car b{font-size:13px}
  .btn{display:inline-flex;align-items:center;gap:8px;background:var(--acc);color:#fff;border:0;
    border-radius:8px;padding:10px 16px;font-size:14px;font-weight:600;cursor:pointer}
  .btn:disabled{opacity:.5;cursor:not-allowed}
  .btn.ghost{background:transparent;border:1px solid var(--bd);color:var(--tx)}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:14px}
  .muted{color:var(--mut);font-size:12px}
  .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
  @media(max-width:880px){.kpis{grid-template-columns:repeat(2,1fr)}}
  .kpi{background:var(--panel2);border:1px solid var(--bd);border-radius:10px;padding:12px 14px}
  .kpi .v{font-size:22px;font-weight:700}
  .kpi .l{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.03em}
  table{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
  th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--bd);vertical-align:top}
  th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.03em}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  .ok{color:var(--ok)} .bad{color:var(--bad)}
  .pill{display:inline-block;padding:1px 7px;border-radius:20px;font-size:11px;font-weight:600}
  .pill.FLAG{background:rgba(248,81,73,.15);color:var(--flag)}
  .pill.WARN{background:rgba(210,153,34,.15);color:var(--warn)}
  .pill.INFO{background:rgba(88,166,255,.12);color:#79c0ff}
  .sec{margin-top:22px}
  .sec h3{font-size:14px;margin:0 0 4px}
  .sec .cap{color:var(--mut);font-size:12px;margin-bottom:6px}
  .scroll{overflow-x:auto;border:1px solid var(--bd);border-radius:10px}
  .err{background:rgba(248,81,73,.12);border:1px solid var(--bad);color:#ffb4ae;
    border-radius:10px;padding:12px 14px;margin-top:14px;white-space:pre-wrap}
  .spin{width:16px;height:16px;border:2px solid rgba(255,255,255,.35);border-top-color:#fff;
    border-radius:50%;animation:sp .7s linear infinite;display:inline-block}
  @keyframes sp{to{transform:rotate(360deg)}}
  .hidden{display:none}
  a.dl{color:#79c0ff;text-decoration:none;border:1px solid var(--bd);padding:8px 12px;
    border-radius:8px;font-size:13px;display:inline-block}
  a.dl:hover{border-color:var(--acc)}
  code{background:#0b0f16;padding:1px 5px;border-radius:5px;font-size:12px}
  .nav{display:flex;gap:8px;margin-top:14px}
  .navbtn{background:transparent;border:1px solid var(--bd);color:var(--mut);border-radius:8px;
    padding:7px 16px;font-size:13px;font-weight:600;cursor:pointer}
  .navbtn.active{background:var(--panel);color:var(--tx);border-color:var(--acc)}
  tr.sep td{border-top:2px solid var(--acc)}
  /* wielo-plikowy picker */
  .drop{display:inline-flex;align-items:center;gap:6px;cursor:pointer;background:var(--panel2);
    border:1px dashed var(--bd);border-radius:8px;padding:7px 12px;font-size:12px;color:var(--mut);
    margin-top:4px}
  .drop:hover{border-color:var(--acc);color:var(--tx)}
  .drop input{display:none}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
  .chip{display:inline-flex;align-items:center;gap:6px;background:#12161d;border:1px solid var(--bd);
    border-radius:20px;padding:3px 6px 3px 10px;font-size:12px;max-width:100%}
  .chip .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:150px}
  .chipx{background:transparent;border:0;color:var(--mut);cursor:pointer;font-size:13px;
    line-height:1;padding:2px 4px;border-radius:50%}
  .chipx:hover{color:var(--bad);background:rgba(248,81,73,.12)}
  /* pasek postępu */
  .progress{margin-top:14px;background:var(--panel2);border:1px solid var(--bd);border-radius:8px;
    overflow:hidden}
  .progress .track{height:8px;background:#0b0f16;overflow:hidden}
  .progress .bar{height:100%;background:var(--acc);width:0;transition:width .2s ease}
  .progress.indet .bar{width:35%;animation:indet 1.1s ease-in-out infinite}
  @keyframes indet{0%{margin-left:-35%}100%{margin-left:100%}}
  .progress .ptxt{font-size:12px;color:var(--mut);padding:6px 10px}
</style>
</head>
<body>
<header>
  <h1>Audyt kosztów transportu — MyBed / Delta Industries</h1>
  <p>Przypisanie realnego kosztu dostawy, audyt (duble, cross-carrier, nieudane, przepłaty)
     i uzgodnienie z fakturami zbiorczymi SPT / Zadbano / D&amp;M Trans.</p>
  <div class="nav">
    <button class="navbtn active" id="navAudyt" onclick="showView('audyt')">Audyt</button>
    <button class="navbtn" id="navCenniki" onclick="showView('cenniki')">Cenniki</button>
  </div>
</header>
<div class="wrap">
  <div class="grid" id="viewAudyt">
    <!-- LEWY PANEL: wejście -->
    <div class="panel">
      <h2>Dane wejściowe</h2>
      <label>Źródło ERP</label>
      <div class="row" style="gap:18px;margin-top:2px">
        <label style="margin:0;color:var(--tx)"><input type="radio" name="erpsrc" value="file" checked onchange="onSrc()"> Plik CSV</label>
        <label style="margin:0;color:var(--tx)" id="srcSupaLabel"><input type="radio" name="erpsrc" value="supabase" id="srcSupa" onchange="onSrc()"> Supabase</label>
      </div>
      <div id="erpFileWrap">
        <label>Eksport ERP (CSV)</label>
        <input type="file" id="erp" accept=".csv">
      </div>
      <div id="supaNote" class="muted hidden" style="margin-top:8px">
        ERP pobierany z Supabase po rdzeniach z zestawień (bez uploadu wielkiego CSV).
        Wgraj tylko zestawienia + faktury poniżej.</div>
      <label>Okres (opcjonalnie — puste = auto z dokumentów)</label>
      <input type="text" id="period" placeholder="auto (np. 2026-02)">

      <div class="car">
        <b>SPT</b> <span class="muted">PDF „flat"</span>
        <label>Zestawienia (spec) — można wiele</label>
        <label class="drop">➕ Dodaj pliki<input type="file" multiple accept=".pdf" onchange="addFiles('spt_spec',this)"></label>
        <div class="chips" id="spt_spec_chips"></div>
        <label>Faktury — można wiele</label>
        <label class="drop">➕ Dodaj pliki<input type="file" multiple accept=".pdf" onchange="addFiles('spt_inv',this)"></label>
        <div class="chips" id="spt_inv_chips"></div>
      </div>
      <div class="car">
        <b>Zadbano</b> <span class="muted">XLSX „itemized"</span>
        <label>Zestawienia (spec) — można wiele</label>
        <label class="drop">➕ Dodaj pliki<input type="file" multiple accept=".xlsx" onchange="addFiles('zad_spec',this)"></label>
        <div class="chips" id="zad_spec_chips"></div>
        <label>Faktury — można wiele</label>
        <label class="drop">➕ Dodaj pliki<input type="file" multiple accept=".pdf" onchange="addFiles('zad_inv',this)"></label>
        <div class="chips" id="zad_inv_chips"></div>
      </div>
      <div class="car">
        <b>D&amp;M Trans</b> <span class="muted">PDF „flat + usługi"</span>
        <label>Zestawienia (spec) — można wiele</label>
        <label class="drop">➕ Dodaj pliki<input type="file" multiple accept=".pdf" onchange="addFiles('dm_spec',this)"></label>
        <div class="chips" id="dm_spec_chips"></div>
        <label>Faktury — można wiele</label>
        <label class="drop">➕ Dodaj pliki<input type="file" multiple accept=".pdf" onchange="addFiles('dm_inv',this)"></label>
        <div class="chips" id="dm_inv_chips"></div>
      </div>

      <label class="hidden" id="saveSupaWrap" style="margin-top:12px;color:var(--tx)">
        <input type="checkbox" id="saveSupa"> Zapisz wyniki do Supabase
        <span class="muted">(fact_delivery_costs + reconciliation_log)</span></label>
      <div class="row">
        <button class="btn" id="runBtn" onclick="runUpload()">Uruchom audyt</button>
        <button class="btn ghost" id="demoBtn" onclick="runDemo()">Pokaż na danych demo</button>
      </div>
      <div id="progress" class="progress hidden">
        <div class="track"><div class="bar" id="progressBar"></div></div>
        <div class="ptxt" id="progressTxt"></div>
      </div>
      <p class="muted" style="margin-top:10px">Możesz dodawać zestawienia i faktury
        <b>partiami, w dowolnej kolejności</b> (przyciskami „➕ Dodaj pliki") — narzędzie
        sparsuje każdą porcję osobno, żeby zmieścić się w limicie ~4,5 MB, i policzy audyt
        na <b>całym okresie łącznie</b>. Duży Eksport.csv? Przełącz źródło ERP na „Supabase"
        (bez uploadu CSV). Bez plików — „Pokaż na danych demo".</p>
    </div>

    <!-- PRAWY PANEL: wyniki -->
    <div>
      <div id="empty" class="panel">
        <h2>Wynik</h2>
        <p class="muted">Uruchom audyt lub demo, żeby zobaczyć uzgodnienie z fakturami,
          flagi audytowe i pliki do pobrania.</p>
      </div>
      <div id="err" class="err hidden"></div>
      <div id="result" class="hidden"></div>
    </div>
  </div>
  <div id="viewCenniki" class="hidden"></div>
</div>

<div class="wrap">
  <details class="panel" id="metodyka" style="margin-top:6px">
    <summary style="cursor:pointer;font-weight:650;color:var(--tx);font-size:15px">📖 Metodyka — co znaczą zakładki audit_report.xlsx i jak je liczymy</summary>
    <div id="glossaryBody" style="margin-top:14px"><p class="muted">Ładuję…</p></div>
  </details>
</div>

<script>
const $ = id => document.getElementById(id);
function fmt(n){return n==null?'—':Number(n).toLocaleString('pl-PL',{minimumFractionDigits:2,maximumFractionDigits:2});}
function esc(s){return (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

const VERCEL_BODY_LIMIT = 4.4*1024*1024;  // ~4,5 MB limit żądania serverless
let SUPA_OK = false;

(async function initConfig(){
  try{ const r=await fetch('/api/config'); const c=await r.json(); SUPA_OK=!!c.supabase_configured; }catch(e){}
  const supaRadio=$('srcSupa'), saveWrap=$('saveSupaWrap'), lbl=$('srcSupaLabel');
  if(SUPA_OK){ supaRadio.disabled=false; saveWrap.classList.remove('hidden'); }
  else { supaRadio.disabled=true; lbl.style.opacity=.45;
    lbl.title='Ustaw SUPABASE_URL i SUPABASE_KEY w zmiennych środowiskowych Vercel'; }
})();

function erpSource(){ const el=document.querySelector('input[name=erpsrc]:checked'); return el?el.value:'file'; }
function onSrc(){
  const supa = erpSource()==='supabase';
  $('erpFileWrap').classList.toggle('hidden', supa);
  $('supaNote').classList.toggle('hidden', !supa);
}

// --- widoki: Audyt / Cenniki ---
function showView(v){
  const audyt = v==='audyt';
  $('viewAudyt').classList.toggle('hidden', !audyt);
  $('viewCenniki').classList.toggle('hidden', audyt);
  $('navAudyt').classList.toggle('active', audyt);
  $('navCenniki').classList.toggle('active', !audyt);
  if(!audyt && !$('viewCenniki').dataset.loaded) loadTariffs();
}
async function loadTariffs(){
  $('viewCenniki').innerHTML='<div class="panel"><p class="muted">Ładuję cenniki…</p></div>';
  try{
    const t = await (await fetch('/api/tariffs')).json();
    $('viewCenniki').innerHTML = renderTariffs(t);
    $('viewCenniki').dataset.loaded='1';
  }catch(e){ $('viewCenniki').innerHTML='<div class="panel err">Nie udało się wczytać cenników: '+esc(e.message)+'</div>'; }
}
function bracketTable(t){
  const cur=t.currency;
  let h='<div class="scroll"><table><thead><tr><th class="num">Od [m³]</th><th class="num">Do [m³]</th>'
    +'<th class="num">bez wniesienia</th><th class="num">z wniesieniem</th></tr></thead><tbody>';
  for(const b of t.brackets){
    h+=`<tr><td class="num">${b.from.toFixed(2)}</td><td class="num">${b.to.toFixed(2)}</td>`
      +`<td class="num">${fmt(b.door)} ${cur}</td><td class="num">${fmt(b.carry)} ${cur}</td></tr>`;
  }
  h+='</tbody></table></div>';
  h+=`<p class="muted" style="margin-top:8px">${esc(t.over_note||'')} · Montaż ${fmt(t.services.montaz)} ${cur} · `
    +`Sprzątanie ${fmt(t.services.sprzatanie)} ${cur}. ${esc(t.services_note||'')}</p>`;
  return h;
}
function matrixTable(t){
  const cur=t.currency;
  let h='<div class="scroll"><table><thead><tr><th>Objętość [m³]</th>';
  for(const w of t.weights) h+=`<th class="num">≤${w} kg</th>`;
  h+='</tr></thead><tbody>';
  for(const r of t.rows){
    h+=`<tr><td>${r.from.toFixed(1)}–${r.to.toFixed(1)}</td>`;
    for(const p of r.prices) h+=`<td class="num">${fmt(p)}</td>`;
    h+='</tr>';
  }
  h+='<tr class="sep"><td><b>Wniesienie +</b></td>';
  for(const c of t.carry_in) h+=`<td class="num">${fmt(c)}</td>`; h+='</tr>';
  h+='<tr><td><b>RUS +</b></td>';
  for(const c of t.rus) h+=`<td class="num">${fmt(c)}</td>`; h+='</tr>';
  h+='</tbody></table></div>';
  const o=t.over||{};
  h+=`<p class="muted" style="margin-top:8px">${esc(t.over_note||'')} Wniesienie +${fmt(o.carry_per_15_kg)}/15 kg, `
    +`RUS +${fmt(o.rus_per_15_kg)}/15 kg. Ceny netto ${cur}.</p>`;
  return h;
}
function renderTariffs(t){
  const card=(title,sub,body)=>`<div class="panel sec"><h2>${title}</h2>`
    +`<p class="muted" style="margin:-8px 0 10px">${sub}</p>${body}</div>`;
  return '<div class="panel"><h2>Cenniki przewoźników</h2>'
    +'<p class="muted">Stawki netto wynegocjowane z przewoźnikami — używane w audycie do wykrywania przepłat. '
    +'Zweryfikuj liczby; jeśli coś się nie zgadza, poprawimy w źródle.</p></div>'
    + card('SPT — Polska (PLN)','Stawka tabelaryczna wg objętości', bracketTable(t.SPT_PL))
    + card('SPT — Niemcy (EUR)','Stawka tabelaryczna wg objętości', bracketTable(t.SPT_DE))
    + card('Zadbano (PLN)','Macierz: objętość × maks. waga przesyłki (wybór kolumny: najmniejsza ≥ waga)', matrixTable(t.ZADBANO));
}

// --- Metodyka (glosariusz zakładek audit_report) ---
(async function initGlossary(){
  try{
    const g = await (await fetch('/api/glossary')).json();
    let h='<div class="scroll"><table><thead><tr><th>Zakładka</th><th>Reguła</th><th>Priorytet</th>'
      +'<th>Co pokazuje</th><th>Jak liczone / próg</th></tr></thead><tbody>';
    for(const r of g.tabs){
      const pill = /FLAG/.test(r.priority)?'FLAG':(/INFO/.test(r.priority)?'INFO':'');
      h+=`<tr><td><b>${esc(r.tab)}</b></td><td>${esc(r.rule)}</td>`
        +`<td>${pill?`<span class="pill ${pill}">${esc(r.priority)}</span>`:esc(r.priority)}</td>`
        +`<td>${esc(r.what)}</td><td>${esc(r.how)}</td></tr>`;
    }
    h+='</tbody></table></div>';
    h+='<p class="muted" style="margin-top:12px"><b>Pozostałe pliki wyjściowe:</b><br>'
      + g.files.map(f=>`• <b>${esc(f.file)}</b> — ${esc(f.what)}`).join('<br>')+'</p>';
    $('glossaryBody').innerHTML=h;
  }catch(e){ $('glossaryBody').innerHTML='<p class="muted">Nie udało się wczytać metodyki.</p>'; }
})();

// --- wielo-plikowy akumulator: spec + faktury per przewoźnik ---
const FILES = {spt_spec:[],spt_inv:[],zad_spec:[],zad_inv:[],dm_spec:[],dm_inv:[]};
function addFiles(key, input){
  for(const f of input.files){
    if(!FILES[key].some(x=>x.name===f.name && x.size===f.size)) FILES[key].push(f);
  }
  input.value='';               // pozwól ponownie dodać ten sam plik po usunięciu
  renderChips(key);
}
function removeFile(key, i){ FILES[key].splice(i,1); renderChips(key); }
function renderChips(key){
  const box=$(key+'_chips'); if(!box) return;
  box.innerHTML = FILES[key].map((f,i)=>
    `<span class="chip"><span class="nm" title="${esc(f.name)}">${esc(f.name)}</span>`
    +`<span class="muted">${(f.size/1024).toFixed(0)} KB</span>`
    +`<button type="button" class="chipx" title="Usuń" onclick="removeFile('${key}',${i})">✕</button></span>`
  ).join('');
}

// Podziel pliki na porcje mieszczące się w limicie żądania (całych plików nie tniemy).
function chunkFiles(items, limit){
  const chunks=[]; let cur=[], sz=0;
  for(const it of items){
    if(it.file.size > limit)
      throw new Error('Plik „'+it.file.name+'" ('+(it.file.size/1048576).toFixed(1)
        +' MB) przekracza limit ~4,5 MB pojedynczego żądania Vercela. Dla tak dużego '
        +'pojedynczego pliku użyj CLI (bez limitu).');
    if(sz+it.file.size > limit && cur.length){ chunks.push(cur); cur=[]; sz=0; }
    cur.push(it); sz+=it.file.size;
  }
  if(cur.length) chunks.push(cur);
  return chunks;
}

// Dołóż sparsowaną porcję do zbieranej całości (per przewoźnik; sumy dopłat Zadbano).
function mergeParsed(acc, batch){
  for(const [c,blk] of Object.entries(batch.carriers||{})){
    const a = acc.carriers[c] || (acc.carriers[c]={deliveries:[],invoices:[],stated_total:null});
    a.deliveries.push(...(blk.deliveries||[]));
    a.invoices.push(...(blk.invoices||[]));
    if(blk.stated_total!=null) a.stated_total=(a.stated_total||0)+blk.stated_total;
  }
  const z=batch.zadbano_summary;
  if(z && z.categories){
    const az = acc.zadbano_summary.categories ? acc.zadbano_summary
      : (acc.zadbano_summary={categories:{},total:0});
    for(const [k,v] of Object.entries(z.categories)) az.categories[k]=(az.categories[k]||0)+v;
    az.total=(az.total||0)+(z.total||0);
  }
}

// --- pasek postępu ---
function showProgress(txt, indet){
  const p=$('progress'); p.classList.remove('hidden');
  p.classList.toggle('indet', !!indet);
  // indet: wyczyść inline width, żeby zadziałała animacja z CSS (.indet .bar)
  $('progressBar').style.width = indet ? '' : '0%';
  $('progressTxt').textContent = txt||'';
}
function setProgress(frac, txt){
  $('progress').classList.remove('indet');
  $('progressBar').style.width = Math.round(frac*100)+'%';
  if(txt!=null) $('progressTxt').textContent = txt;
}
function hideProgress(){ $('progress').classList.add('hidden'); }

// --- POST z paskiem postępu uploadu (XHR; fetch nie daje progresu wysyłki) ---
function xhrPost(url, fd, onProgress){
  return new Promise((resolve, reject)=>{
    const xhr=new XMLHttpRequest();
    xhr.open('POST', url);
    if(fd && xhr.upload && onProgress){
      xhr.upload.onprogress = e=>{ if(e.lengthComputable) onProgress(e.loaded/e.total, false); };
      xhr.upload.onload = ()=> onProgress(1, true);
    }
    xhr.onload = ()=> resolve({status:xhr.status,
      ct:(xhr.getResponseHeader('content-type')||''), text:xhr.responseText});
    xhr.onerror = ()=> reject(new Error('połączenie przerwane'));
    xhr.send(fd||null);
  });
}

async function runDemo(){ await run('/api/sample', null); }
async function runUpload(){
  const src=erpSource();
  // 1) zbierz WSZYSTKIE dołożone pliki przewoźników (spec + faktury), dowolna kolejność
  const items=[];
  const map=[['SPT','spt_spec','spt_inv'],['ZADBANO','zad_spec','zad_inv'],['DM_TRANS','dm_spec','dm_inv']];
  for(const [c,sk,ik] of map){
    for(const f of FILES[sk]) items.push({field:c+'_spec', file:f});
    for(const f of FILES[ik]) items.push({field:c+'_invoice', file:f});
  }
  if(!items.length){ showErr('Dodaj co najmniej jedno zestawienie przewoźnika (przycisk „➕ Dodaj pliki").'); return; }

  let erpFile=null;
  if(src==='file'){
    erpFile=$('erp').files[0];
    if(!erpFile){ showErr('Wgraj plik Eksport ERP (CSV), wybierz źródło Supabase, albo użyj „Pokaż na danych demo".'); return; }
    if(erpFile.size > VERCEL_BODY_LIMIT){ showErr('Sam Eksport.csv ('+(erpFile.size/1048576).toFixed(1)
      +' MB) przekracza limit ~4,5 MB. Przełącz źródło ERP na „Supabase" (bez uploadu CSV) albo użyj CLI.'); return; }
  }

  // 2) podziel pliki na porcje < limit (żeby zmieścić się w limicie żądania)
  let chunks;
  try{ chunks = chunkFiles(items, VERCEL_BODY_LIMIT); }
  catch(e){ showErr(e.message); return; }

  setLoading(true); hideErr();
  try{
    // 3) FAZA 1 — parsuj każdą porcję osobno, zbieraj drobne wyniki
    const merged={carriers:{}, zadbano_summary:{}};
    for(let i=0;i<chunks.length;i++){
      const fd=new FormData();
      fd.append('period', ($('period').value||'').trim());
      for(const it of chunks[i]) fd.append(it.field, it.file);
      const res=await xhrPost('/api/parse', fd, (frac,done)=>{
        if(done) showProgress('Porcja '+(i+1)+'/'+chunks.length+' — parsuję…', true);
        else setProgress(frac, 'Wysyłam pliki (porcja '+(i+1)+'/'+chunks.length+'): '+Math.round(frac*100)+'%');
      });
      if(!res.ct.includes('json')){ showErr('Parsowanie: serwer zwrócił nie-JSON ('+res.status+').'); return; }
      const data=JSON.parse(res.text);
      if(res.status>=400 || data.error){ showErr(data.error||('Błąd parsowania porcji '+(i+1)+' ('+res.status+')')); return; }
      mergeParsed(merged, data);
    }

    // 4) FAZA 2 — audyt na złożonym, PEŁNYM okresie (mały pakiet 'parsed' + ERP)
    showProgress('Liczę audyt na pełnym okresie…', true);
    const fd=new FormData();
    fd.append('period', ($('period').value||'').trim());
    fd.append('erp_source', src);
    if($('saveSupa') && $('saveSupa').checked) fd.append('save_supabase','1');
    if(erpFile) fd.append('erp', erpFile);
    fd.append('parsed', JSON.stringify(merged));
    const res=await xhrPost('/api/run', fd, (frac,done)=>{
      if(done) showProgress('Liczę audyt…', true);
      else setProgress(frac, 'Wysyłam dane do audytu: '+Math.round(frac*100)+'%');
    });
    if(!res.ct.includes('json')){
      const txt=(res.text||'').slice(0,300);
      if(res.status===413) showErr('Dane do audytu przekraczają limit — jeśli ERP jest z pliku, przełącz źródło na „Supabase".');
      else showErr('Serwer zwrócił nie-JSON ('+res.status+'): '+txt);
      return;
    }
    const d=JSON.parse(res.text);
    if(res.status>=400 || d.error){ showErr(d.error||('Błąd '+res.status)); return; }
    render(d);
  }catch(e){ showErr('Nie udało się połączyć: '+e.message); }
  finally{ setLoading(false); hideProgress(); }
}

async function run(url, fd){
  const isUpload = !!fd;
  setLoading(true); hideErr();
  showProgress(isUpload ? 'Wysyłanie plików… 0%' : 'Liczę na danych demo…', !isUpload);
  try{
    let res;
    if(isUpload){
      res = await xhrPost(url, fd, (frac, done)=>{
        if(done) showProgress('Pliki wgrane — liczę audyt…', true);
        else setProgress(frac, 'Wysyłanie plików… '+Math.round(frac*100)+'%');
      });
    } else {
      res = await xhrPost(url, null, null);
    }
    if(!res.ct.includes('json')){
      const txt=(res.text||'').slice(0,300);
      if(res.status===413 || /too large|entity too large/i.test(txt)){
        showErr('Pliki przekraczają limit żądania Vercela (~4,5 MB) — zwykle duży Eksport.csv. '
          +'Zmniejsz go do jednego okresu, wgraj mniej plików, użyj CLI, albo trybu „import ERP z Supabase".');
      } else {
        showErr('Serwer zwrócił nie-JSON ('+res.status+'): '+txt);
      }
      return;
    }
    const data = JSON.parse(res.text);
    if(res.status>=400 || data.error){ showErr(data.error||('Błąd '+res.status)); return; }
    render(data);
  }catch(e){ showErr('Nie udało się połączyć: '+e.message); }
  finally{ setLoading(false); hideProgress(); }
}

function setLoading(on){
  for(const b of ['runBtn','demoBtn']) $(b).disabled=on;
  $('runBtn').innerHTML = on ? '<span class="spin"></span> Liczę…' : 'Uruchom audyt';
}
function showErr(m){ $('err').textContent=m; $('err').classList.remove('hidden'); }
function hideErr(){ $('err').classList.add('hidden'); }

function tbl(cols, rows, rowFn){
  if(!rows||!rows.length) return '<p class="muted">brak pozycji</p>';
  let h='<div class="scroll"><table><thead><tr>'+cols.map(c=>`<th class="${c.num?'num':''}">${c.t}</th>`).join('')+'</tr></thead><tbody>';
  h+=rows.map(rowFn).join('');
  return h+'</tbody></table></div>';
}

function dlLink(f){
  if(!f) return '';
  const mime = f.filename.endsWith('.xlsx')?'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    : f.filename.endsWith('.csv')?'text/csv':'application/json';
  return `<a class="dl" download="${f.filename}" href="data:${mime};base64,${f.base64}">⬇ ${f.filename} (${(f.size/1024).toFixed(0)} KB)</a>`;
}

function render(d){
  $('empty').classList.add('hidden');
  const F=d.findings||{};
  const rec = tbl(
    [{t:'Przewoźnik'},{t:'Faktura'},{t:'Rozliczenie'},{t:'Σ koszt netto',num:1},{t:'Netto FV',num:1},{t:'Delta',num:1},{t:'OK'}],
    d.reconciliation, r=>`<tr><td>${esc(r.carrier)}</td><td><code>${esc(r.invoice_no)}</code></td>
      <td>${esc(r.settlement_no||'—')}</td><td class="num">${fmt(r.actual_sum)}</td>
      <td class="num">${fmt(r.expected_net)}</td><td class="num">${r.delta==null?'—':(r.delta>=0?'+':'')+fmt(r.delta)}</td>
      <td class="${r.within_tolerance?'ok':'bad'}">${r.within_tolerance?'✓':'✗'}</td></tr>`);

  const flagRows = (d.flags_by_rule||[]).map(x=>`<tr><td>${esc(x.rule)}</td>
    <td class="num">${x.FLAG?`<span class="pill FLAG">${x.FLAG}</span>`:'0'}</td>
    <td class="num">${x.WARN?`<span class="pill WARN">${x.WARN}</span>`:'0'}</td>
    <td class="num">${x.INFO?`<span class="pill INFO">${x.INFO}</span>`:'0'}</td></tr>`).join('');

  const cc = tbl([{t:'Rdzeń'},{t:'Zamówienie'},{t:'Koszt łączny',num:1},{t:'Do odzyskania',num:1},{t:'Dowód'}],
    F.cross_carrier, r=>`<tr><td><code>${esc(r.order_core)}</code></td><td>${esc(r.order_number||'—')}</td>
      <td class="num">${fmt(r.amount)}</td><td class="num bad">${fmt(r.recoverable)}</td><td>${esc(r.evidence)}</td></tr>`);

  const failed = tbl([{t:'Rdzeń'},{t:'Przew.'},{t:'Kwota',num:1},{t:'Opis'}],
    F.failed_charged, r=>`<tr><td><code>${esc(r.order_core)}</code></td><td>${esc(r.carrier)}</td>
      <td class="num">${fmt(r.amount)}</td><td>${esc(r.message)}</td></tr>`);

  const duble = tbl([{t:'Rdzeń'},{t:'Przew.'},{t:'Sev'},{t:'Kwota',num:1},{t:'Do odzysk.',num:1},{t:'Dowód'}],
    F.double, r=>`<tr><td><code>${esc(r.order_core)}</code></td><td>${esc(r.carrier)}</td>
      <td><span class="pill ${r.severity}">${r.severity}</span></td><td class="num">${fmt(r.amount)}</td>
      <td class="num">${fmt(r.recoverable)}</td><td>${esc(r.evidence)}</td></tr>`);

  const sm = tbl([{t:'Rdzeń'},{t:'Przew.'},{t:'Opis'}],
    F.service_mismatch, r=>`<tr><td><code>${esc(r.order_core)}</code></td><td>${esc(r.carrier)}</td><td>${esc(r.message)}</td></tr>`);

  const at = tbl([{t:'Rdzeń'},{t:'Przew.'},{t:'Koszt',num:1},{t:'Oczekiwane',num:1},{t:'Opis'}],
    F.above_tariff, r=>`<tr><td><code>${esc(r.order_core)}</code></td><td>${esc(r.carrier)}</td>
      <td class="num">${fmt(r.amount)}</td><td class="num">${fmt(r.expected)}</td><td>${esc(r.message)}</td></tr>`);

  const bt=d.backtest||{};
  const sw=d.supabase_write;
  const swMsg = !sw ? '' : (sw.status==='upserted'
      ? `<p style="margin-top:8px"><span class="ok">✓ Zapisano do Supabase:</span> ${sw.fact_rows} rekordów fact_delivery_costs, ${sw.recon_rows} reconciliation_log</p>`
      : `<p style="margin-top:8px"><span class="bad">Supabase (${esc(sw.status)}):</span> ${esc(sw.error||sw.reason||'')}</p>`);
  const srcMsg = d.erp_source==='supabase' ? ' · źródło ERP: Supabase' : '';
  $('result').innerHTML = `
    <div class="kpis">
      <div class="kpi"><div class="v ${d.reconcile_ok?'ok':'bad'}">${d.reconcile_ok?'✓ zgodne':'✗ rozjazd'}</div><div class="l">Uzgodnienie z FV</div></div>
      <div class="kpi"><div class="v" style="color:var(--flag)">${d.total_flags}</div><div class="l">Flagi (FLAG)</div></div>
      <div class="kpi"><div class="v">${fmt(d.recoverable_estimate)} zł</div><div class="l">Do odzyskania (szac.)</div></div>
      <div class="kpi"><div class="v">${(bt.agreement_rate*100||0).toFixed(1)}%</div><div class="l">Backtest matchera</div></div>
    </div>

    <div class="panel">
      <h2>Uzgodnienie z fakturami — okres ${esc(d.period||'?')} (§9)</h2>${rec}
      <p class="muted" style="margin-top:8px">Dopasowane linie: ${d.counts.matched} / ${d.counts.deliveries} ·
        osierocone: ${d.counts.orphans} · nieobciążone: ${d.counts.unbilled} ·
        zamówienia ERP: ${d.counts.erp_orders}${srcMsg}</p>
    </div>

    <div class="panel sec">
      <h2>Ustalenia audytowe (§6)</h2>
      <div class="scroll"><table><thead><tr><th>Reguła</th><th class="num">FLAG</th><th class="num">WARN</th><th class="num">INFO</th></tr></thead><tbody>${flagRows}</tbody></table></div>
    </div>

    <div class="panel sec"><div class="sec"><h3>🔴 Cross-carrier — obciążone przez &gt;1 przewoźnika</h3>
      <div class="cap">Priorytet WYSOKI. Kwota do odzyskania = min. z dwóch obciążeń.</div>${cc}</div></div>

    <div class="panel sec"><div class="sec"><h3>Nieudane / anulowane obciążone</h3>
      <div class="cap">status ∈ {FAILED, CANCELLED} a koszt &gt; 0.</div>${failed}</div>
      <div class="sec"><h3>Duble / split w obrębie przewoźnika</h3>${duble}</div>
      <div class="sec"><h3>Niespójność poziomu usługi</h3>${sm}</div>
      <div class="sec"><h3>Przepłaty względem cennika</h3>
        <div class="cap">Najpierw względem <b>oficjalnego cennika</b> przewoźnika (× 1,05, gdy znamy
          objętość/wagę), a w razie braku danych — mediana klastra × 1,20 (≥5 obserwacji).
          Kolumna „Oczekiwane" = stawka odniesienia; źródło w kolumnie „Opis".</div>${at}</div>
    </div>

    <div class="panel sec">
      <h2>Pliki do pobrania (§7)</h2>
      <div class="row">
        ${dlLink(d.files&&d.files.audit_report)}
        ${dlLink(d.files&&d.files.enriched_orders)}
        ${dlLink(d.files&&d.files.reference_tariff)}
      </div>
      <p class="muted" style="margin-top:10px">audit_report.xlsx zawiera 17 zakładek (m.in. Cross_carrier,
        Duble, Przeplaty, Nieudane_obciazone, Walidacja_vs_reczne, Podsumowanie_per_przewoznik);
        ostatnia „Legenda" opisuje każdą zakładkę — pełna metodyka w sekcji na dole strony.</p>
      ${swMsg}
    </div>`;
  $('result').classList.remove('hidden');
}
</script>
</body>
</html>
"""
