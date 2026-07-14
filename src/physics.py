"""Modelo físico do veículo.

Funções puras (sem efeitos colaterais) que calculam:

- Densidade do ar com correção de temperatura, altitude e umidade.
- Forças resistivas (aerodinâmica, rolamento, aclive, inércia).
- Potência de tração, vazão mássica de combustível e conversão para
  litros/segundo.

Todas as equações operam em unidades SI (m, s, kg, J, W). O módulo
deliberadamente NÃO toca em HTTP, banco ou logging — quem integra
esses blocos é `service.py`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Constantes físicas (SI)
# ---------------------------------------------------------------------------
G = 9.80665                # m/s² — aceleração gravitacional padrão
R_AIR = 287.058            # J/(kg·K) — constante específica do ar seco
P0 = 101325.0              # Pa — pressão ao nível do mar
T0_K = 288.15              # K — temperatura ao nível do mar (15 °C)
LAPSE = 0.0065             # K/m — lapse rate troposférico
M_AIR = 0.0289644          # kg/mol — massa molar do ar seco
R_UNIV = 8.31447           # J/(mol·K) — constante universal dos gases
WATER_MOLAR = 0.018015     # kg/mol — massa molar da água
T_TRIPLE = 273.16          # K — ponto triplo da água

# Densidade de referência ao nível do mar / 15 °C / ar seco.
RHO0 = 1.225                # kg/m³

# Pressão de vapor de saturação da água (fórmula de Tetens, °C -> Pa).
# Retorna Pa para T em °C. Válida para 0 °C ≤ T ≤ 50 °C.
def _saturation_vapor_pressure_pa(t_c: float) -> float:
    return 610.78 * math.exp((17.27 * t_c) / (t_c + 237.3))


# Propriedades dos combustíveis. Densidade em kg/L e LHV em MJ/kg.
FUEL_PROPERTIES: Dict[str, Tuple[float, float, float]] = {
    # densidade_kg_l, lhv_mj_kg, co2_kg_per_kg_fuel
    "gasoline": (0.745, 42.0, 3.17),
    "ethanol":  (0.789, 27.0, 1.91),
    "diesel":   (0.832, 43.0, 3.20),
    "flex":     (0.760, 36.0, 2.65),  # média ponderada gasolina/etanol
}

# Composição aproximada de um veículo "flex" rodando a etanol.
FLEX_ETHANOL_VOLUME_FACTOR = 1.30     # +30% em volume vs gasolina
FLEX_ETHANOL_CO2_FACTOR = 0.65        # -35% em CO₂ (tailpipe)


# ---------------------------------------------------------------------------
# Atmosfera
# ---------------------------------------------------------------------------
def air_density(temperature_c: float, altitude_m: float, humidity_pct: float) -> float:
    """Densidade do ar (kg/m³) com umidade.

    Passos:
      1. Pressão barométrica via fórmula de pressão troposférica:
         P(h) = P0 · (1 - L·h/T0)^(g·M / (R·L))
      2. Temperatura do ar: a do usuário (Kelvin). O usuário
         informa a temperatura real no local; usar o perfil de
         lapse rate aqui causaria um erro sistemático sempre que
         a condição diferisse da atmosfera padrão.
      3. Pressão parcial de vapor d'água pela equação de Tetens,
         corrigida pela umidade relativa.
      4. Lei dos gases ideais aplicada ao ar úmido:
         ρ = (P_d / (R_d·T)) + (P_v / (R_v·T))
         onde P_d é a pressão do ar seco e P_v a pressão de vapor.
    """
    t_k = temperature_c + 273.15
    h = max(altitude_m, 0.0)

    # 1. Pressão barométrica (ar seco, sem ajuste de umidade — feito abaixo).
    exponent = (G * M_AIR) / (R_UNIV * LAPSE)
    p_dry = P0 * (1.0 - (LAPSE * h) / T0_K) ** exponent

    # 2. Temperatura local (do usuário — ver nota acima).
    t_local = t_k

    # 3. Pressão de vapor d'água
    p_sat = _saturation_vapor_pressure_pa(temperature_c)
    p_vapor = p_sat * (humidity_pct / 100.0)
    # Garante que a pressão parcial não exceda a pressão total.
    p_vapor = min(p_vapor, p_dry * 0.05)  # limite físico razoável
    p_dry_air = p_dry - p_vapor

    # 4. Densidade do ar úmido (mistura de gases ideais)
    r_d = 287.058       # ar seco
    r_v = 461.495       # vapor d'água
    rho = p_dry_air / (r_d * t_local) + p_vapor / (r_v * t_local)
    return rho


# ---------------------------------------------------------------------------
# Forças
# ---------------------------------------------------------------------------
def aero_drag_force(
    cd: float, frontal_area_m2: float, air_density_kg_m3: float, speed_mps: float
) -> float:
    """F_d = 0.5 · ρ · Cd · A · v²   (Newtons)"""
    return 0.5 * air_density_kg_m3 * cd * frontal_area_m2 * speed_mps * speed_mps


def rolling_resistance_force(
    crr: float, mass_kg: float, grade_rad: float, g: float = G
) -> float:
    """F_r = Crr · m · g · cos(θ)   (Newtons)"""
    return crr * mass_kg * g * math.cos(grade_rad)


def climbing_force(mass_kg: float, grade_rad: float, g: float = G) -> float:
    """F_c = m · g · sin(θ)   (Newtons)"""
    return mass_kg * g * math.sin(grade_rad)


def acceleration_force(mass_kg: float, accel_mps2: float) -> float:
    """F_a = m · a   (Newtons)"""
    return mass_kg * accel_mps2


# ---------------------------------------------------------------------------
# Energia e combustível
# ---------------------------------------------------------------------------
def tractive_power(forces_n: float, speed_mps: float) -> float:
    """P_t = ΣF · v   (Watts) — `forces_n` é o somatório de forças."""
    return forces_n * speed_mps


def fuel_flow_kg_per_s(
    power_w: float,
    engine_eff: float,
    drivetrain_eff: float,
    lhv_mj_per_kg: float,
) -> float:
    """ṁ = P_t / (η_eng · η_drivetrain · LHV)   (kg/s)"""
    if lhv_mj_per_kg <= 0 or engine_eff <= 0 or drivetrain_eff <= 0:
        return 0.0
    lhv_j_per_kg = lhv_mj_per_kg * 1_000_000.0
    return power_w / (engine_eff * drivetrain_eff * lhv_j_per_kg)


def fuel_flow_l_per_s(
    power_w: float,
    engine_eff: float,
    drivetrain_eff: float,
    lhv_mj_per_kg: float,
    density_kg_l: float,
) -> float:
    """Vazão volumétrica (L/s) a partir da vazão mássica."""
    mass_flow = fuel_flow_kg_per_s(
        power_w, engine_eff, drivetrain_eff, lhv_mj_per_kg
    )
    if density_kg_l <= 0:
        return 0.0
    return mass_flow / density_kg_l


def idle_fuel_flow_l_per_s(idle_fuel_l_per_h: float) -> float:
    """Vazão em marcha lenta (L/s)."""
    return idle_fuel_l_per_h / 3600.0


# ---------------------------------------------------------------------------
# Estruturas auxiliares
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FuelProps:
    density_kg_l: float
    lhv_mj_kg: float
    co2_kg_per_kg: float


def fuel_properties(fuel_type: str) -> FuelProps:
    """Resolve propriedades do combustível a partir do enum/string."""
    key = (fuel_type or "").lower()
    if key not in FUEL_PROPERTIES:
        # fallback seguro
        density, lhv, co2 = FUEL_PROPERTIES["gasoline"]
    else:
        density, lhv, co2 = FUEL_PROPERTIES[key]
    return FuelProps(density_kg_l=density, lhv_mj_kg=lhv, co2_kg_per_kg=co2)


def grade_from_elevation(
    distance_m: float, elev_rise_m: float
) -> float:
    """Converte aclive (m de subida por m horizontais) em radianos.

    Pequenos aclives (<30%) podem ser aproximados por atan(rise/run)
    sem perda de precisão significativa.
    """
    if distance_m <= 0:
        return 0.0
    grade = elev_rise_m / distance_m
    # Cap em 30% (≈ 16.7°) para evitar singularidades em aclives absurdos.
    grade = max(min(grade, 0.30), -0.30)
    return math.atan(grade)


# ---------------------------------------------------------------------------
# Perfil de velocidade
# ---------------------------------------------------------------------------
# Frequência padrão de paradas por km, em função do perfil.
DEFAULT_STOPS_PER_KM: Dict[str, float] = {
    "constant": 0.0,
    "highway": 0.05,
    "mixed":   0.15,
    "suburban": 0.20,
    "urban":   0.60,
}

# Acelerações típicas em fase de stop-and-go (m/s²).
ACCEL_PHASE_A = 1.0
DECEL_PHASE_A = 1.2
ACCEL_PHASE_DISTANCE_M = 50.0
DECEL_PHASE_DISTANCE_M = 30.0
