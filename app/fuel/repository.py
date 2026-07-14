"""Repositório de veículos (presets).

Camada fina sobre `app.fuel.presets` que expõe operações
tipadas e converte `NotFoundError` quando o `preset_id` é
desconhecido. Isso permite trocar a fonte dos presets (ex.: banco
de dados) sem mexer nas camadas acima.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.errors import NotFoundError
from app.fuel.presets import VEHICLE_PRESETS, get_preset, list_presets


class VehicleRepository:
    """Repositório in-memory de presets de veículos."""

    def list(self) -> List[Dict[str, Any]]:
        return list_presets()

    def get(self, preset_id: str) -> Dict[str, Any]:
        data = get_preset(preset_id)
        if data is None:
            raise NotFoundError("preset", preset_id)
        return data

    def exists(self, preset_id: str) -> bool:
        return preset_id in VEHICLE_PRESETS

    def find_optional(self, preset_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Retorna o preset ou `None` se `preset_id` for vazio/None."""
        if not preset_id:
            return None
        return get_preset(preset_id)
