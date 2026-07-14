"""Middleware de Request ID.

- Se a requisição trouxer `X-Request-ID`, propaga esse valor.
- Caso contrário, gera um UUID4 curto.
- Expõe o ID em `request.state.request_id` para handlers e
  middleware posteriores, e adiciona o header `X-Request-ID` na
  resposta.
"""
from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get(HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers[HEADER] = request_id
        return response
