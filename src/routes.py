"""Rotas HTTP do recurso de cálculo de combustível.

Controllers finos: validam o request, chamam o service e
formatam a resposta. Não há regra de negócio aqui.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Body, Depends, Path

from app.errors import NotFoundError, PayloadTooLargeError, ValidationError
from app.fuel.schemas import (
    BatchCalculationRequest,
    BatchCalculationResponse,
    CalculationRequest,
    CalculationResponse,
)
from app.fuel.service import FuelCalculationService


router = APIRouter(prefix="/api/v1/fuel", tags=["fuel"])


def get_service() -> FuelCalculationService:
    """Injeção do serviço (uma instância por processo é suficiente)."""
    return FuelCalculationService()


@router.get(
    "/presets",
    response_model=List[dict],
    summary="Lista todos os presets de veículos disponíveis.",
)
def list_presets(
    service: FuelCalculationService = Depends(get_service),
) -> List[dict]:
    return service.list_presets()


@router.get(
    "/presets/{preset_id}",
    response_model=dict,
    summary="Retorna um preset específico.",
    responses={404: {"description": "Preset não encontrado"}},
)
def get_preset(
    preset_id: str = Path(..., min_length=1, max_length=64),
    service: FuelCalculationService = Depends(get_service),
) -> dict:
    return service.get_preset(preset_id)


@router.post(
    "/calculate",
    response_model=CalculationResponse,
    summary="Calcula o consumo de combustível para uma viagem.",
    responses={
        404: {"description": "preset_id desconhecido"},
        422: {"description": "Payload inválido"},
    },
)
def calculate(
    payload: CalculationRequest = Body(...),
    service: FuelCalculationService = Depends(get_service),
) -> CalculationResponse:
    return service.calculate(payload)


@router.post(
    "/calculate/batch",
    response_model=BatchCalculationResponse,
    summary="Calcula o consumo para uma lista de viagens (máx. 100).",
    responses={
        413: {"description": "Batch excede o limite"},
        422: {"description": "Payload inválido"},
    },
)
def calculate_batch(
    payload: BatchCalculationRequest = Body(...),
    service: FuelCalculationService = Depends(get_service),
) -> BatchCalculationResponse:
    results = service.calculate_batch(payload.requests)
    return BatchCalculationResponse(count=len(results), results=results)
