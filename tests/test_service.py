"""Testes do serviço de cálculo (end-to-end da lógica).

Cada cenário valida a relação entre dois cálculos de combustível
(>) ou (> e <) sob variações controladas dos parâmetros
ambientais, de carga, de estilo e de veículo. As referências
numéricas foram obtidas executando o serviço e gravando o
resultado de referência.
"""
from __future__ import annotations

import math

import pytest

from app.fuel.schemas import (
    CalculationRequest,
    DriverSpec,
    EnvironmentSpec,
    LoadSpec,
    TripSpec,
    VehicleRequest,
)
from app.fuel.schemas import FuelType, Transmission, VehicleType
from app.fuel.service import FuelCalculationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _request(**overrides) -> CalculationRequest:
    """Constrói um CalculationRequest baseline de carro compacto.

    Cenário padrão: 100 km, 80 km/h, plano, gasolina, 20 °C, sem vento.
    Aceita overrides `model_copy` em qualquer subcampo.
    """
    base = CalculationRequest(
        vehicle=VehicleRequest(
            type=VehicleType.car,
            preset_id="car-compact-popular",
            category="hatch",
            empty_weight_kg=1100.0,
            engine_displacement_l=1.0,
            engine_power_kw=75.0,
            transmission=Transmission.manual,
            cylinders=3,
            drag_coefficient_cd=0.33,
            frontal_area_m2=2.10,
            rolling_resistance_coeff=0.010,
            tire_pressure_kpa=220.0,
            fuel_tank_capacity_l=44.0,
            fuel_type=FuelType.gasoline,
            year=2024,
        ),
        trip=TripSpec(
            distance_km=100.0,
            average_speed_kmh=80.0,
            speed_profile="constant",
            idle_time_min=0.0,
        ),
        environment=EnvironmentSpec(),
        load=LoadSpec(),
        driver=DriverSpec(),
    )
    if overrides:
        return base.model_copy(deep=True, update=overrides)
    return base


def _service() -> FuelCalculationService:
    return FuelCalculationService()


# ===========================================================================
# Cenário de referência
# ===========================================================================
def test_reference_value_within_5pct():
    """Cenário padrão: 100 km, 80 km/h, plano, gasolina, 20 °C.

    Referência calculada à mão (ver `tests/test_service.py` README):
        F_drag = 209.6 N
        F_roll = 115.2 N
        P_tract = 7218.6 W
        P_total (com aux 1500 W) = 8718.6 W
        ṁ = P / (η_eng · η_drv · LHV) = 0.0009769 kg/s
        volume = 0.0009769 / 0.745 = 0.001311 L/s
        para 100 km @ 80 km/h → 1.25 h → ≈ 5.90 L

    Aceita tolerância de ±5% no total de combustível (range 5.6 – 6.2 L).
    """
    service = _service()
    result = service.calculate(_request())
    assert 5.6 <= result.total_fuel_l <= 6.2, (
        f"Esperado ~5.9 L (±5%); obtido {result.total_fuel_l:.3f} L"
    )
    # Métricas derivadas consistentes
    assert math.isclose(
        result.fuel_per_km_l_per_100km,
        result.total_fuel_l / result.distance_km * 100,
        rel_tol=1e-3,
    )


# ===========================================================================
# Estilo de direção
# ===========================================================================
def test_eco_style_less_fuel_than_normal():
    """100 km flat, 80 km/h, 20 °C, no wind, no AC, dry, eco → LESS fuel."""
    service = _service()
    normal = service.calculate(_request())
    eco_req = _request()
    eco_req.driver = eco_req.driver.model_copy(update={"driving_style": "eco"})
    eco = service.calculate(eco_req)
    assert eco.total_fuel_l < normal.total_fuel_l
    # 8% menos (driving_style_factor = 0.92)
    assert math.isclose(eco.total_fuel_l, normal.total_fuel_l * 0.92, rel_tol=1e-3)


def test_aggressive_style_more_fuel_than_normal():
    """100 km flat, 80 km/h, 20 °C, no wind, no AC, dry, aggressive → MORE fuel."""
    service = _service()
    normal = service.calculate(_request())
    agg_req = _request()
    agg_req.driver = agg_req.driver.model_copy(
        update={"driving_style": "aggressive"}
    )
    agg = service.calculate(agg_req)
    assert agg.total_fuel_l > normal.total_fuel_l
    # 18% mais
    assert math.isclose(agg.total_fuel_l, normal.total_fuel_l * 1.18, rel_tol=1e-3)


def test_driving_style_aggressive_includes_warning_factor():
    """O fator `driving_style` aparece com valor 1.18."""
    service = _service()
    agg = _request()
    agg.driver = agg.driver.model_copy(update={"driving_style": "aggressive"})
    result = service.calculate(agg)
    factor_style = next(f for f in result.factors if f.name == "driving_style")
    assert math.isclose(factor_style.factor, 1.18, rel_tol=1e-9)


# ===========================================================================
# Temperatura / cold start
# ===========================================================================
def test_cold_100km_more_fuel_than_warm():
    """100 km flat, 80 km/h, 0 °C → MORE fuel que 20 °C (cold start penalty)."""
    service = _service()
    warm = service.calculate(_request())
    cold = _request()
    cold.environment = cold.environment.model_copy(update={"temperature_c": 0.0})
    cold_result = service.calculate(cold)
    assert cold_result.total_fuel_l > warm.total_fuel_l
    # Diferença de ~4% (temperature_factor a 100 km ≈ 1.04)
    assert 1.02 < cold_result.total_fuel_l / warm.total_fuel_l < 1.10


def test_cold_short_trip_penalty_is_stronger():
    """Viagem curta no frio amplifica o efeito (motor não aquece)."""
    service = _service()
    warm_short = _request()
    warm_short.trip = warm_short.trip.model_copy(update={"distance_km": 5.0})
    warm = service.calculate(warm_short)

    cold_short = _request()
    cold_short.trip = cold_short.trip.model_copy(update={"distance_km": 5.0})
    cold_short.environment = cold_short.environment.model_copy(
        update={"temperature_c": 0.0}
    )
    cold = service.calculate(cold_short)
    # Em 5 km o fator é ~1.37, em 100 km é ~1.04
    assert cold.total_fuel_l / warm.total_fuel_l > 1.30


def test_hot_30c_no_cold_start_penalty():
    """T=30 °C: ar menos denso que a 20 °C, então arrasto é menor → menos combustível.

    O importante: o fator de cold start (que cresce abaixo de 20 °C) não se aplica
    a 30 °C — a temperatura está acima do limiar de 20 °C.
    """
    service = _service()
    normal = service.calculate(_request())
    hot = _request()
    hot.environment = hot.environment.model_copy(update={"temperature_c": 30.0})
    hot_result = service.calculate(hot)
    # 30 °C: ar ~3% menos denso que a 20 °C → arrasto menor → ~2% menos combustível
    assert hot_result.total_fuel_l < normal.total_fuel_l
    # Fator de temperatura reportado é 1.0 (sem cold start penalty)
    factor_temp = next(f for f in hot_result.factors if f.name == "temperature")
    assert math.isclose(factor_temp.factor, 1.0, rel_tol=1e-9)


# ===========================================================================
# Vento
# ===========================================================================
def test_headwind_50kmh_more_fuel():
    """100 km flat, 80 km/h, headwind 50 km/h → MORE fuel que sem vento."""
    service = _service()
    no_wind = service.calculate(_request())
    head = _request()
    head.environment = head.environment.model_copy(
        update={"wind_speed_kmh": 50.0, "wind_direction_deg": 0.0}
    )
    head_result = service.calculate(head)
    assert head_result.total_fuel_l > no_wind.total_fuel_l
    # Speed sobe 50/3.6 = 13.9 m/s, drag scales v² → significativamente mais
    assert head_result.total_fuel_l > no_wind.total_fuel_l * 1.5


def test_tailwind_30kmh_less_fuel():
    """Tailwind 30 km/h → LESS fuel que sem vento."""
    service = _service()
    no_wind = service.calculate(_request())
    tail = _request()
    tail.environment = tail.environment.model_copy(
        update={"wind_speed_kmh": 30.0, "wind_direction_deg": 180.0}
    )
    tail_result = service.calculate(tail)
    assert tail_result.total_fuel_l < no_wind.total_fuel_l


def test_crosswind_30kmh_neutral():
    """Vento a 90° não muda a velocidade efetiva."""
    service = _service()
    no_wind = service.calculate(_request())
    cross = _request()
    cross.environment = cross.environment.model_copy(
        update={"wind_speed_kmh": 30.0, "wind_direction_deg": 90.0}
    )
    cross_result = service.calculate(cross)
    # Crosswind: headwind efetivo = 0 → fuel igual a sem vento
    assert math.isclose(cross_result.total_fuel_l, no_wind.total_fuel_l, rel_tol=1e-3)


# ===========================================================================
# Altitude
# ===========================================================================
def test_altitude_3000m_less_fuel_than_sea_level():
    """100 km flat, 80 km/h, 20 °C, altitude 3000 m → LESS fuel.

    O ar rarefeito reduz o arrasto aerodinâmico (que escala com ρ);
    o fator de altitude de combustão é +6% (3 km acima de 1500 m),
    mas o efeito no arrasto é dominante.
    """
    service = _service()
    sea_level = service.calculate(_request())
    high = _request()
    high.environment = high.environment.model_copy(update={"altitude_m": 3000.0})
    high_result = service.calculate(high)
    assert high_result.total_fuel_l < sea_level.total_fuel_l
    # ~11% menos
    assert 0.85 < high_result.total_fuel_l / sea_level.total_fuel_l < 0.95


def test_altitude_3000m_altitude_factor_is_above_one():
    """Fator de altitude > 1.0 em altitudes > 1500 m."""
    service = _service()
    high = _request()
    high.environment = high.environment.model_copy(update={"altitude_m": 3000.0})
    result = service.calculate(high)
    factor_alt = next(f for f in result.factors if f.name == "altitude")
    assert math.isclose(factor_alt.factor, 1.06, rel_tol=1e-9)


def test_altitude_does_not_break_drivability_for_test_vehicle():
    """A 3000 m o veículo ainda completa a viagem (sem erro de cálculo)."""
    service = _service()
    high = _request()
    high.environment = high.environment.model_copy(update={"altitude_m": 3000.0})
    high.trip = high.trip.model_copy(update={"distance_km": 50.0})
    result = service.calculate(high)
    # Sanidade: não explode, retorna combustível positivo
    assert result.total_fuel_l > 0.0
    assert result.total_fuel_l < 10.0  # faixa razoável para 50 km


# ===========================================================================
# Aclive / declive
# ===========================================================================
def test_uphill_5pct_more_fuel_than_flat():
    """100 km uphill 5% → MORE fuel que flat."""
    service = _service()
    flat = service.calculate(_request())
    up = _request()
    up.trip = up.trip.model_copy(
        update={
            "elevation_profile": [
                {"distance_km": 0, "elevation_m": 0},
                {"distance_km": 50, "elevation_m": 250},
                {"distance_km": 100, "elevation_m": 500},
            ]
        }
    )
    up_result = service.calculate(up)
    assert up_result.total_fuel_l > flat.total_fuel_l
    # +500 m em 100 km = +5% médio, mais arrasto, deve ser ~10-20% mais
    assert 1.05 < up_result.total_fuel_l / flat.total_fuel_l < 1.30


def test_downhill_5pct_less_fuel_than_flat():
    """100 km downhill 5% → LESS fuel (engine idles, sem tração)."""
    service = _service()
    flat = service.calculate(_request())
    down = _request()
    down.trip = down.trip.model_copy(
        update={
            "elevation_profile": [
                {"distance_km": 0, "elevation_m": 500},
                {"distance_km": 50, "elevation_m": 250},
                {"distance_km": 100, "elevation_m": 0},
            ]
        }
    )
    down_result = service.calculate(down)
    assert down_result.total_fuel_l < flat.total_fuel_l
    # Combustível ainda positivo (motor continua funcionando)
    assert down_result.total_fuel_l > 0.0


def test_downhill_no_negative_fuel():
    """O serviço clamp-a em zero: nenhuma resposta com fuel negativo."""
    service = _service()
    # Descida extrema: 30% de perda
    steep = _request()
    steep.trip = steep.trip.model_copy(
        update={
            "elevation_profile": [
                {"distance_km": 0, "elevation_m": 3000},
                {"distance_km": 100, "elevation_m": 0},
            ]
        }
    )
    result = service.calculate(steep)
    assert result.total_fuel_l > 0.0
    # Muito menos que plano
    assert result.total_fuel_l < 2.0


# ===========================================================================
# Carro vs moto
# ===========================================================================
def test_motorcycle_uses_less_fuel_in_litres_than_car():
    """Carro compacto vs moto naked 300: moto usa menos em litros totais."""
    service = _service()
    car = service.calculate(_request())
    moto_req = _request()
    moto_req.vehicle = VehicleRequest(
        type=VehicleType.motorcycle, preset_id="moto-naked-300",
    )
    moto = service.calculate(moto_req)
    # Moto: ~2.2 L, carro: ~5.9 L
    assert moto.total_fuel_l < car.total_fuel_l
    # Menos da metade
    assert moto.total_fuel_l < car.total_fuel_l * 0.5


def test_motorcycle_l_per_100km_better_than_car():
    """Moto naked 300: L/100km muito menor que o carro compacto."""
    service = _service()
    car = service.calculate(_request())
    moto_req = _request()
    moto_req.vehicle = VehicleRequest(
        type=VehicleType.motorcycle, preset_id="moto-naked-300",
    )
    moto = service.calculate(moto_req)
    # Moto: ~2.2 L/100km, carro: ~5.9 L/100km
    assert moto.fuel_per_km_l_per_100km < car.fuel_per_km_l_per_100km


# ===========================================================================
# Ar-condicionado
# ===========================================================================
def test_ac_at_30c_more_fuel():
    """AC a 30 °C → MORE fuel que sem AC."""
    service = _service()
    no_ac = service.calculate(_request())
    ac_req = _request()
    ac_req.driver = ac_req.driver.model_copy(update={"use_ac": True})
    ac_req.environment = ac_req.environment.model_copy(update={"temperature_c": 30.0})
    ac_result = service.calculate(ac_req)
    assert ac_result.total_fuel_l > no_ac.total_fuel_l
    # +2-3 L em 100 km (AC adiciona ~2000-3000 W de aux)
    assert 1.20 < ac_result.total_fuel_l / no_ac.total_fuel_l < 1.50


def test_ac_at_0c_emits_warning():
    """AC ligado a 0 °C gera warning de uso ineficiente."""
    service = _service()
    req = _request()
    req.driver = req.driver.model_copy(update={"use_ac": True})
    req.environment = req.environment.model_copy(update={"temperature_c": -2.0})
    result = service.calculate(req)
    assert any("condicionado" in w.lower() for w in result.warnings)


# ===========================================================================
# Custo
# ===========================================================================
def test_fuel_cost_returned_when_price_set():
    """fuel_price_brl_per_l set → fuel_cost_brl retornado."""
    service = _service()
    req = _request()
    req.driver = req.driver.model_copy(update={"fuel_price_brl_per_l": 6.0})
    result = service.calculate(req)
    assert result.fuel_cost_brl is not None
    assert math.isclose(
        result.fuel_cost_brl, result.total_fuel_l * 6.0, rel_tol=1e-3
    )


def test_fuel_cost_none_when_price_not_set():
    """Sem fuel_price_brl_per_l → fuel_cost_brl = None."""
    service = _service()
    result = service.calculate(_request())
    assert result.fuel_cost_brl is None


def test_fuel_cost_scales_linearly_with_price():
    """fuel_cost_brl é proporcional ao preço por litro."""
    service = _service()
    req = _request()
    req_5 = req.model_copy(deep=True)
    req_5.driver = req_5.driver.model_copy(update={"fuel_price_brl_per_l": 5.0})
    req_8 = req.model_copy(deep=True)
    req_8.driver = req_8.driver.model_copy(update={"fuel_price_brl_per_l": 8.0})
    r5 = service.calculate(req_5)
    r8 = service.calculate(req_8)
    assert math.isclose(r8.fuel_cost_brl, r5.fuel_cost_brl * 8.0 / 5.0, rel_tol=1e-3)


# ===========================================================================
# Combustível flex
# ===========================================================================
def test_flex_ethanol_increases_volume_but_reduces_co2():
    service = _service()
    req = _request()
    req.vehicle = req.vehicle.model_copy(update={"fuel_type": FuelType.flex})
    req.driver = req.driver.model_copy(update={"fuel_quality": "premium"})
    result = service.calculate(req)
    # Volume deve ser ~30% maior
    assert result.total_fuel_l > 7.0
    # CO₂ deve ser menor
    assert result.co2_kg < 17.0


# ===========================================================================
# Carga
# ===========================================================================
def test_load_increases_consumption():
    service = _service()
    no_load = service.calculate(_request())
    loaded = _request()
    loaded.load = loaded.load.model_copy(
        update={"cargo_weight_kg": 400.0, "passenger_count": 4}
    )
    loaded_calc = service.calculate(loaded)
    assert loaded_calc.total_fuel_l > no_load.total_fuel_l


# ===========================================================================
# Aclive (legado)
# ===========================================================================
def test_grade_increases_consumption():
    service = _service()
    flat = service.calculate(_request())
    hilly = _request()
    hilly.trip = hilly.trip.model_copy(
        update={
            "elevation_profile": [
                {"distance_km": 0, "elevation_m": 0},
                {"distance_km": 50, "elevation_m": 500},  # +500 m em 50 km
                {"distance_km": 100, "elevation_m": 500},
            ]
        }
    )
    hilly_result = service.calculate(hilly)
    assert hilly_result.total_fuel_l > flat.total_fuel_l


# ===========================================================================
# Avisos
# ===========================================================================
def test_warnings_for_low_tire_pressure():
    service = _service()
    req = _request()
    req.vehicle = req.vehicle.model_copy(update={"tire_pressure_kpa": 150.0})
    result = service.calculate(req)
    assert any("pneu" in w.lower() for w in result.warnings)


def test_warnings_for_tank_overflow():
    service = _service()
    req = _request()
    req.trip = req.trip.model_copy(update={"distance_km": 1000.0})
    req.vehicle = req.vehicle.model_copy(update={"fuel_tank_capacity_l": 20.0})
    result = service.calculate(req)
    assert any(
        "tanque" in w.lower() or "reabastecimento" in w.lower()
        for w in result.warnings
    )


def test_warnings_for_towing():
    service = _service()
    req = _request()
    req.load = req.load.model_copy(update={"towing_kg": 1500.0})
    result = service.calculate(req)
    assert any("reboc" in w.lower() for w in result.warnings)


# ===========================================================================
# Erros e bordas
# ===========================================================================
def test_unknown_preset_raises_not_found():
    from app.errors import NotFoundError
    service = _service()
    req = _request()
    req.vehicle = req.vehicle.model_copy(update={"preset_id": "no-such-preset"})
    with pytest.raises(NotFoundError):
        service.calculate(req)


def test_batch_respects_limit():
    from app.config import get_settings
    from app.errors import PayloadTooLargeError
    service = _service()
    limit = get_settings().batch_size_limit
    with pytest.raises(PayloadTooLargeError):
        service.calculate_batch([_request()] * (limit + 1))


def test_batch_returns_one_per_request_in_order():
    service = _service()
    results = service.calculate_batch([_request(), _request(), _request()])
    assert len(results) == 3
    for r in results:
        assert r.total_fuel_l > 0


def test_batch_at_limit_succeeds():
    """Batch exatamente no limite (100) deve passar."""
    from app.config import get_settings
    service = _service()
    limit = get_settings().batch_size_limit
    results = service.calculate_batch([_request()] * limit)
    assert len(results) == limit


# ===========================================================================
# Fatores retornados
# ===========================================================================
def test_factors_include_all_corrections():
    """Todos os 13 fatores são retornados no cenário default."""
    service = _service()
    result = service.calculate(_request())
    names = {f.name for f in result.factors}
    expected = {
        "altitude", "temperature", "humidity", "road_condition",
        "driving_style", "fuel_quality", "vehicle_age", "transmission",
        "tire_pressure", "load", "ethanol_blend_volume", "ethanol_blend_co2",
    }
    # Pode ou não ter "ac" (sem AC)
    assert expected.issubset(names)


def test_response_includes_request_metadata():
    """A resposta carrega identificação do veículo e contexto."""
    service = _service()
    result = service.calculate(_request())
    assert result.vehicle_label == "car-compact-popular"
    assert result.fuel_type == FuelType.gasoline
    assert result.distance_km == 100.0
    assert result.average_speed_kmh == 80.0
    assert result.total_mass_kg > 0
    assert result.air_density_kg_per_m3 > 0
    assert result.effective_headwind_kmh == 0.0


# ===========================================================================
# Idling
# ===========================================================================
def test_idling_fuel_increases_with_idle_time():
    """Maior tempo ocioso → mais combustível total."""
    service = _service()
    no_idle = service.calculate(_request())
    req_idle = _request()
    req_idle.trip = req_idle.trip.model_copy(update={"idle_time_min": 30.0})
    with_idle = service.calculate(req_idle)
    # 30 min × 0.6 L/h = 0.3 L extras
    assert with_idle.total_fuel_l > no_idle.total_fuel_l
    assert math.isclose(
        with_idle.total_fuel_l - no_idle.total_fuel_l,
        0.3,
        rel_tol=0.15,  # tolerância: idle penalty de T<10 não se aplica a 20°C
    )
