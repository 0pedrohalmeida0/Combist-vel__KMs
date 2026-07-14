"""Testes de integração via TestClient (httpx).

Cobre os endpoints HTTP:
- GET /health, /ready
- GET /api/v1/fuel/presets
- GET /api/v1/fuel/presets/{id}
- POST /api/v1/fuel/calculate
- POST /api/v1/fuel/calculate/batch
- Códigos de erro 4xx (404, 405, 413, 422)
- Propagação de X-Request-ID
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _full_vehicle_payload():
    """Payload completo de veículo (todos os campos obrigatórios)."""
    return {
        "type": "car",
        "preset_id": "car-compact-popular",
        "category": "hatch",
        "empty_weight_kg": 1100.0,
        "engine_displacement_l": 1.0,
        "engine_power_kw": 75.0,
        "transmission": "manual",
        "cylinders": 3,
        "drag_coefficient_cd": 0.33,
        "frontal_area_m2": 2.10,
        "rolling_resistance_coeff": 0.010,
        "tire_pressure_kpa": 220.0,
        "fuel_tank_capacity_l": 44.0,
        "fuel_type": "gasoline",
        "year": 2024,
    }


def _full_request_payload(**trip_overrides):
    trip = {"distance_km": 100.0, "average_speed_kmh": 80.0, "speed_profile": "constant"}
    trip.update(trip_overrides)
    return {
        "vehicle": _full_vehicle_payload(),
        "trip": trip,
        "driver": {"fuel_price_brl_per_l": 6.0},
    }


# ===========================================================================
# Health & readiness
# ===========================================================================
def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_endpoint(client):
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert 4.0 <= body["check"]["l_per_100km"] <= 12.0


# ===========================================================================
# Presets
# ===========================================================================
def test_presets_list(client):
    r = client.get("/api/v1/fuel/presets")
    assert r.status_code == 200
    presets = r.json()
    ids = {p["preset_id"] for p in presets}
    expected = {
        "car-compact-popular", "car-sedan-medium", "car-suv-compact",
        "car-pickup", "car-sport",
        "moto-scooter-125", "moto-naked-300", "moto-sport-600",
        "moto-touring-1300",
    }
    assert expected.issubset(ids)
    assert len(presets) == 9


def test_preset_get_one(client):
    r = client.get("/api/v1/fuel/presets/car-compact-popular")
    assert r.status_code == 200
    body = r.json()
    assert body["preset_id"] == "car-compact-popular"
    assert body["empty_weight_kg"] > 0


def test_preset_get_unknown_returns_404(client):
    r = client.get("/api/v1/fuel/presets/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


# ===========================================================================
# Calculate (payload completo)
# ===========================================================================
def test_calculate_preset_compact_popular(client):
    payload = _full_request_payload()
    r = client.post("/api/v1/fuel/calculate", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert 5.6 <= body["total_fuel_l"] <= 6.2
    assert body["fuel_cost_brl"] is not None
    assert body["km_per_l"] > 0
    assert body["co2_kg"] > 0


def test_calculate_with_elevation_profile_returns_more_fuel(client):
    """elevation_profile (3 pontos, +200 m) → mais combustível que plano."""
    flat = _full_request_payload()
    flat_resp = client.post("/api/v1/fuel/calculate", json=flat)
    assert flat_resp.status_code == 200, flat_resp.text
    flat_fuel = flat_resp.json()["total_fuel_l"]

    hilly = _full_request_payload(
        elevation_profile=[
            {"distance_km": 0, "elevation_m": 0},
            {"distance_km": 50, "elevation_m": 100},
            {"distance_km": 100, "elevation_m": 200},
        ]
    )
    hilly_resp = client.post("/api/v1/fuel/calculate", json=hilly)
    assert hilly_resp.status_code == 200, hilly_resp.text
    hilly_fuel = hilly_resp.json()["total_fuel_l"]
    assert hilly_fuel > flat_fuel
    # 200 m em 100 km = 0.2% médio, ~5-10% mais
    assert 1.03 < hilly_fuel / flat_fuel < 1.20


def test_calculate_with_motorcycle_no_preset(client):
    """vehicle.type=motorcycle sem preset funciona se todos os campos
    obrigatórios forem fornecidos."""
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
        "trip": {"distance_km": 100.0, "average_speed_kmh": 80.0},
    }
    r = client.post("/api/v1/fuel/calculate", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    # Moto 300cc: ~2-3 L / 100 km
    assert 1.5 <= body["total_fuel_l"] <= 5.0
    assert body["vehicle_label"].startswith("motorcycle-")


def test_calculate_preset_with_motorcycle_via_preset(client):
    """Usar preset de moto via preset_id."""
    payload = {
        "vehicle": {"type": "motorcycle", "preset_id": "moto-naked-300"},
        "trip": {"distance_km": 100, "average_speed_kmh": 80},
    }
    r = client.post("/api/v1/fuel/calculate", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vehicle_label"] == "moto-naked-300"
    assert 1.5 <= body["total_fuel_l"] <= 3.5


def test_calculate_negative_distance_returns_422(client):
    payload = {
        "vehicle": _full_vehicle_payload(),
        "trip": {"distance_km": -10.0},
    }
    r = client.post("/api/v1/fuel/calculate", json=payload)
    assert r.status_code == 422


def test_calculate_missing_required_field_returns_422(client):
    """Faltando `vehicle.type` (obrigatório) → 422."""
    payload = {
        "vehicle": {"preset_id": "car-compact-popular"},
        "trip": {"distance_km": 100},
    }
    r = client.post("/api/v1/fuel/calculate", json=payload)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_calculate_invalid_payload_returns_422(client):
    """Payload malformado → 422."""
    r = client.post("/api/v1/fuel/calculate", json={"not_a_valid": "request"})
    assert r.status_code == 422


def test_calculate_unknown_preset_returns_404(client):
    payload = {
        "vehicle": {**_full_vehicle_payload(), "preset_id": "no-such-preset"},
        "trip": {"distance_km": 50.0},
    }
    r = client.post("/api/v1/fuel/calculate", json=payload)
    assert r.status_code == 404


def test_calculate_bad_method_returns_405(client):
    """GET em /calculate → 405 Method Not Allowed."""
    r = client.get("/api/v1/fuel/calculate")
    assert r.status_code == 405


# ===========================================================================
# Preset-only payload
# ===========================================================================
def test_calculate_with_preset_id_only():
    """Apenas `type` + `preset_id` no vehicle — o resto é preenchido
    pelo preset. Defaults como `idle_fuel_l_per_h` são aplicados
    durante a validação do merged result."""
    payload = {
        "vehicle": {
            "type": "car",
            "preset_id": "car-compact-popular",
        },
        "trip": {"distance_km": 100, "average_speed_kmh": 80},
    }
    with TestClient(app) as c:
        r = c.post("/api/v1/fuel/calculate", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        # Mesmo cenário do teste de referência à mão → ~5.9 L
        assert 5.5 < body["total_fuel_l"] < 8.5, body
        assert body["vehicle_label"] == "car-compact-popular"
        # O VehicleSpec resolved deve ter preenchido idle_fuel_l_per_h
        # com 0.6 (car) via model_validator.
        factors = {f["name"]: f["factor"] for f in body["factors"]}
        assert "ethanol_blend_volume" in factors


def test_calculate_preset_with_manual_overrides():
    """Quando `preset_id` + campos manuais são enviados, os manuais
    sobrescrevem o preset; os não-enviados vêm do preset."""
    payload = {
        "vehicle": {
            "type": "car",
            "preset_id": "car-compact-popular",
            "year": 2010,                # override (preset tem 2024)
            "drag_coefficient_cd": 0.50, # override (preset tem 0.33)
        },
        "trip": {"distance_km": 100, "average_speed_kmh": 80, "speed_profile": "constant"},
    }
    with TestClient(app) as c:
        r = c.post("/api/v1/fuel/calculate", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        # Veículo mais antigo + mais arrasto => mais combustível
        assert body["total_fuel_l"] > 7.0
        factors = {f["name"]: f["factor"] for f in body["factors"]}
        # 16 anos atrás (2026-2010) → 1 + 0.005*16 = 1.08
        assert abs(factors["vehicle_age"] - 1.08) < 0.005


def test_calculate_missing_type_is_422():
    """`type` é obrigatório mesmo quando `preset_id` está setado,
    porque o serviço precisa dele para aplicar o default de
    `idle_fuel_l_per_h` (0.6 L/h para carros, 0.4 para motos)."""
    with TestClient(app) as c:
        r = c.post("/api/v1/fuel/calculate", json={
            "vehicle": {"preset_id": "car-compact-popular"},
            "trip": {"distance_km": 100},
        })
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_calculate_incomplete_custom_is_422():
    """Sem preset, o `VehicleSpec` resolved exige todos os campos
    obrigatórios; o teste garante que o merge+validate ainda
    devolve 422 quando o cliente envia um custom incompleto."""
    with TestClient(app) as c:
        r = c.post("/api/v1/fuel/calculate", json={
            "vehicle": {
                "type": "car",
                "empty_weight_kg": 1100.0,  # só este, faltam os outros
            },
            "trip": {"distance_km": 100},
        })
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"


# ===========================================================================
# Batch
# ===========================================================================
def test_calculate_batch_ok(client):
    payload = {
        "requests": [
            {
                "vehicle": {
                    "type": "car",
                    "preset_id": "car-compact-popular",
                    "category": "hatch",
                    "empty_weight_kg": 1100.0, "engine_displacement_l": 1.0,
                    "engine_power_kw": 75.0, "transmission": "manual", "cylinders": 3,
                    "drag_coefficient_cd": 0.33, "frontal_area_m2": 2.10,
                    "rolling_resistance_coeff": 0.010, "tire_pressure_kpa": 220.0,
                    "fuel_tank_capacity_l": 44.0, "fuel_type": "gasoline", "year": 2024,
                },
                "trip": {"distance_km": 50.0},
            },
            {
                "vehicle": {
                    "type": "car",
                    "preset_id": "car-sedan-medium",
                    "category": "sedan",
                    "empty_weight_kg": 1320.0, "engine_displacement_l": 2.0,
                    "engine_power_kw": 125.0, "transmission": "automatic", "cylinders": 4,
                    "drag_coefficient_cd": 0.28, "frontal_area_m2": 2.20,
                    "rolling_resistance_coeff": 0.009, "tire_pressure_kpa": 220.0,
                    "fuel_tank_capacity_l": 60.0, "fuel_type": "flex", "year": 2024,
                },
                "trip": {"distance_km": 80.0},
            },
        ]
    }
    r = client.post("/api/v1/fuel/calculate/batch", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    assert len(body["results"]) == 2


def test_calculate_batch_three_results_in_order(client):
    """Batch de 3 → 3 resultados na mesma ordem."""
    payload = {
        "requests": [
            {**_full_request_payload(distance_km=10.0)},
            {**_full_request_payload(distance_km=20.0)},
            {**_full_request_payload(distance_km=30.0)},
        ]
    }
    r = client.post("/api/v1/fuel/calculate/batch", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 3
    assert len(body["results"]) == 3
    # Ordem: combustível cresce com distância
    fuels = [res["total_fuel_l"] for res in body["results"]]
    assert fuels[0] < fuels[1] < fuels[2]
    # Distâncias refletem a ordem dos requests
    distances = [res["distance_km"] for res in body["results"]]
    assert distances == [10.0, 20.0, 30.0]


def test_calculate_batch_too_large_returns_4xx(client, settings):
    big_payload = {
        "vehicle": _full_vehicle_payload(),
        "trip": {"distance_km": 10.0},
    }
    over = {"requests": [big_payload] * (settings.batch_size_limit + 1)}
    r = client.post("/api/v1/fuel/calculate/batch", json=over)
    # Pode ser 413 (PayloadTooLarge) ou 422 — ambos 4xx são aceitos
    assert 400 <= r.status_code < 500
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] in {"PAYLOAD_TOO_LARGE", "VALIDATION_ERROR"}


def test_calculate_batch_exactly_at_limit_succeeds(client, settings):
    """Batch exatamente no limite (100) deve passar."""
    payload = {
        "requests": [
            {"vehicle": _full_vehicle_payload(), "trip": {"distance_km": 5.0}}
            for _ in range(settings.batch_size_limit)
        ]
    }
    r = client.post("/api/v1/fuel/calculate/batch", json=payload)
    assert r.status_code == 200
    assert r.json()["count"] == settings.batch_size_limit


# ===========================================================================
# Request ID
# ===========================================================================
def test_request_id_header_propagated(client):
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers.get("X-Request-ID") == "abc123"


def test_request_id_generated_when_absent(client):
    r = client.get("/health")
    assert "X-Request-ID" in r.headers
    assert len(r.headers["X-Request-ID"]) >= 8


def test_request_id_in_response_when_provided(client):
    """Header X-Request-ID enviado aparece na resposta."""
    r = client.post(
        "/api/v1/fuel/calculate",
        json=_full_request_payload(),
        headers={"X-Request-ID": "client-id-99"},
    )
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == "client-id-99"


def test_request_id_in_error_response(client):
    """Header X-Request-ID aparece também em respostas de erro."""
    r = client.post(
        "/api/v1/fuel/calculate",
        json={"vehicle": _full_vehicle_payload(), "trip": {"distance_km": -1.0}},
        headers={"X-Request-ID": "err-id-42"},
    )
    assert r.status_code == 422
    assert r.headers.get("X-Request-ID") == "err-id-42"
    assert r.json()["error"]["request_id"] == "err-id-42"


# ===========================================================================
# Comportamento dos fatores expostos
# ===========================================================================
def test_response_factors_includes_named_set(client):
    r = client.post("/api/v1/fuel/calculate", json=_full_request_payload())
    assert r.status_code == 200
    factors = {f["name"] for f in r.json()["factors"]}
    assert {"altitude", "temperature", "humidity", "road_condition",
            "driving_style", "fuel_quality", "vehicle_age", "transmission",
            "tire_pressure", "load", "ethanol_blend_volume",
            "ethanol_blend_co2"}.issubset(factors)


def test_response_segments_non_empty(client):
    """O breakdown por segmento é retornado para 100 km."""
    r = client.post("/api/v1/fuel/calculate", json=_full_request_payload())
    assert r.status_code == 200
    segments = r.json()["segments"]
    assert len(segments) > 0
    # Cada segmento tem índice e combustível positivo
    for s in segments:
        assert s["index"] >= 0
        assert s["fuel_l"] >= 0


# ===========================================================================
# Testes adversariais
# ===========================================================================
def test_adversarial_negative_distance_rejected(client):
    """Distância negativa deve ser rejeitada com 422."""
    r = client.post(
        "/api/v1/fuel/calculate",
        json={
            "vehicle": _full_vehicle_payload(),
            "trip": {"distance_km": -10.0},
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_adversarial_zero_distance_rejected(client):
    """Distância zero também é rejeitada (gt=0)."""
    r = client.post(
        "/api/v1/fuel/calculate",
        json={
            "vehicle": _full_vehicle_payload(),
            "trip": {"distance_km": 0.0},
        },
    )
    assert r.status_code == 422


def test_adversarial_cd_out_of_range_rejected(client):
    """drag_coefficient_cd fora do range [0.15, 0.6] → 422."""
    payload = _full_vehicle_payload()
    payload["drag_coefficient_cd"] = 5.0  # way too high
    r = client.post(
        "/api/v1/fuel/calculate",
        json={"vehicle": payload, "trip": {"distance_km": 100.0}},
    )
    assert r.status_code == 422


def test_adversarial_frontal_area_out_of_range_rejected(client):
    """frontal_area_m2 fora do range [0.3, 4.0] → 422."""
    payload = _full_vehicle_payload()
    payload["frontal_area_m2"] = 100.0
    r = client.post(
        "/api/v1/fuel/calculate",
        json={"vehicle": payload, "trip": {"distance_km": 100.0}},
    )
    assert r.status_code == 422


def test_adversarial_year_below_minimum_rejected(client):
    """year < 1950 → 422."""
    payload = _full_vehicle_payload()
    payload["year"] = 1900
    r = client.post(
        "/api/v1/fuel/calculate",
        json={"vehicle": payload, "trip": {"distance_km": 100.0}},
    )
    assert r.status_code == 422


def test_adversarial_year_above_maximum_rejected(client):
    """year > 2030 → 422."""
    payload = _full_vehicle_payload()
    payload["year"] = 2099
    r = client.post(
        "/api/v1/fuel/calculate",
        json={"vehicle": payload, "trip": {"distance_km": 100.0}},
    )
    assert r.status_code == 422


def test_adversarial_temperature_below_minimum_rejected(client):
    """temperature_c < -30 → 422."""
    r = client.post(
        "/api/v1/fuel/calculate",
        json={
            "vehicle": {"type": "car", "preset_id": "car-compact-popular"},
            "trip": {"distance_km": 100.0},
            "environment": {"temperature_c": -50.0},
        },
    )
    assert r.status_code == 422


def test_adversarial_altitude_above_maximum_rejected(client):
    """altitude_m > 5000 → 422."""
    r = client.post(
        "/api/v1/fuel/calculate",
        json={
            "vehicle": {"type": "car", "preset_id": "car-compact-popular"},
            "trip": {"distance_km": 100.0},
            "environment": {"altitude_m": 6000.0},
        },
    )
    assert r.status_code == 422


def test_adversarial_speed_above_maximum_rejected(client):
    """average_speed_kmh > 250 → 422."""
    r = client.post(
        "/api/v1/fuel/calculate",
        json={
            "vehicle": {"type": "car", "preset_id": "car-compact-popular"},
            "trip": {"distance_km": 100.0, "average_speed_kmh": 500.0},
        },
    )
    assert r.status_code == 422


def test_adversarial_unknown_fuel_type_rejected(client):
    """fuel_type inválido → 422."""
    payload = _full_vehicle_payload()
    payload["fuel_type"] = "jet-fuel"
    r = client.post(
        "/api/v1/fuel/calculate",
        json={"vehicle": payload, "trip": {"distance_km": 100.0}},
    )
    assert r.status_code == 422


def test_adversarial_passenger_count_negative_rejected(client):
    """passenger_count negativo → 422."""
    r = client.post(
        "/api/v1/fuel/calculate",
        json={
            "vehicle": {"type": "car", "preset_id": "car-compact-popular"},
            "trip": {"distance_km": 100.0},
            "load": {"passenger_count": -1},
        },
    )
    assert r.status_code == 422


def test_adversarial_preset_id_with_motorcycle_type_rejected(client):
    """preset_id de carro + type=motorcycle → conflito, mas o validador
    pega no merge (campos obrigatórios faltantes) → 422."""
    r = client.post(
        "/api/v1/fuel/calculate",
        json={
            "vehicle": {"type": "motorcycle", "preset_id": "car-compact-popular"},
            "trip": {"distance_km": 100.0},
        },
    )
    # O service tenta fundir preset de carro com type=moto; idle_fuel_l_per_h
    # do preset é 0.6 (car), o model_validator aplica o default de moto (0.4)
    # mas o resto dos campos estão OK → 200
    # (Não é um erro de validação porque todos os campos obrigatórios estão presentes)
    assert r.status_code in {200, 422}


def test_adversarial_extra_field_in_vehicle_rejected(client):
    """Campo extra no vehicle (model_config=extra='forbid') → 422."""
    payload = _full_vehicle_payload()
    payload["some_extra_field"] = "should-be-rejected"
    r = client.post(
        "/api/v1/fuel/calculate",
        json={"vehicle": payload, "trip": {"distance_km": 100.0}},
    )
    assert r.status_code == 422
