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
</style>
</head>
<body>
<header>
  <h1>Audyt kosztów transportu — MyBed / Delta Industries</h1>
  <p>Przypisanie realnego kosztu dostawy, audyt (duble, cross-carrier, nieudane, przepłaty)
     i uzgodnienie z fakturami zbiorczymi SPT / Zadbano / D&amp;M Trans.</p>
</header>
<div class="wrap">
  <div class="grid">
    <!-- LEWY PANEL: wejście -->
    <div class="panel">
      <h2>Dane wejściowe</h2>
      <label>Eksport ERP (CSV)</label>
      <input type="file" id="erp" accept=".csv">
      <label>Okres (YYYY-MM)</label>
      <input type="text" id="period" value="2026-02" placeholder="2026-02">

      <div class="car">
        <b>SPT</b> <span class="muted">PDF „flat"</span>
        <label>Zestawienie (spec)</label><input type="file" id="spt_spec" accept=".pdf">
        <label>Faktura</label><input type="file" id="spt_inv" accept=".pdf">
      </div>
      <div class="car">
        <b>Zadbano</b> <span class="muted">XLSX „itemized"</span>
        <label>Zestawienie (spec)</label><input type="file" id="zad_spec" accept=".xlsx">
        <label>Faktura</label><input type="file" id="zad_inv" accept=".pdf">
      </div>
      <div class="car">
        <b>D&amp;M Trans</b> <span class="muted">PDF „flat + usługi"</span>
        <label>Zestawienie (spec)</label><input type="file" id="dm_spec" accept=".pdf">
        <label>Faktura</label><input type="file" id="dm_inv" accept=".pdf">
      </div>

      <div class="row">
        <button class="btn" id="runBtn" onclick="runUpload()">Uruchom audyt</button>
        <button class="btn ghost" id="demoBtn" onclick="runDemo()">Pokaż na danych demo</button>
      </div>
      <p class="muted" style="margin-top:10px">Wgraj min. Eksport ERP + jedno zestawienie.
        Bez plików kliknij „Pokaż na danych demo" — policzy na wbudowanym, syntetycznym
        zestawie (golden cases).</p>
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
</div>

<script>
const $ = id => document.getElementById(id);
function fmt(n){return n==null?'—':Number(n).toLocaleString('pl-PL',{minimumFractionDigits:2,maximumFractionDigits:2});}
function esc(s){return (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

const VERCEL_BODY_LIMIT = 4.4*1024*1024;  // ~4,5 MB limit żądania serverless
async function runDemo(){ await run('/api/sample', null); }
async function runUpload(){
  const erp=$('erp').files[0];
  if(!erp){ showErr('Wgraj plik Eksport ERP (CSV) albo użyj „Pokaż na danych demo".'); return; }
  const fd=new FormData();
  fd.append('period', $('period').value||'2026-02');
  fd.append('erp', erp);
  let total=erp.size, any=false;
  const map=[['SPT','spt_spec','spt_inv'],['ZADBANO','zad_spec','zad_inv'],['DM_TRANS','dm_spec','dm_inv']];
  for(const [c,s,i] of map){
    if($(s).files[0]){ fd.append(c+'_spec',$(s).files[0]); total+=$(s).files[0].size; any=true;
      if($(i).files[0]){ fd.append(c+'_invoice',$(i).files[0]); total+=$(i).files[0].size; } }
  }
  if(!any){ showErr('Wgraj co najmniej jedno zestawienie przewoźnika.'); return; }
  if(total > VERCEL_BODY_LIMIT){
    showErr('Suma wgranych plików to '+(total/1048576).toFixed(1)+' MB, a limit żądania Vercela to '
      +'~4,5 MB. Najczęściej to duży Eksport.csv — zmniejsz go do jednego okresu, użyj CLI, '
      +'albo skorzystaj z trybu „import ERP z Supabase" (bez uploadu).');
    return;
  }
  await run('/api/run', fd);
}

async function run(url, body){
  setLoading(true); hideErr();
  try{
    const opt = body ? {method:'POST', body} : {method:'POST'};
    const r = await fetch(url, opt);
    const ct = r.headers.get('content-type')||'';
    if(!ct.includes('json')){
      const txt=(await r.text()).slice(0,300);
      if(r.status===413 || /too large|entity too large/i.test(txt)){
        showErr('Pliki przekraczają limit żądania Vercela (~4,5 MB) — zwykle duży Eksport.csv. '
          +'Zmniejsz go do jednego okresu, użyj CLI, albo trybu „import ERP z Supabase".');
      } else {
        showErr('Serwer zwrócił nie-JSON ('+r.status+'): '+txt);
      }
      return;
    }
    const data = await r.json();
    if(!r.ok || data.error){ showErr(data.error||('Błąd '+r.status)); return; }
    render(data);
  }catch(e){ showErr('Nie udało się połączyć: '+e.message); }
  finally{ setLoading(false); }
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

  const at = tbl([{t:'Rdzeń'},{t:'Przew.'},{t:'Koszt',num:1},{t:'Mediana',num:1},{t:'Opis'}],
    F.above_tariff, r=>`<tr><td><code>${esc(r.order_core)}</code></td><td>${esc(r.carrier)}</td>
      <td class="num">${fmt(r.amount)}</td><td class="num">${fmt(r.expected)}</td><td>${esc(r.message)}</td></tr>`);

  const bt=d.backtest||{};
  $('result').innerHTML = `
    <div class="kpis">
      <div class="kpi"><div class="v ${d.reconcile_ok?'ok':'bad'}">${d.reconcile_ok?'✓ zgodne':'✗ rozjazd'}</div><div class="l">Uzgodnienie z FV</div></div>
      <div class="kpi"><div class="v" style="color:var(--flag)">${d.total_flags}</div><div class="l">Flagi (FLAG)</div></div>
      <div class="kpi"><div class="v">${fmt(d.recoverable_estimate)} zł</div><div class="l">Do odzyskania (szac.)</div></div>
      <div class="kpi"><div class="v">${(bt.agreement_rate*100||0).toFixed(1)}%</div><div class="l">Backtest matchera</div></div>
    </div>

    <div class="panel">
      <h2>Uzgodnienie z fakturami zbiorczymi (§9)</h2>${rec}
      <p class="muted" style="margin-top:8px">Dopasowane linie: ${d.counts.matched} / ${d.counts.deliveries} ·
        osierocone: ${d.counts.orphans} · nieobciążone: ${d.counts.unbilled} ·
        zamówienia ERP: ${d.counts.erp_orders}</p>
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
        <div class="cap">Koszt transportu &gt; mediana klastra × 1,20 (≥5 obserwacji).</div>${at}</div>
    </div>

    <div class="panel sec">
      <h2>Pliki do pobrania (§7)</h2>
      <div class="row">
        ${dlLink(d.files&&d.files.audit_report)}
        ${dlLink(d.files&&d.files.enriched_orders)}
        ${dlLink(d.files&&d.files.reference_tariff)}
      </div>
      <p class="muted" style="margin-top:10px">audit_report.xlsx zawiera 16 zakładek (m.in. Cross_carrier,
        Duble, Przeplaty, Nieudane_obciazone, Walidacja_vs_reczne, Podsumowanie_per_przewoznik).</p>
    </div>`;
  $('result').classList.remove('hidden');
}
</script>
</body>
</html>
"""
