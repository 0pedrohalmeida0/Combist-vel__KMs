"""Middleware de logging de requisições HTTP.

Gera uma entrada JSON por requisição com método, rota, status e
duração em milissegundos. Inclui o request_id no log e como header
de resposta. Não loga corpo (pode conter PII / ser muito grande).
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.shared.logger import get_logger

log = get_logger("http")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        start = time.perf_counter()
        # Endpoint pode não estar pronto em erros de roteamento, então
        # usamos o path bruto como fallback.
        route_template = request.url.path
        try:
            response: Response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000.0
            log.exception(
                "request.error",
                extra={
                    "request_id": getattr(request.state, "request_id", None),
                    "method": request.method,
                    "route": route_template,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000.0
        # Tenta usar o template de rota (ex.: /api/v1/fuel/presets/{id}).
        try:
            if request.scope.get("route"):
                route_template = request.scope["route"].path  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass

        log.info(
            "request.complete",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "method": request.method,
                "route": route_template,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response
