"""Hierarquia tipada de erros de aplicação.

Todas as exceções operacionais derivam de `AppError` e carregam
`code`, `message` e `status_code`. O handler global em `main.py`
converte-as em respostas JSON consistentes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class AppError(Exception):
    """Erro base da aplicação."""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    status_code = 422

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message, details=details)


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404

    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(f"{resource} não encontrado: {resource_id}")
        self.resource = resource
        self.resource_id = resource_id


class PayloadTooLargeError(AppError):
    code = "PAYLOAD_TOO_LARGE"
    status_code = 413

    def __init__(self, message: str, *, limit: int, received: int) -> None:
        super().__init__(
            message,
            details={"limit": limit, "received": received},
        )
        self.limit = limit
        self.received = received


class InternalError(AppError):
    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str = "Erro interno do servidor") -> None:
        super().__init__(message)


def error_payload(code: str, message: str, request_id: str, details: Any = None) -> Dict[str, Any]:
    """Monta o payload JSON uniforme do handler global."""
    body: Dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
    }
    if details is not None:
        body["details"] = details
    return {"error": body}
