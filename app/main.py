"""Bootstrap do FastAPI.

- Configura logging estruturado.
- Registra middlewares (RequestID → Logging → CORS).
- Expõe endpoints de saúde e a v1 de combustível.
- Define handler global para `AppError` e exceções genéricas.
- Implementa graceful shutdown via `lifespan`.
"""
from __future__ import annotations

import logging
import signal
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from app.config import get_settings
from app.errors import AppError, error_payload
from app.fuel.routes import router as fuel_router
from app.fuel.service import FuelCalculationService
from app.middleware.logging_mw import LoggingMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.shared.logger import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger("app")


# ---------------------------------------------------------------------------
# Readiness check (cálculo de sanidade em-process)
# ---------------------------------------------------------------------------
def _readiness_sanity_check() -> dict:
    """Calcula um cenário padrão para validar o pipeline de cálculo.

    Carro compacto popular, 100 km plana, 80 km/h, condições padrão.
    O resultado deve estar entre 4 e 12 L/100 km para um veículo
    típico. Caso contrário, a aplicação reporta degraded.
    """
    from app.fuel.schemas import (
        CalculationRequest,
        DriverSpec,
        EnvironmentSpec,
        LoadSpec,
        TripSpec,
        VehicleRequest,
    )
    from app.fuel.schemas import FuelType, Transmission, VehicleType

    req = CalculationRequest(
        vehicle=VehicleRequest(
            type=VehicleType.car,
            preset_id="car-compact-popular",
        ),
        trip=TripSpec(
            distance_km=100.0,
            average_speed_kmh=80.0,
            speed_profile="constant",
        ),
        environment=EnvironmentSpec(),
        load=LoadSpec(),
        driver=DriverSpec(),
    )
    service = FuelCalculationService()
    result = service.calculate(req)
    l_per_100km = result.fuel_per_km_l_per_100km
    return {
        "scenario": "car-compact-popular 100km 80km/h flat gasoline",
        "l_per_100km": l_per_100km,
        "total_fuel_l": result.total_fuel_l,
        "ok": 4.0 <= l_per_100km <= 12.0,
    }


# ---------------------------------------------------------------------------
# Lifespan: graceful startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info(
        "app.startup",
        extra={
            "app_name": settings.app_name,
            "version": settings.version,
            "environment": settings.environment,
        },
    )
    log.info("app.ready", extra={"status": "ok"})
    try:
        yield
    finally:
        log.info("app.shutdown", extra={"status": "stopping"})


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Fuel Consumption API",
    version=settings.version,
    description=(
        "API para cálculo de consumo de combustível de veículos leves "
        "(carros e motos). Considera aerodinâmica, resistência de "
        "rolamento, aclive, perfil de paradas, vento, altitude, "
        "temperatura, carga, estilo de direção e qualidade do "
        "combustível."
    ),
    lifespan=lifespan,
)


# Middleware (ordem importa: RequestID → Logging → CORS)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


# Routers
app.include_router(fuel_router)


# ---------------------------------------------------------------------------
# Health & readiness
# ---------------------------------------------------------------------------
@app.get("/health", tags=["health"], summary="Liveness probe.")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready", tags=["health"], summary="Readiness probe.")
def ready() -> JSONResponse:
    check = _readiness_sanity_check()
    status_code = 200 if check["ok"] else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if check["ok"] else "degraded", "check": check},
    )


# ---------------------------------------------------------------------------
# Handlers globais
# ---------------------------------------------------------------------------
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    safe_details = _scrub_for_json(exc.details)
    payload = error_payload(exc.code, exc.message, request_id, safe_details)
    if exc.status_code >= 500:
        log.exception(
            "app.error",
            extra={"request_id": request_id, "code": exc.code},
        )
    else:
        log.warning(
            "app.client_error",
            extra={
                "request_id": request_id,
                "code": exc.code,
                "status": exc.status_code,
            },
        )
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(PydanticValidationError)
async def pydantic_error_handler(
    request: Request, exc: PydanticValidationError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "VALIDATION_ERROR",
            "Payload inválido",
            request_id,
            details=_safe_pydantic_errors(exc),
        ),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Converte erros de validação de request do FastAPI para o formato padrão."""
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "VALIDATION_ERROR",
            "Payload inválido",
            request_id,
            details=_safe_pydantic_errors(exc),
        ),
    )


def _safe_pydantic_errors(exc) -> list:
    """Converte erros do Pydantic para um formato JSON-serializável.

    Os `field_validator` que levantam `ValueError` fazem o Pydantic
    embutir o objeto `ValueError` original em `ctx.error`, o que
    quebra a serialização JSON. Esta função substitui quaisquer
    objetos não serializáveis pela sua representação string.
    """
    return [_scrub_for_json(e) for e in exc.errors()]


def _scrub_for_json(obj):
    """Recursivamente substitui objetos não-JSON por sua str."""
    import json

    if isinstance(obj, dict):
        return {k: _scrub_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_scrub_for_json(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    log.exception(
        "app.unhandled",
        extra={"request_id": request_id, "error_type": type(exc).__name__},
    )
    return JSONResponse(
        status_code=500,
        content=error_payload(
            "INTERNAL_ERROR",
            "Erro interno do servidor",
            request_id,
        ),
    )


# ---------------------------------------------------------------------------
# Graceful shutdown (SIGTERM/SIGINT)
# ---------------------------------------------------------------------------
def _install_signal_handlers() -> None:
    def _handle(signum, _frame):
        sig_name = signal.Signals(signum).name
        log.info("signal.received", extra={"signal": sig_name})
        # Uvicorn intercepta SIGTERM/SIGINT e dispara o shutdown do lifespan.

    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


_install_signal_handlers()
