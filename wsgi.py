"""WSGI entry point para deploy no PythonAnywhere (plano free).

O PythonAnywhere free tier só serve aplicações WSGI. Como a Fuel
Consumption API é FastAPI (ASGI), este arquivo embrulha a app ASGI
numa interface WSGI usando a2wsgi.

Variável obrigatória: `application` — é o que o PythonAnywhere procura.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Garante que o pacote `app` (e portanto `app.main:app`) é importável.
# O PythonAnywhere adiciona o diretório do arquivo de configuração ao
# sys.path, mas a app propriamente dita vive em `src/`, então injetamos
# esse path explicitamente.
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Importa depois de ajustar sys.path
from a2wsgi import WSGIMiddleware  # noqa: E402
from app.main import app  # noqa: E402

# `application` é o símbolo que o PythonAnywhere procura.
application = WSGIMiddleware(app)
