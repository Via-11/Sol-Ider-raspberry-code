// Sol-ider Dashboard JS

Chart.defaults.font.family = "'DM Sans', sans-serif";
Chart.defaults.color = '#7A7060';

const C = {
  sun:  '#F5A623', sunA:  'rgba(245,166,35,.15)',
  sun2: '#FF7B2C', sun2A: 'rgba(255,123,44,.12)',
  grn:  '#3D7A52', grnA:  'rgba(61,122,82,.14)',
  blu:  '#3A7FBF', bluA:  'rgba(58,127,191,.12)',
  ert:  '#8B5A2B', ertA:  'rgba(139,90,43,.12)',
};

let charts    = {};
let histHours = 24;


// --------------------------------------------------------------------
// TOAST
// --------------------------------------------------------------------

function showToast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className   = `toast toast-${type} show`;
  setTimeout(() => { t.className = 'toast'; }, 3500);
}


// --------------------------------------------------------------------
// TAB NAVIGATION
// --------------------------------------------------------------------

document.querySelectorAll('.tab').forEach(t =>
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById(`tab-${t.dataset.tab}`).classList.add('active');
    if (t.dataset.tab === 'records') loadRecords();
  })
);


// --------------------------------------------------------------------
// SESSION BUTTONS
// --------------------------------------------------------------------

document.getElementById('startSessionBtn').addEventListener('click', async () => {
  try {
    const d = await fetch('/api/start_session', { method: 'POST' }).then(r => r.json());
    showToast(d.ok ? 'Drying session started!' : (d.msg || 'Could not start.'), d.ok ? 'success' : 'error');
    if (d.ok) fetchLive();
  } catch { showToast('Could not reach server.', 'error'); }
});

document.getElementById('endSessionBtn').addEventListener('click', async () => {
  try {
    const d = await fetch('/api/end_session', { method: 'POST' }).then(r => r.json());
    showToast(d.ok ? 'Session complete! Record saved.' : (d.msg || 'Could not end.'), d.ok ? 'success' : 'error');
    if (d.ok) { fetchLive(); loadRecords(); }
  } catch { showToast('Could not reach server.', 'error'); }
});


// --------------------------------------------------------------------
// LIVE DATA
// --------------------------------------------------------------------

async function fetchLive() {
  try {
    const d = await fetch('/api/live').then(r => r.json());
    updateCards(d);
    setPill(true, d.drying_in_progress);
    // Hide power buttons in simulation mode
    if (d.simulate) document.body.classList.add('sim-mode');
  } catch {
    setPill(false, false);
  }
}

function setPill(on, drying) {
  const pill = document.getElementById('statusPill');
  const txt  = document.getElementById('statusText');
  pill.className  = 'status-pill' + (on ? '' : ' off');
  txt.textContent = !on ? 'Offline' : drying ? 'Drying…' : 'Online';
}

function updateCards(d) {
  const at = +((+d.temp1 + +d.temp2) / 2).toFixed(1);
  const ah = +((+d.hum1  + +d.hum2)  / 2).toFixed(1);
  const w  = +(+d.weight).toFixed(2);

  const simBadge = document.getElementById('simBadge');
  if (simBadge) simBadge.style.display = d.simulate ? 'inline-flex' : 'none';

  // Temperature
  set('tempAvg', at);
  set('temp1', d.temp1);
  set('temp2', d.temp2);
  document.getElementById('tempFill').style.width = Math.min(at / 60 * 100, 100) + '%';

  // Humidity
  set('humAvg', ah);
  set('hum1', d.hum1);
  set('hum2', d.hum2);
  document.getElementById('humFill').style.width = Math.min(ah, 100) + '%';

  const hs = document.getElementById('humStatus');
  if (ah <= 30) {
    hs.textContent = '✓ Target reached (≤30% RH)';
    hs.className   = 'hum-status hum-ok';
  } else if (ah <= 50) {
    hs.textContent = `${(ah - 30).toFixed(0)}% above target — drying…`;
    hs.className   = 'hum-status hum-warn';
  } else {
    hs.textContent = `${ah}% — high humidity`;
    hs.className   = 'hum-status';
  }

  // Weight
  set('weightVal', w);
  document.getElementById('gaugeFill').style.width = Math.min(w / 6 * 100, 100) + '%';
  const ws = document.getElementById('weightStatus');
  if (w <= 2.0) {
    ws.textContent = '✓ Target weight reached (≤2 kg)';
    ws.style.color = 'var(--green)';
  } else {
    ws.textContent = `Current load: ${w} kg`;
    ws.style.color = 'var(--muted)';
  }

  // Conditions
  const humMet    = ah <= 30;
  const weightMet = w  <= 2.0;
  setCondition('ccheck-hum',    'cval-hum',    humMet,    `${ah}% RH`,  '≤30% RH');
  setCondition('ccheck-weight', 'cval-weight', weightMet, `${w} kg`,    '≤2.0 kg');

  const res = document.getElementById('condResult');
  const txt = document.getElementById('condResultText');
  if (humMet && weightMet) {
    res.className   = 'cond-result ok';
    txt.textContent = '🎉 Food waste is dried — auto-logging!';
  } else if (d.drying_in_progress) {
    res.className   = 'cond-result drying';
    txt.textContent = '🌀 Drying in progress…';
  } else {
    res.className   = 'cond-result';
    const needs = [];
    if (!humMet)    needs.push('humidity');
    if (!weightMet) needs.push('weight');
    txt.textContent = `Waiting for ${needs.join(' & ')} to reach target`;
  }

  // Session banner / start bar
  const banner   = document.getElementById('dryingBanner');
  const startBar = document.getElementById('startBar');
  if (d.drying_in_progress) {
    banner.style.display   = 'block';
    startBar.style.display = 'none';
    if (d.session_start_time) {
      const elapsed = Math.floor((Date.now() - new Date(d.session_start_time)) / 60000);
      const hrs = Math.floor(elapsed / 60), mins = elapsed % 60;
      const el = document.getElementById('sessionElapsed');
      if (el) el.textContent = hrs > 0 ? `${hrs}h ${mins}m elapsed` : `${mins}m elapsed`;
    }
  } else {
    banner.style.display   = 'none';
    startBar.style.display = 'block';
  }

  document.getElementById('lastUpd').textContent = fmtTime(d.last_updated);
}

function setCondition(checkId, valId, met, current, target) {
  const chk = document.getElementById(checkId);
  const val = document.getElementById(valId);
  if (chk) chk.textContent = met ? '✅' : '○';
  if (val) val.textContent  = met ? `${current} ✓` : `${current} (target: ${target})`;
}

function set(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}


// --------------------------------------------------------------------
// HISTORY CHARTS
// --------------------------------------------------------------------

async function loadHistory(hours) {
  try {
    const days = Math.ceil(hours / 24);
    const data = await fetch(`/api/history?days=${days}`).then(r => r.json());
    renderEnv(data);
    renderWeight(data);
  } catch (e) {
    console.warn('History load failed:', e);
  }
}

function renderEnv(data) {
  const labels = data.map(d => fmtShort(d.timestamp));
  const ctx    = document.getElementById('envChart').getContext('2d');
  if (charts.env) charts.env.destroy();
  charts.env = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Avg Temp (°C)',
          data: data.map(d => d.avg_temp),
          borderColor: C.sun, backgroundColor: C.sunA,
          borderWidth: 2, fill: true, tension: .4,
          pointRadius: 0, pointHoverRadius: 4, yAxisID: 'yT'
        },
        {
          label: 'Avg Humidity (%)',
          data: data.map(d => d.avg_hum),
          borderColor: C.blu, backgroundColor: C.bluA,
          borderWidth: 2, fill: true, tension: .4,
          pointRadius: 0, pointHoverRadius: 4, yAxisID: 'yH'
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'top', labels: { boxWidth: 12, padding: 16 } } },
      scales: {
        x:  { ticks: { maxTicksLimit: 8, font: { size: 11 } }, grid: { color: '#F0EDE5' } },
        yT: { type: 'linear', position: 'left',
              title: { display: true, text: '°C', font: { size: 11 } },
              grid: { color: '#F0EDE5' } },
        yH: { type: 'linear', position: 'right', min: 0, max: 100,
              title: { display: true, text: '% RH', font: { size: 11 } },
              grid: { drawOnChartArea: false } }
      }
    }
  });
}

function renderWeight(data) {
  const ctx = document.getElementById('weightChart').getContext('2d');
  if (charts.weight) charts.weight.destroy();
  charts.weight = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(d => fmtShort(d.timestamp)),
      datasets: [{
        label: 'Weight (kg)',
        data: data.map(d => d.weight),
        borderColor: C.grn, backgroundColor: C.grnA,
        borderWidth: 2, fill: true, tension: .3,
        pointRadius: 0, pointHoverRadius: 4
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxTicksLimit: 5, font: { size: 11 } }, grid: { color: '#F0EDE5' } },
        y: { min: 0, title: { display: true, text: 'kg', font: { size: 11 } }, grid: { color: '#F0EDE5' } }
      }
    }
  });
}

document.querySelectorAll('.rbtn').forEach(b =>
  b.addEventListener('click', () => {
    document.querySelectorAll('.rbtn').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    histHours = +b.dataset.hours;
    loadHistory(histHours);
  })
);


// --------------------------------------------------------------------
// RECORDS
// --------------------------------------------------------------------

async function loadRecords() {
  const days = document.getElementById('recDays').value;
  try {
    const [recs, summary] = await Promise.all([
      fetch(`/api/records?days=${days}`).then(r => r.json()),
      fetch(`/api/summary?days=${days}`).then(r => r.json()),
    ]);
    renderTable(recs);
    renderSummary(summary);
  } catch (e) {
    console.warn('Records load failed:', e);
  }
}

function renderSummary(s) {
  set('s-batches',   s.total_batches   || '—');
  set('s-processed', s.total_kg_processed > 0 ? s.total_kg_processed + ' kg' : '—');
  set('s-reduced',   s.total_kg_reduced   > 0 ? s.total_kg_reduced   + ' kg' : '—');
  set('s-pct',       s.avg_reduction_pct  > 0 ? s.avg_reduction_pct  + '%'   : '—');
  set('s-dur',       s.avg_duration_hours > 0 ? s.avg_duration_hours + ' h'  : '—');
  set('s-temp',      s.avg_temperature    > 0 ? s.avg_temperature    + '°C'  : '—');
  set('s-hum',       s.avg_humidity       > 0 ? s.avg_humidity       + '%'   : '—');
}

function renderTable(recs) {
  const tbody = document.getElementById('recBody');
  if (!recs.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-cell">No records in this range.</td></tr>`;
    return;
  }
  tbody.innerHTML = recs.map((r, i) => {
    const pct = r.initial_weight > 0
      ? (r.weight_reduced / r.initial_weight * 100).toFixed(1)
      : '—';
    const cls = +pct >= 40 ? 'b-green' : 'b-amber';
    return `<tr>
      <td><strong>${recs.length - i}</strong></td>
      <td>${fmtDate(r.end_time)}</td>
      <td>${r.initial_weight} kg</td>
      <td>${r.final_weight} kg</td>
      <td><span class="badge ${cls}">▼ ${r.weight_reduced} kg (${pct}%)</span></td>
      <td>${(r.duration_minutes / 60).toFixed(1)} h</td>
      <td>${r.avg_humidity}%</td>
      <td>${r.avg_temperature}°C</td>
      <td style="color:var(--muted);font-size:.78rem">${r.notes || '—'}</td>
    </tr>`;
  }).join('');
}

document.getElementById('recDays').addEventListener('change', loadRecords);


// --------------------------------------------------------------------
// ADD RECORD MODAL
// --------------------------------------------------------------------

document.getElementById('openModal').addEventListener('click', () => {
  const now = new Date();
  document.getElementById('f-start').value = dtLocal(new Date(now - 4 * 3600000));
  document.getElementById('f-end').value   = dtLocal(now);
  document.getElementById('modalBg').style.display = 'flex';
});

['closeModal', 'cancelModal'].forEach(id =>
  document.getElementById(id).addEventListener('click', () =>
    document.getElementById('modalBg').style.display = 'none')
);

document.getElementById('modalBg').addEventListener('click', e => {
  if (e.target === document.getElementById('modalBg'))
    document.getElementById('modalBg').style.display = 'none';
});

document.getElementById('saveModal').addEventListener('click', async () => {
  const st = document.getElementById('f-start').value.replace('T', ' ') + ':00';
  const et = document.getElementById('f-end').value.replace('T', ' ')   + ':00';
  const iw = parseFloat(document.getElementById('f-iw').value);
  const fw = parseFloat(document.getElementById('f-fw').value);
  if (!iw || !fw || !st || !et) {
    showToast('Please fill in all required fields.', 'error'); return;
  }
  try {
    const d = await fetch('/api/records/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_time:      st,
        end_time:        et,
        initial_weight:  iw,
        final_weight:    fw,
        avg_humidity:    parseFloat(document.getElementById('f-hum').value)  || 0,
        avg_temperature: parseFloat(document.getElementById('f-temp').value) || 0,
        notes:           document.getElementById('f-notes').value
      })
    }).then(r => r.json());
    document.getElementById('modalBg').style.display = 'none';
    if (d.ok) { showToast('Record saved!', 'success'); loadRecords(); }
    else showToast('Failed to save: ' + (d.msg || ''), 'error');
  } catch { showToast('Server error.', 'error'); }
});


// --------------------------------------------------------------------
// POWER BUTTONS — Shutdown & Reboot
// --------------------------------------------------------------------

let pendingAction = null;

const powerModalBg    = document.getElementById('powerModalBg');
const powerModalTitle = document.getElementById('powerModalTitle');
const powerModalMsg   = document.getElementById('powerModalMsg');
const confirmPowerBtn = document.getElementById('confirmPowerBtn');

function openPowerModal(action) {
  pendingAction = action;
  if (action === 'shutdown') {
    powerModalTitle.textContent = '⏻ Shut Down Raspberry Pi?';
    powerModalMsg.textContent   = 'The Pi will power off completely. To restart Sol-ider, you must physically unplug and replug the power cable.';
    confirmPowerBtn.textContent = '⏻ Yes, Shut Down';
    confirmPowerBtn.className   = 'btn-power-confirm';
  } else {
    powerModalTitle.textContent = '↺ Restart Raspberry Pi?';
    powerModalMsg.textContent   = 'The Pi will reboot and the web app will be back online in about 30–60 seconds. Your data will not be lost.';
    confirmPowerBtn.textContent = '↺ Yes, Restart';
    confirmPowerBtn.className   = 'btn-power-confirm is-reboot';
  }
  powerModalBg.style.display = 'flex';
}

document.getElementById('shutdownBtn').addEventListener('click', () => openPowerModal('shutdown'));
document.getElementById('rebootBtn').addEventListener('click',   () => openPowerModal('reboot'));
document.getElementById('closePowerModal').addEventListener('click',  () => powerModalBg.style.display = 'none');
document.getElementById('cancelPowerModal').addEventListener('click', () => powerModalBg.style.display = 'none');
powerModalBg.addEventListener('click', e => { if (e.target === powerModalBg) powerModalBg.style.display = 'none'; });

confirmPowerBtn.addEventListener('click', async () => {
  powerModalBg.style.display = 'none';
  const action   = pendingAction;
  const endpoint = action === 'shutdown' ? '/api/shutdown' : '/api/reboot';
  try {
    const d = await fetch(endpoint, { method: 'POST' }).then(r => r.json());
    if (d.ok) {
      showToast(action === 'shutdown' ? '⏻ Shutting down…' : '↺ Rebooting…', 'success');
      if (action === 'shutdown') {
        // Dim the page after 3s so user sees it's shutting down
        setTimeout(() => {
          document.body.style.opacity        = '0.3';
          document.body.style.pointerEvents  = 'none';
          document.body.style.transition     = 'opacity 1s';
        }, 3000);
      }
    } else {
      showToast(d.msg || 'Command failed.', 'error');
    }
  } catch {
    showToast('Could not reach server.', 'error');
  }
});


// --------------------------------------------------------------------
// HELPERS
// --------------------------------------------------------------------

function fmtTime(ts) {
  if (!ts) return '—';
  return new Date(ts).toLocaleString('en-PH', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  });
}

function fmtShort(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

function fmtDate(ts) {
  if (!ts) return '—';
  return new Date(ts).toLocaleString('en-PH', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

function dtLocal(d) {
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}


// --------------------------------------------------------------------
// INIT
// --------------------------------------------------------------------

(async () => {
  await fetchLive();
  await loadHistory(histHours);
  setInterval(fetchLive, 8000);
  setInterval(() => loadHistory(histHours), 60000);
})();
