"""Serviço de cálculo de combustível.

Orquestra `physics` (integração) e `corrections` (fatores) e
produz um `CalculationResponse`. Não toca em HTTP, não faz I/O
de banco e não loga — é uma função pura em cima do request.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from pydantic import ValidationError as PydanticValidationError

from app.config import get_settings
from app.errors import NotFoundError, PayloadTooLargeError, ValidationError
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
from app.fuel.physics import (
    ACCEL_PHASE_A,
    ACCEL_PHASE_DISTANCE_M,
    DECEL_PHASE_A,
    DECEL_PHASE_DISTANCE_M,
    FLEX_ETHANOL_CO2_FACTOR,
    FLEX_ETHANOL_VOLUME_FACTOR,
    FuelProps,
    acceleration_force,
    aero_drag_force,
    air_density,
    climbing_force,
    fuel_flow_l_per_s,
    fuel_properties,
    grade_from_elevation,
    idle_fuel_flow_l_per_s,
    rolling_resistance_force,
    tractive_power,
)
from app.fuel.repository import VehicleRepository
from app.fuel.schemas import (
    CalculationRequest,
    CalculationResponse,
    FactorContribution,
    FuelType,
    SegmentBreakdown,
    VehicleSpec,
)


# Erros de validação Pydantic são reembalados em ValidationError.
def _coerce_validation_error(exc: PydanticValidationError) -> ValidationError:
    return ValidationError("Payload inválido", details=exc.errors())


def _enum_value(field) -> str:
    """Aceita enum (com `.value`) ou string crua (ex.: após `model_copy`)."""
    if hasattr(field, "value"):
        return field.value
    return str(field)


class FuelCalculationService:
    """Coordena a integração da viagem e aplica os fatores de correção."""

    def __init__(self, repository: Optional[VehicleRepository] = None) -> None:
        self.repo = repository or VehicleRepository()
        self.settings = get_settings()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def list_presets(self) -> List[Dict]:
        return self.repo.list()

    def get_preset(self, preset_id: str) -> Dict:
        return self.repo.get(preset_id)

    def calculate(self, request: CalculationRequest) -> CalculationResponse:
        try:
            return self._calculate_internal(request)
        except PydanticValidationError as exc:
            raise _coerce_validation_error(exc) from exc

    def calculate_batch(
        self, requests: List[CalculationRequest]
    ) -> List[CalculationResponse]:
        limit = self.settings.batch_size_limit
        if len(requests) > limit:
            raise PayloadTooLargeError(
                f"Batch excede o limite de {limit} requisições",
                limit=limit,
                received=len(requests),
            )
        return [self.calculate(req) for req in requests]

    # ------------------------------------------------------------------
    # Núcleo do cálculo
    # ------------------------------------------------------------------
    def _calculate_internal(self, request: CalculationRequest) -> CalculationResponse:
        # 1. Resolve veículo (preset + overrides)
        vehicle = self._resolve_vehicle(request.vehicle)

        # 2. Massa total
        total_mass = self._total_mass_kg(vehicle, request)

        # 3. Propriedades do combustível
        fuel = fuel_properties(_enum_value(vehicle.fuel_type))
        # Flex é tratado no volume/CO2; aqui usamos a média para
        # fluxo mássico (LHV médio). O multiplicador de volume é
        # aplicado em ethanol_blend_factor abaixo.
        lhv = fuel.lhv_mj_kg

        # 4. Atmosfera / ambiente
        env = request.environment
        rho = air_density(env.temperature_c, env.altitude_m, env.humidity_pct)
        headwind = effective_headwind_kmh(
            env.wind_speed_kmh, env.wind_direction_deg, 0.0
        )

        # 5. Auxiliares e AC
        avg_speed_kmh = request.trip.average_speed_kmh
        ac_mult, ac_aux_w = ac_factor(
            request.driver.use_ac, env.temperature_c,
            request.trip.distance_km, avg_speed_kmh,
        )
        aux_power_w = vehicle.aux_power_w + ac_aux_w

        # 6. Integração por segmento
        segment_length_m = self.settings.segment_length_m
        segments, raw_fuel_l, raw_energy_j = self._integrate_trip(
            vehicle=vehicle,
            trip=request.trip,
            total_mass_kg=total_mass,
            towing_kg=request.load.towing_kg,
            air_density=rho,
            headwind_kmh=headwind,
            aux_power_w=aux_power_w,
            segment_length_m=segment_length_m,
            road_condition=_enum_value(env.road_condition),
        )
        idle_fuel_l = self._idle_fuel(
            vehicle=vehicle, idle_time_min=request.trip.idle_time_min,
        )

        # 7. Fatores multiplicativos / aditivos
        factors: List[FactorContribution] = []
        warnings: List[str] = []

        # Atmosfera
        f_alt = altitude_factor(env.altitude_m)
        factors.append(FactorContribution(name="altitude", factor=f_alt))

        f_temp = temperature_factor(
            env.temperature_c, request.trip.idle_time_min, request.trip.distance_km
        )
        factors.append(FactorContribution(name="temperature", factor=f_temp))

        f_hum = humidity_factor(env.humidity_pct)
        factors.append(FactorContribution(name="humidity", factor=f_hum))

        f_road = road_condition_factor(_enum_value(env.road_condition))
        factors.append(FactorContribution(name="road_condition", factor=f_road))

        f_style = driving_style_factor(_enum_value(request.driver.driving_style))
        factors.append(FactorContribution(name="driving_style", factor=f_style))

        f_qual = fuel_quality_factor(_enum_value(request.driver.fuel_quality))
        factors.append(FactorContribution(name="fuel_quality", factor=f_qual))

        f_age = vehicle_age_factor(vehicle.year)
        factors.append(FactorContribution(name="vehicle_age", factor=f_age))

        f_trans = transmission_factor(_enum_value(vehicle.transmission))
        factors.append(FactorContribution(name="transmission", factor=f_trans))

        f_tire = tire_pressure_factor(vehicle.tire_pressure_kpa)
        if f_tire > 1.05:
            warnings.append(
                f"Pressão de pneu baixa ({vehicle.tire_pressure_kpa:.0f} kPa): "
                f"consumo pode subir {((f_tire - 1.0) * 100):.1f}%."
            )
        factors.append(FactorContribution(name="tire_pressure", factor=f_tire))

        f_load = load_factor(
            vehicle.empty_weight_kg,
            request.load.passenger_count * request.load.passenger_avg_weight_kg
            + request.load.cargo_weight_kg,
            request.load.towing_kg,
        )
        factors.append(FactorContribution(name="load", factor=f_load))

        # AC
        if request.driver.use_ac:
            factors.append(FactorContribution(name="ac", factor=ac_mult))
            if env.temperature_c < 0.0:
                warnings.append(
                    "Ar-condicionado ligado a 0 °C: usado apenas para "
                    "desembaçar, aquecimento do habitáculo é ineficiente."
                )

        # Flex / ethanol
        eth_volume_factor, eth_co2_factor = ethanol_blend_factor(
            _enum_value(vehicle.fuel_type),
            _enum_value(request.driver.fuel_quality),
        )
        factors.append(FactorContribution(name="ethanol_blend_volume", factor=eth_volume_factor))
        factors.append(FactorContribution(name="ethanol_blend_co2", factor=eth_co2_factor))

        # 8. Combina tudo
        multiplicative = (
            f_alt * f_temp * f_hum * f_road * f_style * f_qual * f_age
            * f_trans * f_tire * f_load * ac_mult * eth_volume_factor
        )

        total_fuel_l = raw_fuel_l * multiplicative + idle_fuel_l
        total_energy_j = raw_energy_j * multiplicative

        # 9. Custo (se houver)
        cost_brl: Optional[float] = None
        if request.driver.fuel_price_brl_per_l is not None:
            cost_brl = total_fuel_l * request.driver.fuel_price_brl_per_l

        # 10. CO₂
        co2_kg = (
            total_fuel_l * fuel.density_kg_l * fuel.co2_kg_per_kg * eth_co2_factor
        )

        # 11. Métricas finais
        distance_km = request.trip.distance_km
        l_per_100km = total_fuel_l / distance_km * 100.0
        km_per_l = distance_km / total_fuel_l if total_fuel_l > 0 else 0.0
        trip_duration_h = (
            distance_km / avg_speed_kmh
            if avg_speed_kmh > 0
            else (request.trip.idle_time_min / 60.0)
        )

        # 12. Rótulo amigável do veículo
        vehicle_label = vehicle.preset_id or self._vehicle_label(vehicle)

        # 13. Avisos adicionais
        if request.load.towing_kg > 0:
            warnings.append(
                f"Rebocando {request.load.towing_kg:.0f} kg: verifique "
                "limites do veículo e do engate."
            )
        if total_fuel_l > vehicle.fuel_tank_capacity_l:
            warnings.append(
                f"Combustível necessário ({total_fuel_l:.1f} L) excede a "
                f"capacidade do tanque ({vehicle.fuel_tank_capacity_l:.1f} L). "
                "Planeje paradas para reabastecimento."
            )

        return CalculationResponse(
            vehicle_label=vehicle_label,
            fuel_type=vehicle.fuel_type,
            distance_km=distance_km,
            trip_duration_h=trip_duration_h,
            average_speed_kmh=avg_speed_kmh,
            total_fuel_l=round(total_fuel_l, 4),
            fuel_per_km_l_per_100km=round(l_per_100km, 4),
            km_per_l=round(km_per_l, 4),
            energy_mj=round(total_energy_j / 1_000_000.0, 4),
            co2_kg=round(co2_kg, 4),
            fuel_cost_brl=round(cost_brl, 2) if cost_brl is not None else None,
            factors=factors,
            segments=segments,
            warnings=warnings,
            total_mass_kg=round(total_mass, 2),
            air_density_kg_per_m3=round(rho, 4),
            effective_headwind_kmh=round(headwind, 2),
            aux_power_effective_w=round(aux_power_w, 1),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_vehicle(self, provided: "VehicleRequest") -> VehicleSpec:
        """Mescla `preset_id` (se houver) com os campos do cliente e
        revalida o resultado contra a `VehicleSpec` estrita.

        Comportamento:
          - Sem `preset_id` → exige todos os campos obrigatórios no `provided`
            (validação estrita do `VehicleSpec` falhará com 422 se faltar algo).
          - Com `preset_id` → completa o que faltar a partir do preset, depois
            sobrescreve com os campos que o cliente efetivamente enviou
            (`exclude_unset=True` — só conta o que estava no JSON).
          - `preset_id` desconhecido → 404.
        """
        from app.fuel.schemas import VehicleRequest  # import local evita ciclo
        provided_req: VehicleRequest = (
            provided if isinstance(provided, VehicleRequest) else None
        )
        # Quando o chamador já passou um VehicleSpec resolvido, retornamos direto.
        if isinstance(provided, VehicleSpec) and not isinstance(provided, VehicleRequest):
            return provided

        preset_id = getattr(provided, "preset_id", None)
        preset = self.repo.find_optional(preset_id)
        if preset_id and preset is None:
            raise NotFoundError("preset", preset_id)

        if preset is None:
            # Veículo totalmente custom — sem preset. Precisa de todos
            # os campos obrigatórios; o VehicleSpec.model_validate
            # abaixo se encarrega de validar.
            merged: Dict = provided.model_dump(exclude_unset=True)
        else:
            # 1) parte do preset
            merged = {k: v for k, v in preset.items() if k != "preset_id"}
            # 2) sobrepõe com o que o cliente efetivamente enviou
            for k, v in provided.model_dump(exclude_unset=True).items():
                if v is not None and k != "preset_id":
                    merged[k] = v
            merged["preset_id"] = preset_id
            # remove campos descritivos que não fazem parte do schema
            merged.pop("description", None)

        try:
            return VehicleSpec.model_validate(merged)
        except PydanticValidationError as exc:
            raise _coerce_validation_error(exc) from exc

    @staticmethod
    def _total_mass_kg(vehicle: VehicleSpec, req: CalculationRequest) -> float:
        people = req.load.passenger_count * req.load.passenger_avg_weight_kg
        return vehicle.empty_weight_kg + people + req.load.cargo_weight_kg

    @staticmethod
    def _vehicle_label(v: VehicleSpec) -> str:
        cat = v.category or "custom"
        return f"{_enum_value(v.type)}-{cat} ({v.year})"

    @staticmethod
    def _idle_fuel(vehicle: VehicleSpec, idle_time_min: float) -> float:
        if idle_time_min <= 0:
            return 0.0
        # Vazão em L/h * horas ociosas.
        return vehicle.idle_fuel_l_per_h * (idle_time_min / 60.0)

    # ------------------------------------------------------------------
    # Integração da viagem
    # ------------------------------------------------------------------
    def _integrate_trip(
        self,
        *,
        vehicle: VehicleSpec,
        trip,
        total_mass_kg: float,
        towing_kg: float,
        air_density: float,
        headwind_kmh: float,
        aux_power_w: float,
        segment_length_m: float,
        road_condition: str,
    ) -> Tuple[List[SegmentBreakdown], float, float]:
        """Integra o combustível e a energia consumida ao longo da viagem.

        Estratégia:
          1. Define o perfil de elevação (interpolado ou plano).
          2. Para cada segmento de `segment_length_m`:
             - calcula inclinação média;
             - velocidade efetiva = cruise + vento de proa;
             - soma forças e converte em potência;
             - adiciona potência auxiliar (ac + base) ao motor;
             - integra ṁ·dt.
          3. Soma também a energia gasta em cada stop-and-go
             (fase de desaceleração + aceleração subsequente).
        """
        distance_m = trip.distance_km * 1000.0
        n_segments = max(1, int(math.ceil(distance_m / segment_length_m)))
        actual_dx = distance_m / n_segments  # ajusta para fechar exatamente

        # Perfil de elevação
        grade_per_m = self._build_grade_profile(trip, n_segments, actual_dx)

        # Velocidade de cruzeiro
        cruise_mps = trip.average_speed_kmh / 3.6
        headwind_mps = headwind_kmh / 3.6
        speed_mps = max(cruise_mps + headwind_mps, 0.5)  # limite mínimo

        # Paradas por km (resolve perfil)
        stops_per_km = resolve_stops_per_km(
            _enum_value(trip.speed_profile), trip.stops_per_km
        )
        # Probabilidade de parada por segmento.
        p_stop = min(1.0, stops_per_km * (actual_dx / 1000.0))

        # Incremento de área por reboque
        towing_inc = towing_aero_increment(towing_kg, _enum_value(vehicle.type))
        frontal_area = vehicle.frontal_area_m2 + towing_inc

        # Crr com correção de piso
        crr_factor = rolling_resistance_road_factor(road_condition)
        crr = vehicle.rolling_resistance_coeff * crr_factor

        # Potência base auxiliar (sem AC — AC já foi somado no caller)
        aux_w = aux_power_w

        segments_out: List[SegmentBreakdown] = []
        total_fuel_l = 0.0
        total_energy_j = 0.0
        fuel = fuel_properties(_enum_value(vehicle.fuel_type))

        # Loop principal
        for i in range(n_segments):
            start_m = i * actual_dx
            end_m = (i + 1) * actual_dx
            grade_rad = grade_per_m[i]
            grade_pct = math.tan(grade_rad) * 100.0

            f_drag = aero_drag_force(
                vehicle.drag_coefficient_cd, frontal_area, air_density, speed_mps
            )
            f_roll = rolling_resistance_force(crr, total_mass_kg, grade_rad)
            f_climb = climbing_force(total_mass_kg, grade_rad)
            f_total = f_drag + f_roll + f_climb
            p_t = max(0.0, tractive_power(f_total, speed_mps))
            # Auxiliares entram como potência adicional demandada do motor.
            p_total = p_t + aux_w

            dt = actual_dx / max(speed_mps, 0.5)
            fuel_l = fuel_flow_l_per_s(
                p_total,
                vehicle.engine_thermal_efficiency,
                vehicle.drivetrain_efficiency,
                fuel.lhv_mj_kg,
                fuel.density_kg_l,
            ) * dt
            energy_j = p_t * dt  # só a tração conta como "trabalho mecânico"

            # Stop-and-go: se a probabilidade sorteia uma parada neste
            # segmento, cobramos a energia extra de desaceleração + aceleração.
            if p_stop > 0 and self._roll_stop(i, p_stop):
                fuel_l, energy_j = self._add_stop_cycle(
                    fuel_l=fuel_l, energy_j=energy_j,
                    mass_kg=total_mass_kg, cruise_speed_mps=cruise_mps,
                    fuel=fuel, engine_eff=vehicle.engine_thermal_efficiency,
                    drivetrain_eff=vehicle.drivetrain_efficiency,
                )

            total_fuel_l += fuel_l
            total_energy_j += energy_j

            segments_out.append(
                SegmentBreakdown(
                    index=i,
                    start_km=round(start_m / 1000.0, 4),
                    end_km=round(end_m / 1000.0, 4),
                    grade_pct=round(grade_pct, 4),
                    speed_kmh=round(speed_mps * 3.6, 3),
                    tractive_power_w=round(p_t, 1),
                    fuel_l=round(fuel_l, 6),
                )
            )

        return segments_out, total_fuel_l, total_energy_j

    # ------------------------------------------------------------------
    # Perfil de elevação
    # ------------------------------------------------------------------
    @staticmethod
    def _build_grade_profile(
        trip, n_segments: int, dx_m: float
    ) -> List[float]:
        """Retorna a inclinação (rad) por segmento."""
        if not trip.elevation_profile or len(trip.elevation_profile) < 2:
            return [0.0] * n_segments

        # Constrói pontos (distância_m, elevação_m) e interpola linearmente.
        # Aceita tanto ElevationPoint quanto dict.
        def _d(p, key, default=None):
            if isinstance(p, dict):
                return p.get(key, default)
            return getattr(p, key, default)

        points = [
            (_d(p, "distance_km") * 1000.0, _d(p, "elevation_m", 0.0))
            for p in trip.elevation_profile
        ]

        # Inicializa com zeros (caso o perfil não cubra a viagem).
        grades = [0.0] * n_segments
        for i in range(n_segments):
            s_m = i * dx_m
            e_m = (i + 1) * dx_m
            s_elev = _interp_elev(points, s_m)
            e_elev = _interp_elev(points, e_m)
            rise = e_elev - s_elev
            grades[i] = grade_from_elevation(dx_m, rise)
        return grades

    # ------------------------------------------------------------------
    # Stop-and-go
    # ------------------------------------------------------------------
    @staticmethod
    def _roll_stop(segment_index: int, probability: float) -> bool:
        """Determinismo útil: pseudo-aleatório estável por índice."""
        # Usa hashing simples para reproducibilidade em testes.
        if probability <= 0:
            return False
        # Probabilidade acumulada uniforme baseada em hash.
        h = (segment_index * 2654435761) & 0xFFFFFFFF
        u = (h % 10000) / 10000.0
        return u < probability

    @staticmethod
    def _add_stop_cycle(
        *,
        fuel_l: float, energy_j: float,
        mass_kg: float, cruise_speed_mps: float,
        fuel: FuelProps, engine_eff: float, drivetrain_eff: float,
    ) -> Tuple[float, float]:
        """Adiciona o custo de um stop-and-go.

        Fase 1 — desaceleração a DECEL_PHASE_A até parar (energia cinética
        é dissipada nos freios, sem custo de combustível além de manter
        a marcha lenta).
        Fase 2 — parada em marcha lenta por Duração implícita (~10 s).
        Fase 3 — aceleração a ACCEL_PHASE_A até cruise_speed_mps
        (energia cinética + perdas).
        """
        # Energia cinética perdida e recuperada (mitigada pela eficiência
        # do powertrain na fase de aceleração).
        ke = 0.5 * mass_kg * cruise_speed_mps * cruise_speed_mps

        # Combustível para acelerar de volta a cruise.
        # Energia química necessária = KE / (η_eng · η_drivetrain)
        energy_in_j = ke / max(engine_eff * drivetrain_eff, 0.05)
        fuel_accel = energy_in_j / (fuel.lhv_mj_kg * 1_000_000.0) / max(fuel.density_kg_l, 1e-6)

        # Idle por ~10 s na parada
        idle_fuel = 0.6 * 10.0 / 3600.0  # L (assumindo 0.6 L/h para carros)

        return (
            fuel_l + fuel_accel + idle_fuel,
            energy_j + ke,  # reporta a KE mecânica que foi reaplicada
        )


# ---------------------------------------------------------------------------
# Interpolação de elevação
# ---------------------------------------------------------------------------
def _interp_elev(points, x_m: float) -> float:
    """Interpolação linear; fora do range, prende nos extremos."""
    if x_m <= points[0][0]:
        return points[0][1]
    if x_m >= points[-1][0]:
        return points[-1][1]
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        if x0 <= x_m <= x1:
            if x1 == x0:
                return y0
            t = (x_m - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return points[-1][1]  # fallback
