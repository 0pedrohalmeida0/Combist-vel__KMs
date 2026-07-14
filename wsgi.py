"""WSGI entry point para deploy no PythonAnywhere (plano free).

O PythonAnywhere free tier só serve aplicações WSGI. Como a Fuel
Consumption API é FastAPI (ASGI), este arquivo embrulha a app ASGI
numa interface WSGI usando `a2wsgi.ASGIMiddleware` (que converte
ASGI → WSGI).

Variável obrigatória: `application` — é o que o PythonAnywhere procura.
"""

from __future__ import annotations

import sys
from pathlib import Path

# O PythonAnywhere adiciona o diretório deste arquivo ao sys.path,
# então `app.main` é importável diretamente a partir da raiz.
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Importa depois de ajustar sys.path
from a2wsgi import ASGIMiddleware  # noqa: E402
from app.main import app  # noqa: E402

# `application` é o símbolo que o PythonAnywhere procura.
application = ASGIMiddleware(app)
