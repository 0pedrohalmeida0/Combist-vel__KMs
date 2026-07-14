"""Testes para as funções de correção.

Cada fator é exercitado com pelo menos três casos, incluindo
valores de fronteira. Os valores esperados são derivados das
fórmulas nas docstrings de `app.fuel.corrections`.
"""
from __future__ import annotations

import math

import pytest

from app.fuel.corrections import (
    ac_factor,
    altitude_factor,
    driving_style_factor,
    effective_headwind_kmh,
    ethanol_blend_factor,
    fuel_quality_factor,
    humidity_factor,
    load_factor,
    resolve_stops_per_km,
    road_condition_factor,
    rolling_resistance_road_factor,
    temperature_factor,
    tire_pressure_factor,
    towing_aero_increment,
    transmission_factor,
    vehicle_age_factor,
)


# ===========================================================================
# Altitude
# ===========================================================================
def test_altitude_sea_level_no_penalty():
    """0 m → 1.0 (sem penalidade)."""
    assert altitude_factor(0) == 1.0


def test_altitude_1500m_boundary_no_penalty():
    """1500 m é o limite: exatamente 1.0."""
    assert altitude_factor(1500) == 1.0


def test_altitude_3500m_penalty_8pct():
    """3500 m: +4% por 1000 m acima de 1500 → 1 + 0.04*2 = 1.08."""
    assert math.isclose(altitude_factor(3500), 1.08, rel_tol=1e-9)


def test_altitude_increases_factor_linearly():
    """+4% por 1000 m acima de 1500 m, monótono crescente."""
    f2000 = altitude_factor(2000)
    f3000 = altitude_factor(3000)
    assert math.isclose(f2000, 1.02, rel_tol=1e-9)
    assert math.isclose(f3000, 1.06, rel_tol=1e-9)
    # Monotônico
    assert altitude_factor(2000) < altitude_factor(3000) < altitude_factor(4000)


def test_altitude_capped_at_25pct():
    """Cap em +25% (≈ 7750 m)."""
    f_extreme = altitude_factor(10000)
    assert math.isclose(f_extreme, 1.25, rel_tol=1e-9)
    f_extreme2 = altitude_factor(50000)
    assert math.isclose(f_extreme2, 1.25, rel_tol=1e-9)


# ===========================================================================
# Temperatura
# ===========================================================================
def test_temperature_20c_no_penalty():
    """A 20 °C com 0 min ociosos o fator é 1.0."""
    assert math.isclose(temperature_factor(20.0, 0, 100), 1.0, rel_tol=1e-9)


def test_temperature_30c_no_penalty():
    """Acima de 20 °C: nenhum fator de motor frio."""
    assert math.isclose(temperature_factor(30.0, 0, 100), 1.0, rel_tol=1e-9)


def test_temperature_0c_short_trip_max_penalty():
    """T=0, viagem muito curta (d=0): exp(0)=1, (20-0)/20=1 → fator = 2.0."""
    f = temperature_factor(0.0, 0, 0.0)
    assert math.isclose(f, 2.0, rel_tol=1e-9)


def test_temperature_minus_10c_short_trip_2x_plus_idle():
    """T=-10, viagem curta, ocioso: fator base ~ (1+30/20) = 2.5 + idle."""
    f = temperature_factor(-10.0, 0, 0.0)
    assert math.isclose(f, 1.0 + (20.0 - (-10.0)) / 20.0, rel_tol=1e-9)
    # Esperado: 1 + 1.5 = 2.5
    assert math.isclose(f, 2.5, rel_tol=1e-9)


def test_temperature_minus_10c_with_idle_adds_penalty():
    """T=-10 (já < 10), ocioso por 5 min: idle_penalty = 5*0.01 = 0.05."""
    f = temperature_factor(-10.0, 5.0, 100.0)
    # Base: 1 + 1.5*exp(-20) ≈ 1.0
    # Idle: +0.05
    assert math.isclose(f, 1.05, abs_tol=1e-3)


def test_temperature_cold_long_trip_decays_to_one():
    """T=0, viagem muito longa: exp(-100/5) ≈ 3.7e-9 → fator ≈ 1.0."""
    f = temperature_factor(0.0, 0, 100.0)
    assert math.isclose(f, 1.0, abs_tol=1e-3)


def test_temperature_cold_idle_capped_at_15pct():
    """Idle penalty satura em +15%."""
    f = temperature_factor(0.0, 100.0, 1000.0)  # muito idle, viagem muito longa
    # Base: 1 + 1*exp(-200) ≈ 1.0
    # Idle: min(0.15, 100*0.01=1.0) = 0.15
    assert math.isclose(f, 1.15, abs_tol=1e-3)


# ===========================================================================
# Umidade
# ===========================================================================
def test_humidity_at_60pct_is_neutral():
    """A 60% UR o fator é exatamente 1.0."""
    assert math.isclose(humidity_factor(60.0), 1.0, rel_tol=1e-9)


def test_humidity_dry_increases_factor():
    """0% UR → 1.012 (ar mais denso, combustão ligeiramente melhor)."""
    assert math.isclose(humidity_factor(0.0), 1.012, rel_tol=1e-9)


def test_humidity_wet_decreases_factor():
    """100% UR → 0.992."""
    assert math.isclose(humidity_factor(100.0), 0.992, rel_tol=1e-9)


def test_humidity_30pct():
    """30% UR → 1 + (60-30)*0.0002 = 1.006."""
    assert math.isclose(humidity_factor(30.0), 1.006, rel_tol=1e-9)


# ===========================================================================
# Condição da pista
# ===========================================================================
def test_road_condition_dry_neutral():
    assert road_condition_factor("dry") == 1.0


def test_road_condition_wet():
    assert road_condition_factor("wet") == 1.05


def test_road_condition_snow():
    assert road_condition_factor("snow") == 1.20


def test_road_condition_ice():
    assert road_condition_factor("ice") == 1.35


def test_road_condition_unknown_falls_back_neutral():
    """Valor desconhecido → 1.0 (fallback)."""
    assert road_condition_factor("mars") == 1.0


def test_road_condition_rolling_factors_dry():
    assert rolling_resistance_road_factor("dry") == 1.0


def test_road_condition_rolling_factors_wet():
    assert rolling_resistance_road_factor("wet") == 1.10


def test_road_condition_rolling_factors_snow():
    assert rolling_resistance_road_factor("snow") == 1.30


def test_road_condition_rolling_factors_ice():
    assert rolling_resistance_road_factor("ice") == 1.60


def test_road_condition_rolling_factor_ordering():
    """A resistência de rolamento cresce monotonicamente com a severidade."""
    assert (
        rolling_resistance_road_factor("dry")
        < rolling_resistance_road_factor("wet")
        < rolling_resistance_road_factor("snow")
        < rolling_resistance_road_factor("ice")
    )


# ===========================================================================
# Vento
# ===========================================================================
def test_effective_headwind_pure_headwind():
    """Vento de 0° (norte) com veículo indo para 0° = headwind puro."""
    assert math.isclose(effective_headwind_kmh(30.0, 0.0, 0.0), 30.0, rel_tol=1e-9)


def test_effective_headwind_zero_wind():
    """Vento zero → headwind efetivo zero."""
    assert effective_headwind_kmh(0.0, 0.0, 0.0) == 0.0


def test_effective_headwind_80kmh_headwind():
    """Vento de 80 km/h de frente → 80 km/h contra."""
    assert math.isclose(effective_headwind_kmh(80.0, 0.0, 0.0), 80.0, rel_tol=1e-9)


def test_effective_headwind_pure_tailwind():
    """Vento de 180° com veículo indo para 0° = tailwind puro (−30 km/h)."""
    assert math.isclose(effective_headwind_kmh(30.0, 180.0, 0.0), -30.0, rel_tol=1e-9)


def test_effective_headwind_80kmh_tailwind():
    """Vento de 80 km/h de trás → −80 km/h."""
    assert math.isclose(effective_headwind_kmh(80.0, 180.0, 0.0), -80.0, rel_tol=1e-9)


def test_effective_headwind_crosswind_is_zero():
    """Vento a 90° (leste) com veículo indo para 0° = crosswind (0)."""
    assert math.isclose(effective_headwind_kmh(30.0, 90.0, 0.0), 0.0, abs_tol=1e-9)


def test_effective_headwind_45_degrees():
    """Vento a 45°: headwind = v·cos(45°) ≈ 0.707·v."""
    assert math.isclose(
        effective_headwind_kmh(100.0, 45.0, 0.0),
        100.0 * math.cos(math.radians(45.0)),
        rel_tol=1e-9,
    )


# ===========================================================================
# Ar-condicionado
# ===========================================================================
def test_ac_off_no_effect():
    """AC desligado: (1.0, 0.0)."""
    factor, aux = ac_factor(False, 35.0, 100.0, 80.0)
    assert factor == 1.0
    assert aux == 0.0


def test_ac_hot_above_22c_adds_power_and_penalty():
    """T=35, AC on: aux > 1500 W e fator > 1.0."""
    factor, aux = ac_factor(True, 35.0, 100.0, 80.0)
    assert factor > 1.0
    assert aux > 1500.0
    # aux_w = 1500 + (35-22)*150 = 3450
    assert math.isclose(aux, 3450.0, rel_tol=1e-9)
    # factor = 1 + min(0.15, 0.01*(35-22)) = 1.13
    assert math.isclose(factor, 1.13, rel_tol=1e-9)


def test_ac_30c_civilized():
    """T=30, AC on: aux_w = 1500 + 8*150 = 2700; fator = 1.08."""
    factor, aux = ac_factor(True, 30.0, 100.0, 80.0)
    assert math.isclose(aux, 2700.0, rel_tol=1e-9)
    assert math.isclose(factor, 1.08, rel_tol=1e-9)


def test_ac_cold_below_10c():
    """T=5, AC on: 0 < 5 < 10 → aux_w = 1000 + 5*100 = 1500; fator = 1.025."""
    factor, aux = ac_factor(True, 5.0, 100.0, 80.0)
    assert math.isclose(aux, 1500.0, rel_tol=1e-9)
    assert math.isclose(factor, 1.025, rel_tol=1e-9)


def test_ac_freezing_is_mostly_ineffective():
    """T<0: AC só desumidifica → aux_w = 200, fator = 1.01."""
    factor, aux = ac_factor(True, -5.0, 100.0, 80.0)
    assert math.isclose(aux, 200.0, rel_tol=1e-9)
    assert math.isclose(factor, 1.01, rel_tol=1e-9)


def test_ac_moderate_temperature_neutral_band():
    """T entre 10 e 22: aux_w = 800, fator = 1.02."""
    factor, aux = ac_factor(True, 15.0, 100.0, 80.0)
    assert math.isclose(aux, 800.0, rel_tol=1e-9)
    assert math.isclose(factor, 1.02, rel_tol=1e-9)


def test_ac_low_speed_increases_aux_power():
    """Velocidade < 20 km/h aumenta aux_w em 5%."""
    _, aux_high = ac_factor(True, 30.0, 100.0, 80.0)
    _, aux_low = ac_factor(True, 30.0, 100.0, 10.0)
    assert math.isclose(aux_low, aux_high * 1.05, rel_tol=1e-9)


# ===========================================================================
# Carga / reboque
# ===========================================================================
def test_load_factor_small_load_is_neutral():
    """Até 200 kg extras: 1.0."""
    assert load_factor(1100.0, 100.0, 0.0) == 1.0


def test_load_factor_at_200kg_boundary_neutral():
    """Exatamente 200 kg: 1.0 (boundary)."""
    assert load_factor(1100.0, 200.0, 0.0) == 1.0


def test_load_factor_300kg_light_penalty():
    """300 kg: 0.5% por 100 kg acima de 200 → 1.005."""
    f = load_factor(1100.0, 300.0, 0.0)
    assert math.isclose(f, 1.005, rel_tol=1e-9)


def test_load_factor_heavy_load_increases():
    assert load_factor(1100.0, 600.0, 0.0) > 1.0


def test_load_factor_capped_at_5pct():
    """Carga absurda: cap em +5%."""
    f = load_factor(1100.0, 5000.0, 0.0)
    assert math.isclose(f, 1.05, rel_tol=1e-9)


def test_load_factor_towing_counts_too():
    """Towing também entra no cálculo."""
    f_passenger = load_factor(1100.0, 250.0, 0.0)
    f_towing = load_factor(1100.0, 0.0, 250.0)
    assert math.isclose(f_passenger, f_towing, rel_tol=1e-9)


def test_towing_aero_increment_zero_without_trailer():
    assert towing_aero_increment(0.0, "car") == 0.0
    assert towing_aero_increment(0.0, "motorcycle") == 0.0


def test_towing_aero_increment_grows_with_mass():
    a = towing_aero_increment(1000.0, "car")
    b = towing_aero_increment(3000.0, "car")
    assert b > a > 0


def test_towing_aero_increment_capped():
    """A partir de 3000 kg, satura em 0.5 m² (carro)."""
    a = towing_aero_increment(3000.0, "car")
    b = towing_aero_increment(10000.0, "car")
    assert math.isclose(a, 0.5, rel_tol=1e-9)
    assert math.isclose(b, 0.5, rel_tol=1e-9)


def test_towing_aero_motorcycle_smaller_than_car():
    a = towing_aero_increment(2000.0, "car")
    b = towing_aero_increment(2000.0, "motorcycle")
    assert a > b


# ===========================================================================
# Estilo de direção
# ===========================================================================
def test_driving_style_eco():
    assert driving_style_factor("eco") == 0.92


def test_driving_style_normal():
    assert driving_style_factor("normal") == 1.00


def test_driving_style_aggressive():
    assert driving_style_factor("aggressive") == 1.18


def test_driving_style_unknown_falls_back_normal():
    """Estilo desconhecido → 1.0 (fallback)."""
    assert driving_style_factor("racer") == 1.0


# ===========================================================================
# Pneu
# ===========================================================================
def test_tire_pressure_nominal_neutral():
    assert tire_pressure_factor(220.0) == 1.0


def test_tire_pressure_above_nominal_no_penalty():
    """Pneu mais cheio que o nominal → 1.0 (sem penalidade)."""
    assert tire_pressure_factor(250.0) == 1.0


def test_tire_pressure_underinflated_penalty():
    """Pneu murcho (180 kPa) gera penalidade."""
    f = tire_pressure_factor(180.0)
    assert math.isclose(f, 1.0 + 0.002 * 40, rel_tol=1e-9)  # 1.08


def test_tire_pressure_very_low_150kpa():
    """150 kPa: diff = 70 → 1.14."""
    f = tire_pressure_factor(150.0)
    assert math.isclose(f, 1.14, rel_tol=1e-9)


# ===========================================================================
# Qualidade do combustível
# ===========================================================================
def test_fuel_quality_regular():
    assert fuel_quality_factor("regular") == 1.0


def test_fuel_quality_premium_3pct_better():
    """Premium → 0.97 (3% mais eficiente)."""
    assert fuel_quality_factor("premium") == 0.97


def test_fuel_quality_unknown_falls_back_regular():
    assert fuel_quality_factor("biodiesel") == 1.0


# ===========================================================================
# Idade do veículo
# ===========================================================================
def test_vehicle_age_factor_new_car_neutral():
    assert vehicle_age_factor(2026) == 1.0


def test_vehicle_age_factor_future_year_neutral():
    """Ano futuro também é 1.0 (sem penalidade)."""
    assert vehicle_age_factor(2030) == 1.0


def test_vehicle_age_factor_10_years_old():
    """10 anos: 1 + 0.005*10 = 1.05."""
    f = vehicle_age_factor(2016)
    assert math.isclose(f, 1.05, rel_tol=1e-9)


def test_vehicle_age_factor_old_car_penalty_capped():
    """1950: 76 anos → satura em 1.20."""
    f = vehicle_age_factor(1950)
    assert math.isclose(f, 1.20, rel_tol=1e-9)


# ===========================================================================
# Transmissão
# ===========================================================================
def test_transmission_manual():
    assert transmission_factor("manual") == 1.00


def test_transmission_automatic_5pct_penalty():
    assert transmission_factor("automatic") == 1.05


def test_transmission_cvt_3pct_penalty():
    assert transmission_factor("cvt") == 1.03


def test_transmission_unknown_falls_back_manual():
    assert transmission_factor("dct") == 1.00


# ===========================================================================
# Ethanol / flex blend
# ===========================================================================
def test_ethanol_volume_factor_is_130pct():
    vf, cf = ethanol_blend_factor("ethanol", "regular")
    assert math.isclose(vf, 1.30, rel_tol=1e-9)
    assert math.isclose(cf, 0.65, rel_tol=1e-9)


def test_ethanol_premium_same_as_regular():
    """Para ethanol puro, regular e premium se comportam igual."""
    vf, cf = ethanol_blend_factor("ethanol", "premium")
    assert math.isclose(vf, 1.30, rel_tol=1e-9)
    assert math.isclose(cf, 0.65, rel_tol=1e-9)


def test_flex_premium_treats_as_ethanol():
    vf, cf = ethanol_blend_factor("flex", "premium")
    assert math.isclose(vf, 1.30, rel_tol=1e-9)
    assert math.isclose(cf, 0.65, rel_tol=1e-9)


def test_flex_regular_treats_as_gasoline():
    vf, cf = ethanol_blend_factor("flex", "regular")
    assert vf == 1.0
    assert cf == 1.0


def test_gasoline_premium_3pct_volume_bonus():
    vf, cf = ethanol_blend_factor("gasoline", "premium")
    assert math.isclose(vf, 0.97, rel_tol=1e-9)


def test_diesel_premium_1pct_volume_bonus():
    vf, cf = ethanol_blend_factor("diesel", "premium")
    assert math.isclose(vf, 0.99, rel_tol=1e-9)


def test_diesel_regular_neutral():
    vf, cf = ethanol_blend_factor("diesel", "regular")
    assert vf == 1.0
    assert cf == 1.0


# ===========================================================================
# Paradas (perfil de velocidade)
# ===========================================================================
def test_resolve_stops_per_km_explicit_overrides_profile():
    """Valor explícito positivo sobrescreve o perfil."""
    assert resolve_stops_per_km("urban", 0.5) == 0.5


def test_resolve_stops_per_km_explicit_zero_falls_back_to_profile():
    """Valor explícito 0 → usa perfil (não sobrescreve)."""
    assert resolve_stops_per_km("urban", 0.0) == 0.6


def test_resolve_stops_per_km_from_profile_urban():
    assert resolve_stops_per_km("urban", 0.0) == 0.6


def test_resolve_stops_per_km_from_profile_suburban():
    assert resolve_stops_per_km("suburban", 0.0) == 0.20


def test_resolve_stops_per_km_from_profile_mixed():
    assert resolve_stops_per_km("mixed", 0.0) == 0.15


def test_resolve_stops_per_km_from_profile_highway():
    assert resolve_stops_per_km("highway", 0.0) == 0.05


def test_resolve_stops_per_km_from_profile_constant():
    assert resolve_stops_per_km("constant", 0.0) == 0.0


def test_resolve_stops_per_km_unknown_profile_is_zero():
    """Perfil desconhecido → 0 paradas (fallback seguro)."""
    assert resolve_stops_per_km("underwater", 0.0) == 0.0
