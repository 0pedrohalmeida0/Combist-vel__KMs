/* =========================================================================
   Fuel Consumption — Front-end logic
   100% client-side: usa o engine em JS puro (frontend/engine/) — sem
   API externa, sem CORS, sem servidor Python.
   ========================================================================= */

(() => {
  'use strict';

  // -----------------------------------------------------------------------
  // DOM helpers
  // -----------------------------------------------------------------------
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const form = $('#calc-form');
  const submitBtn = $('#submit-btn');
  const resetBtn = $('#reset-btn');
  const vehicleTypeSel = $('#vehicle-type');
  const vehiclePresetSel = $('#vehicle-preset');
  const elevContainer = $('#elev-points');
  const addElevBtn = $('#add-elev');
  const clearElevBtn = $('#clear-elev');
  const distanceInput = form.querySelector('[name="trip.distance_km"]');

  const resultEmpty = $('#result-empty');
  const resultContent = $('#result-content');
  const resultError = $('#result-error');

  let factorsChart = null;
  let elevCounter = 0;

  // localStorage key para o cache do form (principalmente a distância).
  const FORM_CACHE_KEY = 'fuel:form-cache:v1';

  // Engine é carregado dinamicamente (ES module) — resolvido em
  // `engineReady` antes do usuário poder submeter.
  let engineReady = null;  // Promise<{ calculate, listPresets, getPreset }>

  // -----------------------------------------------------------------------
  // Init
  // -----------------------------------------------------------------------
  async function init() {
    // Sensible defaults
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

    // Engine + presets em paralelo
    try {
      engineReady = loadEngine();
      const { listPresets } = await engineReady;
      const presets = listPresets();
      populatePresets(presets);
      // Sem status indicator: o engine tá sempre disponível localmente
    } catch (err) {
      showError(`Erro ao carregar o motor de cálculo: ${err.message}`);
    }

    // Restaura valores do cache local (de uma sessão anterior ou de antes
    // de algum reset do DOM). Não sobrescreve o que o usuário já digitou
    // nesta sessão.
    restoreFormCache();

    // Salva o cache a cada input/change. Usando 'input' cobre text/number,
    // 'change' cobre select/checkbox (a maioria dos browsers não dispara
    // 'input' em selects).
    form.addEventListener('input', saveFormCache);
    form.addEventListener('change', saveFormCache);
  }

  async function loadEngine() {
    const mod = await import('./engine/index.js');
    return mod;
  }

  // -----------------------------------------------------------------------
  // Presets
  // -----------------------------------------------------------------------
  function populatePresets(presets) {
    const current = vehiclePresetSel.value;
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
    if (!('driver.use_ac' in obj)) {
      setDeep(obj, 'driver.use_ac', false);
    }
    return obj;
  }

  // -----------------------------------------------------------------------
  // Cache do form (localStorage). Salvamos em dois momentos:
  //   1) em cada 'input'/'change' do form  →  permite restauração se algo
  //      resetar o DOM depois (bug raro mas que aconteceu);
  //   2) em cada submit bem-sucedido       →  marca o último cálculo válido.
  // Ao iniciar, restauramos tudo. Se o campo distância estiver vazio mas
  // o cache tiver valor, usamos o cache como fallback e mostramos aviso.
  // -----------------------------------------------------------------------
  function saveFormCache() {
    try {
      const data = {};
      for (const el of form.elements) {
        if (!el.name || el.disabled) continue;
        if (el.type === 'checkbox') data[el.name] = el.checked;
        else data[el.name] = el.value;
      }
      localStorage.setItem(FORM_CACHE_KEY, JSON.stringify(data));
    } catch (e) { /* localStorage indisponível — tudo bem */ }
  }

  function loadFormCache() {
    try {
      const raw = localStorage.getItem(FORM_CACHE_KEY);
      if (!raw) return {};
      return JSON.parse(raw) || {};
    } catch (e) { return {}; }
  }

  function restoreFormCache() {
    const cache = loadFormCache();
    if (!cache) return;
    for (const [name, value] of Object.entries(cache)) {
      const el = form.elements[name];
      if (!el) continue;
      // Só restaura se o campo está vazio no HTML (não sobrescreve o que
      // o usuário já digitou na sessão atual).
      if (el.type === 'checkbox') {
        if (el.checked !== value) el.checked = value;
      } else {
        const current = el.value;
        if (current === '' || current == null) {
          el.value = value;
        }
      }
    }
  }

  // Distância: se o campo estiver vazio mas houver cache, usa o cache
  // e retorna um aviso. Retorna null se nem o cache tem valor.
  function recoverDistance() {
    if (distanceInput && distanceInput.value && parseFloat(distanceInput.value) > 0) {
      return null;
    }
    const cache = loadFormCache();
    const cached = cache['trip.distance_km'];
    if (cached && parseFloat(cached) > 0) {
      distanceInput.value = cached;
      return `Distância recuperada do cache local (${cached} km) — o campo havia sido limpo.`;
    }
    return null;
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

    if (!payload.trip || !payload.trip.distance_km) {
      // Tenta recuperar a distância do cache local antes de desistir.
      const recovered = recoverDistance();
      if (recovered) {
        // Re-parseia o form com o campo agora preenchido.
        const reparsed = cleanNulls(parseForm());
        if (reparsed.trip && reparsed.trip.distance_km) {
          payload = reparsed;
          // Mostra um aviso suave em vez de erro — o usuário vai ver que
          // pegamos do cache mas o cálculo segue.
          showSoftWarning(recovered);
        }
      }
    }
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

    try {
      const engine = await engineReady;
      const data = engine.calculate(payload);
      saveFormCache();  // marca o último estado válido do form
      renderResult(data);
    } catch (e) {
      // Erros de validação do engine têm .code/.statusCode
      const detail = e.code ? `[${e.code}] ${e.message}` : e.message;
      showError(detail);
    } finally {
      submitBtn.disabled = false;
      submitBtn.dataset.loading = 'false';
    }
  }

  function onReset() {
    form.reset();
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

  // Aviso não-fatal: mostra uma tarja dentro do result-content sem
  // bloquear a visualização do resultado. Usado quando a gente recupera
  // um valor do cache.
  function showSoftWarning(msg) {
    let banner = $('#result-warning-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'result-warning-banner';
      banner.className = 'soft-warning';
      const result = $('#result-content');
      result.insertBefore(banner, result.firstChild);
    }
    banner.textContent = `ℹ ${msg}`;
  }

  // -----------------------------------------------------------------------
  // Result rendering
  // -----------------------------------------------------------------------
  function renderResult(data) {
    resultError.classList.add('hidden');
    resultEmpty.classList.add('hidden');
    resultContent.classList.remove('hidden');

    // Limpa o banner de aviso da renderização anterior.
    const oldBanner = $('#result-warning-banner');
    if (oldBanner) oldBanner.remove();

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

    const items = factors
      .filter(f => f.name !== 'ethanol_blend_co2')
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
