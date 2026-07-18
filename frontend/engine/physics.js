// physics.js — modelo físico do veículo
// Portado de app/fuel/physics.py. Funções puras, unidades SI.

export const G = 9.80665;              // m/s²
export const R_AIR = 287.058;          // J/(kg·K)
export const P0 = 101325.0;           // Pa
export const T0_K = 288.15;            // K
export const LAPSE = 0.0065;           // K/m
export const M_AIR = 0.0289644;        // kg/mol
export const R_UNIV = 8.31447;         // J/(mol·K)
export const RHO0 = 1.225;             // kg/m³ ao nível do mar / 15 °C

/** Pressão de vapor de saturação (Tetens) — T em °C, retorna Pa. */
function saturationVaporPressurePa(tC) {
  return 610.78 * Math.exp((17.27 * tC) / (tC + 237.3));
}

/**
 * Densidade do ar (kg/m³) com umidade, temperatura e altitude.
 * 1. Pressão barométrica (fórmula troposférica)
 * 2. Temperatura local (fornecida pelo usuário)
 * 3. Pressão parcial de vapor d'água (Tetens + umidade relativa)
 * 4. Lei dos gases ideais pro ar úmido
 */
export function airDensity(temperatureC, altitudeM, humidityPct) {
  const tK = temperatureC + 273.15;
  const h = Math.max(altitudeM, 0.0);

  // 1. Pressão barométrica (ar seco)
  const exponent = (G * M_AIR) / (R_UNIV * LAPSE);
  const pDry = P0 * Math.pow(1.0 - (LAPSE * h) / T0_K, exponent);

  // 3. Pressão de vapor d'água
  const pSat = saturationVaporPressurePa(temperatureC);
  const pVapor = Math.min(pSat * (humidityPct / 100.0), pDry * 0.05);
  const pDryAir = pDry - pVapor;

  // 4. Densidade do ar úmido
  const rD = 287.058;   // ar seco
  const rV = 461.495;   // vapor d'água
  return pDryAir / (rD * tK) + pVapor / (rV * tK);
}

/** F_d = 0.5 · ρ · Cd · A · v² */
export function aeroDragForce(cd, frontalAreaM2, airDensityKgM3, speedMps) {
  return 0.5 * airDensityKgM3 * cd * frontalAreaM2 * speedMps * speedMps;
}

/** F_r = Crr · m · g · cos(θ) */
export function rollingResistanceForce(crr, massKg, gradeRad, g = G) {
  return crr * massKg * g * Math.cos(gradeRad);
}

/** F_c = m · g · sin(θ) */
export function climbingForce(massKg, gradeRad, g = G) {
  return massKg * g * Math.sin(gradeRad);
}

/** F_a = m · a */
export function accelerationForce(massKg, accelMps2) {
  return massKg * accelMps2;
}

/** P_t = ΣF · v */
export function tractivePower(forcesN, speedMps) {
  return forcesN * speedMps;
}

/** ṁ = P / (η_eng · η_drivetrain · LHV)   [kg/s] */
export function fuelFlowKgPerS(powerW, engineEff, drivetrainEff, lhvMjPerKg) {
  if (lhvMjPerKg <= 0 || engineEff <= 0 || drivetrainEff <= 0) return 0.0;
  const lhvJPerKg = lhvMjPerKg * 1_000_000.0;
  return powerW / (engineEff * drivetrainEff * lhvJPerKg);
}

/** Vazão volumétrica (L/s) a partir da mássica. */
export function fuelFlowLPerS(powerW, engineEff, drivetrainEff, lhvMjPerKg, densityKgL) {
  const massFlow = fuelFlowKgPerS(powerW, engineEff, drivetrainEff, lhvMjPerKg);
  if (densityKgL <= 0) return 0.0;
  return massFlow / densityKgL;
}

/** Marcha lenta em L/s. */
export function idleFuelFlowLPerS(idleFuelLPerH) {
  return idleFuelLPerH / 3600.0;
}

/** Propriedades do combustível por tipo. */
export const FUEL_PROPERTIES = {
  gasoline: { densityKgL: 0.745, lhvMjKg: 42.0, co2KgPerKg: 3.17 },
  ethanol:  { densityKgL: 0.789, lhvMjKg: 27.0, co2KgPerKg: 1.91 },
  diesel:   { densityKgL: 0.832, lhvMjKg: 43.0, co2KgPerKg: 3.20 },
  flex:     { densityKgL: 0.760, lhvMjKg: 36.0, co2KgPerKg: 2.65 },
};

export function fuelProperties(fuelType) {
  const key = (fuelType || '').toLowerCase();
  if (key in FUEL_PROPERTIES) return FUEL_PROPERTIES[key];
  return FUEL_PROPERTIES.gasoline;  // fallback seguro
}

/** Aclive (m de subida por m horizontais) → radianos. Cap em 30%. */
export function gradeFromElevation(distanceM, elevRiseM) {
  if (distanceM <= 0) return 0.0;
  const grade = Math.max(Math.min(elevRiseM / distanceM, 0.30), -0.30);
  return Math.atan(grade);
}

/** Paradas por km default por perfil. */
export const DEFAULT_STOPS_PER_KM = {
  constant: 0.0,
  highway: 0.05,
  mixed:   0.15,
  suburban: 0.20,
  urban:   0.60,
};

/** Resolve paradas por km (explícito > default do perfil). */
export function resolveStopsPerKm(speedProfile, explicit) {
  if (explicit && explicit > 0) return Number(explicit);
  return DEFAULT_STOPS_PER_KM[(speedProfile || '').toLowerCase()] ?? 0.0;
}

// Stop-and-go (m/s² e distâncias)
export const ACCEL_PHASE_A = 1.0;
export const DECEL_PHASE_A = 1.2;
export const ACCEL_PHASE_DISTANCE_M = 50.0;
export const DECEL_PHASE_DISTANCE_M = 30.0;
