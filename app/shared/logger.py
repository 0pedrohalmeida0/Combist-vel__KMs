"""Logger JSON estruturado.

Implementação enxuta usando apenas a stdlib (`logging` + formatação
manual). Cada registro inclui timestamp ISO-8601 UTC, nível, mensagem,
e — quando disponíveis — request_id, rota, método, status e duração
em milissegundos. Outros campos extras podem ser anexados via `extra=`.

Uso típico:
    from app.shared.logger import get_logger
    log = get_logger(__name__)
    log.info("calculo.concluido", extra={"distance_km": 100, "fuel_l": 6.7})
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

# Campos reservados que não devem ser duplicados em `extra`.
_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Formatter que serializa cada `LogRecord` em uma linha JSON."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Campos contextuais opcionais.
        for key in (
            "request_id", "route", "method", "status", "duration_ms",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        # Extras adicionais via logger.info(..., extra={"k": v})
        for key, value in record.__dict__.items():
            if key in _RESERVED or key in payload:
                continue
            if key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Configura o logger raiz uma única vez."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Silencia loggers muito verbosos por padrão.
    logging.getLogger("uvicorn.access").setLevel("WARNING")

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger que respeita a configuração global."""
    return logging.getLogger(name)
