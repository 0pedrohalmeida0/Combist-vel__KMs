"""Fatores de correção aplicados ao consumo base.

Cada função é pura: recebe parâmetros físicos e devolve um
fator multiplicativo (1.0 = sem efeito) ou um delta aditivo
(quando explicitado em l/h). Esses fatores são combinados em
`service.py` na seguinte ordem lógica:

    driving_fuel × driving_style × fuel_quality × vehicle_age ×
    transmission × tire_pressure × ethanol_blend × road_condition ×
    humidity_factor_de_ar

A penalidade de altitude é refletida na densidade do ar (a
combustão é menos eficiente em ar rarefeito) — `altitude_factor`
representa a penalidade adicional que o motor sofre mesmo com
a mistura otimizada.

Os valores foram calibrados para serem plausíveis e monotônicos
nas faixas de operação típicas; não substituem medições reais.
"""
from __future__ import annotations

import math
from typing import Tuple

from .physics import DEFAULT_STOPS_PER_KM


# ---------------------------------------------------------------------------
# Atmosfera / ambiente
# ---------------------------------------------------------------------------
def altitude_factor(altitude_m: float) -> float:
    """Penalidade de altitude na eficiência de combustão.

    +4% a cada 1000 m acima de 1500 m, com cap em +25% (≈ 7750 m).
    Abaixo de 1500 m não há penalidade.
    """
    if altitude_m <= 1500.0:
        return 1.0
    excess_km = (altitude_m - 1500.0) / 1000.0
    return min(1.0 + 0.04 * excess_km, 1.25)


def temperature_factor(temp_c: float, idle_time_min: float, distance_km: float) -> float:
    """Penalidade por motor frio.

    f(T) = 1 + max(0, (20 - T)/20) · exp(-distance_km / 5)
    Também cresce com tempo parado em frio: +1% por minuto ocioso
    abaixo de 10 °C (limitado a +15%).
    """
    base = 1.0 + max(0.0, (20.0 - temp_c) / 20.0) * math.exp(-distance_km / 5.0)
    if idle_time_min > 0 and temp_c < 10.0:
        idle_penalty = min(0.15, idle_time_min * 0.01)
        base += idle_penalty
    return base


def humidity_factor(humidity_pct: float) -> float:
    """Ar úmido é ~1% menos denso que ar seco → penalidade desprezível.

    Modelado como desvio linear centrado em 60% UR (default).
    """
    # 0% UR → 1.01 (ar mais denso, combustão ligeiramente melhor)
    # 100% UR → 0.99 (ar menos denso, combustão ligeiramente pior)
    return 1.0 + (60.0 - humidity_pct) * 0.0002


def road_condition_factor(cond: str) -> float:
    table = {
        "dry":  1.00,
        "wet":  1.05,
        "snow": 1.20,
        "ice":  1.35,
    }
    return table.get(cond.lower(), 1.0)


def rolling_resistance_road_factor(cond: str) -> float:
    """Multiplicador adicional na resistência de rolamento."""
    table = {
        "dry":  1.00,
        "wet":  1.10,
        "snow": 1.30,
        "ice":  1.60,
    }
    return table.get(cond.lower(), 1.0)


# ---------------------------------------------------------------------------
# Vento
# ---------------------------------------------------------------------------
def effective_headwind_kmh(
    wind_speed_kmh: float, wind_direction_deg: float, vehicle_heading_deg: float = 0.0
) -> float:
    """Componente de vento contrário (km/h, positivo = contra o veículo).

    `wind_direction_deg` é a direção DE onde o vento sopra (0 = norte,
    convenção meteorológica). 0° de diferença significa vento de frente
    (headwind puro).
    """
    # Diferença angular entre o vetor de origem do vento e a frente do carro.
    diff = math.radians(wind_direction_deg - vehicle_heading_deg)
    # cos(diff) = +1 quando vento vem de frente (headwind), -1 quando vem de trás.
    return wind_speed_kmh * math.cos(diff)


# ---------------------------------------------------------------------------
# Carga e ar-condicionado
# ---------------------------------------------------------------------------
def ac_factor(
    use_ac: bool,
    temperature_c: float,
    distance_km: float,
    speed_kmh: float,
) -> Tuple[float, float]:
    """Devolve (fator_multiplicativo, aux_power_adicional_W).

    AC comprime ~1.5–3 kW do alternador. Penalidade cresce
    linearmente com T acima de 22 °C e decai abaixo de 10 °C
    (penalidade de aquecimento do habitáculo). A 0 °C o AC
    é praticamente inútil para aquecer — devolvemos um aviso
    por meio do fator `0.99` (efeito desprezível) e o consumidor
    pode checar a string de retorno.
    """
    if not use_ac:
        return 1.0, 0.0

    if temperature_c >= 22.0:
        # Resfriamento: até +3 kW a 40 °C.
        aux_w = 1500.0 + (temperature_c - 22.0) * 150.0
        factor = 1.0 + min(0.15, 0.01 * (temperature_c - 22.0))
    elif temperature_c <= 10.0:
        # Aquecimento: menor demanda do AC (1–1.5 kW), mas cresce com a diferença.
        # Abaixo de 0 °C o AC não aquece — só desumidifica (ineficaz).
        if temperature_c < 0.0:
            aux_w = 200.0
            factor = 1.01
        else:
            aux_w = 1000.0 + (10.0 - temperature_c) * 100.0
            factor = 1.0 + 0.005 * (10.0 - temperature_c)
    else:
        aux_w = 800.0
        factor = 1.02

    # Em baixa velocidade o compressor é mais exigido (radiador do
    # condensador recebe menos ar). Pequeno bônus quando parado no
    # trânsito: +5% sobre aux_w se v < 20 km/h.
    if speed_kmh < 20.0:
        aux_w *= 1.05
    return factor, aux_w


def load_factor(
    vehicle_mass_kg: float, payload_kg: float, towing_kg: float
) -> float:
    """Fator multiplicativo devido à carga transportada.

    A maior parte do efeito da carga é tratada passando a massa
    total para `physics.tractive_power`. Aqui modelamos efeitos
    secundários (motor trabalhando mais perto do limite de
    torque): +0.5% por 100 kg acima de 200 kg, até +5%.
    """
    extra = payload_kg + towing_kg
    if extra <= 200.0:
        return 1.0
    return 1.0 + min(0.05, 0.005 * (extra - 200.0) / 100.0)


def towing_aero_increment(towing_kg: float, vehicle_type: str) -> float:
    """Incremento de área frontal (m²) ao rebocar um trailer."""
    if towing_kg <= 0:
        return 0.0
    base = 1.0 if vehicle_type == "car" else 0.3
    # Até 50% da área base do trailer a 3000 kg rebocados.
    factor = min(1.0, towing_kg / 3000.0)
    return base * factor * 0.5


# ---------------------------------------------------------------------------
# Estilo e manutenção
# ---------------------------------------------------------------------------
def driving_style_factor(style: str) -> float:
    table = {
        "eco":       0.92,
        "normal":    1.00,
        "aggressive": 1.18,
    }
    return table.get(style.lower(), 1.0)


def tire_pressure_factor(actual_kpa: float, nominal_kpa: float = 220.0) -> float:
    """Pneu murcho aumenta resistência de rolamento."""
    if actual_kpa >= nominal_kpa:
        return 1.0
    diff = nominal_kpa - actual_kpa
    return 1.0 + 0.002 * diff


def fuel_quality_factor(quality: str) -> float:
    table = {"regular": 1.0, "premium": 0.97}
    return table.get(quality.lower(), 1.0)


def vehicle_age_factor(year: int, ref_year: int = 2026) -> float:
    """Veículos mais antigos são menos eficientes (capped em +20%)."""
    if year >= ref_year:
        return 1.0
    return min(1.20, 1.0 + 0.005 * (ref_year - year))


def transmission_factor(transmission: str) -> float:
    table = {"manual": 1.00, "automatic": 1.05, "cvt": 1.03}
    return table.get(transmission.lower(), 1.0)


def ethanol_blend_factor(fuel_type: str, fuel_quality: str):
    """Retorna (volume_factor, co2_factor) para o tipo de combustível.

    Para `flex` com `premium`, assume-se uso de etanol (E100) — que
    entrega ~30% menos km/L mas emite ~35% menos CO₂ no escapamento.
    Para `flex` regular, usa gasolina (E22/E27).
    """
    ft = (fuel_type or "").lower()
    fq = (fuel_quality or "").lower()
    if ft == "ethanol":
        return 1.30, 0.65
    if ft == "flex":
        if fq == "premium":
            return 1.30, 0.65
        return 1.00, 1.00
    if ft == "diesel":
        # Diesel premium pode ter aditivos melhoradores — 1% de economia.
        return 0.99 if fq == "premium" else 1.00, 1.00
    # Gasoline
    return 0.97 if fq == "premium" else 1.00, 1.00


# ---------------------------------------------------------------------------
# Perfil de velocidade (paradas por km)
# ---------------------------------------------------------------------------
def resolve_stops_per_km(speed_profile: str, explicit: float) -> float:
    """Resolve o número de paradas por km, usando o explícito se > 0."""
    if explicit and explicit > 0:
        return float(explicit)
    return DEFAULT_STOPS_PER_KM.get(speed_profile.lower(), 0.0)
