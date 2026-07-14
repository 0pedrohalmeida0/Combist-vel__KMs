"""Schemas Pydantic v2 — DTOs de entrada e saída.

A nomenclatura segue o padrão `FooRequest` (entrada) e
`FooResponse` (saída).

Importante: a requisição HTTP usa `VehicleSpecInput`, uma versão
*parcial* da especificação do veículo em que todos os campos são
opcionais. Isso permite que o cliente envie apenas o `preset_id`
(ex.: `{"vehicle": {"preset_id": "car-compact-popular"}}`) e deixe
o serviço mesclar com o preset. A validação completa acontece
*após* o merge, em `service._resolve_vehicle`, que revalida o
resultado contra a `VehicleSpec` estrita e devolve 422 em caso
de inconsistência.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums de domínio
# ---------------------------------------------------------------------------
class VehicleType(str, Enum):
    car = "car"
    motorcycle = "motorcycle"


class Transmission(str, Enum):
    manual = "manual"
    automatic = "automatic"
    cvt = "cvt"


class FuelType(str, Enum):
    gasoline = "gasoline"
    ethanol = "ethanol"
    diesel = "diesel"
    flex = "flex"


class SpeedProfile(str, Enum):
    constant = "constant"
    urban = "urban"
    suburban = "suburban"
    highway = "highway"
    mixed = "mixed"


class RoadCondition(str, Enum):
    dry = "dry"
    wet = "wet"
    snow = "snow"
    ice = "ice"


class DrivingStyle(str, Enum):
    eco = "eco"
    normal = "normal"
    aggressive = "aggressive"


class FuelQuality(str, Enum):
    regular = "regular"
    premium = "premium"


# Categorias válidas por tipo. Mantidas em dicionário para evitar
# importar do `presets.py` (que carrega dados) dentro do schema.
CAR_CATEGORIES = {
    "compact", "sedan", "hatch", "suv", "pickup", "sport", "crossover", "custom",
}
MOTO_CATEGORIES = {
    "naked", "sport", "touring", "cruiser", "scooter", "trail", "custom",
}


# ---------------------------------------------------------------------------
# Veículo — duas versões
# ---------------------------------------------------------------------------
class VehicleSpec(BaseModel):
    """Especificação completa e validada de um veículo (uso interno)."""

    model_config = ConfigDict(extra="forbid")

    type: VehicleType
    category: Optional[str] = Field(default=None)
    preset_id: Optional[str] = Field(default=None)

    empty_weight_kg: float = Field(gt=0)
    engine_displacement_l: float = Field(gt=0)
    engine_power_kw: float = Field(gt=0)
    transmission: Transmission
    cylinders: int = Field(ge=1)
    drag_coefficient_cd: float = Field(ge=0.15, le=0.6)
    frontal_area_m2: float = Field(ge=0.3, le=4.0)
    rolling_resistance_coeff: float = Field(ge=0.005, le=0.025)
    tire_pressure_kpa: float = Field(ge=120, le=350)
    fuel_tank_capacity_l: float = Field(gt=0)
    fuel_type: FuelType
    drivetrain_efficiency: float = Field(default=0.85, ge=0.5, le=0.95)
    engine_thermal_efficiency: float = Field(default=0.25, ge=0.15, le=0.45)
    aux_power_w: float = Field(default=1500, ge=0, le=5000)
    idle_fuel_l_per_h: float = Field(default=None, ge=0)
    year: int = Field(ge=1950, le=2030)

    @model_validator(mode="after")
    def _apply_type_defaults(self):
        if self.idle_fuel_l_per_h is None:
            object.__setattr__(
                self,
                "idle_fuel_l_per_h",
                0.4 if self.type == VehicleType.motorcycle else 0.6,
            )
        return self

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v, info):  # type: ignore[no-untyped-def]
        if v is None:
            return v
        vtype = info.data.get("type") if hasattr(info, "data") else None
        try:
            vtype_val = vtype.value if hasattr(vtype, "value") else vtype
        except Exception:
            vtype_val = None

        valid_values: List[str] = ["custom"]
        if vtype_val == "car":
            valid_values.extend(sorted(CAR_CATEGORIES - {"custom"}))
        elif vtype_val == "motorcycle":
            valid_values.extend(sorted(MOTO_CATEGORIES - {"custom"}))
        if v not in valid_values:
            raise ValueError(
                f"category {v!r} inválida para type {vtype_val!r}. "
                f"Permitidas: {valid_values}"
            )
        return v


class VehicleRequest(BaseModel):
    """Especificação *parcial* do veículo (entrada HTTP).

    Apenas `type` é obrigatório — é o que o serviço usa para
    inferir o default de `idle_fuel_l_per_h` quando o preset
    não cobre esse campo. Todos os outros campos são opcionais
    aqui; o serviço mescla com o `preset_id` (quando informado)
    e revalida o resultado contra o `VehicleSpec` estrito.

    Quando `preset_id` for omitido, o `VehicleSpec` resolved
    exigirá todos os outros campos numéricos obrigatórios.
    """

    model_config = ConfigDict(extra="forbid")

    # type é OBRIGATÓRIO no request: usado para aplicar o default
    # de `idle_fuel_l_per_h` no VehicleSpec resolved.
    type: VehicleType
    category: Optional[str] = None
    preset_id: Optional[str] = None

    # Geometria / massa
    empty_weight_kg: Optional[float] = None
    frontal_area_m2: Optional[float] = None
    drag_coefficient_cd: Optional[float] = None
    rolling_resistance_coeff: Optional[float] = None

    # Motor / trem de força
    engine_displacement_l: Optional[float] = None
    engine_power_kw: Optional[float] = None
    transmission: Optional[Transmission] = None
    cylinders: Optional[int] = None
    drivetrain_efficiency: Optional[float] = None
    engine_thermal_efficiency: Optional[float] = None

    # Pneus / tanque
    tire_pressure_kpa: Optional[float] = None
    fuel_tank_capacity_l: Optional[float] = None
    fuel_type: Optional[FuelType] = None

    # Auxiliares
    aux_power_w: Optional[float] = None
    idle_fuel_l_per_h: Optional[float] = None

    # Ano
    year: Optional[int] = None


# ---------------------------------------------------------------------------
# Demais sub-seções da requisição
# ---------------------------------------------------------------------------
class ElevationPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    distance_km: float = Field(ge=0)
    elevation_m: float


class TripSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distance_km: float = Field(gt=0)
    average_speed_kmh: float = Field(default=80.0, gt=0, le=250)
    speed_profile: SpeedProfile = Field(default=SpeedProfile.mixed)
    idle_time_min: float = Field(default=0.0, ge=0)
    stops_per_km: float = Field(default=0.0, ge=0)
    elevation_profile: Optional[List[ElevationPoint]] = Field(default=None)

    @field_validator("elevation_profile")
    @classmethod
    def _validate_elevation(cls, v):
        if v is None:
            return v
        if len(v) < 2:
            return v
        distances = [p.distance_km for p in v]
        for i in range(1, len(distances)):
            if distances[i] <= distances[i - 1]:
                raise ValueError(
                    "elevation_profile deve ser estritamente crescente em "
                    "distance_km (encontrado valor não-crescente em "
                    f"índice {i}: {distances[i]} <= {distances[i-1]})"
                )
        return v


class EnvironmentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temperature_c: float = Field(default=20.0, ge=-30, le=50)
    altitude_m: float = Field(default=0.0, ge=-100, le=5000)
    humidity_pct: float = Field(default=60.0, ge=0, le=100)
    wind_speed_kmh: float = Field(default=0.0, ge=0, le=150)
    wind_direction_deg: float = Field(default=0.0, ge=0, le=360)
    road_condition: RoadCondition = Field(default=RoadCondition.dry)


class LoadSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passenger_count: int = Field(default=1, ge=0, le=9)
    passenger_avg_weight_kg: float = Field(default=75.0, gt=0)
    cargo_weight_kg: float = Field(default=0.0, ge=0)
    towing_kg: float = Field(default=0.0, ge=0)


class DriverSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    driving_style: DrivingStyle = Field(default=DrivingStyle.normal)
    use_ac: bool = Field(default=False)
    fuel_quality: FuelQuality = Field(default=FuelQuality.regular)
    fuel_price_brl_per_l: Optional[float] = Field(default=None, gt=0)


# ---------------------------------------------------------------------------
# Request raiz
# ---------------------------------------------------------------------------
class CalculationRequest(BaseModel):
    """Requisição de cálculo.

    Apenas `vehicle` e `trip.distance_km` são obrigatórios. O
    `vehicle` é aceito em formato *parcial*: campos faltantes
    são preenchidos a partir do `preset_id` (quando informado)
    e o resultado é então revalidado. Se mesmo após o merge
    faltar algum campo obrigatório, a resposta será 422.
    """

    model_config = ConfigDict(extra="forbid")

    vehicle: VehicleRequest
    trip: TripSpec
    environment: EnvironmentSpec = Field(default_factory=EnvironmentSpec)
    load: LoadSpec = Field(default_factory=LoadSpec)
    driver: DriverSpec = Field(default_factory=DriverSpec)


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------
class SegmentBreakdown(BaseModel):
    """Detalhe de um segmento físico integrado."""

    index: int
    start_km: float
    end_km: float
    grade_pct: float
    speed_kmh: float
    tractive_power_w: float
    fuel_l: float


class FactorContribution(BaseModel):
    """Contribuição individual de cada correção."""

    name: str
    factor: float
    note: Optional[str] = None


class CalculationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Identificação
    vehicle_label: str
    fuel_type: FuelType
    distance_km: float
    trip_duration_h: float
    average_speed_kmh: float

    # Resultados primários
    total_fuel_l: float
    fuel_per_km_l_per_100km: float
    km_per_l: float
    energy_mj: float
    co2_kg: float

    # Custo (opcional)
    fuel_cost_brl: Optional[float] = None

    # Detalhamento
    factors: List[FactorContribution]
    segments: List[SegmentBreakdown]
    warnings: List[str]

    # Auxiliares úteis para o consumidor
    total_mass_kg: float
    air_density_kg_per_m3: float
    effective_headwind_kmh: float
    aux_power_effective_w: float


class BatchCalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requests: List[CalculationRequest]


class BatchCalculationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int
    results: List[CalculationResponse]


# ---------------------------------------------------------------------------
# Tipos auxiliares
# ---------------------------------------------------------------------------
ResolvedVehicle = VehicleSpec
