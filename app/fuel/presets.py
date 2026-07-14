"""Presets de veículos com especificações realistas do mercado brasileiro.

Cada preset é um dicionário Python que satisfaz integralmente o
schema `VehicleSpec`. Para usar um preset basta informar o campo
`preset_id` no payload — campos faltantes são preenchidos a partir
do preset antes de aplicar overrides do usuário.

Atualize este arquivo (e a documentação) sempre que adicionar ou
alterar um preset. Os valores aqui foram calibrados para
representar modelos populares vendidos no Brasil; servem apenas
como referência e não substituem dados de fábrica.
"""
from __future__ import annotations

from typing import Any, Dict, List


# Estrutura: dict[preset_id] -> VehicleSpec (em dict para evitar import
# circular com schemas).
VEHICLE_PRESETS: Dict[str, Dict[str, Any]] = {
    # ------------------------------------------------------------------
    # CARROS
    # ------------------------------------------------------------------
    "car-compact-popular": {
        "type": "car",
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
        "drivetrain_efficiency": 0.85,
        "engine_thermal_efficiency": 0.25,
        "aux_power_w": 1500.0,
        "idle_fuel_l_per_h": 0.6,
        "year": 2024,
        "description": "Hatch compacto popular (1.0 aspirado) — referência: Chevrolet Onix 1.0",
    },
    "car-sedan-medium": {
        "type": "car",
        "category": "sedan",
        "empty_weight_kg": 1320.0,
        "engine_displacement_l": 2.0,
        "engine_power_kw": 125.0,
        "transmission": "automatic",
        "cylinders": 4,
        "drag_coefficient_cd": 0.28,
        "frontal_area_m2": 2.20,
        "rolling_resistance_coeff": 0.009,
        "tire_pressure_kpa": 220.0,
        "fuel_tank_capacity_l": 60.0,
        "fuel_type": "flex",
        "drivetrain_efficiency": 0.84,
        "engine_thermal_efficiency": 0.27,
        "aux_power_w": 1500.0,
        "idle_fuel_l_per_h": 0.6,
        "year": 2024,
        "description": "Sedan médio flex (2.0) — referência: Toyota Corolla 2.0",
    },
    "car-suv-compact": {
        "type": "car",
        "category": "suv",
        "empty_weight_kg": 1600.0,
        "engine_displacement_l": 1.3,
        "engine_power_kw": 130.0,
        "transmission": "automatic",
        "cylinders": 4,
        "drag_coefficient_cd": 0.34,
        "frontal_area_m2": 2.55,
        "rolling_resistance_coeff": 0.011,
        "tire_pressure_kpa": 220.0,
        "fuel_tank_capacity_l": 60.0,
        "fuel_type": "gasoline",
        "drivetrain_efficiency": 0.83,
        "engine_thermal_efficiency": 0.28,
        "aux_power_w": 1500.0,
        "idle_fuel_l_per_h": 0.6,
        "year": 2024,
        "description": "SUV compacto turbo (1.3T) — referência: Jeep Compass 1.3T",
    },
    "car-pickup": {
        "type": "car",
        "category": "pickup",
        "empty_weight_kg": 2100.0,
        "engine_displacement_l": 2.8,
        "engine_power_kw": 150.0,
        "transmission": "automatic",
        "cylinders": 4,
        "drag_coefficient_cd": 0.40,
        "frontal_area_m2": 2.80,
        "rolling_resistance_coeff": 0.012,
        "tire_pressure_kpa": 240.0,
        "fuel_tank_capacity_l": 80.0,
        "fuel_type": "diesel",
        "drivetrain_efficiency": 0.83,
        "engine_thermal_efficiency": 0.32,
        "aux_power_w": 1800.0,
        "idle_fuel_l_per_h": 0.8,
        "year": 2023,
        "description": "Picape média diesel (2.8) — referência: Toyota Hilux",
    },
    "car-sport": {
        "type": "car",
        "category": "sport",
        "empty_weight_kg": 1350.0,
        "engine_displacement_l": 1.5,
        "engine_power_kw": 150.0,
        "transmission": "automatic",
        "cylinders": 4,
        "drag_coefficient_cd": 0.30,
        "frontal_area_m2": 2.15,
        "rolling_resistance_coeff": 0.010,
        "tire_pressure_kpa": 230.0,
        "fuel_tank_capacity_l": 47.0,
        "fuel_type": "gasoline",
        "drivetrain_efficiency": 0.86,
        "engine_thermal_efficiency": 0.30,
        "aux_power_w": 1500.0,
        "idle_fuel_l_per_h": 0.6,
        "year": 2024,
        "description": "Esportivo compacto turbo (1.5T) — referência: Honda Civic Si",
    },
    # ------------------------------------------------------------------
    # MOTOS
    # ------------------------------------------------------------------
    "moto-scooter-125": {
        "type": "motorcycle",
        "category": "scooter",
        "empty_weight_kg": 110.0,
        "engine_displacement_l": 0.125,
        "engine_power_kw": 8.0,
        "transmission": "cvt",
        "cylinders": 1,
        "drag_coefficient_cd": 0.55,
        "frontal_area_m2": 0.55,
        "rolling_resistance_coeff": 0.012,
        "tire_pressure_kpa": 200.0,
        "fuel_tank_capacity_l": 8.0,
        "fuel_type": "gasoline",
        "drivetrain_efficiency": 0.82,
        "engine_thermal_efficiency": 0.22,
        "aux_power_w": 250.0,
        "idle_fuel_l_per_h": 0.4,
        "year": 2024,
        "description": "Scooter urbana 125cc — referência: Honda Biz 125",
    },
    "moto-naked-300": {
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
        "drivetrain_efficiency": 0.83,
        "engine_thermal_efficiency": 0.24,
        "aux_power_w": 250.0,
        "idle_fuel_l_per_h": 0.4,
        "year": 2024,
        "description": "Naked 300cc — referência: Honda CB300F",
    },
    "moto-sport-600": {
        "type": "motorcycle",
        "category": "sport",
        "empty_weight_kg": 195.0,
        "engine_displacement_l": 0.600,
        "engine_power_kw": 88.0,
        "transmission": "manual",
        "cylinders": 4,
        "drag_coefficient_cd": 0.45,
        "frontal_area_m2": 0.70,
        "rolling_resistance_coeff": 0.011,
        "tire_pressure_kpa": 220.0,
        "fuel_tank_capacity_l": 18.0,
        "fuel_type": "gasoline",
        "drivetrain_efficiency": 0.85,
        "engine_thermal_efficiency": 0.27,
        "aux_power_w": 250.0,
        "idle_fuel_l_per_h": 0.5,
        "year": 2023,
        "description": "Esportiva 600cc — referência: Honda CBR600RR",
    },
    "moto-touring-1300": {
        "type": "motorcycle",
        "category": "touring",
        "empty_weight_kg": 420.0,
        "engine_displacement_l": 1.8,
        "engine_power_kw": 92.0,
        "transmission": "manual",
        "cylinders": 6,
        "drag_coefficient_cd": 0.60,
        "frontal_area_m2": 1.10,
        "rolling_resistance_coeff": 0.010,
        "tire_pressure_kpa": 220.0,
        "fuel_tank_capacity_l": 25.0,
        "fuel_type": "gasoline",
        "drivetrain_efficiency": 0.84,
        "engine_thermal_efficiency": 0.28,
        "aux_power_w": 600.0,
        "idle_fuel_l_per_h": 0.6,
        "year": 2022,
        "description": "Touring 1800cc — referência: Honda Gold Wing",
    },
}


def list_presets() -> List[Dict[str, Any]]:
    """Retorna todos os presets com `preset_id` injetado no dicionário."""
    return [{"preset_id": pid, **data} for pid, data in VEHICLE_PRESETS.items()]


def get_preset(preset_id: str) -> Dict[str, Any]:
    """Retorna o preset (cópia rasa) ou `None` se inexistente."""
    data = VEHICLE_PRESETS.get(preset_id)
    if data is None:
        return None
    return {**data, "preset_id": preset_id}
