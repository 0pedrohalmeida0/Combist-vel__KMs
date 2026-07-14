"""Testes unitários das funções puras de física.

Cobre:
- Densidade do ar (T, altitude, umidade).
- Forças resistivas (aerodinâmica, rolamento, aclive, inércia).
- Potência de tração, vazão mássica e volumétrica de combustível.
- Propriedades dos combustíveis (LHV, densidade, CO₂).
- Conversão de aclive e perfil de velocidade.

Todos os valores esperados são calculados à mão a partir das
equações no `physics.py` — a suíte funciona como uma verificação
numérica da implementação.
"""
from __future__ import annotations

import math

import pytest

from app.fuel.physics import (
    FUEL_PROPERTIES,
    G,
    acceleration_force,
    aero_drag_force,
    air_density,
    climbing_force,
    fuel_flow_kg_per_s,
    fuel_flow_l_per_s,
    fuel_properties,
    grade_from_elevation,
    idle_fuel_flow_l_per_s,
    rolling_resistance_force,
    tractive_power,
)


# ---------------------------------------------------------------------------
# Atmosfera / densidade do ar
# ---------------------------------------------------------------------------
def test_air_density_at_sea_level_15c_dry():
    # 15 °C, 0 m, 0% UR → aproximadamente 1.225 kg/m³
    rho = air_density(temperature_c=15.0, altitude_m=0.0, humidity_pct=0.0)
    assert 1.20 < rho < 1.25


def test_air_density_at_sea_level_20c_60pct():
    """Condições padrão de referência ISO (~1.204 kg/m³)."""
    rho = air_density(temperature_c=20.0, altitude_m=0.0, humidity_pct=60.0)
    assert 1.18 < rho < 1.22


def test_air_density_decreases_with_altitude():
    """0 m vs 2000 m: a 2000 m a densidade cai ~20%."""
    rho0 = air_density(15.0, 0.0, 0.0)
    rho2000 = air_density(15.0, 2000.0, 0.0)
    assert rho2000 < rho0
    assert rho0 / rho2000 > 1.15
    # Faixa esperada: ~0.98-1.05 kg/m³ a 2000 m
    assert 0.95 < rho2000 < 1.10


def test_air_density_at_5000m_is_about_half():
    """No topo de montanha: densidade cai a quase metade do nível do mar."""
    rho0 = air_density(15.0, 0.0, 0.0)
    rho5000 = air_density(15.0, 5000.0, 0.0)
    assert rho5000 < rho0 / 1.55
    assert rho5000 < 0.80


def test_air_density_increases_when_temperature_drops():
    """Ar frio é mais denso: a 0 °C a densidade é ~7% maior que a 20 °C."""
    rho_warm = air_density(20.0, 0.0, 0.0)
    rho_cold = air_density(0.0, 0.0, 0.0)
    assert rho_cold > rho_warm
    # Razão esperada ~ (293/273) ≈ 1.073
    assert 1.05 < rho_cold / rho_warm < 1.10


def test_air_density_humidity_makes_air_lighter():
    """Vapor d'água (M=18) é mais leve que N₂/O₂ (M≈29), então ar úmido é menos denso."""
    rho_dry = air_density(20.0, 0.0, humidity_pct=0.0)
    rho_wet = air_density(20.0, 0.0, humidity_pct=100.0)
    assert rho_wet < rho_dry
    # Diferença pequena: ~1-2%
    assert (rho_dry - rho_wet) / rho_dry < 0.02


def test_air_density_humidity_nudges_only_slightly():
    """A 60% UR e 100% UR a diferença é desprezível (1-2%)."""
    rho60 = air_density(20.0, 0.0, humidity_pct=60.0)
    rho100 = air_density(20.0, 0.0, humidity_pct=100.0)
    assert abs(rho60 - rho100) / rho60 < 0.02


# ---------------------------------------------------------------------------
# Arrasto aerodinâmico
# ---------------------------------------------------------------------------
def test_aero_drag_zero_at_zero_speed():
    assert aero_drag_force(0.33, 2.10, 1.225, 0.0) == 0.0


def test_aero_drag_50kmh():
    # v = 50/3.6 = 13.888 m/s
    v = 50.0 / 3.6
    f = aero_drag_force(0.33, 2.10, 1.225, v)
    # Esperado = 0.5 * 1.225 * 0.33 * 2.10 * 13.888^2 ≈ 81.88 N
    assert 80.0 < f < 84.0


def test_aero_drag_120kmh():
    v = 120.0 / 3.6
    f = aero_drag_force(0.33, 2.10, 1.225, v)
    # Esperado = 0.5 * 1.225 * 0.33 * 2.10 * 33.33^2 ≈ 471.6 N
    assert 465.0 < f < 480.0


def test_aero_drag_scales_with_cd_and_area():
    base = aero_drag_force(0.30, 2.0, 1.225, 20.0)
    scaled = aero_drag_force(0.60, 2.0, 1.225, 20.0)
    assert math.isclose(scaled, 2 * base, rel_tol=1e-9)


def test_aero_drag_scales_with_speed_squared_25_50_100():
    """Testa a relação F ∝ v² em 25, 50 e 100 km/h.

    Esperado: F(50) / F(25) ≈ 4 e F(100) / F(50) ≈ 4.
    """
    v25 = 25.0 / 3.6
    v50 = 50.0 / 3.6
    v100 = 100.0 / 3.6
    cd, area, rho = 0.30, 2.10, 1.225

    f25 = aero_drag_force(cd, area, rho, v25)
    f50 = aero_drag_force(cd, area, rho, v50)
    f100 = aero_drag_force(cd, area, rho, v100)

    # F(50) ≈ 4 · F(25)
    assert math.isclose(f50 / f25, 4.0, rel_tol=1e-9)
    # F(100) ≈ 4 · F(50)
    assert math.isclose(f100 / f50, 4.0, rel_tol=1e-9)
    # F(100) ≈ 16 · F(25)
    assert math.isclose(f100 / f25, 16.0, rel_tol=1e-9)

    # Sanity numérico dos valores absolutos
    assert 18.0 < f25 < 19.5    # ~18.6 N
    assert 73.0 < f50 < 76.0    # ~74.4 N
    assert 296.0 < f100 < 300.0 # ~297.6 N


def test_aero_drag_scales_with_air_density():
    """Densidade do ar entra linearmente no arrasto."""
    base = aero_drag_force(0.33, 2.10, 1.0, 20.0)
    doubled = aero_drag_force(0.33, 2.10, 2.0, 20.0)
    assert math.isclose(doubled, 2 * base, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Resistência de rolamento
# ---------------------------------------------------------------------------
def test_rolling_resistance_flat():
    # Crr=0.01, m=1100, plano
    f = rolling_resistance_force(0.010, 1100.0, 0.0)
    # 0.01 * 1100 * 9.80665 = 107.87 N
    assert math.isclose(f, 0.010 * 1100.0 * G, rel_tol=1e-9)


def test_rolling_resistance_5pct_grade():
    grade = math.atan(0.05)
    f = rolling_resistance_force(0.010, 1100.0, grade)
    expected = 0.010 * 1100.0 * G * math.cos(grade)
    assert math.isclose(f, expected, rel_tol=1e-9)
    # Em 5% a componente cos reduz ~0.12%
    flat = rolling_resistance_force(0.010, 1100.0, 0.0)
    assert f < flat


def test_rolling_resistance_scales_linearly_with_mass():
    """F_r = Crr · m · g · cos(θ) — relação linear com a massa."""
    crr = 0.010
    grade = math.atan(0.05)
    f1 = rolling_resistance_force(crr, 1000.0, grade)
    f2 = rolling_resistance_force(crr, 2000.0, grade)
    f3 = rolling_resistance_force(crr, 1500.0, grade)
    # Linear com m
    assert math.isclose(f2, 2 * f1, rel_tol=1e-9)
    assert math.isclose(f3, 1.5 * f1, rel_tol=1e-9)


def test_rolling_resistance_zero_mass_is_zero():
    assert rolling_resistance_force(0.010, 0.0, 0.0) == 0.0


# ---------------------------------------------------------------------------
# Força de aclive / inércia
# ---------------------------------------------------------------------------
def test_climbing_force_flat_is_zero():
    assert climbing_force(1100.0, 0.0) == 0.0


def test_climbing_force_5pct_grade():
    grade = math.atan(0.05)
    f = climbing_force(1100.0, grade)
    # m · g · sin(θ) = 1100 * 9.80665 * 0.0499 ≈ 538 N
    assert 530.0 < f < 550.0


def test_climbing_force_zero_pct_grade():
    assert climbing_force(1500.0, math.atan(0.0)) == 0.0


def test_climbing_force_5pct_grade_exact():
    """Compara com a expressão exata m·g·sin(θ)."""
    mass = 1500.0
    grade = math.atan(0.05)
    f = climbing_force(mass, grade)
    expected = mass * G * math.sin(grade)
    assert math.isclose(f, expected, rel_tol=1e-9)


def test_climbing_force_10pct_grade():
    """10% de inclinação: F_c = m·g·sin(atan(0.10)) ≈ 0.0995·m·g."""
    mass = 1200.0
    grade = math.atan(0.10)
    f = climbing_force(mass, grade)
    expected = mass * G * math.sin(grade)
    assert math.isclose(f, expected, rel_tol=1e-9)
    # ~1173 N para 1200 kg
    assert 1160.0 < f < 1180.0


def test_climbing_force_scales_linearly_with_mass():
    """F_c = m·g·sin(θ) — relação linear com a massa."""
    grade = math.atan(0.05)
    f1 = climbing_force(1000.0, grade)
    f2 = climbing_force(2000.0, grade)
    assert math.isclose(f2, 2 * f1, rel_tol=1e-9)


def test_acceleration_force_proportional_to_mass():
    f1 = acceleration_force(1000.0, 1.5)
    f2 = acceleration_force(2000.0, 1.5)
    assert math.isclose(f2, 2 * f1, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Potência e combustível
# ---------------------------------------------------------------------------
def test_tractive_power_zero_when_no_force():
    assert tractive_power(0.0, 20.0) == 0.0


def test_tractive_power_force_times_speed():
    f, v = 300.0, 20.0
    assert math.isclose(tractive_power(f, v), f * v, rel_tol=1e-9)


def test_fuel_flow_kg_per_s_zero_with_zero_power():
    assert fuel_flow_kg_per_s(0.0, 0.25, 0.85, 42.0) == 0.0


def test_fuel_flow_kg_per_s_proportional_to_power():
    a = fuel_flow_kg_per_s(10_000.0, 0.25, 0.85, 42.0)
    b = fuel_flow_kg_per_s(20_000.0, 0.25, 0.85, 42.0)
    assert math.isclose(b, 2 * a, rel_tol=1e-9)


def test_fuel_flow_zero_with_invalid_inputs():
    """LHV ≤ 0, η_eng ≤ 0, η_drv ≤ 0 → vazão 0 (sem explosão)."""
    assert fuel_flow_kg_per_s(10_000.0, 0.25, 0.85, 0.0) == 0.0
    assert fuel_flow_kg_per_s(10_000.0, 0.0, 0.85, 42.0) == 0.0
    assert fuel_flow_kg_per_s(10_000.0, 0.25, 0.0, 42.0) == 0.0
    assert fuel_flow_kg_per_s(10_000.0, 0.25, 0.85, -1.0) == 0.0


def test_fuel_flow_l_per_s_matches_kg_per_s_over_density():
    power = 10_000.0
    kg_s = fuel_flow_kg_per_s(power, 0.25, 0.85, 42.0)
    l_s = fuel_flow_l_per_s(power, 0.25, 0.85, 42.0, 0.745)
    assert math.isclose(l_s, kg_s / 0.745, rel_tol=1e-9)


def test_fuel_flow_l_per_s_zero_with_zero_density():
    """Densidade ≤ 0 → vazão volumétrica 0."""
    assert fuel_flow_l_per_s(10_000.0, 0.25, 0.85, 42.0, 0.0) == 0.0


def test_idle_fuel_flow_l_per_s():
    # 0.6 L/h = 0.6 / 3600 L/s
    assert math.isclose(idle_fuel_flow_l_per_s(0.6), 0.6 / 3600.0, rel_tol=1e-9)


def test_idle_fuel_flow_scales_linearly_with_l_per_h():
    """Vazão em marcha lenta é linear com a vazão horária nominal."""
    a = idle_fuel_flow_l_per_s(0.4)
    b = idle_fuel_flow_l_per_s(0.8)
    c = idle_fuel_flow_l_per_s(1.2)
    assert math.isclose(b, 2 * a, rel_tol=1e-9)
    assert math.isclose(c, 3 * a, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Propriedades dos combustíveis
# ---------------------------------------------------------------------------
def test_fuel_properties_for_each_fuel():
    for ft in ("gasoline", "ethanol", "diesel", "flex"):
        props = fuel_properties(ft)
        assert props.density_kg_l > 0
        assert props.lhv_mj_kg > 0
        assert props.co2_kg_per_kg > 0


def test_fuel_properties_unknown_falls_back_to_gasoline():
    """Tipo desconhecido → fallback seguro para gasolina."""
    props = fuel_properties("nuclear")
    expected = fuel_properties("gasoline")
    assert props == expected


def test_fuel_properties_empty_falls_back_to_gasoline():
    """String vazia → fallback gasolina."""
    props = fuel_properties("")
    expected = fuel_properties("gasoline")
    assert props == expected


def test_lhv_values_match_table():
    """LHV por combustível: gasolina 42, etanol 27, diesel 43 MJ/kg."""
    assert fuel_properties("gasoline").lhv_mj_kg == 42.0
    assert fuel_properties("ethanol").lhv_mj_kg == 27.0
    assert fuel_properties("diesel").lhv_mj_kg == 43.0


def test_ethanol_has_less_energy_per_litre_than_gasoline():
    """Energia por litro = densidade × LHV. Etanol (0.789 × 27 = 21.3 MJ/L)
    é menor que gasolina (0.745 × 42 = 31.3 MJ/L)."""
    e_gas = fuel_properties("gasoline").density_kg_l * fuel_properties("gasoline").lhv_mj_kg
    e_eth = fuel_properties("ethanol").density_kg_l * fuel_properties("ethanol").lhv_mj_kg
    e_die = fuel_properties("diesel").density_kg_l * fuel_properties("diesel").lhv_mj_kg
    assert e_eth < e_gas
    assert e_die > e_gas > e_eth


def test_ethanol_needs_more_volume_per_mj_than_gasoline():
    """Para uma mesma energia (1 MJ):
       V_gas = 1 / (0.745 × 42) = 0.03197 L
       V_eth = 1 / (0.789 × 27) = 0.04692 L → ~47% a mais."""
    rho_g, lhv_g = fuel_properties("gasoline").density_kg_l, fuel_properties("gasoline").lhv_mj_kg
    rho_e, lhv_e = fuel_properties("ethanol").density_kg_l, fuel_properties("ethanol").lhv_mj_kg
    v_gas_per_mj = 1.0 / (rho_g * lhv_g)
    v_eth_per_mj = 1.0 / (rho_e * lhv_e)
    assert v_eth_per_mj > v_gas_per_mj
    # Etanol precisa de ~1.47× mais volume
    assert 1.40 < v_eth_per_mj / v_gas_per_mj < 1.55


# ---------------------------------------------------------------------------
# Conversão de aclive
# ---------------------------------------------------------------------------
def test_grade_from_elevation_zero_distance():
    assert grade_from_elevation(0.0, 5.0) == 0.0


def test_grade_from_elevation_5pct():
    g = grade_from_elevation(100.0, 5.0)
    assert math.isclose(g, math.atan(0.05), rel_tol=1e-9)


def test_grade_from_elevation_capped_at_30pct():
    g = grade_from_elevation(100.0, 50.0)
    assert math.isclose(g, math.atan(0.30), rel_tol=1e-9)


def test_grade_from_elevation_negative_capped():
    """Aclives negativos também saturam em -30%."""
    g = grade_from_elevation(100.0, -50.0)
    assert math.isclose(g, math.atan(-0.30), rel_tol=1e-9)


def test_grade_from_elevation_3pct():
    g = grade_from_elevation(100.0, 3.0)
    assert math.isclose(g, math.atan(0.03), rel_tol=1e-9)
