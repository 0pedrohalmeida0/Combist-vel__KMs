"""Testes de integração end-to-end via httpx.AsyncClient.

Diferente de `test_routes.py` (que usa `TestClient` síncrono do FastAPI),
este arquivo sobe a aplicação de verdade via `httpx.AsyncClient`
apontando para o `app` ASGI, exercitando o stack completo
ASGI + middlewares.
"""
from __future__ import annotations

import math

import httpx
import pytest

from app.main import app


@pytest.fixture()
async def async_client():
    """httpx.AsyncClient apontando para o app ASGI."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client


# ===========================================================================
# Fluxos end-to-end
# ===========================================================================
async def test_list_presets_pick_one_calculate(async_client):
    """Lista presets → escolhe um → calcula → sanity-check."""
    r = await async_client.get("/api/v1/fuel/presets")
    assert r.status_code == 200
    presets = r.json()
    assert len(presets) >= 1

    chosen = next(p for p in presets if p["preset_id"] == "car-compact-popular")
    assert chosen["empty_weight_kg"] > 0

    payload = {
        "vehicle": {"type": "car", "preset_id": chosen["preset_id"]},
        "trip": {"distance_km": 100, "average_speed_kmh": 80},
    }
    r2 = await async_client.post("/api/v1/fuel/calculate", json=payload)
    assert r2.status_code == 200
    body = r2.json()

    # Sanity: 100 km @ 80 km/h num compacto popular → ~5-7 L
    assert 4.0 < body["total_fuel_l"] < 8.0
    assert body["fuel_per_km_l_per_100km"] > 0
    assert body["km_per_l"] > 0
    assert body["co2_kg"] > 0
    assert body["vehicle_label"] == "car-compact-popular"


async def test_calculate_with_custom_vehicle_no_preset(async_client):
    """Veículo 100% custom (sem preset) retorna resultado sensato."""
    payload = {
        "vehicle": {
            "type": "car",
            "category": "sedan",
            "empty_weight_kg": 1400.0,
            "engine_displacement_l": 1.8,
            "engine_power_kw": 110.0,
            "transmission": "automatic",
            "cylinders": 4,
            "drag_coefficient_cd": 0.30,
            "frontal_area_m2": 2.20,
            "rolling_resistance_coeff": 0.010,
            "tire_pressure_kpa": 220.0,
            "fuel_tank_capacity_l": 55.0,
            "fuel_type": "flex",
            "year": 2024,
        },
        "trip": {"distance_km": 200.0, "average_speed_kmh": 100.0},
    }
    r = await async_client.post("/api/v1/fuel/calculate", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    # Sedan 1.8 flex a 100 km/h por 200 km → ~14-18 L
    assert 10.0 < body["total_fuel_l"] < 22.0
    # L/100km consistente
    assert math.isclose(
        body["fuel_per_km_l_per_100km"],
        body["total_fuel_l"] / 2.0,  # 200 km
        rel_tol=1e-2,
    )
    assert body["vehicle_label"].startswith("car-sedan")


async def test_calculate_with_full_environment_block(async_client):
    """Bloco de environment com 6 variáveis (todas os campos possíveis)."""
    payload = {
        "vehicle": {"type": "car", "preset_id": "car-compact-popular"},
        "trip": {"distance_km": 150.0, "average_speed_kmh": 90.0, "speed_profile": "highway"},
        "environment": {
            "temperature_c": 5.0,
            "altitude_m": 1200.0,
            "humidity_pct": 80.0,
            "wind_speed_kmh": 20.0,
            "wind_direction_deg": 30.0,
            "road_condition": "wet",
        },
        "load": {
            "passenger_count": 2,
            "passenger_avg_weight_kg": 80.0,
            "cargo_weight_kg": 50.0,
            "towing_kg": 0.0,
        },
        "driver": {
            "driving_style": "eco",
            "use_ac": False,
            "fuel_quality": "premium",
            "fuel_price_brl_per_l": 5.89,
        },
    }
    r = await async_client.post("/api/v1/fuel/calculate", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    # 150 km @ 90 km/h compacto popular, frio, vento, chuva → ~7-11 L
    assert 5.0 < body["total_fuel_l"] < 15.0
    # Custo retornado (preço setado)
    assert body["fuel_cost_brl"] is not None
    assert math.isclose(
        body["fuel_cost_brl"], body["total_fuel_l"] * 5.89, rel_tol=1e-3
    )
    # Wet road → factor > 1.0
    factors = {f["name"]: f["factor"] for f in body["factors"]}
    assert factors["road_condition"] == 1.05
    # Eco → 0.92
    assert math.isclose(factors["driving_style"], 0.92, rel_tol=1e-9)
    # Premium → 0.97
    assert math.isclose(factors["fuel_quality"], 0.97, rel_tol=1e-9)
    # Cold → > 1.0
    assert factors["temperature"] > 1.0


async def test_request_id_roundtrip_via_header(async_client):
    """X-Request-ID é ecoado na resposta em fluxo end-to-end."""
    r = await async_client.get(
        "/api/v1/fuel/presets",
        headers={"X-Request-ID": "integration-test-001"},
    )
    assert r.status_code == 200
    assert r.headers["X-Request-ID"] == "integration-test-001"


async def test_health_via_async_client(async_client):
    r = await async_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_ready_via_async_client(async_client):
    r = await async_client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert 4.0 <= body["check"]["l_per_100km"] <= 12.0


async def test_full_calculate_then_batch(async_client):
    """Calcula uma viagem simples e depois submete em batch."""
    single = {
        "vehicle": {"type": "car", "preset_id": "car-compact-popular"},
        "trip": {"distance_km": 50.0, "average_speed_kmh": 60.0},
    }
    r1 = await async_client.post("/api/v1/fuel/calculate", json=single)
    assert r1.status_code == 200
    fuel_single = r1.json()["total_fuel_l"]

    # Batch com 3 cópias do mesmo request
    batch_payload = {"requests": [single, single, single]}
    r2 = await async_client.post("/api/v1/fuel/calculate/batch", json=batch_payload)
    assert r2.status_code == 200
    body = r2.json()
    assert body["count"] == 3
    # Cada resultado do batch deve ser idêntico ao single
    for res in body["results"]:
        assert math.isclose(res["total_fuel_l"], fuel_single, rel_tol=1e-6)


async def test_calculate_with_motorcycle_full_block(async_client):
    """Bloco completo de moto naked 300, sem preset, com todos os campos."""
    payload = {
        "vehicle": {
            "type": "motorcycle",
            "category": "naked",
            "empty_weight_kg": 160.0,
            "engine_displacement_l": 0.300,
            "engine_power_kw": 23.0,
            "transmission": "manual",
            "cylinders": 1,
            "drag_coefficient_cd": 0.50,
            "frontal_area_m2": 0.65,
            "rolling_resistance_coeff": 0.011,
            "tire_pressure_kpa": 200.0,
            "fuel_tank_capacity_l": 14.0,
            "fuel_type": "gasoline",
            "year": 2024,
        },
        "trip": {
            "distance_km": 80.0,
            "average_speed_kmh": 80.0,
            "speed_profile": "highway",
        },
        "environment": {
            "temperature_c": 20.0,
            "altitude_m": 500.0,
            "humidity_pct": 50.0,
        },
        "driver": {"driving_style": "normal", "fuel_price_brl_per_l": 6.5},
    }
    r = await async_client.post("/api/v1/fuel/calculate", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    # Moto 300cc 80 km → ~1.8-3.0 L
    assert 1.5 < body["total_fuel_l"] < 4.0
    assert body["vehicle_label"].startswith("motorcycle-naked")
    assert body["fuel_cost_brl"] is not None


# ===========================================================================
# Edge cases (validation)
# ===========================================================================
async def test_calculate_with_invalid_category_returns_422(async_client):
    """Categoria inválida para o tipo (moto com categoria de carro) → 422."""
    payload = {
        "vehicle": {
            "type": "motorcycle",
            "category": "sedan",  # categoria de carro, não moto
            "empty_weight_kg": 160.0, "engine_displacement_l": 0.300,
            "engine_power_kw": 23.0, "transmission": "manual", "cylinders": 1,
            "drag_coefficient_cd": 0.50, "frontal_area_m2": 0.65,
            "rolling_resistance_coeff": 0.011, "tire_pressure_kpa": 200.0,
            "fuel_tank_capacity_l": 14.0, "fuel_type": "gasoline", "year": 2024,
        },
        "trip": {"distance_km": 100.0},
    }
    r = await async_client.post("/api/v1/fuel/calculate", json=payload)
    assert r.status_code == 422


async def test_calculate_with_non_monotonic_elevation_returns_422(async_client):
    """elevation_profile com distância não-crescente → 422."""
    payload = {
        "vehicle": {"type": "car", "preset_id": "car-compact-popular"},
        "trip": {
            "distance_km": 100.0,
            "elevation_profile": [
                {"distance_km": 0, "elevation_m": 0},
                {"distance_km": 50, "elevation_m": 100},
                {"distance_km": 50, "elevation_m": 200},  # não crescente
            ],
        },
    }
    r = await async_client.post("/api/v1/fuel/calculate", json=payload)
    assert r.status_code == 422


async def test_calculate_with_year_out_of_range_returns_422(async_client):
    """year < 1950 ou > 2030 → 422."""
    payload = {
        "vehicle": {
            "type": "car", "category": "hatch",
            "empty_weight_kg": 1100.0, "engine_displacement_l": 1.0,
            "engine_power_kw": 75.0, "transmission": "manual", "cylinders": 3,
            "drag_coefficient_cd": 0.33, "frontal_area_m2": 2.10,
            "rolling_resistance_coeff": 0.010, "tire_pressure_kpa": 220.0,
            "fuel_tank_capacity_l": 44.0, "fuel_type": "gasoline",
            "year": 1900,
        },
        "trip": {"distance_km": 100.0},
    }
    r = await async_client.post("/api/v1/fuel/calculate", json=payload)
    assert r.status_code == 422


# ===========================================================================
# Repository / catálogo
# ===========================================================================
def test_repository_exists_method():
    from app.fuel.repository import VehicleRepository
    repo = VehicleRepository()
    assert repo.exists("car-compact-popular")
    assert not repo.exists("does-not-exist")


def test_repository_find_optional_returns_none_for_empty():
    from app.fuel.repository import VehicleRepository
    repo = VehicleRepository()
    assert repo.find_optional(None) is None
    assert repo.find_optional("") is None
    assert repo.find_optional("unknown-id") is None


def test_repository_get_raises_not_found():
    from app.errors import NotFoundError
    from app.fuel.repository import VehicleRepository
    repo = VehicleRepository()
    with pytest.raises(NotFoundError):
        repo.get("does-not-exist")

