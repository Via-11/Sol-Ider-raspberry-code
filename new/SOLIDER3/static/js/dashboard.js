// Sol-ider Dashboard JS

Chart.defaults.font.family = "'DM Sans', sans-serif";
Chart.defaults.color = '#7A7060';

const C = {
  sun:  '#F5A623', sunA: 'rgba(245,166,35,.15)',
  sun2: '#FF7B2C', sun2A:'rgba(255,123,44,.12)',
  grn:  '#3D7A52', grnA: 'rgba(61,122,82,.14)',
  blu:  '#3A7FBF', bluA: 'rgba(58,127,191,.12)',
  ert:  '#8B5A2B', ertA: 'rgba(139,90,43,.12)',
};

let charts = {};
let histDays = 1;

// Tab navigation
document.querySelectorAll('.tab').forEach(t =>
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    const id = `tab-${t.dataset.tab}`;
    document.getElementById(id).classList.add('active');
    if (t.dataset.tab === 'records')  loadRecords();
    if (t.dataset.tab === 'analysis') loadAnalysis();
  })
);

// Live data
async function fetchLive() {
  try {
    const r = await fetch('/api/live');
    const d = await r.json();
    updateCards(d);
    setPill(true);
  } catch { setPill(false); }
}

function setPill(on) {
  const pill = document.getElementById('statusPill');
  const txt  = document.getElementById('statusText');
  pill.className = 'status-pill' + (on ? '' : ' off');
  txt.textContent = on ? 'Sensor Online' : 'Sensor Offline';
}

function updateCards(d) {
  const at = +((+d.temp1 + +d.temp2) / 2).toFixed(1);
  const ah = +((+d.hum1  + +d.hum2)  / 2).toFixed(1);
  const w  = +(+d.weight).toFixed(2);

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
    hs.textContent = 'Target reached (<=30% RH)';
    hs.className = 'hum-status hum-ok';
  } else if (ah <= 50) {
    hs.textContent = `${(ah - 30).toFixed(0)}% above target - drying...`;
    hs.className = 'hum-status hum-warn';
  } else {
    hs.textContent = `${ah}% - high humidity`;
    hs.className = 'hum-status hum-high';
  }

  // Weight
  set('weightVal', w);
  document.getElementById('gaugeFill').style.width = Math.min(w / 6 * 100, 100) + '%';
  const ws = document.getElementById('weightStatus');
  if (w <= 2.0) {
    ws.textContent = 'Target weight reached (<=2 kg)';
    ws.style.color = 'var(--green)';
  } else {
    ws.textContent = `Current load: ${w} kg`;
    ws.style.color = 'var(--muted)';
  }

  // Drying conditions card
  const humMet    = ah <= 30;
  const weightMet = w  <= 2.0;

  setCondition('condHum',    'ccheck-hum',    'cval-hum',    humMet,    `${ah}% RH`, '<=30% RH');
  setCondition('condWeight', 'ccheck-weight', 'cval-weight', weightMet, `${w} kg`,   '<=2.0 kg');

  const res = document.getElementById('condResult');
  const txt = document.getElementById('condResultText');
  if (humMet && weightMet) {
    res.className = 'cond-result dried';
    txt.textContent = 'Food waste is dried - auto-logging!';
  } else {
    res.className = 'cond-result';
    const needs = [];
    if (!humMet)    needs.push('humidity');
    if (!weightMet) needs.push('weight');
    txt.textContent = `Waiting for ${needs.join(' & ')} to reach target`;
  }

  // Drying banner
  document.getElementById('dryingBanner').style.display =
    d.drying_in_progress ? 'block' : 'none';

  document.getElementById('lastUpd').textContent = fmtTime(d.last_updated);
}

function setCondition(rowId, checkId, valId, met, current, target) {
  const row = document.getElementById(rowId);
  const chk = document.getElementById(checkId);
  const val = document.getElementById(valId);
  row.className = 'cond-row' + (met ? ' met' : '');
  chk.textContent = met ? 'OK' : 'o';
  val.textContent = met ? `${current} OK` : `${current} (target: ${target})`;
}

function set(id, val) {
  document.getElementById(id).textContent = val;
}

// History charts
async function loadHistory(days) {
  const res  = await fetch(`/api/history?days=${days}`);
  const data = await res.json();
  renderEnv(data);
  renderWeight(data);
}

function renderEnv(data) {
  const labels = data.map(d => fmtShort(d.timestamp));
  const ctx = document.getElementById('envChart').getContext('2d');
  if (charts.env) charts.env.destroy();
  charts.env = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Avg Temp (C)',
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
              title: { display: true, text: 'Temp C', font: { size: 11 } },
              grid: { color: '#F0EDE5' } },
        yH: { type: 'linear', position: 'right', min: 0, max: 100,
              title: { display: true, text: 'Humidity %', font: { size: 11 } },
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

// Records
async function loadRecords() {
  const days = document.getElementById('recDays').value;
  const [rRes, aRes] = await Promise.all([
    fetch(`/api/records?days=${days}`),
    fetch(`/api/analysis?days=${days}`)
  ]);
  const recs = await rRes.json();
  const ana  = await aRes.json();
  renderTable(recs);
  if (!ana.error) {
    set('s-batches', ana.total_batches);
    set('s-reduced', ana.total_weight_reduced_kg + ' kg');
    set('s-avgDur',  (ana.avg_duration_minutes / 60).toFixed(1) + ' h');
    set('s-avgPct',  ana.avg_reduction_pct + '%');
  }
}

function renderTable(recs) {
  const tbody = document.getElementById('recBody');
  if (!recs.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-cell">No records in this range.</td></tr>`;
    return;
  }
  tbody.innerHTML = recs.map((r, i) => {
    const pct = (r.weight_reduced / r.initial_weight * 100).toFixed(1);
    const cls = +pct >= 40 ? 'b-green' : 'b-amber';
    return `<tr>
      <td><strong>${recs.length - i}</strong></td>
      <td>${fmtDate(r.end_time)}</td>
      <td>${r.initial_weight} kg</td>
      <td>${r.final_weight} kg</td>
      <td><span class="badge ${cls}">-${r.weight_reduced} kg (${pct}%)</span></td>
      <td>${(r.duration_minutes / 60).toFixed(1)} h</td>
      <td>${r.avg_humidity}%</td>
      <td>${r.avg_temperature}C</td>
      <td style="color:var(--muted);font-size:.78rem">${r.notes || '-'}</td>
    </tr>`;
  }).join('');
}

document.getElementById('recDays').addEventListener('change', loadRecords);

// Analysis
async function loadAnalysis() {
  const days = document.getElementById('anaDays').value;
  const res  = await fetch(`/api/analysis?days=${days}`);
  const data = await res.json();
  if (data.error) return;
  renderAnalysis(data);
}

function renderAnalysis(d) {
  const descs = {
    'Excellent':         'Outstanding! The system is reducing food waste by more than half per batch.',
    'Good':              'Solid performance. Most batches are reaching the dryness target effectively.',
    'Fair':              'Moderate efficiency. Try optimizing solar exposure or reducing batch size.',
    'Needs Improvement': 'Below target. Check sensor calibration, panel angle, and sealing.'
  };
  set('effScore', d.efficiency_rating);
  set('effDesc',  descs[d.efficiency_rating] || '');
  set('e-batches', d.total_batches);
  set('e-reduced', d.total_weight_reduced_kg + ' kg');
  set('e-pct',     d.avg_reduction_pct + '%');
  set('e-dur',     (d.avg_duration_minutes / 60).toFixed(1) + ' h');

  const dl = Object.keys(d.daily_totals).sort();
  makeBar('dailyChart',  'daily',  dl, dl.map(k => +d.daily_totals[k].toFixed(2)),  'Daily kg',  C.sun, C.sunA);

  const wl = Object.keys(d.weekly_totals).sort();
  makeBar('weeklyChart', 'weekly', wl, wl.map(k => +d.weekly_totals[k].toFixed(2)), 'Weekly kg', C.grn, C.grnA);

  makeBatch(d.records.slice().reverse());
  renderInsights(d);
}

function makeBar(canvasId, key, labels, vals, label, color, bg) {
  const ctx = document.getElementById(canvasId).getContext('2d');
  if (charts[key]) charts[key].destroy();
  charts[key] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label, data: vals,
        backgroundColor: bg, borderColor: color,
        borderWidth: 2, borderRadius: 6
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11 } } },
        y: { beginAtZero: true, grid: { color: '#F0EDE5' }, title: { display: true, text: 'kg', font: { size: 11 } } }
      }
    }
  });
}

function makeBatch(recs) {
  const ctx = document.getElementById('batchChart').getContext('2d');
  if (charts.batch) charts.batch.destroy();
  charts.batch = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: recs.map((_, i) => `Batch ${i + 1}`),
      datasets: [
        {
          label: 'Initial Weight',
          data: recs.map(r => r.initial_weight),
          backgroundColor: C.ertA, borderColor: C.ert,
          borderWidth: 1.5, borderRadius: 4
        },
        {
          label: 'Final Weight',
          data: recs.map(r => r.final_weight),
          backgroundColor: 'rgba(61,122,82,.45)', borderColor: C.grn,
          borderWidth: 1.5, borderRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'top', labels: { boxWidth: 12 } },
        tooltip: {
          callbacks: {
            afterBody(items) {
              const r = recs[items[0].dataIndex];
              const p = (r.weight_reduced / r.initial_weight * 100).toFixed(1);
              return [
                `Reduced: ${r.weight_reduced} kg (${p}%)`,
                `Duration: ${(r.duration_minutes / 60).toFixed(1)} h`
              ];
            }
          }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 10 } } },
        y: { beginAtZero: true, grid: { color: '#F0EDE5' }, title: { display: true, text: 'kg' } }
      }
    }
  });
}

function renderInsights(d) {
  const ins = [];
  const pct = d.avg_reduction_pct;
  const hrs = (d.avg_duration_minutes / 60).toFixed(1);
  const co2 = (d.total_weight_reduced_kg * 0.5).toFixed(1);
  const wpw = (d.total_batches / +document.getElementById('anaDays').value * 7).toFixed(1);

  if (pct >= 55)
    ins.push({ c: 'g', t: `Excellent average reduction of ${pct}% - the dehydrator is exceeding efficiency targets. Food waste is being cut by more than half per batch.` });
  else if (pct >= 40)
    ins.push({ c: '',  t: `Good average reduction of ${pct}%. The system is drying food waste effectively and consistently meeting targets.` });
  else
    ins.push({ c: '',  t: `Average reduction of ${pct}% is below the 40% target. Consider longer drying sessions or smaller batch loads.` });

  if (d.avg_duration_minutes < 240)
    ins.push({ c: 'g', t: `Fast average drying time of ${hrs} hours - excellent solar exposure and conditions.` });
  else if (d.avg_duration_minutes < 480)
    ins.push({ c: 'b', t: `Average drying time is ${hrs} hours, consistent with typical solar dehydrator performance.` });
  else
    ins.push({ c: '',  t: `Average drying time of ${hrs} hours is longer than ideal. Check lid sealing and panel orientation.` });

  ins.push({ c: 'b', t: `Processing approximately ${wpw} batches per week, totaling ${d.total_weight_reduced_kg} kg of food waste reduced over this period.` });
  ins.push({ c: 'g', t: `Estimated ${co2} kg of CO2-equivalent emissions avoided through landfill methane reduction. Sol-ider is making a real environmental impact!` });

  document.getElementById('insightsBody').innerHTML =
    ins.map(i => `<div class="insight ${i.c}">${i.t}</div>`).join('');
}

document.getElementById('anaDays').addEventListener('change', loadAnalysis);

// Range buttons
document.querySelectorAll('.rbtn').forEach(b =>
  b.addEventListener('click', () => {
    document.querySelectorAll('.rbtn').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    histDays = +b.dataset.days;
    loadHistory(histDays);
  })
);

// Modal
document.getElementById('openModal').addEventListener('click', () => {
  const now = new Date();
  const s   = new Date(now - 4 * 3600000);
  document.getElementById('f-start').value = dtLocal(s);
  document.getElementById('f-end').value   = dtLocal(now);
  document.getElementById('modalBg').style.display = 'flex';
});

['closeModal', 'cancelModal'].forEach(id =>
  document.getElementById(id).addEventListener('click', () =>
    document.getElementById('modalBg').style.display = 'none')
);

document.getElementById('saveModal').addEventListener('click', async () => {
  const st = document.getElementById('f-start').value.replace('T', ' ') + ':00';
  const et = document.getElementById('f-end').value.replace('T', ' ')   + ':00';
  const iw = parseFloat(document.getElementById('f-iw').value);
  const fw = parseFloat(document.getElementById('f-fw').value);
  if (!iw || !fw || !st || !et) {
    alert('Please fill in all required fields.');
    return;
  }
  await fetch('/api/records/add', {
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
  });
  document.getElementById('modalBg').style.display = 'none';
  loadRecords();
});

// Helpers
function fmtTime(ts) {
  if (!ts) return '-';
  return new Date(ts).toLocaleString('en-PH', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

function fmtShort(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()} ` +
         `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function fmtDate(ts) {
  if (!ts) return '-';
  return new Date(ts).toLocaleString('en-PH', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

function dtLocal(d) {
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}` +
         `T${p(d.getHours())}:${p(d.getMinutes())}`;
}

// Init
(async () => {
  await fetchLive();
  await loadHistory(histDays);
  setInterval(fetchLive, 8000);
  setInterval(() => loadHistory(histDays), 60000);
})();