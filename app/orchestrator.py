"""
Orquestador Asíncrono — núcleo del Agente Inmobiliario.

Modelo de datos unificado: todas las búsquedas devuelven MultiSearchResult
(lista de PropertyResult), sin importar si la búsqueda fue por referencia
exacta o por lenguaje natural.

Flujo búsqueda por referencia:
  1. Construye filtro exacto FM: {"codigo_ref": "==REF-2024-001"}
  2. Ejecuta search_by_filters → lista de registros
  3. Para cada registro: imagen más reciente + link a carpeta Dropbox (en paralelo)

Flujo búsqueda por lenguaje natural:
  1. AgentService parsea la consulta → filtros FM + interpretación
  2. Ejecuta search_by_filters con los filtros extraídos → lista de registros
  3. Para cada registro: imagen más reciente + link a carpeta Dropbox (en paralelo)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.agent_service import AgentService
from app.services.dbx_service import DropboxService
from app.services.fm_service import FileMakerService
from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class PropertyResult:
    """Un inmueble individual dentro de un resultado de búsqueda."""
    fm_record: dict[str, Any]
    codigo_ref: str                # extraído del campo fm_ref_field del registro
    preview_image: str | None      # URL de la imagen más reciente en Dropbox
    dropbox_folder_url: str | None # Link directo a la carpeta Dropbox


@dataclass
class MultiSearchResult:
    """Resultado unificado de cualquier tipo de búsqueda (N inmuebles)."""
    query: str                           # término original del usuario
    interpretation: str                  # explicación del agente (vacío en búsqueda por ref)
    filters_applied: dict[str, str]      # filtros FM que se usaron
    results: list[PropertyResult] = field(default_factory=list)
    total_found: int = 0
    error: str | None = None

    @property
    def found(self) -> bool:
        return self.total_found > 0 and self.error is None


class RealEstateOrchestrator:
    """
    Orquesta las búsquedas combinando FileMaker, Dropbox y el agente NL.
    Stateless: puede atender múltiples requests concurrentes de forma segura.
    """

    def __init__(self) -> None:
        self._fm = FileMakerService()
        self._dbx = DropboxService()
        self._agent = AgentService()
        self._settings = get_settings()

    async def _build_property_results(
        self, records: list[dict[str, Any]]
    ) -> list[PropertyResult]:
        """
        Para cada registro FM, obtiene en paralelo:
        - La imagen más reciente de Dropbox
        - El link a la carpeta completa de Dropbox
        """
        ref_field = self._settings.fm_ref_field

        async def build_one(record: dict[str, Any]) -> PropertyResult:
            codigo_ref = str(record.get(ref_field, ""))
            preview_image, folder_url = await asyncio.gather(
                self._dbx.get_latest_image_link(codigo_ref),
                self._dbx.get_folder_link(codigo_ref),
            )
            return PropertyResult(
                fm_record=record,
                codigo_ref=codigo_ref,
                preview_image=preview_image,
                dropbox_folder_url=folder_url,
            )

        return await asyncio.gather(*[build_one(r) for r in records])

    async def _execute_search(
        self, query: str, filters: dict[str, str], interpretation: str
    ) -> MultiSearchResult:
        """Ejecuta los filtros contra FM y construye el resultado."""
        try:
            records = await self._fm.search_by_filters(filters)
        except Exception as exc:
            logger.error("Orquestador: error FileMaker — %s", exc)
            return MultiSearchResult(
                query=query,
                interpretation=interpretation,
                filters_applied=filters,
                error=f"Error consultando FileMaker: {exc}",
            )

        if not records:
            return MultiSearchResult(
                query=query,
                interpretation=interpretation,
                filters_applied=filters,
                error=f"No se encontraron inmuebles para '{query}'.",
            )

        try:
            results = await self._build_property_results(records)
        except Exception as exc:
            logger.error("Orquestador: error Dropbox — %s", exc)
            results = [
                PropertyResult(
                    fm_record=r,
                    codigo_ref=str(r.get(self._settings.fm_ref_field, "")),
                    preview_image=None,
                    dropbox_folder_url=None,
                )
                for r in records
            ]

        logger.info("Orquestador: %d resultado(s) para '%s'", len(results), query)
        return MultiSearchResult(
            query=query,
            interpretation=interpretation,
            filters_applied=filters,
            results=list(results),
            total_found=len(results),
        )

    # ─── API pública ─────────────────────────────────────────────────────────

    async def natural_language_search(self, nl_query: str) -> MultiSearchResult:
        """
        Busca inmuebles interpretando una consulta en lenguaje natural.

        Args:
            nl_query: Consulta libre (ej: "casa en Barcelona con balcón luminoso").
        """
        logger.info("Orquestador: búsqueda NL '%s'", nl_query)

        try:
            parsed = self._agent.parse(nl_query)
        except Exception as exc:
            logger.error("Orquestador: error en AgentService — %s", exc)
            return MultiSearchResult(
                query=nl_query,
                interpretation="",
                filters_applied={},
                error=f"Error al interpretar la consulta: {exc}",
            )

        if not parsed.filters:
            return MultiSearchResult(
                query=nl_query,
                interpretation=parsed.interpretation,
                filters_applied={},
                error="No se pudieron extraer criterios de búsqueda de la consulta.",
            )

        return await self._execute_search(
            nl_query, parsed.filters, parsed.interpretation
        )
