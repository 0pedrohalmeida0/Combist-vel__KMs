// corrections.js — fatores de correção aplicados ao consumo base
// Portado de app/fuel/corrections.py.

import { DEFAULT_STOPS_PER_KM } from './physics.js';

// ---------- Atmosfera / ambiente ----------

/** +4% a cada 1000 m acima de 1500 m, cap em +25%. */
export function altitudeFactor(altitudeM) {
  if (altitudeM <= 1500.0) return 1.0;
  const excessKm = (altitudeM - 1500.0) / 1000.0;
  return Math.min(1.0 + 0.04 * excessKm, 1.25);
}

/** Penalidade por motor frio + tempo parado em frio. */
export function temperatureFactor(tempC, idleTimeMin, distanceKm) {
  let base = 1.0 + Math.max(0.0, (20.0 - tempC) / 20.0) * Math.exp(-distanceKm / 5.0);
  if (idleTimeMin > 0 && tempC < 10.0) {
    const idlePenalty = Math.min(0.15, idleTimeMin * 0.01);
    base += idlePenalty;
  }
  return base;
}

/** Umidade UR%: 0% → 1.01, 100% → 0.99 (variação desprezível). */
export function humidityFactor(humidityPct) {
  return 1.0 + (60.0 - humidityPct) * 0.0002;
}

const ROAD_FACTORS = { dry: 1.00, wet: 1.05, snow: 1.20, ice: 1.35 };
export function roadConditionFactor(cond) {
  return ROAD_FACTORS[(cond || '').toLowerCase()] ?? 1.0;
}

const ROLLING_ROAD_FACTORS = { dry: 1.00, wet: 1.10, snow: 1.30, ice: 1.60 };
export function rollingResistanceRoadFactor(cond) {
  return ROLLING_ROAD_FACTORS[(cond || '').toLowerCase()] ?? 1.0;
}

// ---------- Vento ----------

/** Componente de vento contrário (km/h, positivo = contra o veículo). */
export function effectiveHeadwindKmh(windSpeedKmh, windDirectionDeg, vehicleHeadingDeg = 0.0) {
  const diff = (windDirectionDeg - vehicleHeadingDeg) * Math.PI / 180.0;
  return windSpeedKmh * Math.cos(diff);
}

// ---------- Carga e AC ----------

/** AC: retorna (fator_multiplicativo, aux_power_adicional_W). */
export function acFactor(useAc, temperatureC, distanceKm, speedKmh) {
  if (!useAc) return { factor: 1.0, auxW: 0.0 };

  let auxW, factor;
  if (temperatureC >= 22.0) {
    auxW = 1500.0 + (temperatureC - 22.0) * 150.0;
    factor = 1.0 + Math.min(0.15, 0.01 * (temperatureC - 22.0));
  } else if (temperatureC <= 10.0) {
    if (temperatureC < 0.0) {
      auxW = 200.0;
      factor = 1.01;
    } else {
      auxW = 1000.0 + (10.0 - temperatureC) * 100.0;
      factor = 1.0 + 0.005 * (10.0 - temperatureC);
    }
  } else {
    auxW = 800.0;
    factor = 1.02;
  }

  if (speedKmh < 20.0) auxW *= 1.05;
  return { factor, auxW };
}

/** Fator multiplicativo de carga (efeitos secundários; primário via massa). */
export function loadFactor(vehicleMassKg, payloadKg, towingKg) {
  const extra = payloadKg + towingKg;
  if (extra <= 200.0) return 1.0;
  return 1.0 + Math.min(0.05, 0.005 * (extra - 200.0) / 100.0);
}

/** Incremento de área frontal ao rebocar. */
export function towingAeroIncrement(towingKg, vehicleType) {
  if (towingKg <= 0) return 0.0;
  const base = vehicleType === 'car' ? 1.0 : 0.3;
  const factor = Math.min(1.0, towingKg / 3000.0);
  return base * factor * 0.5;
}

// ---------- Estilo e manutenção ----------

const STYLE_FACTORS = { eco: 0.92, normal: 1.00, aggressive: 1.18 };
export function drivingStyleFactor(style) {
  return STYLE_FACTORS[(style || '').toLowerCase()] ?? 1.0;
}

/** Pneu murcho aumenta resistência. */
export function tirePressureFactor(actualKpa, nominalKpa = 220.0) {
  if (actualKpa >= nominalKpa) return 1.0;
  return 1.0 + 0.002 * (nominalKpa - actualKpa);
}

const FUEL_QUALITY_FACTORS = { regular: 1.0, premium: 0.97 };
export function fuelQualityFactor(quality) {
  return FUEL_QUALITY_FACTORS[(quality || '').toLowerCase()] ?? 1.0;
}

/** Veículos mais antigos menos eficientes (cap em +20%). */
export function vehicleAgeFactor(year, refYear = 2026) {
  if (year >= refYear) return 1.0;
  return Math.min(1.20, 1.0 + 0.005 * (refYear - year));
}

const TRANSMISSION_FACTORS = { manual: 1.00, automatic: 1.05, cvt: 1.03 };
export function transmissionFactor(transmission) {
  return TRANSMISSION_FACTORS[(transmission || '').toLowerCase()] ?? 1.0;
}

/** Retorna { volumeFactor, co2Factor } para o combustível. */
export function ethanolBlendFactor(fuelType, fuelQuality) {
  const ft = (fuelType || '').toLowerCase();
  const fq = (fuelQuality || '').toLowerCase();
  if (ft === 'ethanol') return { volumeFactor: 1.30, co2Factor: 0.65 };
  if (ft === 'flex') {
    if (fq === 'premium') return { volumeFactor: 1.30, co2Factor: 0.65 };
    return { volumeFactor: 1.00, co2Factor: 1.00 };
  }
  if (ft === 'diesel') {
    return fq === 'premium'
      ? { volumeFactor: 0.99, co2Factor: 1.00 }
      : { volumeFactor: 1.00, co2Factor: 1.00 };
  }
  return fq === 'premium'
    ? { volumeFactor: 0.97, co2Factor: 1.00 }
    : { volumeFactor: 1.00, co2Factor: 1.00 };
}

/** Resolve paradas por km (explícito > default do perfil). */
export function resolveStopsPerKm(speedProfile, explicit) {
  if (explicit && explicit > 0) return Number(explicit);
  return DEFAULT_STOPS_PER_KM[(speedProfile || '').toLowerCase()] ?? 0.0;
}
