/* =========================================================================
   Fuel Consumption API — Front-end logic
   ========================================================================= */

(() => {
  'use strict';

  // -----------------------------------------------------------------------
  // Config
  // -----------------------------------------------------------------------
  const LS_KEY = 'fuel_api_base';
  // DEFAULT_API pode ser:
  //   '' (vazio)       — usa URL relativa; requer o proxy /api/* no Netlify
  //   URL absoluta     — aponta direto pro back-end (sem proxy)
  // Se você descomentou o bloco [[redirects]] em netlify.toml, deixa ''.
  const DEFAULT_API = 'https://seuusuario.pythonanywhere.com';

  // -----------------------------------------------------------------------
  // DOM helpers
  // -----------------------------------------------------------------------
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const apiBaseInput = $('#api-base');
  const apiStatus = $('#api-status');
  const form = $('#calc-form');
  const submitBtn = $('#submit-btn');
  const resetBtn = $('#reset-btn');
  const vehicleTypeSel = $('#vehicle-type');
  const vehiclePresetSel = $('#vehicle-preset');
  const elevContainer = $('#elev-points');
  const addElevBtn = $('#add-elev');
  const clearElevBtn = $('#clear-elev');

  const resultEmpty = $('#result-empty');
  const resultContent = $('#result-content');
  const resultError = $('#result-error');

  let factorsChart = null;
  let elevCounter = 0;

  // -----------------------------------------------------------------------
  // Init
  // -----------------------------------------------------------------------
  function init() {
    const saved = localStorage.getItem(LS_KEY) || DEFAULT_API;
    apiBaseInput.value = saved;
    apiBaseInput.addEventListener('change', () => {
      localStorage.setItem(LS_KEY, apiBaseInput.value.trim());
      checkApiHealth();
    });

    // Sensible defaults for the first paint
    if (!form.elements['trip.average_speed_kmh'].value) {
      form.elements['trip.average_speed_kmh'].value = 80;
    }
    if (!form.elements['environment.temperature_c'].value) {
      form.elements['environment.temperature_c'].value = 20;
    }
    if (!form.elements['environment.altitude_m'].value) {
      form.elements['environment.altitude_m'].value = 0;
    }
    if (!form.elements['environment.humidity_pct'].value) {
      form.elements['environment.humidity_pct'].value = 60;
    }
    if (!form.elements['environment.wind_speed_kmh'].value) {
      form.elements['environment.wind_speed_kmh'].value = 0;
    }
    if (!form.elements['environment.wind_direction_deg'].value) {
      form.elements['environment.wind_direction_deg'].value = 0;
    }
    if (!form.elements['load.passenger_count'].value) {
      form.elements['load.passenger_count'].value = 1;
    }
    if (!form.elements['load.passenger_avg_weight_kg'].value) {
      form.elements['load.passenger_avg_weight_kg'].value = 75;
    }
    if (!form.elements['load.cargo_weight_kg'].value) {
      form.elements['load.cargo_weight_kg'].value = 0;
    }
    if (!form.elements['load.towing_kg'].value) {
      form.elements['load.towing_kg'].value = 0;
    }
    if (!form.elements['trip.idle_time_min'].value) {
      form.elements['trip.idle_time_min'].value = 0;
    }

    form.addEventListener('submit', onSubmit);
    resetBtn.addEventListener('click', onReset);
    addElevBtn.addEventListener('click', () => addElevPoint());
    clearElevBtn.addEventListener('click', () => {
      elevContainer.innerHTML = '';
    });

    // Try to load presets on startup
    loadPresets();
    checkApiHealth();
  }

  // -----------------------------------------------------------------------
  // API health & presets
  // -----------------------------------------------------------------------
  async function checkApiHealth() {
    setApiStatus('checking');
    const base = apiBaseInput.value.trim().replace(/\/+$/, '');
    if (!base) {
      setApiStatus('unknown');
      return;
    }
    try {
      const res = await fetch(`${base}/health`, { method: 'GET' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data && data.status === 'ok') {
        setApiStatus('ok');
      } else {
        setApiStatus('error');
      }
    } catch (e) {
      setApiStatus('error');
    }
  }

  function setApiStatus(state) {
    apiStatus.dataset.state = state;
    const tip = {
      unknown: 'API não verificada',
      checking: 'Verificando…',
      ok: 'API online',
      error: 'API indisponível',
    }[state] || state;
    apiStatus.title = tip;
  }

  async function loadPresets() {
    const base = apiBaseInput.value.trim().replace(/\/+$/, '');
    if (!base) return;
    try {
      const res = await fetch(`${base}/api/v1/fuel/presets`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const presets = await res.json();
      populatePresets(presets);
    } catch (e) {
      // silently fail — user can still enter custom specs
      console.warn('Não foi possível carregar presets:', e);
    }
  }

  function populatePresets(presets) {
    // Save current selection
    const current = vehiclePresetSel.value;

    // Reset, keep the "custom" placeholder
    vehiclePresetSel.innerHTML = '<option value="">— veículo custom —</option>';

    for (const p of presets || []) {
      const opt = document.createElement('option');
      opt.value = p.preset_id;
      const friendlyType = p.type === 'motorcycle' ? 'Moto' : 'Carro';
      const name = p.label || p.preset_id;
      const fuel = p.fuel_type || '';
      opt.textContent = `${friendlyType} · ${name}${fuel ? ' (' + fuel + ')' : ''}`;
      vehiclePresetSel.appendChild(opt);
    }

    if (current) vehiclePresetSel.value = current;

    // Default to the first car preset for convenience
    if (!current) {
      const firstCar = (presets || []).find(p => p.preset_id === 'car-compact-popular');
      if (firstCar) vehiclePresetSel.value = 'car-compact-popular';
    }
  }

  // -----------------------------------------------------------------------
  // Elevation editor
  // -----------------------------------------------------------------------
  function addElevPoint(distance = '', elevation = '') {
    const idx = elevCounter++;
    const row = document.createElement('div');
    row.className = 'elev-row';
    row.dataset.idx = idx;
    row.innerHTML = `
      <input type="number" step="0.1" min="0" placeholder="km"
             data-elev-d="${idx}" value="${distance}" />
      <input type="number" step="1" placeholder="m"
             data-elev-e="${idx}" value="${elevation}" />
      <button type="button" data-elev-rm="${idx}" title="Remover">×</button>
    `;
    row.querySelector(`[data-elev-rm="${idx}"]`).addEventListener('click', () => {
      row.remove();
    });
    elevContainer.appendChild(row);
  }

  function readElevationProfile() {
    const rows = $$('.elev-row');
    if (rows.length === 0) return null;
    const points = [];
    for (const r of rows) {
      const d = parseFloat(r.querySelector('[data-elev-d]').value);
      const e = parseFloat(r.querySelector('[data-elev-e]').value);
      if (Number.isFinite(d) && Number.isFinite(e)) {
        points.push({ distance_km: d, elevation_m: e });
      }
    }
    if (points.length < 2) return null;
    // Must be strictly ascending
    for (let i = 1; i < points.length; i++) {
      if (points[i].distance_km <= points[i - 1].distance_km) {
        throw new Error('Pontos de elevação devem estar em ordem crescente de distância.');
      }
    }
    return points;
  }

  // -----------------------------------------------------------------------
  // Form parsing
  // -----------------------------------------------------------------------
  function parseForm() {
    const fd = new FormData(form);
    const obj = {};
    for (const [name, value] of fd.entries()) {
      setDeep(obj, name, parseValue(value));
    }
    // Checkboxes: FormData omits unchecked — we add `false` if absent
    if (!('driver.use_ac' in obj)) {
      setDeep(obj, 'driver.use_ac', false);
    }
    return obj;
  }

  function setDeep(obj, dotted, value) {
    const parts = dotted.split('.');
    let cur = obj;
    for (let i = 0; i < parts.length - 1; i++) {
      const p = parts[i];
      if (!(p in cur)) cur[p] = {};
      cur = cur[p];
    }
    cur[parts[parts.length - 1]] = value;
  }

  function parseValue(v) {
    if (v === '' || v === null || v === undefined) return null;
    if (v === 'on') return true;
    // numeric?
    if (/^-?\d+(\.\d+)?$/.test(v)) return Number(v);
    return v;
  }

  function cleanNulls(o) {
    if (Array.isArray(o)) {
      return o.map(cleanNulls).filter((v) => v !== null && v !== undefined);
    }
    if (o && typeof o === 'object') {
      const out = {};
      for (const [k, v] of Object.entries(o)) {
        const cleaned = cleanNulls(v);
        if (cleaned !== null && cleaned !== undefined && cleaned !== '') {
          out[k] = cleaned;
        }
      }
      return out;
    }
    return o;
  }

  // -----------------------------------------------------------------------
  // Submit
  // -----------------------------------------------------------------------
  async function onSubmit(e) {
    e.preventDefault();
    submitBtn.disabled = true;
    submitBtn.dataset.loading = 'true';
    resultError.classList.add('hidden');
    resultContent.classList.add('hidden');
    resultEmpty.classList.add('hidden');

    let payload;
    try {
      const parsed = parseForm();
      const elev = readElevationProfile();
      if (elev) parsed.trip.elevation_profile = elev;
      payload = cleanNulls(parsed);
    } catch (e) {
      showError(`Formulário inválido: ${e.message}`);
      submitBtn.disabled = false;
      submitBtn.dataset.loading = 'false';
      return;
    }

    // Validation: at least distance
    if (!payload.trip || !payload.trip.distance_km) {
      showError('Informe a distância da viagem (campo obrigatório).');
      submitBtn.disabled = false;
      submitBtn.dataset.loading = 'false';
      return;
    }
    if (!payload.vehicle || !payload.vehicle.type) {
      showError('Informe o tipo de veículo (carro ou moto).');
      submitBtn.disabled = false;
      submitBtn.dataset.loading = 'false';
      return;
    }

    const base = apiBaseInput.value.trim().replace(/\/+$/, '');
    try {
      const res = await fetch(`${base}/api/v1/fuel/calculate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const text = await res.text();
      if (!res.ok) {
        let detail = text;
        try {
          const j = JSON.parse(text);
          detail = j.error ? JSON.stringify(j.error, null, 2) : (j.detail || text);
        } catch (_) { /* keep raw text */ }
        throw new Error(`HTTP ${res.status}\n${detail}`);
      }
      const data = JSON.parse(text);
      renderResult(data);
    } catch (e) {
      showError(e.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.dataset.loading = 'false';
    }
  }

  function onReset() {
    form.reset();
    // Restore defaults
    form.elements['trip.average_speed_kmh'].value = 80;
    form.elements['environment.temperature_c'].value = 20;
    form.elements['environment.altitude_m'].value = 0;
    form.elements['environment.humidity_pct'].value = 60;
    form.elements['environment.wind_speed_kmh'].value = 0;
    form.elements['environment.wind_direction_deg'].value = '0';
    form.elements['load.passenger_count'].value = 1;
    form.elements['load.passenger_avg_weight_kg'].value = 75;
    form.elements['load.cargo_weight_kg'].value = 0;
    form.elements['load.towing_kg'].value = 0;
    form.elements['trip.idle_time_min'].value = 0;
    form.elements['trip.speed_profile'].value = 'mixed';
    form.elements['driver.driving_style'].value = 'normal';
    form.elements['driver.fuel_quality'].value = 'regular';
    form.elements['environment.road_condition'].value = 'dry';
    elevContainer.innerHTML = '';
    resultContent.classList.add('hidden');
    resultError.classList.add('hidden');
    resultEmpty.classList.remove('hidden');
  }

  function showError(msg) {
    resultContent.classList.add('hidden');
    resultEmpty.classList.add('hidden');
    resultError.classList.remove('hidden');
    $('#error-detail').textContent = msg;
  }

  // -----------------------------------------------------------------------
  // Result rendering
  // -----------------------------------------------------------------------
  function renderResult(data) {
    resultError.classList.add('hidden');
    resultEmpty.classList.add('hidden');
    resultContent.classList.remove('hidden');

    $('#vehicle-label').textContent = data.vehicle_label || '—';
    const fuelBadge = $('#fuel-type-badge');
    fuelBadge.textContent = (data.fuel_type || '').toUpperCase();

    $('#m-fuel').textContent = `${fmt(data.total_fuel_l, 2)} L`;
    $('#m-fuel-cost').textContent = data.fuel_cost_brl != null
      ? `≈ R$ ${fmt(data.fuel_cost_brl, 2)}`
      : 'sem preço configurado';

    $('#m-km-l').textContent = data.km_per_l > 0
      ? `${fmt(data.km_per_l, 2)} km/L`
      : '∞';
    $('#m-l-100km').textContent = `${fmt(data.fuel_per_km_l_per_100km, 2)} L/100 km`;

    $('#m-duration').textContent = `${fmt(data.trip_duration_h, 2)} h`;
    $('#m-distance').textContent = `${fmt(data.distance_km, 1)} km · ${fmt(data.average_speed_kmh, 0)} km/h`;

    $('#m-energy').textContent = `${fmt(data.energy_mj, 1)} MJ`;
    $('#m-co2').textContent = `${fmt(data.co2_kg, 2)} kg CO₂`;

    $('#m-mass').textContent = `${fmt(data.total_mass_kg, 0)} kg`;
    $('#m-air').textContent = `${fmt(data.air_density_kg_per_m3, 3)} kg/m³`;
    $('#m-headwind').textContent = `${fmt(data.effective_headwind_kmh, 1)} km/h`;
    $('#m-aux').textContent = `${fmt(data.aux_power_effective_w, 0)} W`;

    renderFactors(data.factors || []);
    renderWarnings(data.warnings || []);
    renderSegments(data.segments || []);
  }

  // -----------------------------------------------------------------------
  // Factors chart
  // -----------------------------------------------------------------------
  function renderFactors(factors) {
    const canvas = $('#factors-chart');
    if (!canvas || !window.Chart) return;

    // Group positive/negative around 1.0 visually; sort by impact
    const items = factors
      .filter(f => f.name !== 'ethanol_blend_co2') // only one of the ethanol factors for clarity
      .map(f => ({ name: prettyName(f.name), factor: f.factor }));

    items.sort((a, b) => Math.abs(Math.log(b.factor)) - Math.abs(Math.log(a.factor)));

    const labels = items.map(i => i.name);
    const values = items.map(i => i.factor);
    const colors = values.map(v =>
      v > 1.01 ? 'rgba(248, 81, 73, 0.78)' :
      v < 0.99 ? 'rgba(63, 185, 80, 0.78)' :
                 'rgba(139, 149, 164, 0.6)'
    );

    if (factorsChart) factorsChart.destroy();
    factorsChart = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Fator multiplicativo',
          data: values,
          backgroundColor: colors,
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: 'y',
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const v = ctx.parsed.x;
                const delta = (v - 1) * 100;
                const sign = delta >= 0 ? '+' : '';
                return `× ${v.toFixed(3)}  (${sign}${delta.toFixed(1)}%)`;
              },
            },
          },
        },
        scales: {
          x: {
            beginAtZero: false,
            grid: { color: 'rgba(139, 149, 164, 0.15)' },
            ticks: {
              color: 'rgba(139, 149, 164, 0.9)',
              callback: (v) => `×${v.toFixed(2)}`,
            },
          },
          y: {
            grid: { display: false },
            ticks: { color: 'rgba(230, 237, 243, 0.9)' },
          },
        },
      },
    });
  }

  function prettyName(name) {
    const map = {
      altitude: 'Altitude',
      temperature: 'Temperatura',
      humidity: 'Umidade',
      road_condition: 'Piso',
      driving_style: 'Estilo de direção',
      fuel_quality: 'Qualidade comb.',
      vehicle_age: 'Idade do veículo',
      transmission: 'Câmbio',
      tire_pressure: 'Pressão pneus',
      load: 'Carga',
      ac: 'Ar-condicionado',
      ethanol_blend_volume: 'Blend etanol (vol.)',
      ethanol_blend_co2: 'Blend etanol (CO₂)',
    };
    return map[name] || name;
  }

  function renderWarnings(warnings) {
    const block = $('#warnings-block');
    const list = $('#warnings-list');
    list.innerHTML = '';
    if (warnings.length === 0) {
      block.classList.add('hidden');
      return;
    }
    block.classList.remove('hidden');
    for (const w of warnings) {
      const li = document.createElement('li');
      li.textContent = w;
      list.appendChild(li);
    }
  }

  function renderSegments(segments) {
    const tbody = $('#segments-table tbody');
    tbody.innerHTML = '';
    // Show only the first 50 to keep DOM light
    const show = segments.slice(0, 50);
    for (const s of show) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${s.index}</td>
        <td>${fmt(s.start_km, 3)}</td>
        <td>${fmt(s.end_km, 3)}</td>
        <td>${fmt(s.grade_pct, 2)}%</td>
        <td>${fmt(s.speed_kmh, 1)}</td>
        <td>${fmt(s.tractive_power_w, 0)}</td>
        <td>${fmt(s.fuel_l, 5)}</td>
      `;
      tbody.appendChild(tr);
    }
    if (segments.length > 50) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td colspan="7" style="text-align:center; color: var(--text-muted);">… +${segments.length - 50} segmentos</td>`;
      tbody.appendChild(tr);
    }
  }

  // -----------------------------------------------------------------------
  // Format
  // -----------------------------------------------------------------------
  function fmt(n, decimals = 2) {
    if (n === null || n === undefined || Number.isNaN(n)) return '—';
    if (typeof n !== 'number') return String(n);
    return n.toLocaleString('pt-BR', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  // -----------------------------------------------------------------------
  // Boot
  // -----------------------------------------------------------------------
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
