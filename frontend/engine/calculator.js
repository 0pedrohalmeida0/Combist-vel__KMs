// calculator.js — orquestra física + correções e produz o resultado final
// Portado de app/fuel/service.py. API idêntica à do back-end.

import {
  airDensity, aeroDragForce, rollingResistanceForce, climbingForce,
  tractivePower, fuelFlowLPerS, fuelProperties, gradeFromElevation,
  resolveStopsPerKm, G,
} from './physics.js';

import {
  altitudeFactor, temperatureFactor, humidityFactor, roadConditionFactor,
  rollingResistanceRoadFactor, effectiveHeadwindKmh, acFactor, loadFactor,
  drivingStyleFactor, tirePressureFactor, fuelQualityFactor, vehicleAgeFactor,
  transmissionFactor, ethanolBlendFactor, towingAeroIncrement,
} from './corrections.js';

import { VEHICLE_PRESETS, getPreset } from './presets.js';

const DEFAULT_SEGMENT_LENGTH_M = 100.0;

// =====================================================================
// Defaults
// =====================================================================

const TRIP_DEFAULTS = {
  average_speed_kmh: 80,
  speed_profile: 'mixed',
  idle_time_min: 0,
  stops_per_km: 0,
  elevation_profile: null,
};

const ENVIRONMENT_DEFAULTS = {
  temperature_c: 20,
  altitude_m: 0,
  humidity_pct: 60,
  wind_speed_kmh: 0,
  wind_direction_deg: 0,
  road_condition: 'dry',
};

const LOAD_DEFAULTS = {
  passenger_count: 1,
  passenger_avg_weight_kg: 75,
  cargo_weight_kg: 0,
  towing_kg: 0,
};

const DRIVER_DEFAULTS = {
  driving_style: 'normal',
  use_ac: false,
  fuel_quality: 'regular',
  fuel_price_brl_per_l: null,
};

const VEHICLE_OVERRIDE_DEFAULTS = {
  type: null,        // obrigatório se não usar preset
  category: null,
  empty_weight_kg: null,
  engine_displacement_l: null,
  engine_power_kw: null,
  transmission: null,
  cylinders: null,
  drag_coefficient_cd: null,
  frontal_area_m2: null,
  rolling_resistance_coeff: null,
  tire_pressure_kpa: null,
  fuel_tank_capacity_l: null,
  fuel_type: null,
  drivetrain_efficiency: null,
  engine_thermal_efficiency: null,
  aux_power_w: null,
  idle_fuel_l_per_h: null,
  year: null,
};

function mergeDefaults(provided, defaults) {
  const out = { ...defaults };
  if (provided) {
    for (const [k, v] of Object.entries(provided)) {
      if (v !== null && v !== undefined && v !== '') out[k] = v;
    }
  }
  return out;
}

// =====================================================================
// Vehicle resolution
// =====================================================================

class CalcError extends Error {
  constructor(code, message, statusCode = 400) {
    super(message);
    this.code = code;
    this.statusCode = statusCode;
  }
}

function resolveVehicle(provided) {
  // Validação mínima
  if (!provided || !provided.type) {
    throw new CalcError('VALIDATION_ERROR', 'Campo "vehicle.type" é obrigatório', 422);
  }
  if (!['car', 'motorcycle'].includes(provided.type)) {
    throw new CalcError('VALIDATION_ERROR', `vehicle.type inválido: ${provided.type}`, 422);
  }

  const preset = provided.preset_id ? getPreset(provided.preset_id) : null;
  if (provided.preset_id && !preset) {
    throw new CalcError('NOT_FOUND', `preset não encontrado: ${provided.preset_id}`, 404);
  }

  let merged;
  if (!preset) {
    // Veículo totalmente custom — exige todos os campos obrigatórios
    merged = { ...provided };
  } else {
    // 1) parte do preset
    merged = { ...preset };
    // 2) sobrepõe com o que veio do cliente
    for (const [k, v] of Object.entries(provided)) {
      if (v !== null && v !== undefined && v !== '' && k !== 'preset_id') {
        merged[k] = v;
      }
    }
  }

  // Defaults para campos derivados
  if (merged.idle_fuel_l_per_h == null) {
    merged.idle_fuel_l_per_h = merged.type === 'motorcycle' ? 0.4 : 0.6;
  }

  // Validação de ranges (idêntica ao back-end)
  const rangeChecks = [
    ['empty_weight_kg', 0, null, '> 0'],
    ['engine_power_kw', 0, null, '> 0'],
    ['engine_displacement_l', 0, null, '> 0'],
    ['drag_coefficient_cd', 0.15, 0.6, '[0.15, 0.6]'],
    ['frontal_area_m2', 0.3, 4.0, '[0.3, 4]'],
    ['rolling_resistance_coeff', 0.005, 0.025, '[0.005, 0.025]'],
    ['tire_pressure_kpa', 120, 350, '[120, 350]'],
    ['fuel_tank_capacity_l', 0, null, '> 0'],
    ['year', 1950, 2030, '[1950, 2030]'],
  ];
  for (const [field, min, max, desc] of rangeChecks) {
    const v = merged[field];
    if (v == null) {
      throw new CalcError('VALIDATION_ERROR', `vehicle.${field} é obrigatório (${desc})`, 422);
    }
    if (v <= 0 && min > 0) {
      throw new CalcError('VALIDATION_ERROR', `vehicle.${field} deve ser > 0`, 422);
    }
    if (min !== null && v < min) {
      throw new CalcError('VALIDATION_ERROR', `vehicle.${field} = ${v} fora de ${desc}`, 422);
    }
    if (max !== null && v > max) {
      throw new CalcError('VALIDATION_ERROR', `vehicle.${field} = ${v} fora de ${desc}`, 422);
    }
  }
  if (!['manual', 'automatic', 'cvt'].includes(merged.transmission)) {
    throw new CalcError('VALIDATION_ERROR', `vehicle.transmission inválido: ${merged.transmission}`, 422);
  }
  if (!['gasoline', 'ethanol', 'diesel', 'flex'].includes(merged.fuel_type)) {
    throw new CalcError('VALIDATION_ERROR', `vehicle.fuel_type inválido: ${merged.fuel_type}`, 422);
  }
  if (merged.drivetrain_efficiency == null) merged.drivetrain_efficiency = 0.85;
  if (merged.engine_thermal_efficiency == null) merged.engine_thermal_efficiency = 0.25;
  if (merged.aux_power_w == null) merged.aux_power_w = 1500;

  return merged;
}

function totalMassKg(vehicle, load) {
  return vehicle.empty_weight_kg
    + load.passenger_count * load.passenger_avg_weight_kg
    + load.cargo_weight_kg;
}

function idleFuelL(vehicle, idleTimeMin) {
  if (idleTimeMin <= 0) return 0.0;
  return vehicle.idle_fuel_l_per_h * (idleTimeMin / 60.0);
}

// =====================================================================
// Elevation profile
// =====================================================================

function buildGradeProfile(elevationProfile, nSegments, dxM) {
  if (!elevationProfile || elevationProfile.length < 2) {
    return new Array(nSegments).fill(0.0);
  }
  const points = elevationProfile.map(p => [p.distance_km * 1000.0, p.elevation_m ?? 0.0]);

  const grades = new Array(nSegments).fill(0.0);
  for (let i = 0; i < nSegments; i++) {
    const sM = i * dxM;
    const eM = (i + 1) * dxM;
    const sElev = interpElev(points, sM);
    const eElev = interpElev(points, eM);
    const rise = eElev - sElev;
    grades[i] = gradeFromElevation(dxM, rise);
  }
  return grades;
}

function interpElev(points, xM) {
  if (xM <= points[0][0]) return points[0][1];
  if (xM >= points[points.length - 1][0]) return points[points.length - 1][1];
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    if (x0 <= xM && xM <= x1) {
      if (x1 === x0) return y0;
      const t = (xM - x0) / (x1 - x0);
      return y0 + t * (y1 - y0);
    }
  }
  return points[points.length - 1][1];
}

// =====================================================================
// Trip integration
// =====================================================================

function rollStop(segmentIndex, probability) {
  if (probability <= 0) return false;
  // Hash determinístico por índice, igual ao Python.
  // `>>> 0` força JS a tratar como unsigned 32-bit (em Python `& 0xFFFFFFFF` é unsigned por padrão).
  const h = (segmentIndex * 2654435761) >>> 0;
  const u = (h % 10000) / 10000.0;
  return u < probability;
}

function addStopCycle({ fuelL, energyJ, massKg, cruiseSpeedMps, fuel,
                       engineEff, drivetrainEff }) {
  const ke = 0.5 * massKg * cruiseSpeedMps * cruiseSpeedMps;
  const energyInJ = ke / Math.max(engineEff * drivetrainEff, 0.05);
  const fuelAccel = energyInJ / (fuel.lhvMjKg * 1_000_000.0) / Math.max(fuel.densityKgL, 1e-6);
  const idleFuel = 0.6 * 10.0 / 3600.0;  // 10 s de marcha lenta
  return { fuelL: fuelL + fuelAccel + idleFuel, energyJ: energyJ + ke };
}

function integrateTrip(opts) {
  const { vehicle, trip, totalMassKg, towingKg, airDensity, headwindKmh,
          auxPowerW, segmentLengthM, roadCondition } = opts;

  const distanceM = trip.distance_km * 1000.0;
  const nSegments = Math.max(1, Math.ceil(distanceM / segmentLengthM));
  const actualDx = distanceM / nSegments;

  const gradePerSeg = buildGradeProfile(trip.elevation_profile, nSegments, actualDx);

  const cruiseMps = trip.average_speed_kmh / 3.6;
  const headwindMps = headwindKmh / 3.6;
  const speedMps = Math.max(cruiseMps + headwindMps, 0.5);

  const stopsPerKm = resolveStopsPerKm(trip.speed_profile, trip.stops_per_km);
  const pStop = Math.min(1.0, stopsPerKm * (actualDx / 1000.0));

  const towingInc = towingAeroIncrement(towingKg, vehicle.type);
  const frontalArea = vehicle.frontal_area_m2 + towingInc;
  const crrFactor = rollingResistanceRoadFactor(roadCondition);
  const crr = vehicle.rolling_resistance_coeff * crrFactor;

  const auxW = auxPowerW;
  const fuel = fuelProperties(vehicle.fuel_type);

  const segments = [];
  let totalFuelL = 0.0;
  let totalEnergyJ = 0.0;

  for (let i = 0; i < nSegments; i++) {
    const startM = i * actualDx;
    const endM = (i + 1) * actualDx;
    const gradeRad = gradePerSeg[i];
    const gradePct = Math.tan(gradeRad) * 100.0;

    const fDrag = aeroDragForce(vehicle.drag_coefficient_cd, frontalArea, airDensity, speedMps);
    const fRoll = rollingResistanceForce(crr, totalMassKg, gradeRad);
    const fClimb = climbingForce(totalMassKg, gradeRad);
    const fTotal = fDrag + fRoll + fClimb;
    const pT = Math.max(0.0, tractivePower(fTotal, speedMps));
    const pTotal = pT + auxW;

    const dt = actualDx / Math.max(speedMps, 0.5);
    let fuelL = fuelFlowLPerS(
      pTotal,
      vehicle.engine_thermal_efficiency,
      vehicle.drivetrain_efficiency,
      fuel.lhvMjKg,
      fuel.densityKgL,
    ) * dt;
    let energyJ = pT * dt;

    if (pStop > 0 && rollStop(i, pStop)) {
      const out = addStopCycle({
        fuelL, energyJ, massKg: totalMassKg, cruiseSpeedMps: cruiseMps,
        fuel, engineEff: vehicle.engine_thermal_efficiency,
        drivetrainEff: vehicle.drivetrain_efficiency,
      });
      fuelL = out.fuelL;
      energyJ = out.energyJ;
    }

    totalFuelL += fuelL;
    totalEnergyJ += energyJ;
    segments.push({
      index: i,
      start_km: round(startM / 1000.0, 4),
      end_km: round(endM / 1000.0, 4),
      grade_pct: round(gradePct, 4),
      speed_kmh: round(speedMps * 3.6, 3),
      tractive_power_w: round(pT, 1),
      fuel_l: round(fuelL, 6),
    });
  }

  return { segments, totalFuelL, totalEnergyJ };
}

// =====================================================================
// API pública
// =====================================================================

function round(n, decimals) {
  if (n == null || Number.isNaN(n)) return n;
  const f = 10 ** decimals;
  return Math.round(n * f) / f;
}

function validateElevationProfile(profile) {
  if (!profile || profile.length < 2) return;
  for (let i = 1; i < profile.length; i++) {
    if (profile[i].distance_km <= profile[i - 1].distance_km) {
      throw new CalcError(
        'VALIDATION_ERROR',
        'elevation_profile deve ser estritamente crescente em distance_km',
        422,
      );
    }
  }
}

export function calculate(rawRequest) {
  // 1. Defaults + validação de entrada
  if (!rawRequest) throw new CalcError('VALIDATION_ERROR', 'Payload vazio', 422);
  if (!rawRequest.vehicle) throw new CalcError('VALIDATION_ERROR', 'vehicle é obrigatório', 422);
  if (!rawRequest.trip) throw new CalcError('VALIDATION_ERROR', 'trip é obrigatório', 422);

  const trip = mergeDefaults(rawRequest.trip, TRIP_DEFAULTS);
  if (trip.distance_km <= 0) {
    throw new CalcError('VALIDATION_ERROR', 'trip.distance_km deve ser > 0', 422);
  }
  if (trip.average_speed_kmh <= 0 || trip.average_speed_kmh > 250) {
    throw new CalcError('VALIDATION_ERROR', `trip.average_speed_kmh = ${trip.average_speed_kmh} fora de [1, 250]`, 422);
  }
  if (trip.idle_time_min < 0) {
    throw new CalcError('VALIDATION_ERROR', 'trip.idle_time_min não pode ser negativo', 422);
  }
  validateElevationProfile(trip.elevation_profile);

  const environment = mergeDefaults(rawRequest.environment, ENVIRONMENT_DEFAULTS);
  const load = mergeDefaults(rawRequest.load, LOAD_DEFAULTS);
  const driver = mergeDefaults(rawRequest.driver, DRIVER_DEFAULTS);
  const vehicle = resolveVehicle(rawRequest.vehicle);

  // 2. Massa total
  const totalMass = totalMassKg(vehicle, load);

  // 3. Atmosfera
  const rho = airDensity(environment.temperature_c, environment.altitude_m, environment.humidity_pct);
  const headwind = effectiveHeadwindKmh(environment.wind_speed_kmh, environment.wind_direction_deg, 0.0);

  // 4. AC
  const ac = acFactor(driver.use_ac, environment.temperature_c, trip.distance_km, trip.average_speed_kmh);
  const auxPowerW = vehicle.aux_power_w + ac.auxW;

  // 5. Integração
  const fuel = fuelProperties(vehicle.fuel_type);
  const { segments, totalFuelL: rawFuel, totalEnergyJ: rawEnergy } = integrateTrip({
    vehicle, trip, totalMassKg: totalMass, towingKg: load.towing_kg,
    airDensity: rho, headwindKmh: headwind, auxPowerW,
    segmentLengthM: DEFAULT_SEGMENT_LENGTH_M,
    roadCondition: environment.road_condition,
  });
  const idleFuel = idleFuelL(vehicle, trip.idle_time_min);

  // 6. Fatores de correção
  const factors = [];
  const warnings = [];

  const fAlt = altitudeFactor(environment.altitude_m);
  factors.push({ name: 'altitude', factor: fAlt });

  const fTemp = temperatureFactor(environment.temperature_c, trip.idle_time_min, trip.distance_km);
  factors.push({ name: 'temperature', factor: fTemp });

  const fHum = humidityFactor(environment.humidity_pct);
  factors.push({ name: 'humidity', factor: fHum });

  const fRoad = roadConditionFactor(environment.road_condition);
  factors.push({ name: 'road_condition', factor: fRoad });

  const fStyle = drivingStyleFactor(driver.driving_style);
  factors.push({ name: 'driving_style', factor: fStyle });

  const fQual = fuelQualityFactor(driver.fuel_quality);
  factors.push({ name: 'fuel_quality', factor: fQual });

  const fAge = vehicleAgeFactor(vehicle.year);
  factors.push({ name: 'vehicle_age', factor: fAge });

  const fTrans = transmissionFactor(vehicle.transmission);
  factors.push({ name: 'transmission', factor: fTrans });

  const fTire = tirePressureFactor(vehicle.tire_pressure_kpa);
  if (fTire > 1.05) {
    warnings.push(
      `Pressão de pneu baixa (${vehicle.tire_pressure_kpa.toFixed(0)} kPa): ` +
      `consumo pode subir ${((fTire - 1.0) * 100).toFixed(1)}%.`
    );
  }
  factors.push({ name: 'tire_pressure', factor: fTire });

  const payloadMass = load.passenger_count * load.passenger_avg_weight_kg + load.cargo_weight_kg;
  const fLoad = loadFactor(vehicle.empty_weight_kg, payloadMass, load.towing_kg);
  factors.push({ name: 'load', factor: fLoad });

  if (driver.use_ac) {
    factors.push({ name: 'ac', factor: ac.factor });
    if (environment.temperature_c < 0.0) {
      warnings.push(
        'Ar-condicionado ligado a 0 °C: usado apenas para desembaçar, ' +
        'aquecimento do habitáculo é ineficiente.'
      );
    }
  }

  const eth = ethanolBlendFactor(vehicle.fuel_type, driver.fuel_quality);
  factors.push({ name: 'ethanol_blend_volume', factor: eth.volumeFactor });
  factors.push({ name: 'ethanol_blend_co2', factor: eth.co2Factor });

  // 7. Combina tudo
  const multiplicative =
    fAlt * fTemp * fHum * fRoad * fStyle * fQual * fAge *
    fTrans * fTire * fLoad * ac.factor * eth.volumeFactor;

  const totalFuelL = rawFuel * multiplicative + idleFuel;
  const totalEnergyJ = rawEnergy * multiplicative;

  // 8. Custo (se houver)
  const costBrl = driver.fuel_price_brl_per_l != null
    ? totalFuelL * driver.fuel_price_brl_per_l
    : null;

  // 9. CO₂
  const co2Kg = totalFuelL * fuel.densityKgL * fuel.co2KgPerKg * eth.co2Factor;

  // 10. Métricas finais
  const distanceKm = trip.distance_km;
  const lPer100km = (totalFuelL / distanceKm) * 100.0;
  const kmPerL = totalFuelL > 0 ? distanceKm / totalFuelL : 0.0;
  const tripDurationH = trip.average_speed_kmh > 0
    ? distanceKm / trip.average_speed_kmh
    : (trip.idle_time_min / 60.0);

  // 11. Rótulo e avisos
  const vehicleLabel = vehicle.preset_id
    || `${vehicle.type}-${vehicle.category || 'custom'} (${vehicle.year})`;

  if (load.towing_kg > 0) {
    warnings.push(
      `Rebocando ${load.towing_kg.toFixed(0)} kg: verifique limites do veículo e do engate.`
    );
  }
  if (totalFuelL > vehicle.fuel_tank_capacity_l) {
    warnings.push(
      `Combustível necessário (${totalFuelL.toFixed(1)} L) excede a capacidade do tanque ` +
      `(${vehicle.fuel_tank_capacity_l.toFixed(1)} L). Planeje paradas para reabastecimento.`
    );
  }

  return {
    vehicle_label: vehicleLabel,
    fuel_type: vehicle.fuel_type,
    distance_km: round(distanceKm, 4),
    trip_duration_h: round(tripDurationH, 4),
    average_speed_kmh: round(trip.average_speed_kmh, 4),
    total_fuel_l: round(totalFuelL, 4),
    fuel_per_km_l_per_100km: round(lPer100km, 4),
    km_per_l: round(kmPerL, 4),
    energy_mj: round(totalEnergyJ / 1_000_000.0, 4),
    co2_kg: round(co2Kg, 4),
    fuel_cost_brl: costBrl != null ? round(costBrl, 2) : null,
    factors,
    segments,
    warnings,
    total_mass_kg: round(totalMass, 2),
    air_density_kg_per_m3: round(rho, 4),
    effective_headwind_kmh: round(headwind, 2),
    aux_power_effective_w: round(auxPowerW, 1),
  };
}
